from django.core.management.base import BaseCommand
from jobsy.models import Job
import logging


class Command(BaseCommand):
    help = 'Runs workflow checks for all active jobs'

    def handle(self, *args, **options):
        logger = logging.getLogger('jobsy')
        for job in Job.objects.filter(active=True):
            logger.info(f"Checking job: {job}")
            job.workflow_check()
