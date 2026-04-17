from rest_framework import serializers
from item.serializers import ItemSerializer
from .models import *

class CategorySerializer(serializers.ModelSerializer):
    items = ItemSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "positions",
            "items",
        ]

class CategoryPositionsChangesSerializer(serializers.Serializer):
    positions = serializers.CharField(required=True)
