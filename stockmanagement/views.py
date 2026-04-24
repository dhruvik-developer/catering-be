from rest_framework.response import Response
from rest_framework import status, generics
from radha.Utils.permissions import *
from radha.Utils.unit_normalizer import (
    default_display_unit,
    normalize_unit,
    parse_threshold_to_base,
    to_base_unit,
    to_decimal,
    to_number,
    to_readable_quantity_unit,
)
from .serializers import *


def _request_quantity_to_base(raw_quantity, stoke_item, raw_unit=None):
    request_unit = normalize_unit(raw_unit)
    if not request_unit:
        # API responses expose weight in KG and liquid in L.
        request_unit = default_display_unit(stoke_item.type)
    return to_base_unit(raw_quantity, request_unit)


# --------------------    StokeCategoryViewSet    --------------------


class StokeCategoryViewSet(generics.GenericAPIView):
    serializer_class = StokeCategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "stock_categories"

    def post(self, request):
        if StokeCategory.objects.filter(name=request.data.get("name")).exists():
            return Response(
                {
                    "status": False,
                    "message": "Category already exists",
                    "data": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        serializer = StokeCategorySerializer(data=request.data)
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
        queryset = StokeCategory.objects.all().order_by("name", "id")
        page = self.paginate_queryset(queryset)
        queryset = page if page is not None else queryset
        serializer = StokeCategorySerializer(queryset, many=True)
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


class EditeStokeCategoryViewSet(generics.GenericAPIView):
    serializer_class = StokeCategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "stock_categories"

    def put(self, request, pk=None):
        try:
            category = StokeCategory.objects.get(pk=pk)
            serializer = StokeCategorySerializer(
                category, data=request.data, partial=True
            )
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
        except StokeCategory.DoesNotExist:
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
            category = StokeCategory.objects.get(pk=pk)
            category.delete()
            return Response(
                {
                    "status": True,
                    "message": "Category deleted successfully",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except StokeCategory.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, pk=None):
        try:
            category = StokeCategory.objects.get(pk=pk)
            serializer = StokeCategorySerializer(category)
            return Response(
                {
                    "status": True,
                    "message": "Category retrieved successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except StokeCategory.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )


# --------------------    StokeItemViewSet    --------------------


class StokeItemViewSet(generics.GenericAPIView):
    serializer_class = StokeItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "stock_items"

    def get(self, request):
        queryset = StokeItem.objects.select_related("category", "created_by").all()
        page = self.paginate_queryset(queryset)
        queryset = page if page is not None else queryset
        serializer = StokeItemSerializer(queryset, many=True)
        if page is not None:
            self.paginator.message = "StokeItem list"
            return self.get_paginated_response(serializer.data)

        return Response(
            {
                "status": True,
                "message": "StokeItem list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if StokeItem.objects.filter(name=request.data.get("name")).exists():
            return Response(
                {
                    "status": False,
                    "message": "StokeItem already exists",
                    "data": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        serializer = StokeItemSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save(
                created_by=request.user if request.user.is_authenticated else None
            )
            return Response(
                {
                    "status": True,
                    "message": "StokeItem created successfully",
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


class EditStokeItemViewSet(generics.GenericAPIView):
    serializer_class = StokeItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "stock_items"

    def get(self, request, pk=None):
        try:
            stokeitem = StokeItem.objects.get(pk=pk)
            serializer = StokeItemSerializer(stokeitem)
            return Response(
                {
                    "status": True,
                    "message": "StokeItem retrieved successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except StokeItem.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "StokeItem not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    def put(self, request, pk=None):
        try:
            stokeitem = StokeItem.objects.get(pk=pk)
            payload = request.data.copy()

            input_quantity = _request_quantity_to_base(
                payload.get("quantity", 0),
                stokeitem,
                payload.get("type"),
            )
            payload["quantity"] = str(to_decimal(stokeitem.quantity) + input_quantity)

            payload["total_price"] = str(
                to_decimal(payload.get("total_price", 0)) + to_decimal(stokeitem.total_price)
            )
            quantity_base = to_decimal(payload.get("quantity", 0))
            if quantity_base > 0:
                payload["nte_price"] = str(
                    to_decimal(payload.get("total_price", 0)) / quantity_base
                )

            # Keep storage type in base units.
            payload["type"] = stokeitem.type

            serializer = StokeItemSerializer(stokeitem, data=payload, partial=True)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                return Response(
                    {
                        "status": True,
                        "message": "StokeItem updated successfully",
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
        except StokeItem.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "StokeItem not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    def delete(self, request, pk=None):
        try:
            stokeitem = StokeItem.objects.get(pk=pk)
            stokeitem.delete()
            return Response(
                {
                    "status": True,
                    "message": "StokeItem deleted successfully",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except StokeItem.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "StokeItem not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )


# --------------------    AddRemoveStokeItemViewSet    --------------------


class AddRemoveStokeItemViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "stock_adjustments"

    def post(self, request):
        if not StokeItem.objects.filter(
            id=request.data.get("id"), name=request.data.get("name")
        ).exists():
            return Response(
                {
                    "status": False,
                    "message": "StokeItem is not exists",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        quantity = request.data.get("quantity")
        nte_price = request.data.get("nte_price")
        total_price = request.data.get("total_price", None)
        price = ""
        stoke_item = StokeItem.objects.get(
            id=request.data.get("id"), name=request.data.get("name")
        )
        quantity_in_base = _request_quantity_to_base(
            quantity, stoke_item, request.data.get("type")
        )
        current_quantity = to_decimal(stoke_item.quantity)
        result = current_quantity - quantity_in_base
        if result < 0:
            readable_current, readable_current_type = to_readable_quantity_unit(
                stoke_item.quantity, stoke_item.type
            )
            return Response(
                {
                    "status": False,
                    "message": (
                        f"Insufficient stock: only {to_number(readable_current)} "
                        f"{readable_current_type} available."
                    ),
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if total_price:
            price = total_price
        else:
            price = str(quantity_in_base * to_decimal(nte_price))
        stoke_item.total_price = str(to_decimal(stoke_item.total_price) - to_decimal(price))
        stoke_item.quantity = result
        stoke_item.save()

        readable_quantity, readable_type = to_readable_quantity_unit(
            stoke_item.quantity, stoke_item.type
        )
        return Response(
            {
                "status": True,
                "message": "StokeItem Quantity Remove successfully",
                "data": {
                    "id": stoke_item.id,
                    "name": stoke_item.name,
                    "quantity": to_number(readable_quantity),
                    "type": readable_type,
                    "nte_price": str(stoke_item.nte_price),
                    "total_price": str(stoke_item.total_price),
                },
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        if not StokeItem.objects.filter(
            id=request.data.get("id"), name=request.data.get("name")
        ).exists():
            return Response(
                {
                    "status": False,
                    "message": "StokeItem is not exists",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        quantity = request.data.get("quantity")
        total_price = request.data.get("total_price", None)
        stoke_item = StokeItem.objects.get(
            id=request.data.get("id"), name=request.data.get("name")
        )
        quantity_in_base = _request_quantity_to_base(
            quantity, stoke_item, request.data.get("type")
        )
        result = to_decimal(stoke_item.quantity) + quantity_in_base
        stoke_item.quantity = result
        if total_price:
            stoke_item.total_price = str(
                to_decimal(stoke_item.total_price) + to_decimal(total_price)
            )
        else:
            total_price = str(quantity_in_base * to_decimal(stoke_item.nte_price))
            stoke_item.total_price = str(
                to_decimal(stoke_item.total_price) + to_decimal(total_price)
            )
        # Weighted average unit price. Guarded against zero quantity (e.g. an
        # add of zero that leaves stock at zero) so we don't crash on division.
        if result > 0:
            stoke_item.nte_price = str(
                to_decimal(stoke_item.total_price) / result
            )
        else:
            stoke_item.nte_price = "0"
        stoke_item.save()

        readable_quantity, readable_type = to_readable_quantity_unit(
            stoke_item.quantity, stoke_item.type
        )
        return Response(
            {
                "status": True,
                "message": "StokeItem Quantity Added successfully",
                "data": {
                    "id": stoke_item.id,
                    "name": stoke_item.name,
                    "quantity": to_number(readable_quantity),
                    "type": readable_type,
                    "nte_price": str(stoke_item.nte_price),
                    "total_price": str(stoke_item.total_price),
                },
            },
            status=status.HTTP_200_OK,
        )
