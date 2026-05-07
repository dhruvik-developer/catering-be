from rest_framework import serializers
from .models import *


class IngridientsItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngridientsItem
        fields = ["id", "branch_profile", "name", "category"]
        read_only_fields = ["branch_profile"]


class IngridientsCategorySerializer(serializers.ModelSerializer):
    items = IngridientsItemSerializer(many=True, read_only=True)

    class Meta:
        model = IngridientsCategory
        fields = [
            "id",
            "branch_profile",
            "name",
            "is_common",
            "items",
        ]
        read_only_fields = ["branch_profile"]
