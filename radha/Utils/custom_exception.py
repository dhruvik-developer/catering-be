import logging

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ErrorDetail


logger = logging.getLogger(__name__)
DEFAULT_ERROR_MESSAGE = "Something went wrong."
GENERIC_VALIDATION_MESSAGES = {
    "validation error",
    "please correct the errors and try again.",
}


def contains_error_detail(value):
    if isinstance(value, ErrorDetail):
        return True
    if isinstance(value, dict):
        return any(contains_error_detail(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_error_detail(item) for item in value)
    return False


def first_error_message(value, default=DEFAULT_ERROR_MESSAGE):
    if value is None:
        return default
    if isinstance(value, ErrorDetail):
        return str(value)
    if isinstance(value, str):
        return value or default
    if isinstance(value, dict):
        for key in ("message", "detail", "non_field_errors"):
            if key in value:
                message = first_error_message(value[key], default="")
                if message:
                    return message
        for item in value.values():
            message = first_error_message(item, default="")
            if message:
                return message
        return default
    if isinstance(value, (list, tuple)):
        for item in value:
            message = first_error_message(item, default="")
            if message:
                return message
        return default
    return str(value) or default


def error_message_from_response_data(data, default=DEFAULT_ERROR_MESSAGE):
    if isinstance(data, dict) and data.get("status") is False:
        message = data.get("message")
        nested_errors = data.get("errors", data.get("data"))
        if (
            nested_errors is not None
            and (not message or str(message).lower() in GENERIC_VALIDATION_MESSAGES)
        ):
            return first_error_message(nested_errors, default=default)
        if message:
            return str(message)
    return first_error_message(data, default=default)


def error_body(data=None, message=None, default=DEFAULT_ERROR_MESSAGE):
    return {
        "status": False,
        "message": message or error_message_from_response_data(data, default=default),
    }


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled API exception")
        return Response(
            error_body(message="Internal server error."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    response.data = error_body(getattr(exc, "detail", response.data))
    return response
