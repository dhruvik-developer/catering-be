from django.urls import path

from .views import (
    PdfFormatterDetailAPIView,
    PdfFormatterHtmlAPIView,
    PdfFormatterListCreateAPIView,
)


urlpatterns = [
    path("pdf-formatters/", PdfFormatterListCreateAPIView.as_view()),
    path("pdf-formatters/<int:pk>/", PdfFormatterDetailAPIView.as_view()),
    path("pdf-formatters/<int:pk>/html/", PdfFormatterHtmlAPIView.as_view()),
]
