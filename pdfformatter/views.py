from django.db.models import Q
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.response import Response

from radha.Utils.permissions import IsAdminUserOrReadOnly

from .models import PdfFormatter
from .serializers import PdfFormatterSerializer


class PdfFormatterListCreateAPIView(generics.GenericAPIView):
    serializer_class = PdfFormatterSerializer
    queryset = PdfFormatter.objects.select_related("created_by")
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "pdf_formatters"

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        code = self.request.query_params.get("code")
        is_active = self.request.query_params.get("is_active")
        is_default = self.request.query_params.get("is_default")

        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(code__icontains=search)
                | Q(description__icontains=search)
            )

        if code:
            queryset = queryset.filter(code=code.strip())

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        if is_default is not None:
            queryset = queryset.filter(is_default=is_default.lower() == "true")

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "PDF formatters fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        formatter = serializer.save(
            created_by=request.user if request.user.is_authenticated else None
        )
        return Response(
            {
                "status": True,
                "message": "PDF formatter created successfully.",
                "data": self.get_serializer(formatter).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PdfFormatterDetailAPIView(generics.GenericAPIView):
    serializer_class = PdfFormatterSerializer
    queryset = PdfFormatter.objects.select_related("created_by")
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "pdf_formatters"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        formatter = self.get_object(pk)
        if not formatter:
            return Response(
                {"status": False, "message": "PDF formatter not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(formatter)
        return Response(
            {
                "status": True,
                "message": "PDF formatter fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        formatter = self.get_object(pk)
        if not formatter:
            return Response(
                {"status": False, "message": "PDF formatter not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(formatter, data=request.data)
        serializer.is_valid(raise_exception=True)
        formatter = serializer.save()

        return Response(
            {
                "status": True,
                "message": "PDF formatter updated successfully.",
                "data": self.get_serializer(formatter).data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        formatter = self.get_object(pk)
        if not formatter:
            return Response(
                {"status": False, "message": "PDF formatter not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(formatter, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        formatter = serializer.save()

        return Response(
            {
                "status": True,
                "message": "PDF formatter updated successfully.",
                "data": self.get_serializer(formatter).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        formatter = self.get_object(pk)
        if not formatter:
            return Response(
                {"status": False, "message": "PDF formatter not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        formatter.delete()
        return Response(
            {
                "status": True,
                "message": "PDF formatter deleted successfully.",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )


class PdfFormatterHtmlAPIView(generics.GenericAPIView):
    queryset = PdfFormatter.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "pdf_formatters"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        formatter = self.get_object(pk)
        if not formatter:
            return Response(
                {"status": False, "message": "PDF formatter not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return HttpResponse(
            formatter.html_content,
            content_type="text/html; charset=utf-8",
        )
