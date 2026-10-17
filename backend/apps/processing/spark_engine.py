"""PySpark data-processing engine.

Runs inside the Celery worker. Responsibilities:
  * Own a single long-lived ``SparkSession`` per worker process.
  * Load a user's CSV/Excel file from their S3 bucket into a Spark DataFrame.
  * Apply the pattern-matching transform across target column(s) using
    partition-parallel Spark SQL functions (never row-by-row Python UDFs).
  * Write the processed DataFrame to Parquet for paginated reads.

Partitioning / parallelism
---------------------------
CSV is read directly from ``s3a://`` so Spark splits the object across input
partitions automatically. Before the transform we ``repartition`` to roughly
``row_count / SPARK_ROWS_PER_PARTITION`` partitions (bounded to a sane range)
so each task processes a similar slice and all cores stay busy as the row count
grows into the millions. ``regexp_replace`` / ``regexp_extract`` are Catalyst
expressions — they run inside the JVM per-partition with no Python round-trip,
which is what lets this scale. See the README for the full rationale.

Credential isolation
---------------------
Per-job AWS credentials are set on the shared Hadoop configuration for the
duration of the read and cleared afterwards. The worker runs with
``--concurrency=1`` so two users' credentials never coexist on the shared
context; horizontal scale comes from running more worker replicas.
"""
from __future__ import annotations

import io
import logging
import os
import threading

from django.conf import settings

from apps.s3connector.services import S3Credentials

logger = logging.getLogger("apps.processing")

_spark = None
_spark_lock = threading.Lock()


def get_spark():
    """Return the process-wide SparkSession, creating it on first use."""
    global _spark
    if _spark is not None:
        return _spark
    with _spark_lock:
        if _spark is not None:
            return _spark
        from pyspark.sql import SparkSession

        builder = (
            SparkSession.builder.appName("nl-regex-processor")
            .master(settings.SPARK_MASTER)
            .config("spark.driver.memory", settings.SPARK_DRIVER_MEMORY)
            .config("spark.executor.memory", settings.SPARK_EXECUTOR_MEMORY)
            .config("spark.sql.session.timeZone", "UTC")
            # s3a committer + sensible defaults for object-store reads.
            .config(
                "spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            )
            .config("spark.hadoop.fs.s3a.connection.maximum", "64")
            # Fail fast on bad credentials / unreachable buckets instead of the
            # long default retry storm, so jobs error in seconds with a clear
            # message rather than hanging.
            .config("spark.hadoop.fs.s3a.attempts.maximum", "1")
            .config("spark.hadoop.fs.s3a.retry.limit", "2")
            .config("spark.hadoop.fs.s3a.retry.interval", "500ms")
            .config("spark.hadoop.fs.s3a.connection.establish.timeout", "5000")
            .config("spark.hadoop.fs.s3a.connection.timeout", "15000")
            .config("spark.sql.shuffle.partitions", "64")
        )
        _spark = builder.getOrCreate()
        _spark.sparkContext.setLogLevel("WARN")
        logger.info("SparkSession started (master=%s).", settings.SPARK_MASTER)
        return _spark


def _set_s3_credentials(spark, creds: S3Credentials) -> None:
    hconf = spark._jsc.hadoopConfiguration()
    hconf.set("fs.s3a.access.key", creds.access_key)
    hconf.set("fs.s3a.secret.key", creds.secret_key)
    if creds.region:
        hconf.set("fs.s3a.endpoint", f"s3.{creds.region}.amazonaws.com")


def _clear_s3_credentials(spark) -> None:
    hconf = spark._jsc.hadoopConfiguration()
    for k in ("fs.s3a.access.key", "fs.s3a.secret.key", "fs.s3a.endpoint"):
        hconf.unset(k)


def load_dataframe(spark, creds: S3Credentials, key: str):
    """Load the selected S3 object into a Spark DataFrame.

    CSV/TSV is read directly via s3a (distributed). Excel is downloaded with
    boto3 and converted via pandas (Excel files are bounded in size), then
    parallelized into Spark.
    """
    lower = key.lower()
    if lower.endswith((".csv", ".tsv")):
        sep = "\t" if lower.endswith(".tsv") else ","
        _set_s3_credentials(spark, creds)
        try:
            df = (
                spark.read.option("header", "true")
                .option("sep", sep)
                .option("inferSchema", "false")  # keep everything as string for regex
                .option("mode", "PERMISSIVE")
                .csv(f"s3a://{creds.bucket}/{key}")
            )
            # Force schema resolution now so credential errors surface here.
            _ = df.columns
            return df
        finally:
            _clear_s3_credentials(spark)
    elif lower.endswith((".xlsx", ".xls")):
        import boto3
        import pandas as pd

        client = boto3.client(
            "s3",
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key,
            region_name=creds.region,
        )
        obj = client.get_object(Bucket=creds.bucket, Key=key)
        pdf = pd.read_excel(io.BytesIO(obj["Body"].read()), dtype=str).fillna("")
        return spark.createDataFrame(pdf)
    raise ValueError(f"Unsupported file type: {key}")


def _target_partitions(row_count: int) -> int:
    per = max(1, settings.SPARK_ROWS_PER_PARTITION)
    n = max(1, (row_count + per - 1) // per)
    return min(n, 512)  # cap to avoid tiny-partition overhead


def apply_transform(spark, df, spec: dict, columns: list[str], replacement: str):
    """Apply the transform described by `spec` to `columns`.

    Returns (result_df, match_count). The match count is computed with a single
    distributed aggregation, not by iterating rows.
    """
    from pyspark.sql import functions as F

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Target column(s) not found in file: {missing}")

    operation = spec["operation"]

    from pyspark import StorageLevel

    # Size parallelism to the data, then cache so the repeated actions below
    # (match counts + final write) don't re-read the whole file from S3 each time.
    row_count = df.count()
    df = df.repartition(_target_partitions(row_count)).persist(StorageLevel.MEMORY_AND_DISK)

    match_count = 0

    if operation == "replace":
        pattern = spec["pattern"]
        # Count matches across all target columns (rows where the col matches).
        match_expr = None
        for c in columns:
            e = F.when(F.col(c).rlike(pattern), F.lit(1)).otherwise(F.lit(0))
            match_expr = e if match_expr is None else (match_expr + e)
        match_count = (
            df.select(F.sum((match_expr > 0).cast("int")).alias("m")).first()["m"] or 0
        )
        for c in columns:
            df = df.withColumn(c, F.regexp_replace(F.col(c), pattern, replacement))

    elif operation == "extract":
        pattern = spec["pattern"]
        for c in columns:
            new_col = f"{c}_extracted"
            df = df.withColumn(new_col, F.regexp_extract(F.col(c), pattern, 0))
            match_count += (
                df.select(F.sum((F.length(F.col(new_col)) > 0).cast("int")).alias("m"))
                .first()["m"]
                or 0
            )

    elif operation == "standardize":
        for c in columns:
            # Build the transformed expression from the ORIGINAL column.
            col_expr = F.col(c)
            for rule in spec["rules"]:
                col_expr = F.regexp_replace(col_expr, rule["pattern"], rule["replacement"])
            # Count changed rows by comparing original vs transformed on the
            # current df, BEFORE overwriting the column (otherwise both sides
            # would resolve to the new value and the count would always be 0).
            match_count += (
                df.select(F.sum((F.col(c) != col_expr).cast("int")).alias("m")).first()["m"]
                or 0
            )
            df = df.withColumn(c, col_expr)
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return df, int(match_count), int(row_count)


def write_result(df, job_id: str) -> str:
    """Persist the processed DataFrame to Parquet for paginated reads, then
    release any cached data (safe: one job at a time per worker)."""
    out = os.path.join(settings.RESULTS_DIR, str(job_id))
    df.write.mode("overwrite").parquet(out)
    df.sparkSession.catalog.clearCache()
    return out
