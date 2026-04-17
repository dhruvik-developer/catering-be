from rest_framework import serializers
from .models import *
from radha.Utils.unit_normalizer import (
    normalize_quantity_unit,
    to_number,
    to_readable_quantity_unit,
)

class StokeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StokeItem
        fields = [
            "id",
            "name",
            "category",
            "quantity",
            "alert",
            "type",
            "nte_price",
            "total_price",
        ]

    def validate(self, attrs):
        quantity = attrs.get("quantity", getattr(self.instance, "quantity", 0))
        stock_type = attrs.get("type", getattr(self.instance, "type", ""))
        base_quantity, base_type = normalize_quantity_unit(quantity, stock_type)

        attrs["quantity"] = base_quantity
        attrs["type"] = base_type
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        readable_quantity, readable_type = to_readable_quantity_unit(
            instance.quantity, instance.type
        )
        data["quantity"] = to_number(readable_quantity)
        data["type"] = readable_type
        return data


class StokeCategorySerializer(serializers.ModelSerializer):
    stokeitem = StokeItemSerializer(many=True, read_only=True)

    class Meta:
        model = StokeCategory
        fields = ["id", "name", "stokeitem"]
