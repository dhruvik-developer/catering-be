from rest_framework import serializers
from .models import Item, RecipeIngredient
from ListOfIngridients.models import IngridientsItem, IngridientsCategory
from radha.Utils.unit_normalizer import (
    normalize_quantity_unit,
    to_number,
    to_readable_quantity_unit,
)


def _readable_recipe_quantity_unit(quantity, unit):
    readable_quantity, readable_unit = to_readable_quantity_unit(quantity, unit)
    return to_number(readable_quantity), readable_unit


class IngredientCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IngridientsCategory
        fields = ["id", "name"]


class IngridientsItemSerializer(serializers.ModelSerializer):
    category = IngredientCategorySerializer(read_only=True)

    class Meta:
        model = IngridientsItem
        fields = ["id", "name", "category"]


class RecipeIngredientDetailSerializer(serializers.ModelSerializer):
    ingredient = serializers.CharField(source="ingredient.name", read_only=True)
    category = serializers.CharField(source="ingredient.category.name", read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ["id", "ingredient", "category", "quantity", "unit", "person_count"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["quantity"], data["unit"] = _readable_recipe_quantity_unit(
            instance.quantity, instance.unit
        )
        return data


class RecipeIngredientSerializer(serializers.ModelSerializer):
    item = serializers.CharField(source="item.name", read_only=True)
    ingredient = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_category = serializers.CharField(source="ingredient.category.name", read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ["id", "item", "ingredient", "ingredient_category", "quantity", "unit", "person_count"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["quantity"], data["unit"] = _readable_recipe_quantity_unit(
            instance.quantity, instance.unit
        )
        return data


class RecipeIngredientCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeIngredient
        fields = ["id", "item", "ingredient", "quantity", "unit", "person_count"]

    def validate(self, attrs):
        quantity = attrs.get("quantity", getattr(self.instance, "quantity", 0))
        unit = attrs.get("unit", getattr(self.instance, "unit", ""))
        base_quantity, base_unit = normalize_quantity_unit(quantity, unit)

        attrs["quantity"] = float(base_quantity)
        attrs["unit"] = base_unit
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["quantity"], data["unit"] = _readable_recipe_quantity_unit(
            instance.quantity, instance.unit
        )
        return data


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "category", "base_cost", "selection_rate"]


class ItemDetailSerializer(serializers.ModelSerializer):
    item = serializers.CharField(source="name", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    ingredients = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = ["id", "item", "category", "ingredients"]

    def get_ingredients(self, obj):
        recipe_qs = obj.recipe_ingredients.select_related("ingredient__category").all()
        ingredients = []
        for ri in recipe_qs:
            readable_quantity, readable_unit = _readable_recipe_quantity_unit(
                ri.quantity, ri.unit
            )
            ingredients.append(
                {
                    "ingredient": ri.ingredient.name,
                    "category": ri.ingredient.category.name if ri.ingredient.category else None,
                    "quantity": readable_quantity,
                    "unit": readable_unit,
                    "person_count": ri.person_count,
                }
            )
        return ingredients




