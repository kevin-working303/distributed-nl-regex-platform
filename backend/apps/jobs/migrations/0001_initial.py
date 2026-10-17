import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Job",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("bucket", models.CharField(max_length=255)),
                ("file_key", models.CharField(max_length=1024)),
                (
                    "operation",
                    models.CharField(
                        choices=[
                            ("replace", "Replace"),
                            ("extract", "Extract"),
                            ("standardize", "Standardize"),
                        ],
                        default="replace",
                        max_length=20,
                    ),
                ),
                ("description", models.TextField(help_text="Natural-language pattern description")),
                ("replacement", models.TextField(blank=True, default="")),
                ("target_columns", models.JSONField(default=list)),
                ("encrypted_credentials", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Running"),
                            ("SUCCESS", "Success"),
                            ("FAILED", "Failed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        db_index=True,
                        default="QUEUED",
                        max_length=20,
                    ),
                ),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("stage", models.CharField(blank=True, default="", max_length=64)),
                ("spec", models.JSONField(blank=True, null=True)),
                ("row_count", models.BigIntegerField(blank=True, null=True)),
                ("match_count", models.BigIntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
