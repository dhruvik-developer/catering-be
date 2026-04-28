from rest_framework import serializers
from item.serializers import ItemSerializer
from .models import *

class CategorySerializer(serializers.ModelSerializer):
    items = ItemSerializer(many=True, read_only=True)
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "positions",
            "items",
            "parent",
            "subcategories",
        ]

    def get_subcategories(self, obj):
        # Only return one level of subcategories to avoid deep recursion if needed,
        # but here we can just serialize them.
        serializer = CategorySerializer(obj.subcategories.all().order_by('positions'), many=True)
        return serializer.data

class CategoryPositionsChangesSerializer(serializers.Serializer):
    positions = serializers.CharField(required=True)
