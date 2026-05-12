from django.http import JsonResponse
from django.urls import Resolver404

from radha.Utils.custom_exception import (
    contains_error_detail,
    error_body,
    error_message_from_response_data,
)
from user.tenanting import reset_schema


class TenantSchemaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reset_schema()
        try:
            return self.get_response(request)
        finally:
            reset_schema()


class ApiNotFoundMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Resolver404:
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "status": False,
                        "message": "Not found.",
                    },
                    status=404,
                )
            raise


class ApiErrorResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/") or not hasattr(response, "data"):
            return response

        data = response.data
        is_error_response = (
            response.status_code >= 400
            or getattr(response, "exception", False)
            or (isinstance(data, dict) and data.get("status") is False)
            or contains_error_detail(data)
        )
        if not is_error_response:
            return response

        response.data = error_body(
            message=error_message_from_response_data(data),
        )
        return response
