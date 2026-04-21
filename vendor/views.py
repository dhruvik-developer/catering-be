from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from .models import Vendor, VendorCategory, IngridientsCategory
from .serializers import VendorSerializer, CategorySerializer
from radha.Utils.permissions import IsAdminUserOrReadOnly



class CategoryListCreateAPIView(generics.GenericAPIView):
    serializer_class = CategorySerializer
    queryset = IngridientsCategory.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "vendor_categories"

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {"status": True, "message": "Categories fetched successfully", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"status": True, "message": "Category created successfully", "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

class CategoryDetailAPIView(generics.GenericAPIView):
    serializer_class = CategorySerializer
    queryset = IngridientsCategory.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "vendor_categories"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"status": False, "message": "Category not found"}, status=404)

        serializer = self.get_serializer(category)
        return Response({"status": True, "data": serializer.data})

    def put(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"status": False, "message": "Category not found"}, status=404)

        serializer = self.get_serializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"status": True, "message": "Category updated", "data": serializer.data})

    def delete(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"status": False, "message": "Category not found"}, status=404)

        category.delete()
        return Response({"status": True, "message": "Category deleted"})
        

class VendorListCreateAPIView(generics.GenericAPIView):
    serializer_class = VendorSerializer
    queryset = Vendor.objects.select_related("user_account").prefetch_related("vendor_categories__category")
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "vendors"

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get("category_id")

        if category_id:
            queryset = queryset.filter(
                vendor_categories__category__id=category_id
            ).distinct()

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {"status": True, "message": "Vendors fetched successfully", "data": serializer.data}
        )

    @transaction.atomic
    def post(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admin can create this resource.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()

        return Response(
            {"status": True, "message": "Vendor created successfully", "data": VendorSerializer(vendor).data},
            status=status.HTTP_201_CREATED,
        )


class VendorDetailAPIView(generics.GenericAPIView):
    serializer_class = VendorSerializer
    queryset = Vendor.objects.select_related("user_account").prefetch_related("vendor_categories__category")
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "vendors"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        vendor = self.get_object(pk)
        if not vendor:
            return Response({"status": False, "message": "Vendor not found"}, status=404)

        serializer = self.get_serializer(vendor)
        return Response({"status": True, "data": serializer.data})

    @transaction.atomic
    def put(self, request, pk):
        vendor = self.get_object(pk)
        if not vendor:
            return Response({"status": False, "message": "Vendor not found"}, status=404)

        serializer = self.get_serializer(vendor, data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()

        return Response({"status": True, "message": "Vendor updated", "data": serializer.data})

    def delete(self, request, pk):
        vendor = self.get_object(pk)
        if not vendor:
            return Response({"status": False, "message": "Vendor not found"}, status=404)

        vendor.delete()
        return Response({"status": True, "message": "Vendor deleted"})
