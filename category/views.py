from rest_framework.response import Response
from rest_framework import status, generics
from django.db import transaction
from radha.Utils.permissions import *
from .serializers import *
from django.shortcuts import get_object_or_404


# --------------------    CategoryViewSet    --------------------


class CategoryViewSet(generics.GenericAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "categories"

    def post(self, request):
        if Category.objects.filter(name=request.data.get("name")).exists():
            return Response(
                {
                    "status": False,
                    "message": "Category already exists",
                    "data": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        last_category = Category.objects.order_by('-positions').first()
        last_positions = last_category.positions if last_category else 0

        request.data["positions"] = last_positions + 1
        serializer = CategorySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Category created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "Something went wrong",
                "data": {},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        queryset = Category.objects.all().order_by("positions", "id")
        page = self.paginate_queryset(queryset)
        queryset = page if page is not None else queryset
        serializer = CategorySerializer(queryset, many=True)
        if page is not None:
            self.paginator.message = "Category list"
            return self.get_paginated_response(serializer.data)

        return Response(
            {
                "status": True,
                "message": "Category list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CategoryGetViewSet(generics.GenericAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "categories"

    def put(self, request, pk=None):
        try:
            category = Category.objects.get(pk=pk)
            serializer = CategorySerializer(category, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                return Response(
                    {
                        "status": True,
                        "message": "Category updated successfully",
                        "data": serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Category.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    def delete(self, request, pk=None):
        try:
            with transaction.atomic():
                # Get the category to be deleted
                category = get_object_or_404(Category, pk=pk)
                deleted_position = category.positions

                # Delete the category
                category.delete()

                # Update positions of all categories after the deleted one
                Category.objects.filter(
                    positions__gt=deleted_position
                ).update(positions=models.F("positions") - 1)

                return Response(
                    {
                        "status": True,
                        "message": "Category deleted and positions updated successfully",
                    },
                    status=200,
                )

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)

    def get(self, request, pk=None):
        try:
            category = Category.objects.get(pk=pk)
            serializer = CategorySerializer(category)
            return Response(
                {
                    "status": True,
                    "message": "Category retrieved successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except Category.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class CategoryPositionsChangesViewSet(generics.GenericAPIView):
    serializer_class = CategoryPositionsChangesSerializer
    permission_classes = [IsOwnerOrAdmin]
    permission_resource = "categories"

    def post(self, request, pk):
        try:
            new_positions = request.data.get("positions")

            # Get the category whose position is being updated
            category = get_object_or_404(Category, pk=pk)
            old_positions = category.positions

            if old_positions == new_positions:
                return Response(
                    {
                        "status": False,
                        "message": "No changes needed, position is the same.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # If moving up (better position, smaller number)
            if new_positions < old_positions:
                # Shift all employees between new_position and old_position down by 1
                Category.objects.filter(
                    positions__gte=new_positions, positions__lt=old_positions
                ).update(positions=models.F("positions") + 1)

            # If moving down (worse position, larger number)
            elif new_positions > old_positions:
                # Shift all employees between old_position and new_position up by 1
                Category.objects.filter(
                    positions__gt=old_positions, positions__lte=new_positions
                ).update(positions=models.F("positions") - 1)

            # Assign the new position to the employee
            category.positions = new_positions
            category.save()

            return Response(
                {
                    "status": True,
                    "message": f"{category.name} moved to position {new_positions}",
                },
                status=200,
            )

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)
