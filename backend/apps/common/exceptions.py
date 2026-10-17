"""Shared API error types and a DRF exception handler.

Keeps error responses consistent across the S3, jobs and processing layers and
guarantees we never leak a stack trace (or anything resembling a credential)
to the client.
"""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("apps.common")


class AppError(Exception):
    """Base class for expected, user-facing errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Request could not be processed."

    def __init__(self, message: str | None = None, *, code: str | None = None):
        self.message = message or self.default_message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class S3ConnectionError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_message = "Could not connect to S3 with the provided credentials."


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "The provided AWS credentials are invalid."


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_message = "Validation failed."


class RegexValidationError(ValidationError):
    default_message = "The generated or supplied regular expression is unsafe or invalid."


def api_exception_handler(exc, context):
    """DRF exception handler that renders :class:`AppError` cleanly."""
    if isinstance(exc, AppError):
        logger.info("AppError (%s): %s", exc.code, exc.message)
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        return Response(
            {"error": {"code": "ValidationError", "message": response.data}},
            status=response.status_code,
        )

    # Unexpected: log server-side (without request body) and return opaque 500.
    logger.exception("Unhandled exception in API")
    return Response(
        {"error": {"code": "InternalError", "message": "An internal error occurred."}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
