from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import islice

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count, Q
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
import structlog


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ModelBackfillResult:
    model_label: str
    missing_objects: int
    created_rows: int


def _chunked(iterable, size: int):
    iterator = iter(iterable)
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            return
        yield chunk


class Command(BaseCommand):
    help = (
        "Backfill missing history creation entries (history_type='+') "
        "for objects that have history but no creation row, and for "
        "existing objects that have no history at all."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            action="append",
            dest="app_labels",
            default=[],
            help="Optional app label filter. Can be provided multiple times.",
        )
        parser.add_argument(
            "--model",
            action="append",
            dest="model_labels",
            default=[],
            help="Optional model filter in 'app_label.ModelName' format.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Batch size for querying and bulk inserts.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show what would be changed without writing to DB.",
        )
        parser.add_argument(
            "--reason",
            default="Backfilled missing creation history record",
            help="history_change_reason for created backfill rows.",
        )

    def handle(self, *args, **options):
        batch_size: int = options["batch_size"]
        dry_run: bool = options["dry_run"]
        reason: str = options["reason"]
        app_labels = set(options["app_labels"] or [])
        model_labels: list[str] = options["model_labels"] or []

        if batch_size <= 0:
            self.stderr.write(self.style.ERROR("--batch-size must be > 0"))
            return

        models = self._resolve_models(app_labels=app_labels, model_labels=model_labels)
        if not models:
            self.stdout.write("No history-enabled models matched filters.")
            return

        total_missing = 0
        total_created = 0
        existing_tables = set(connection.introspection.table_names())

        self.stdout.write(
            f"Processing {len(models)} model(s), dry_run={dry_run}, batch_size={batch_size}"
        )

        for model in models:
            history_model = self._get_history_model(model)
            history_table = history_model._meta.db_table
            if history_table not in existing_tables:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {model._meta.label_lower}: "
                        f"history table '{history_table}' does not exist."
                    )
                )
                logger.warning(
                    "history_creation_backfill_model_skipped_missing_table",
                    model=model._meta.label_lower,
                    history_table=history_table,
                )
                continue

            try:
                result = self._backfill_model(
                    model=model,
                    batch_size=batch_size,
                    dry_run=dry_run,
                    reason=reason,
                )
                total_missing += result.missing_objects
                total_created += result.created_rows
                self.stdout.write(
                    f"{result.model_label}: missing_objects={result.missing_objects}, "
                    f"created_rows={result.created_rows}"
                )
            except (OperationalError, ProgrammingError) as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {model._meta.label_lower}: database error while reading history "
                        f"('{exc}')."
                    )
                )
                logger.warning(
                    "history_creation_backfill_model_skipped_db_error",
                    model=model._meta.label_lower,
                    error=str(exc),
                )
                continue

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"missing_objects={total_missing}, created_rows={total_created}, dry_run={dry_run}"
            )
        )

    def _resolve_models(self, app_labels: set[str], model_labels: list[str]):
        selected = set()

        if model_labels:
            for model_label in model_labels:
                try:
                    model = apps.get_model(model_label)
                except LookupError as exc:
                    raise CommandError(f"Unknown model '{model_label}'") from exc
                selected.add(model)
        else:
            for model in apps.get_models():
                if app_labels and model._meta.app_label not in app_labels:
                    continue
                selected.add(model)

        history_enabled_models = []
        for model in sorted(selected, key=lambda m: m._meta.label_lower):
            history_attr = getattr(model._meta, "simple_history_manager_attribute", None)
            if not history_attr:
                continue
            history_manager = getattr(model, history_attr, None)
            if history_manager is None:
                continue
            history_enabled_models.append(model)

        return history_enabled_models

    def _get_history_model(self, model):
        history_attr = model._meta.simple_history_manager_attribute
        history_manager = getattr(model, history_attr)
        return history_manager.model

    def _backfill_model(
        self,
        model,
        batch_size: int,
        dry_run: bool,
        reason: str,
    ) -> ModelBackfillResult:
        history_model = self._get_history_model(model)
        object_pk_name = model._meta.pk.attname

        if not any(field.name == "history_type" for field in history_model._meta.fields):
            return ModelBackfillResult(model._meta.label_lower, 0, 0)

        missing_plus_ids_qs = (
            history_model.objects.values(object_pk_name)
            .annotate(created_count=Count("history_id", filter=Q(history_type="+")))
            .filter(created_count=0)
            .order_by(object_pk_name)
            .values_list(object_pk_name, flat=True)
        )
        missing_plus_ids = list(missing_plus_ids_qs)
        no_history_ids = list(
            model._default_manager.exclude(
                pk__in=history_model.objects.values_list(object_pk_name, flat=True)
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )

        missing_ids = missing_plus_ids + no_history_ids
        if not missing_ids:
            return ModelBackfillResult(model._meta.label_lower, 0, 0)

        total_created_rows = 0
        for id_chunk in _chunked(missing_plus_ids, batch_size):
            rows_to_create = self._build_creation_rows_from_history(
                history_model=history_model,
                object_pk_name=object_pk_name,
                object_ids=id_chunk,
                reason=reason,
            )

            if dry_run or not rows_to_create:
                total_created_rows += len(rows_to_create)
                continue

            with transaction.atomic():
                history_model.objects.bulk_create(rows_to_create, batch_size=batch_size)
            total_created_rows += len(rows_to_create)

        for id_chunk in _chunked(no_history_ids, batch_size):
            rows_to_create = self._build_creation_rows_from_live_objects(
                model=model,
                history_model=history_model,
                object_ids=id_chunk,
                reason=reason,
            )

            if dry_run or not rows_to_create:
                total_created_rows += len(rows_to_create)
                continue

            with transaction.atomic():
                history_model.objects.bulk_create(rows_to_create, batch_size=batch_size)
            total_created_rows += len(rows_to_create)

        logger.info(
            "history_creation_backfill_finished",
            model=model._meta.label_lower,
            dry_run=dry_run,
            missing_objects=len(missing_ids),
            missing_plus_objects=len(missing_plus_ids),
            no_history_objects=len(no_history_ids),
            created_rows=total_created_rows,
        )
        return ModelBackfillResult(
            model_label=model._meta.label_lower,
            missing_objects=len(missing_ids),
            created_rows=total_created_rows,
        )

    def _build_creation_rows_from_history(
        self,
        history_model,
        object_pk_name: str,
        object_ids: list[object],
        reason: str,
    ):
        queryset = history_model.objects.filter(**{f"{object_pk_name}__in": object_ids}).order_by(
            object_pk_name, "history_date", "history_id"
        )

        created_rows = []
        seen_object_ids = set()
        for historical_row in queryset.iterator():
            object_id = getattr(historical_row, object_pk_name)
            if object_id in seen_object_ids:
                continue
            seen_object_ids.add(object_id)

            tracked_values = {
                field.attname: getattr(historical_row, field.attname)
                for field in history_model.tracked_fields
            }
            backfill_history_date = historical_row.history_date - timedelta(microseconds=1)
            created_rows.append(
                history_model(
                    history_date=backfill_history_date,
                    history_user=historical_row.history_user,
                    history_change_reason=reason,
                    history_type="+",
                    **tracked_values,
                )
            )

        return created_rows

    def _build_creation_rows_from_live_objects(
        self,
        model,
        history_model,
        object_ids: list[object],
        reason: str,
    ):
        queryset = model._default_manager.filter(pk__in=object_ids).order_by("pk")

        created_rows = []
        history_date = timezone.now()
        for obj in queryset.iterator():
            tracked_values = {
                field.attname: getattr(obj, field.attname)
                for field in history_model.tracked_fields
            }
            created_rows.append(
                history_model(
                    history_date=history_date,
                    history_user=None,
                    history_change_reason=reason,
                    history_type="+",
                    **tracked_values,
                )
            )

        return created_rows
