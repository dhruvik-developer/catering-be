from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import Vendor, VendorCategory
from ListOfIngridients.models import IngridientsCategory

UserModel = get_user_model()


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
    linked_user_id = serializers.UUIDField(source="user_account.id", read_only=True)
    linked_username = serializers.CharField(
        source="user_account.username",
        read_only=True,
    )
    login_enabled = serializers.SerializerMethodField()
    login_username = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    login_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    login_email = serializers.EmailField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Vendor
        fields = [
            "id",
            "user_account",
            "linked_user_id",
            "linked_username",
            "login_enabled",
            "login_username",
            "login_password",
            "login_email",
            "name",
            "mobile_no",
            "address",
            "is_active",
            "vendor_categories",
        ]
        read_only_fields = [
            "user_account",
            "linked_user_id",
            "linked_username",
            "login_enabled",
        ]

    def get_login_enabled(self, obj):
        return obj.user_account_id is not None

    def validate(self, attrs):
        username = attrs.get("login_username")
        password = attrs.get("login_password")
        existing_user = getattr(self.instance, "user_account", None)

        if username == "":
            username = None
        if password == "":
            password = None

        if username and not existing_user and not password:
            raise serializers.ValidationError(
                {"login_password": "Password is required when creating a vendor login."}
            )

        if password and len(password) < 4:
            raise serializers.ValidationError(
                {"login_password": "Password must be at least 4 characters long."}
            )

        if username:
            users = UserModel.objects.filter(username=username)
            if existing_user:
                users = users.exclude(pk=existing_user.pk)
            if users.exists():
                raise serializers.ValidationError(
                    {"login_username": "This username is already in use."}
                )

        return attrs

    def _upsert_login_user(self, vendor, validated_data):
        username = validated_data.pop("login_username", None)
        password = validated_data.pop("login_password", None)
        email = validated_data.pop("login_email", None)

        username = username or None
        password = password or None
        email = email or ""

        linked_user = vendor.user_account
        if not username and not linked_user:
            return

        if linked_user is None and username:
            linked_user = UserModel.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=vendor.name,
                is_active=vendor.is_active,
            )
            vendor.user_account = linked_user
            vendor.save(update_fields=["user_account"])
            return

        if linked_user is not None:
            if username:
                linked_user.username = username
            if "login_email" in self.initial_data:
                linked_user.email = email
            linked_user.first_name = vendor.name
            linked_user.is_active = vendor.is_active
            if password:
                linked_user.set_password(password)
            linked_user.save()

    def create(self, validated_data):
        request = self.context.get("request")
        if request is None or not request.user.is_superuser:
            raise PermissionDenied("Only admin allowed.")

        categories_data = validated_data.pop("vendor_categories", [])
        vendor = Vendor.objects.create(
            **{
                key: value
                for key, value in validated_data.items()
                if key not in {"login_username", "login_password", "login_email"}
            }
        )

        for cat_data in categories_data:
            VendorCategory.objects.create(
                vendor=vendor,
                category=cat_data["category"],
            )

        self._upsert_login_user(vendor, validated_data)
        return vendor

    def update(self, instance, validated_data):
        categories_data = validated_data.pop("vendor_categories", None)

        for attr, value in list(validated_data.items()):
            if attr in {"login_username", "login_password", "login_email"}:
                continue
            setattr(instance, attr, value)

        instance.save()

        if categories_data is not None:
            instance.vendor_categories.all().delete()

            for cat_data in categories_data:
                VendorCategory.objects.create(
                    vendor=instance,
                    category=cat_data["category"],
                )

        self._upsert_login_user(instance, validated_data)
        return instance
