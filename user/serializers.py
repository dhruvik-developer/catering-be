from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import *


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class NoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Note
        fields = ["id", "title", "content"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = UserModel
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is None or not request.user.is_superuser:
            raise PermissionDenied("Only admin allowed.")

        user = UserModel.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        return user

    def validate_password(self, value):
        # Add password strength validation if needed
        if len(value) < 4:
            raise serializers.ValidationError(
                "Password must be at least 4 characters long."
            )
        return value


class ChangePasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        # Add password strength validation if needed
        if len(value) < 4:
            raise serializers.ValidationError(
                "Password must be at least 4 characters long."
            )
        return value


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = [
            "id",
            "caters_name",
            "phone_number",
            "whatsapp_number",
            "fssai_number",
            "godown_address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
