from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.generic.base import View
from .models import Job, JobInstance


class JobListView(LoginRequiredMixin, View):
    http_method_names = ['get', 'options']

    def get(self, request, *args, **kwargs):
        qs = Job.objects.all()
        jobs = [{
            'id': job.id,
            'name': job.name,
            'schedule': job.schedule,
            'deadline': job.deadline,
            'expected_finish': job.get_expected_finish(),
            'owner': job.owner.email,
            'active': job.active,
        } for job in qs]
        return JsonResponse(jobs, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(never_cache, name='dispatch')
class JobDetailView(View):
    http_method_names = ['get', 'post', 'options']

    def get(self, request, *args, **kwargs):
        job = Job.objects.get(id=kwargs["id"])
        instance = job.jobinstance_set.first()
        tz = timezone.get_default_timezone()
        job_dict = {
            'id': job.id,
            'name': job.name,
            'schedule': job.schedule,
            'deadline': job.deadline,
            'expected_finish': job.get_expected_finish(),
            'owner': job.owner.email,
            'last_checked': job.last_checked.astimezone(tz).isoformat() if job.last_checked else None,
            'last_good': job.last_good.astimezone(tz).isoformat() if job.last_good else None,
            'last_notify': job.last_notify.astimezone(tz).isoformat() if job.last_notify else None,
            'active': job.active,
            'url': job.url,
            'last_instance': {
                'created': instance.created.astimezone(tz).isoformat(),
                'status': instance.status,
            } if instance else None,
        }
        return JsonResponse(job_dict)

    def post(self, request, *args, **kwargs):
        """Should receive a POST request having param ?status=<value>
        """
        if 'status' not in self.request.POST or not self.request.POST['status']:
            return HttpResponseBadRequest('ERROR')
        job = Job.objects.get(id=kwargs['id'])
        JobInstance.objects.create(
            job=job,
            status=request.POST['status']
        )

        return HttpResponse('OK')
