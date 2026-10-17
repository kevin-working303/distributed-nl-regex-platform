"""Job persistence.

A Job captures one processing request end-to-end: its status, progress, the
(non-sensitive) parameters, the resulting spec/stats, and any error. User AWS
credentials are stored ONLY as an encrypted token (Fernet), never in plaintext,
and are excluded from every serializer.
"""
import uuid

from django.db import models


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Operation(models.TextChoices):
    REPLACE = "replace", "Replace"
    EXTRACT = "extract", "Extract"
    STANDARDIZE = "standardize", "Standardize"


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Request parameters (non-sensitive).
    bucket = models.CharField(max_length=255)
    file_key = models.CharField(max_length=1024)
    operation = models.CharField(
        max_length=20, choices=Operation.choices, default=Operation.REPLACE
    )
    description = models.TextField(help_text="Natural-language pattern description")
    replacement = models.TextField(blank=True, default="")
    target_columns = models.JSONField(default=list)

    # Encrypted credentials token (Fernet). Never returned to clients.
    encrypted_credentials = models.TextField()

    # Lifecycle.
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True
    )
    progress = models.PositiveSmallIntegerField(default=0)  # 0-100
    stage = models.CharField(max_length=64, blank=True, default="")

    # Results.
    spec = models.JSONField(null=True, blank=True)       # generated regex/rules
    row_count = models.BigIntegerField(null=True, blank=True)
    match_count = models.BigIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.status}]"

    def set_progress(self, progress: int, stage: str = "") -> None:
        self.progress = max(0, min(100, progress))
        if stage:
            self.stage = stage
        self.save(update_fields=["progress", "stage", "updated_at"])
