import logging
import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django.core.management import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore, register_events, register_job

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    timezone=settings.TIME_ZONE,
    jobstores={"default": DjangoJobStore()},
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    },
)


@register_job(
    scheduler,
    trigger=IntervalTrigger(minutes=1),
    id="need_to_open_notification",
    replace_existing=True,
    max_instances=1,
)
def need_to_open_notification_job():
    from dispatch.crons import need_to_open_notification
    need_to_open_notification()
    logger.info("[need_to_open_notification] tick")

@register_job(
    scheduler,
    trigger=IntervalTrigger(hours=24),
    id="check_missing_duties",
    replace_existing=True,
    max_instances=1,
)
def check_missing_duties_job():
    from dispatch.crons import check_missing_duties
    check_missing_duties()
    logger.info("[check_missing_duties] tick")


class Command(BaseCommand):
    help = "Run APScheduler in this process"

    def handle(self, *args, **options):
        register_events(scheduler)
        scheduler.start()
        self.stdout.write(self.style.SUCCESS("APScheduler started"))

        def _graceful_exit(signum, frame):
            self.stdout.write("Shutting down scheduler...")
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGTERM, _graceful_exit)
        signal.signal(signal.SIGINT, _graceful_exit)

        while True:
            time.sleep(60)
