from rest_framework import serializers
from .models import Vendor, VendorCategory
from ListOfIngridients.models import IngridientsCategory


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IngridientsCategory
        fields = ["id", "name"]


class VendorCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = VendorCategory
        fields = ["id", "category", "category_name"]


class VendorSerializer(serializers.ModelSerializer):
    vendor_categories = VendorCategorySerializer(many=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "name",
            "mobile_no",
            "address",
            "is_active",
            "vendor_categories",
        ]

    def create(self, validated_data):
        categories_data = validated_data.pop("vendor_categories")
        vendor = Vendor.objects.create(**validated_data)

        for cat_data in categories_data:
            VendorCategory.objects.create(
                vendor=vendor,
                category=cat_data["category"],
            )

        return vendor

    def update(self, instance, validated_data):
        categories_data = validated_data.pop("vendor_categories", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if categories_data is not None:
            instance.vendor_categories.all().delete()

            for cat_data in categories_data:
                VendorCategory.objects.create(
                    vendor=instance,
                    category=cat_data["category"],
                )

        return instance
