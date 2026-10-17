"""S3 API: connect / list files / inspect columns.

These are synchronous, lightweight calls (metadata only) — safe to run inline
in the web process. Anything that reads full file contents happens in Celery.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import ColumnsSerializer, CredentialsSerializer, ListFilesSerializer
from .services import S3Credentials, get_column_headers, list_files, verify_connection


def _creds(data: dict) -> S3Credentials:
    return S3Credentials(
        access_key=data["access_key"],
        secret_key=data["secret_key"],
        bucket=data["bucket"],
        region=data.get("region"),
    )


@api_view(["POST"])
def connect(request):
    """Validate credentials + bucket reachability. Returns no credential data."""
    s = CredentialsSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    verify_connection(_creds(s.validated_data))
    return Response({"connected": True, "bucket": s.validated_data["bucket"]})


@api_view(["POST"])
def files(request):
    s = ListFilesSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    result = list_files(_creds(s.validated_data), prefix=s.validated_data.get("prefix", ""))
    return Response({"files": result, "count": len(result)})


@api_view(["POST"])
def columns(request):
    s = ColumnsSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    cols = get_column_headers(_creds(s.validated_data), s.validated_data["key"])
    return Response({"columns": cols})
