from django.http import JsonResponse
from django.urls import Resolver404

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
                        "detail": "Not found.",
                    },
                    status=404,
                )
            raise
