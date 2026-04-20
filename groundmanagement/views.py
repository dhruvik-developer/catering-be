from django.db.models.deletion import ProtectedError
from rest_framework import generics, status
from rest_framework.response import Response

from radha.Utils.permissions import IsAdminUserOrReadOnly

from .models import GroundCategory, GroundItem
from .serializers import (
    GroundCategorySerializer,
    GroundItemSerializer,
)


class GroundCategoryViewSet(generics.GenericAPIView):
    serializer_class = GroundCategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ground_categories"

    def get(self, request):
        queryset = (
            GroundCategory.objects.prefetch_related("ground_items")
            .all()
            .order_by("name")
        )
        serializer = self.serializer_class(queryset, many=True)
        return Response(
            {
                "status": True,
                "message": "Ground category list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Ground category created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )


class GroundCategoryDetailViewSet(generics.GenericAPIView):
    serializer_class = GroundCategorySerializer
    queryset = GroundCategory.objects.prefetch_related("ground_items").all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ground_categories"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response(
                {"status": False, "message": "Ground category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(category)
        return Response(
            {
                "status": True,
                "message": "Ground category detail",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response(
                {"status": False, "message": "Ground category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Ground category updated successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response(
                {"status": False, "message": "Ground category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Ground category updated successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response(
                {"status": False, "message": "Ground category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            category.delete()
        except ProtectedError:
            return Response(
                {
                    "status": False,
                    "message": "Cannot delete ground category because it is linked with ground items.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"status": True, "message": "Ground category deleted successfully"},
            status=status.HTTP_200_OK,
        )


class GroundItemViewSet(generics.GenericAPIView):
    serializer_class = GroundItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ground_items"

    def get(self, request):
        queryset = GroundItem.objects.select_related("category").all().order_by("name")
        category_id = request.query_params.get("category_id")
        is_active = request.query_params.get("is_active")

        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=(is_active.lower() == "true"))

        serializer = self.serializer_class(queryset, many=True)
        return Response(
            {"status": True, "message": "Ground item list", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Ground item created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )


class GroundItemDetailViewSet(generics.GenericAPIView):
    serializer_class = GroundItemSerializer
    queryset = GroundItem.objects.select_related("category").all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ground_items"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Ground item not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(item)
        return Response(
            {"status": True, "message": "Ground item detail", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Ground item not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Ground item updated successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Ground item not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Ground item updated successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Ground item not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            item.delete()
        except ProtectedError:
            return Response(
                {
                    "status": False,
                    "message": "Cannot delete ground item because it is linked with event ground requirements.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"status": True, "message": "Ground item deleted successfully"},
            status=status.HTTP_200_OK,
        )
