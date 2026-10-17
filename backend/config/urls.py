from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/s3/", include("apps.s3connector.urls")),
    path("api/jobs/", include("apps.jobs.urls")),
]
