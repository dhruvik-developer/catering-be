from rest_framework.response import Response
from rest_framework import status, generics
from django.db import transaction
from user.branching import (
    ensure_object_in_user_branch,
    filter_branch_queryset,
    get_branch_save_kwargs,
)
from radha.Utils.permissions import *
from .serializers import *
from django.shortcuts import get_object_or_404


# --------------------    CategoryViewSet    --------------------


class CategoryViewSet(generics.GenericAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "categories"

    def get_queryset(self):
        return filter_branch_queryset(Category.objects.all(), self.request)

    def post(self, request):
        branch_kwargs = get_branch_save_kwargs(request)
        parent_id = request.data.get("parent")
        if parent_id:
            parent = get_object_or_404(self.get_queryset(), id=parent_id)
            branch_kwargs["branch_profile"] = parent.branch_profile

        if self.get_queryset().filter(
            name=request.data.get("name"),
            parent_id=parent_id,
        ).exists():
            return Response(
                {
                    "status": False,
                    "message": "Category already exists",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        last_category = self.get_queryset().filter(parent_id=parent_id).order_by('-positions').first()
        last_positions = last_category.positions if last_category else 0

        request.data["positions"] = last_positions + 1
        serializer = CategorySerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save(**branch_kwargs)
            return Response(
                {
                    "status": True,
                    "message": "Category created successfully",
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
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        queryset = self.get_queryset().filter(parent__isnull=True).order_by('positions')
        serializer = CategorySerializer(queryset, many=True)
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

    def get_queryset(self):
        return filter_branch_queryset(Category.objects.all(), self.request)

    def put(self, request, pk=None):
        try:
            category = self.get_queryset().get(pk=pk)
            serializer = CategorySerializer(category, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                parent = serializer.validated_data.get("parent")
                if parent:
                    ensure_object_in_user_branch(parent, request)
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
                status=status.HTTP_200_OK,
            )
        except Category.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

    def delete(self, request, pk=None):
        try:
            with transaction.atomic():
                # Get the category to be deleted
                category = get_object_or_404(self.get_queryset(), pk=pk)
                deleted_position = category.positions

                # Delete the category
                category.delete()

                # Update positions of all categories after the deleted one
                self.get_queryset().filter(
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
            category = self.get_queryset().get(pk=pk)
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
                status=status.HTTP_200_OK,
            )


class CategoryPositionsChangesViewSet(generics.GenericAPIView):
    serializer_class = CategoryPositionsChangesSerializer
    permission_classes = [IsOwnerOrAdmin]
    permission_resource = "categories"

    def get_queryset(self):
        return filter_branch_queryset(Category.objects.all(), self.request)

    def post(self, request, pk):
        try:
            new_positions = request.data.get("positions")

            # Get the category whose position is being updated
            category = get_object_or_404(self.get_queryset(), pk=pk)
            old_positions = category.positions

            if old_positions == new_positions:
                return Response(
                    {
                        "status": False,
                        "message": "No changes needed, position is the same.",
                    },
                    status=200,
                )

            # If moving up (better position, smaller number)
            if new_positions < old_positions:
                # Shift all categories between new_position and old_position down by 1
                self.get_queryset().filter(
                    parent=category.parent,
                    positions__gte=new_positions, positions__lt=old_positions
                ).update(positions=models.F("positions") + 1)

            # If moving down (worse position, larger number)
            elif new_positions > old_positions:
                # Shift all categories between old_position and new_position up by 1
                self.get_queryset().filter(
                    parent=category.parent,
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
            return Response({"status": True, "message": str(e)}, status=500)
