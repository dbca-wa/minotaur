from django.contrib import admin
from django.views.generic.base import RedirectView
from django.urls import path, include


admin.site.site_header = 'Minotaur monitoring service admin'
admin.site.index_title = 'Minotaur monitoring service'
admin.site.site_title = 'Minotaur'


urlpatterns = [
    path('jobs/', include('jobsy.urls')),
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='admin:index'), name='home'),
]
