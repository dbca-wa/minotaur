from django.contrib import admin
from django.views.generic.base import RedirectView
from django.urls import path, include

urlpatterns = [
    path('jobs/', include('jobsy.urls')),
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='admin:index'), name='home'),
]
