from croniter import croniter
from django.contrib.admin import register, ModelAdmin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from jobsy.models import Job, JobInstance


class JobAdminForm(ModelForm):
    def clean_schedule(self):
        schedule = self.cleaned_data["schedule"].strip()
        if not croniter.is_valid(schedule):
            raise ValidationError("Value is not a valid cron schedule")
        return schedule


@register(Job)
class JobAdmin(ModelAdmin):
    fields = ("name", "schedule", "deadline", "status", "owner", "active")
    form = JobAdminForm
    list_display = (
        "id",
        "created",
        "name",
        "schedule",
        "deadline",
        "owner",
        "active",
        "last_checked",
        "last_good",
        "last_notify",
        "workflow_check_result",
    )
    list_filter = ("active",)
    search_fields = ("name", "status", "owner")
