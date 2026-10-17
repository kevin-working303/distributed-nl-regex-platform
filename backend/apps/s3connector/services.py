"""S3 access layer.

All boto3 interaction lives here so the API/task layers never touch raw AWS
SDK calls. Credentials are passed in explicitly per call — nothing is read from
the ambient environment or a shared config, satisfying the "bring your own
bucket" requirement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from apps.common.exceptions import InvalidCredentialsError, S3ConnectionError

logger = logging.getLogger("apps.s3connector")

# File types we can actually load into Spark.
SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".xls")

_BOTO_CONFIG = Config(
    connect_timeout=10,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "standard"},
)


@dataclass(frozen=True)
class S3Credentials:
    """Value object for a single user's S3 access. Never logged or serialized."""

    access_key: str
    secret_key: str
    bucket: str
    region: str | None = None

    def to_dict(self) -> dict:
        return {
            "access_key": self.access_key,
            "secret_key": self.secret_key,
            "bucket": self.bucket,
            "region": self.region,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "S3Credentials":
        return cls(
            access_key=data["access_key"],
            secret_key=data["secret_key"],
            bucket=data["bucket"],
            region=data.get("region"),
        )


def _client(creds: S3Credentials):
    return boto3.client(
        "s3",
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        region_name=creds.region,
        config=_BOTO_CONFIG,
    )


def _translate_error(exc: Exception) -> Exception:
    """Map boto3 errors onto our user-facing error types (no secrets leaked)."""
    if isinstance(exc, NoCredentialsError):
        return InvalidCredentialsError()
    if isinstance(exc, EndpointConnectionError):
        return S3ConnectionError("Could not reach the S3 endpoint. Check the region.")
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "403", "AccessDenied"):
            return InvalidCredentialsError(
                "AWS credentials were rejected or lack permission for this bucket."
            )
        if code in ("NoSuchBucket", "404"):
            return S3ConnectionError("The specified bucket does not exist.")
        return S3ConnectionError(f"S3 error: {code or 'unknown'}.")
    return S3ConnectionError()


def verify_connection(creds: S3Credentials) -> None:
    """Raise a user-facing error if we cannot access the bucket."""
    try:
        _client(creds).head_bucket(Bucket=creds.bucket)
    except Exception as exc:  # noqa: BLE001 - translated below
        logger.info("S3 verify_connection failed for bucket=%s", creds.bucket)
        raise _translate_error(exc)


def list_files(creds: S3Credentials, prefix: str = "", max_keys: int = 1000) -> list[dict]:
    """List supported CSV/Excel objects in the bucket."""
    try:
        paginator = _client(creds).get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=creds.bucket,
            Prefix=prefix,
            PaginationConfig={"MaxItems": max_keys},
        )
        files: list[dict] = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                if not key.lower().endswith(SUPPORTED_EXTENSIONS):
                    continue
                files.append(
                    {
                        "key": key,
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "type": key.lower().rsplit(".", 1)[-1],
                    }
                )
        return files
    except Exception as exc:  # noqa: BLE001
        logger.info("S3 list_files failed for bucket=%s", creds.bucket)
        raise _translate_error(exc)


def get_column_headers(creds: S3Credentials, key: str) -> list[str]:
    """Cheaply read just the header row/columns so the UI can offer columns
    to target without loading the whole file. Reads a small byte range for CSV
    and the first rows for Excel."""
    import io

    client = _client(creds)
    lower = key.lower()
    try:
        if lower.endswith((".csv", ".tsv")):
            sep = "\t" if lower.endswith(".tsv") else ","
            # Grab the first ~64KB; enough for a header line.
            obj = client.get_object(Bucket=creds.bucket, Key=key, Range="bytes=0-65535")
            first_line = obj["Body"].read().split(b"\n", 1)[0].decode("utf-8", "replace")
            return [c.strip().strip('"') for c in first_line.split(sep) if c.strip()]
        # Excel: read first rows via pandas.
        import pandas as pd

        obj = client.get_object(Bucket=creds.bucket, Key=key)
        df = pd.read_excel(io.BytesIO(obj["Body"].read()), nrows=1)
        return [str(c) for c in df.columns]
    except Exception as exc:  # noqa: BLE001
        raise _translate_error(exc)
