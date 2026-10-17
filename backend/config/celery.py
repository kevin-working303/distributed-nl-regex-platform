"""Celery application bootstrap.

The worker uses a single PySpark session per process (see
``apps.processing.spark_engine``). Concurrency is kept at 1 per worker so that
per-user AWS credentials set on the shared Spark context never bleed between
concurrently running jobs; scale out by adding worker replicas instead.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("regex_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Reasonable defaults for long-running Spark jobs.
app.conf.update(
    worker_prefetch_multiplier=1,       # don't hoard jobs on one worker
    task_acks_late=True,                # re-queue if a worker dies mid-job
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
)


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
