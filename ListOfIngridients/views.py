from rest_framework.response import Response
from rest_framework import status, generics
from user.branching import (
    ensure_object_in_user_branch,
    filter_branch_queryset,
    get_branch_save_kwargs,
)
from radha.Utils.permissions import *
from .models import *
from .serializers import *


# --------------------    IngridientsCategoryViewset    --------------------


class IngridientsCategoryViewset(generics.GenericAPIView):
    serializer_class = IngridientsCategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ingredient_categories"

    def get_queryset(self):
        return filter_branch_queryset(IngridientsCategory.objects.all(), self.request)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(**get_branch_save_kwargs(request))
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_200_OK)

    def get(self,request,pk=None):
        if pk:
            queryset = self.get_queryset().filter(pk=pk)
        else:
            queryset = self.get_queryset()

        serializer = IngridientsCategorySerializer(queryset, many=True)

        return Response(
            {
                "status": True,
                "message": "Ingridients Category list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None, *args, **kwargs):
        try:
            instance = self.get_queryset().get(pk=pk)
        except IngridientsCategory.DoesNotExist:
            return Response(
                {"status": False, "message": "Ingridients Categories not found"},
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_200_OK)

    def delete(self, request, pk=None, *args, **kwargs):
        try:
            instance = self.get_queryset().get(pk=pk)
        except IngridientsCategory.DoesNotExist:
            return Response(
                {"status": False, "message": "Ingridients Categories not found"},
                status=status.HTTP_200_OK,
            )
        instance.delete()
        return Response(
            {"status": True, "message": "Ingridients Categories deleted"},
            status=status.HTTP_200_OK,
        )


# --------------------    IngridientsItemViewset    --------------------


class IngridientsItemViewset(generics.GenericAPIView):
    serializer_class = IngridientsItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ingredient_items"

    def get_queryset(self):
        return filter_branch_queryset(IngridientsItem.objects.all(), self.request)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            category = serializer.validated_data.get("category")
            ensure_object_in_user_branch(category, request)
            serializer.save(branch_profile=category.branch_profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_200_OK)

    def get(self,request,pk=None):
        if pk:
            queryset = self.get_queryset().filter(pk=pk)
        else:
            queryset = self.get_queryset()
        serializer = IngridientsItemSerializer(queryset, many=True)
        return Response(
            {
                "status": True,
                "message": "Ingridients Item list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None, *args, **kwargs):
        try:
            instance = self.get_queryset().get(pk=pk)
        except IngridientsItem.DoesNotExist:
            return Response(
                {"status": False, "message": "Ingridients Item not found"},
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            category = serializer.validated_data.get("category")
            if category:
                ensure_object_in_user_branch(category, request)
                serializer.save(branch_profile=category.branch_profile)
                return Response(serializer.data, status=status.HTTP_200_OK)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_200_OK)

    def delete(self, request, pk=None, *args, **kwargs):
        try:
            instance = self.get_queryset().get(pk=pk)
        except IngridientsItem.DoesNotExist:
            return Response(
                {"status": False, "message": "Ingridients Item not found"},
                status=status.HTTP_200_OK,
            )
        instance.delete()
        return Response(
            {"status": True, "message": "Ingridients Item deleted"},
            status=status.HTTP_200_OK,
        )
