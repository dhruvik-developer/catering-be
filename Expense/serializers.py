from rest_framework import serializers
from .models import Expense, Category, ExpenseEntity

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ExpenseEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseEntity
        fields = '__all__'

class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    entity_name = serializers.CharField(source='entity.name', read_only=True)
    entity_type = serializers.CharField(source='entity.get_entity_type_display', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value

    def validate_payment_mode(self, value):
        valid_modes = [choice[0] for choice in Expense.PAYMENT_MODE_CHOICES]
        if value not in valid_modes:
            raise serializers.ValidationError("Invalid payment mode")
        return value