from croniter import croniter
from cron_descriptor import get_description
from datetime import datetime, timedelta
from django.conf import settings
from django.core import mail
from django.db import models
from django.urls import reverse
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
    url = models.URLField(max_length=2048, null=True, blank=True, help_text='Job URL')

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    def get_absolute_url(self):
        return reverse('job_detail', kwargs={'id': self.id})

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

    def get_schedule_desc(self):
        """Returns schedule cron expresssion as a human-readable string.
        """
        return get_description(self.schedule)

    def check_within_schedule_deadline(self):
        """Returns boolean result for whether the current time is within the scheduled running time
        for this job (i.e. after the expected start and before the finish deadline).
        """
        return self.get_expected_finish() > datetime.now(timezone.get_default_timezone())

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

    def send_notification(self, check_time=None):
        """Method to email a notification to a job owner.
        """
        if not check_time:
            check_time = datetime.now(timezone.get_default_timezone())
        subject = f"JOB FAILURE NOTIFICATION: {self.name}"
        body = f"""Check time: {check_time.strftime("%A %-d-%b-%Y %H:%M:%S %Z")}\n
This job has exceeded its expected completion deadline: {self.get_expected_finish().strftime("%A %-d-%b-%Y %H:%M:%S %Z")}"""
        body_html = f"""<p>Check time: {check_time.strftime("%A %-d-%b-%Y %H:%M:%S %Z")}</p>
<p>This job has exceeded its expected completion deadline: {self.get_expected_finish().strftime("%A %-d-%b-%Y %H:%M:%S %Z")}</p>"""
        if self.url:
            body += f"\nURL: {self.url}"
            body_html += f"<p>URL: <a href='{self.url}'>{self.url}</a></p>"
        mail.send_mail(
            subject=subject,
            message=body,
            from_email=settings.NOREPLY_EMAIL,
            recipient_list=[self.owner.email],
            html_message=body_html,
        )

    def notify_workflow(self, log=True):
        """Function to run through the normal workflow of checking whether a job is in a good state
        or not, updating the current state, and sending notifications (if required).
        """
        if log:
            logger = logging.getLogger('jobsy')

        # Don't continue checking if the expected finish is later than now.
        if self.check_within_schedule_deadline():
            if log:
                logger.info(f"Job is currently inside the schedule deadline")
            self.set_workflow_result('Inside schedule deadline')
            return None

        self.set_checked()
        check_result = self.check_good()
        check_time = datetime.now(timezone.get_default_timezone())

        # If check_result is None, we can't validly assess the job completion state.
        if check_result is None:
            self.set_workflow_result('Check result unknown')
            return None
        elif check_result:  # Check is successful.
            self.set_good()
            self.set_workflow_result('Success')
            return True
        else:  # Check is not successful.
            self.set_workflow_result('Fail')
            if log:
                logger.warn("Job not recorded as completed (failure)")
            # Determine is we need to send a notification to the job owner.
            notify = self.check_notify()
            if notify and settings.SEND_NOTIFICATIONS:
                self.set_notify()
                if log:
                    logger.info(f"Sending a notification")
                self.send_notification(check_time)
            else:
                if log:
                    logger.info("Not sending a notification at this time")
            return False


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
