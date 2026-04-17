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

    def post(self, request):
        if StokeCategory.objects.filter(name=request.data.get("name")).exists():
            return Response(
                {
                    "status": False,
                    "message": "Category already exists",
                    "data": {},
                },
                status=status.HTTP_200_OK,
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
        queryset = StokeCategory.objects.all()
        serializer = StokeCategorySerializer(queryset, many=True)
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
                status=status.HTTP_200_OK,
            )
        except StokeCategory.DoesNotExist:
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
                status=status.HTTP_200_OK,
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
                status=status.HTTP_200_OK,
            )


# --------------------    StokeItemViewSet    --------------------


class StokeItemViewSet(generics.GenericAPIView):
    serializer_class = StokeItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get(self, request):
        queryset = StokeItem.objects.all()
        serializer = StokeItemSerializer(queryset, many=True)
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
                status=status.HTTP_200_OK,
            )
        serializer = StokeItemSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "StokeItem created successfully",
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


class EditStokeItemViewSet(generics.GenericAPIView):
    serializer_class = StokeItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]

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
                status=status.HTTP_200_OK,
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
                status=status.HTTP_200_OK,
            )
        except StokeItem.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "StokeItem not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
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
                status=status.HTTP_200_OK,
            )


# --------------------    AddRemoveStokeItemViewSet    --------------------


class AddRemoveStokeItemViewSet(generics.GenericAPIView):
    permission_classes = [IsOwnerOrAdmin]

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
                status=status.HTTP_200_OK,
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
        result = to_decimal(stoke_item.quantity) - quantity_in_base
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
                status=status.HTTP_200_OK,
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
            stoke_item.nte_price = str(
                to_decimal(stoke_item.total_price) / to_decimal(stoke_item.quantity)
            )
        else:
            total_price = str(quantity_in_base * to_decimal(stoke_item.nte_price))
            stoke_item.total_price = str(
                to_decimal(stoke_item.total_price) + to_decimal(total_price)
            )
            stoke_item.nte_price = str(
                to_decimal(stoke_item.total_price) / to_decimal(stoke_item.quantity)
            )
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


# --------------------    AlertstokeItemViewSet    --------------------


class AlertstokeItemViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUserOrReadOnly]

    def get(self, request):
        alerts_list = []
        all_stoke_itmes = StokeItem.objects.all()
        for stokes in all_stoke_itmes:
            fallback_unit = default_display_unit(stokes.type)
            alert_threshold = parse_threshold_to_base(stokes.alert, fallback_unit)
            if to_decimal(stokes.quantity) <= alert_threshold:
                alerts_list.append(stokes)

        serializer = StokeItemSerializer(alerts_list, many=True)

        return Response(
            {
                "status": True,
                "message": "StokeItem Quantity Added successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
