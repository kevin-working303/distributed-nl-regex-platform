from django.urls import path

from . import views

urlpatterns = [
    path("", views.submit, name="job-submit"),
    path("<uuid:job_id>/", views.detail, name="job-detail"),
    path("<uuid:job_id>/results/", views.results, name="job-results"),
    path("<uuid:job_id>/cancel/", views.cancel, name="job-cancel"),
]
