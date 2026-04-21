from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, PermissionDenied):
        detail = str(getattr(exc, "detail", exc))
        return Response(
            {
                "status": False,
                "message": detail,
                "detail": detail,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    return response
