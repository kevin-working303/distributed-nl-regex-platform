"""Jobs API.

  POST /api/jobs/                 submit a job → returns {id} immediately
  GET  /api/jobs/<id>/            poll status/progress/result metadata
  GET  /api/jobs/<id>/results/    paginated processed rows
  POST /api/jobs/<id>/cancel/     request cancellation

The submit endpoint encrypts credentials, persists the job as QUEUED, and
dispatches a Celery task — it never blocks on the actual processing.
"""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.crypto import encrypt_credentials
from apps.common.exceptions import ValidationError
from apps.processing import results as results_reader
from apps.processing.tasks import process_job

from .models import Job, JobStatus
from .serializers import JobCreateSerializer, JobSerializer


@api_view(["POST"])
def submit(request):
    s = JobCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    token = encrypt_credentials(
        {
            "access_key": data["access_key"],
            "secret_key": data["secret_key"],
            "bucket": data["bucket"],
            "region": data.get("region"),
        }
    )

    job = Job.objects.create(
        bucket=data["bucket"],
        file_key=data["file_key"],
        operation=data["operation"],
        description=data["description"],
        replacement=data.get("replacement", ""),
        target_columns=data["target_columns"],
        encrypted_credentials=token,
        status=JobStatus.QUEUED,
    )

    async_result = process_job.delay(str(job.id))
    job.celery_task_id = async_result.id
    job.save(update_fields=["celery_task_id"])

    return Response({"id": str(job.id), "status": job.status}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
def detail(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    return Response(JobSerializer(job).data)


@api_view(["GET"])
def results(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if job.status != JobStatus.SUCCESS:
        raise ValidationError(
            f"Results are not ready (job status: {job.status}).", code="NotReady"
        )
    if not results_reader.result_exists(job_id):
        return Response(
            {"rows": [], "columns": [], "offset": 0, "limit": 0, "total": 0}
        )
    try:
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
    except ValueError:
        raise ValidationError("offset and limit must be integers.")

    page = results_reader.read_page(str(job_id), offset=offset, limit=limit)
    return Response(page)


@api_view(["POST"])
def cancel(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if job.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
        return Response(
            {"id": str(job.id), "status": job.status, "detail": "Job already finished."}
        )

    job.status = JobStatus.CANCELLED
    job.stage = "Cancelled"
    job.save(update_fields=["status", "stage", "updated_at"])

    # Truly stop the work: terminate=True sends SIGTERM to the worker child
    # executing the task, which tears down its Spark driver thread and any
    # in-flight distributed action immediately (not just between stages). The
    # status flag + between-stage checks remain as a belt-and-suspenders guard,
    # and process_job returns early if it ever re-runs a cancelled job.
    if job.celery_task_id:
        from config.celery import app as celery_app

        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")

    return Response({"id": str(job.id), "status": job.status})
