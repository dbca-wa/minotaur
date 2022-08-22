from croniter import croniter
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import models
from django.utils import timezone
import logging
import uuid


class Job(models.Model):
    """A Job represents something that needs to happen.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    name = models.CharField(max_length=256, help_text="Descriptive name for this job")
    schedule = models.CharField(max_length=64, help_text="Job schedule (crontab format)")
    deadline = models.IntegerField(default=5, help_text="The deadline in minutes after the scheduled time in which a job should be completed")
    status = models.CharField(max_length=64, help_text="Expected status value for job instances")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, help_text="Job owner (destination for notifications)")
    active = models.BooleanField(default=True)
    last_checked = models.DateTimeField(null=True, blank=True, editable=False)  # Timestamp that this job was last checked.
    last_good = models.DateTimeField(null=True, blank=True, editable=False)  # Timestamp that this job was last checked and found to be OK.
    last_notify = models.DateTimeField(null=True, blank=True, editable=False)  # Timestamp that an email notification was sent to owner.
    workflow_check_result = models.CharField(max_length=64, null=True, blank=True, editable=False)  # Result of the last check.

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    def get_next(self):
        """Based on the current local time, get the timestamp of the next scheduled instance of this job.
        """
        return croniter(self.schedule, datetime.now(timezone.get_default_timezone())).get_next(datetime)

    def get_prev(self):
        """Based on the current local time, get the timestamp of the previous scheduled instance of this job.
        """
        return croniter(self.schedule, datetime.now(timezone.get_default_timezone())).get_prev(datetime)

    def get_expected_finish(self):
        """Returns a datetime for the expected finish of the previous instance (the previous start
        plus the deadline in minutes).
        """
        start = self.get_prev()
        return start + timedelta(minutes=self.deadline)

    def check_good(self):
        """Method to check a job and determine if a JobInstance exists having a created value
        greater than or equal to the previous scheduled timestamp, and a status matching the
        required value. Returns Boolean or None (unknown).
        - None: no instances exist, so we don't know if the job ran or not.
        - True: the most-recent instance ran after the most-recent scheduled time, AND the status was as expected.
        - False: the most-recent instance ran before the most-recent scheduled time, OR the status was not as expected.
        """
        instance = self.jobinstance_set.first()
        if instance:
            return instance.created >= self.get_prev() and instance.status == self.status
        else:
            return None

    def check_notify(self):
        """Method to check whether it MIGHT BE valid to send a notification. Returns Boolean.
        """
        if not self.last_good or not self.active:  # If we have no known last_good value, skip notify.
            return False
        return self.last_notify is None or self.last_notify < self.last_good

    def set_checked(self):
        self.last_checked = datetime.now(timezone.get_default_timezone())
        self.save()

    def set_good(self):
        self.last_good = datetime.now(timezone.get_default_timezone())
        self.save()

    def set_notify(self):
        self.last_notify = datetime.now(timezone.get_default_timezone())
        self.save()

    def set_workflow_result(self, result):
        self.workflow_check_result = result
        self.save()

    def send_notification(self):
        """Method to email a notification to a job owner.
        """
        now = datetime.now(timezone.get_default_timezone())
        subject = f"JOB FAILURE NOTIFICATION: {self.name}"
        body = f"""Email timestamp: {now}\n
This job has passed its expected completion deadline: {self.get_expected_finish()}"""
        msg = EmailMessage(subject=subject, body=body, from_email=settings.NOREPLY_EMAIL, to=[self.owner.email])
        msg.send(fail_silently=True)

    def notify_workflow(self):
        """Function to run through the normal workflow of checking whether a job is in a good state
        or not, updating the current state, and sending notifications (if required).
        """
        expected_finish = self.get_expected_finish()
        check_begins = datetime.now(timezone.get_default_timezone())
        logger = logging.getLogger('jobsy')

        # Don't continue checking if the expected finish is later than now.
        if expected_finish > check_begins:
            self.set_workflow_result('Skipped (instance window)')
            return

        self.set_checked()
        check_result = self.check_good()

        # If check_result is None, we can't validly assess the job completion state.
        if check_result is None:
            self.set_workflow_result('Check result null')
            return

        if check_result:  # Check is good.
            self.set_good()
            self.set_workflow_result('Success')
        else:  # Check is bad.
            self.set_workflow_result('Fail')
            logger.warn("Job not recorded as completed (failure)")
            # Determine is we need to send a notification to the job owner.
            notify = self.check_notify()
            if notify and settings.SEND_NOTIFICATIONS:
                self.set_notify()
                logger.info(f"Sending a notification")
                self.send_notification()
            else:
                logger.info("Not sending a notification at this time")


class JobInstance(models.Model):
    """Represents an instance of a Job which may or may not have been completed.
    The status is just free text (success, error, warning, etc.)
    """
    created = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    status = models.CharField(max_length=256)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        tz = timezone.get_default_timezone()
        return f'{self.job.id}|{self.created.astimezone(tz).isoformat()}|{self.status}'
