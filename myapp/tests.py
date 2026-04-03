import logging
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django_apscheduler.models import DjangoJob, DjangoJobExecution

from myapp.admin import admin as myapp_admin_module
from myapp.management.commands.run_scheduler import scheduler
from myapp.models import Device
from myapp.scheduler_utils import cleanup_old_job_executions
from myproject.observability import DailyStructuredFileHandler, build_logging_config


class DailyStructuredFileHandlerTests(TestCase):
    def test_daily_file_handler_writes_current_day_file_and_cleans_old_ones(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = Path(tmp_dir)
            handler = DailyStructuredFileHandler(
                log_dir=log_dir,
                filename_prefix="application",
                retention_days=14,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            handler._today = lambda: date(2026, 3, 22)

            (log_dir / "application-2026-03-01.log").write_text("old\n", encoding="utf-8")
            (log_dir / "application-2026-03-08.log").write_text("keep\n", encoding="utf-8")

            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="hello world",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
            handler.close()

            current_log = log_dir / "application-2026-03-22.log"

            self.assertTrue(current_log.exists())
            self.assertIn("hello world", current_log.read_text(encoding="utf-8"))
            self.assertFalse((log_dir / "application-2026-03-01.log").exists())
            self.assertTrue((log_dir / "application-2026-03-08.log").exists())

    def test_json_formatter_preserves_unicode_characters(self):
        processor = build_logging_config()["formatters"]["json"]["processor"]

        rendered = processor(
            None,
            "info",
            {
                "event": "notification_created",
                "notification_title": "Отсутствуют дежурства в системе",
            },
        )

        self.assertIn("Отсутствуют дежурства в системе", rendered)
        self.assertNotIn("\\u041e", rendered)


class SchedulerAdminTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="scheduler-admin",
            password="pass",
            email="scheduler-admin@example.com",
        )
        self.client.force_login(self.superuser)

    def test_superuser_can_open_scheduler_execution_admin(self):
        job = DjangoJob.objects.create(id="need_to_open_notification", job_state=b"state")
        DjangoJobExecution.objects.create(
            job=job,
            status=DjangoJobExecution.SUCCESS,
            run_time=timezone.now(),
            duration=1.25,
            finished=timezone.now().timestamp(),
        )

        response = self.client.get(
            reverse("admin:django_apscheduler_djangojobexecution_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "need_to_open_notification")

    def test_admin_cleanup_action_deletes_old_scheduler_executions(self):
        job = DjangoJob.objects.create(id="cleanup-test-job", job_state=b"state")
        old_execution = DjangoJobExecution.objects.create(
            job=job,
            status=DjangoJobExecution.SUCCESS,
            run_time=timezone.now() - timedelta(days=30),
            duration=1.0,
            finished=(timezone.now() - timedelta(days=30)).timestamp(),
        )
        recent_execution = DjangoJobExecution.objects.create(
            job=job,
            status=DjangoJobExecution.SUCCESS,
            run_time=timezone.now() - timedelta(days=1),
            duration=1.0,
            finished=(timezone.now() - timedelta(days=1)).timestamp(),
        )

        response = self.client.post(
            reverse("admin:django_apscheduler_djangojobexecution_changelist"),
            data={
                "action": "cleanup_old_job_executions_action",
                "_selected_action": [old_execution.pk, recent_execution.pk],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(DjangoJobExecution.objects.filter(pk=old_execution.pk).exists())
        self.assertTrue(DjangoJobExecution.objects.filter(pk=recent_execution.pk).exists())

    def test_cleanup_helper_deletes_only_old_scheduler_executions(self):
        job = DjangoJob.objects.create(id="cleanup-helper-job", job_state=b"state")
        old_execution = DjangoJobExecution.objects.create(
            job=job,
            status=DjangoJobExecution.SUCCESS,
            run_time=timezone.now() - timedelta(days=20),
            duration=1.0,
            finished=(timezone.now() - timedelta(days=20)).timestamp(),
        )
        recent_execution = DjangoJobExecution.objects.create(
            job=job,
            status=DjangoJobExecution.SUCCESS,
            run_time=timezone.now() - timedelta(days=2),
            duration=1.0,
            finished=(timezone.now() - timedelta(days=2)).timestamp(),
        )

        deleted_count = cleanup_old_job_executions(
            retention_days=14,
            now_value=timezone.now(),
        )

        self.assertEqual(deleted_count, 1)
        self.assertFalse(DjangoJobExecution.objects.filter(pk=old_execution.pk).exists())
        self.assertTrue(DjangoJobExecution.objects.filter(pk=recent_execution.pk).exists())

    def test_scheduler_registers_cleanup_job(self):
        cleanup_job = scheduler.get_job("cleanup_old_job_executions")

        self.assertIsNotNone(cleanup_job)


class BackfillHistoryCreationCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="history-backfill-user",
            password="pass",
        )

    def _create_device_with_missing_plus_history(self):
        device = Device.objects.create(
            user=self.user,
            notification_token="token-v1",
        )
        device.history.filter(history_type="+").delete()
        device.notification_token = "token-v2"
        device.save()
        return device

    def _create_device_without_history(self):
        device = Device.objects.create(
            user=self.user,
            notification_token="token-v1",
        )
        device.history.all().delete()
        return device

    def test_dry_run_does_not_write_backfill_rows(self):
        device = self._create_device_with_missing_plus_history()

        self.assertFalse(device.history.filter(history_type="+").exists())
        call_command(
            "backfill_history_creation",
            model_labels=["myapp.Device"],
            dry_run=True,
            batch_size=50,
        )
        self.assertFalse(device.history.filter(history_type="+").exists())

    def test_backfill_creates_missing_plus_history_row(self):
        device = self._create_device_with_missing_plus_history()

        self.assertFalse(device.history.filter(history_type="+").exists())
        call_command(
            "backfill_history_creation",
            model_labels=["myapp.Device"],
            batch_size=50,
        )

        plus_record = device.history.filter(history_type="+").first()
        self.assertIsNotNone(plus_record)
        first_non_plus = device.history.exclude(history_type="+").earliest("history_date")
        self.assertLess(plus_record.history_date, first_non_plus.history_date)

    def test_backfill_skips_model_when_history_table_missing(self):
        output = StringIO()
        history_model = Device.history.model
        missing_history_table = f"{history_model._meta.db_table}_missing"

        with mock.patch.object(history_model._meta, "db_table", missing_history_table):
            call_command(
                "backfill_history_creation",
                model_labels=["myapp.Device"],
                dry_run=True,
                batch_size=50,
                stdout=output,
            )

        command_output = output.getvalue()
        self.assertIn("Skipping myapp.device", command_output)
        self.assertIn(missing_history_table, command_output)

    def test_history_changes_shows_explanation_for_unknown_first_diff(self):
        device = self._create_device_with_missing_plus_history()
        call_command(
            "backfill_history_creation",
            model_labels=["myapp.Device"],
            batch_size=50,
        )

        admin_instance = myapp_admin_module.site._registry[Device]
        request = RequestFactory().get("/")
        history_records = list(device.history.all())

        admin_instance.set_history_delta_changes(request, history_records)

        newest_record = history_records[0]
        self.assertTrue(newest_record.history_delta_changes)
        self.assertEqual(newest_record.history_delta_changes[0]["field"], "history")
        self.assertIn(
            "Точный diff первого изменения недоступен",
            newest_record.history_delta_changes[0]["new"],
        )

    def test_backfill_enables_future_diff_for_objects_without_history(self):
        device = self._create_device_without_history()
        self.assertFalse(device.history.exists())

        call_command(
            "backfill_history_creation",
            model_labels=["myapp.Device"],
            batch_size=50,
        )

        self.assertTrue(device.history.filter(history_type="+").exists())

        device.notification_token = "token-v2"
        device.save()

        history_records = list(device.history.all())
        newest_record = history_records[0]
        previous_record = history_records[1]
        delta = newest_record.diff_against(previous_record)

        self.assertEqual(newest_record.history_type, "~")
        self.assertIn("notification_token", delta.changed_fields)
