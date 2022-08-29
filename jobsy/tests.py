from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Job, JobInstance


class JobTestCase(TestCase):
    """Unit tests for the Job model class.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='testuser@test.email', password='pass')
        self.job = Job.objects.create(
            name='Test job',
            schedule='0 * * * *',  # Hourly in minute 0
            deadline=1,
            status='ok',
            owner=self.user,
            active=True,
        )

    def test_get_absolute_url(self):
        """Test Job.get_absolute_url
        """
        self.assertTrue(self.job.get_absolute_url())
        self.assertIsInstance(self.job.get_absolute_url(), str)

    def test_get_next(self):
        """Test Job.get_next
        """
        self.assertTrue(self.job.get_next())
        td = self.job.get_next() - datetime.now(timezone.get_default_timezone())
        # Next instance should be <= 3600 seconds in the future.
        self.assertTrue(td.seconds <= 3600)

    def test_get_prev(self):
        """Test Job.get_prev
        """
        self.assertTrue(self.job.get_prev())
        td = datetime.now(timezone.get_default_timezone()) - self.job.get_prev()
        # Previous instance should be <= 3600 seconds ago.
        self.assertTrue(td.seconds <= 3600)

    def test_get_expected_finish(self):
        """Test Job.get_expected_finish
        """
        self.assertTrue(self.job.get_expected_finish())
        td = datetime.now(timezone.get_default_timezone()) - self.job.get_expected_finish()
        # Previous expected finished should be <= 3660 seconds ago.
        # NOTE: sometimes this test will fail if it runs within the instance period.
        if not self.job.check_within_schedule_deadline():
            self.assertTrue(td.seconds <= 3660)

    def test_get_schedule_desc(self):
        """Test Job.get_schedule_desc
        """
        self.assertTrue(self.job.get_schedule_desc())
        self.assertIsInstance(self.job.get_schedule_desc(), str)

    def test_check_good_no_instances(self):
        """Test Job.check_good when no instances are recorded
        """
        self.assertIsNone(self.job.check_good())

    def test_check_good_normal(self):
        """Test Job.check_good when an instance was recorded as expected
        """
        created = self.job.get_prev() + timedelta(minutes=1)
        JobInstance.objects.create(
            created=created,
            job=self.job,
            status='ok',
        )
        self.assertTrue(self.job.check_good())

    def test_check_good_error(self):
        """Test Job.check_good when an instance was recorded with an error result
        """
        created = self.job.get_prev() + timedelta(minutes=1)
        JobInstance.objects.create(
            created=created,
            job=self.job,
            status='error',
        )
        self.assertFalse(self.job.check_good())

    def test_check_good_late(self):
        """Test Job.check_good when an instance hasn't been recorded since the expected completion
        """
        created = self.job.get_prev() - timedelta(minutes=9)
        JobInstance.objects.create(
            created=created,
            job=self.job,
            status='ok',
        )
        self.assertFalse(self.job.check_good())

    def test_check_notify_no_last_good(self):
        """Test Job.check_notify when a job has no last_good value
        """
        self.assertFalse(self.job.check_notify())

    def test_check_notify_inactive(self):
        """Test Job.check_notify when a job is inactive
        """
        self.job.active = False
        self.job.save()
        self.assertFalse(self.job.check_notify())

    def test_check_notify_never_notified(self):
        """Test Job.check_notify where a notification has never been recorded previously
        """
        self.job.last_good = self.job.get_prev() + timedelta(minutes=1)
        self.job.save()
        self.assertTrue(self.job.check_notify())

    def test_check_notify_previous(self):
        """Test Job.check_notify where the previous notification was earlier than the previous last_good value
        """
        self.job.last_good = self.job.get_prev() - timedelta(hours=1)  # About two hours ago
        self.job.last_notify = self.job.get_prev() - timedelta(hours=3)  # About four hours ago
        self.job.save()
        self.assertTrue(self.job.check_notify())

    def test_notify_workflow_success(self):
        """Test Job.notify_workflow when an instance was recorded as expected
        """
        created = self.job.get_prev() + timedelta(minutes=1)
        JobInstance.objects.create(
            created=created,
            job=self.job,
            status='ok',
        )
        self.assertTrue(self.job.notify_workflow(log=False))
        self.assertEqual(self.job.workflow_check_result, 'Success')
        self.assertIsNotNone(self.job.last_good)
        self.assertTrue(self.job.last_good < datetime.now(timezone.get_default_timezone()))
        self.assertIsNotNone(self.job.last_checked)
        self.assertTrue(self.job.last_checked < datetime.now(timezone.get_default_timezone()))

    def test_notify_workflow_fail(self):
        """Test Job.notify_workflow when an instance was not recorded as expected
        """
        self.job.last_good = self.job.get_prev() + timedelta(minutes=1)  # Jobs need to have been good at least once to enable notifications.
        settings.SEND_NOTIFICATIONS = True  # Manually set this to enable email.
        created = self.job.get_prev() - timedelta(hours=2)
        JobInstance.objects.create(
            created=created,
            job=self.job,
            status='ok',
        )
        self.assertFalse(self.job.notify_workflow(log=False))
        self.assertEqual(self.job.workflow_check_result, 'Fail')
        self.assertIsNotNone(self.job.last_checked)
        self.assertTrue(self.job.last_checked < datetime.now(timezone.get_default_timezone()))
        self.assertEqual(len(mail.outbox), 1)

    def test_notify_workflow_unknown(self):
        """Test Job.notify_workflow when no instance has been recorded yet
        """
        self.assertIsNone(self.job.notify_workflow(log=False))
        self.assertEqual(self.job.workflow_check_result, 'Check result unknown')
        self.assertIsNone(self.job.last_good)
        self.assertIsNotNone(self.job.last_checked)
        self.assertTrue(self.job.last_checked < datetime.now(timezone.get_default_timezone()))

    def test_job_list_anonymous(self):
        """Test that an anonymous user is redirected to the admin login
        """
        url = reverse('job_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTemplateUsed(template_name='admin/login.html')

    def test_job_list_loggedin(self):
        """Test that a logged in user can see the job list view
        """
        self.client.login(username='testuser', password='pass')
        url = reverse('job_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_job_detail_get(self):
        """Test that the job detail view work for GET
        """
        url = reverse('job_detail', kwargs={'id': self.job.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_job_detail_post(self):
        """Test that a valid POST request to the job detail view creates an instance
        """
        self.assertFalse(JobInstance.objects.exists())
        url = reverse('job_detail', kwargs={'id': self.job.id})
        response = self.client.post(url, {'status': 'ok'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(JobInstance.objects.exists())

    def test_job_detail_post_invalid(self):
        """Test that an invalid POST request to the job detail view does not create an instance
        """
        self.assertFalse(JobInstance.objects.exists())
        url = reverse('job_detail', kwargs={'id': self.job.id})
        response = self.client.post(url, {'status': ''})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobInstance.objects.exists())
        response = self.client.post(url, {'foo': 'bar'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobInstance.objects.exists())
