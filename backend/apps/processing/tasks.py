"""Celery tasks — all heavy work lives here, never in the web process.

The pipeline: decrypt creds → generate/validate spec (LLM, cached) → load into
Spark → apply the partition-parallel transform → write Parquet. Progress is
persisted on the Job row at each stage so the frontend can poll it. Failures,
retries and cancellation are handled explicitly.
"""
from __future__ import annotations

import logging

from celery import shared_task
from celery.exceptions import Ignore

from apps.common.crypto import decrypt_credentials
from apps.jobs.models import Job, JobStatus
from apps.llm.generator import generate_spec
from apps.s3connector.services import S3Credentials

logger = logging.getLogger("apps.processing")


def _is_cancelled(job_id) -> bool:
    return (
        Job.objects.filter(pk=job_id, status=JobStatus.CANCELLED).exists()
    )


def _clean_error(exc: Exception) -> str:
    """Turn any exception (including unpickleable Py4J/Java errors with giant
    stack traces) into a short, user-friendly, pickleable message."""
    s = str(exc)
    low = s.lower()
    if any(k in low for k in ("403", "forbidden", "invalidaccesskeyid",
                              "signaturedoesnotmatch", "access denied")):
        return "Access denied by S3 — check your AWS credentials and bucket permissions."
    if "nosuchbucket" in low or "does not exist" in low or ("404" in s and "bucket" in low):
        return "The specified S3 bucket or file was not found."
    if "nosuchkey" in low or "key does not exist" in low:
        return "The selected file was not found in the bucket."
    if "unknownhost" in low or ("connect" in low and "time" in low):
        return "Could not reach S3 — check the region and your network."
    # Our own AppErrors and ValueErrors carry clean messages already.
    first = next((ln for ln in s.splitlines() if ln.strip()), s)
    return (first or exc.__class__.__name__)[:300]


# Permanent failures should not be retried (retrying a bad credential wastes time).
_PERMANENT_MARKERS = (
    "access denied", "credentials", "not found", "forbidden",
    "unsupported file", "column", "unsafe", "invalid regular expression",
)


def _is_permanent(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _PERMANENT_MARKERS)


@shared_task(
    bind=True,
    name="processing.process_job",
    queue="processing",
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def process_job(self, job_id: str):
    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        logger.error("process_job: job %s not found", job_id)
        return

    if job.status == JobStatus.CANCELLED:
        logger.info("Job %s was cancelled before start.", job_id)
        return

    job.status = JobStatus.RUNNING
    job.celery_task_id = self.request.id or ""
    job.error = ""
    job.save(update_fields=["status", "celery_task_id", "error", "updated_at"])

    try:
        # 1. Decrypt per-job credentials (held only in memory from here on).
        creds = S3Credentials.from_dict(decrypt_credentials(job.encrypted_credentials))

        job.set_progress(10, "Generating pattern from description")
        spec = generate_spec(job.operation, job.description, job.target_columns)
        job.spec = spec
        job.save(update_fields=["spec", "updated_at"])

        if _is_cancelled(job_id):
            raise Ignore()

        # 2. Spark: load the file.
        from .spark_engine import apply_transform, get_spark, load_dataframe, write_result

        job.set_progress(30, "Loading data from S3 into Spark")
        spark = get_spark()
        df = load_dataframe(spark, creds, job.file_key)

        if _is_cancelled(job_id):
            raise Ignore()

        # 3. Apply the transform across partitions.
        job.set_progress(55, "Applying pattern across partitions")
        result_df, match_count, row_count = apply_transform(
            spark, df, spec, job.target_columns, job.replacement
        )

        if _is_cancelled(job_id):
            raise Ignore()

        # 4. Persist results for paginated reads.
        job.set_progress(85, "Writing results")
        write_result(result_df, job_id)

        # 5. Done.
        job.status = JobStatus.SUCCESS
        job.progress = 100
        job.stage = "Completed"
        job.row_count = row_count
        job.match_count = match_count
        job.save(
            update_fields=[
                "status", "progress", "stage", "row_count", "match_count", "updated_at"
            ]
        )
        logger.info("Job %s completed: %s/%s matched.", job_id, match_count, row_count)

    except Ignore:
        # Cancellation path — leave status as CANCELLED, don't mark failed.
        logger.info("Job %s cancelled mid-run.", job_id)
        raise

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed.", job_id)
        message = _clean_error(exc)

        # Don't clobber a cancellation that raced in.
        job.refresh_from_db()
        if job.status == JobStatus.CANCELLED:
            return

        # Retry only transient failures, and only while retries remain. Always
        # retry with a sanitized, pickleable exception — the original may be an
        # unpickleable Py4J/Java error.
        if not _is_permanent(message) and self.request.retries < self.max_retries:
            raise self.retry(exc=RuntimeError(message), countdown=10)

        job.status = JobStatus.FAILED
        job.error = message[:2000]
        job.stage = "Failed"
        job.save(update_fields=["status", "error", "stage", "updated_at"])
