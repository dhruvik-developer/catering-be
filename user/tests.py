from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from django_tenants.utils import schema_context
from tenancy.models import Client, Domain


UserModel = get_user_model()


class UserCreationAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = UserModel.objects.create_superuser(
            username="admin-user",
            email="admin@example.com",
            password="admin1234",
        )
        self.manager = UserModel.objects.create_user(
            username="manager-user",
            email="manager@example.com",
            password="manager1234",
        )

        module, _ = PermissionModule.objects.get_or_create(
            code="users",
            defaults={"name": "Users"},
        )
        create_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="users.create",
            defaults={
                "action": "create",
                "name": "Create User",
            },
        )
        view_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="users.view",
            defaults={
                "action": "view",
                "name": "View User",
            },
        )

        UserPermissionAssignment.objects.create(
            user=self.manager,
            permission=create_permission,
            is_allowed=True,
        )
        UserPermissionAssignment.objects.create(
            user=self.manager,
            permission=view_permission,
            is_allowed=True,
        )

    def test_non_admin_cannot_create_user_even_with_create_permission(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/users/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(response.data["detail"]),
            "Only platform admin or tenant admin can create this resource.",
        )
        self.assertFalse(UserModel.objects.filter(username="new-user").exists())

    def test_admin_can_create_user(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/users/",
            {
                "username": "created-by-admin",
                "email": "created@example.com",
                "password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertTrue(UserModel.objects.filter(username="created-by-admin").exists())

    def test_non_admin_with_view_permission_can_still_list_users(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "User list fetched successfully.")


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", ".localhost"],
    SAAS_ROOT_DOMAIN="localhost",
)
class TenantSaaSTests(TestCase):
    def setUp(self):
        connection.set_schema_to_public()
        self.client = APIClient()
        self.platform_admin = UserModel.objects.create_superuser(
            username="platform-admin",
            email="platform@example.com",
            password="admin1234",
        )
        self.category_module, _ = PermissionModule.objects.get_or_create(
            code="categories",
            defaults={"name": "Categories"},
        )
        self.users_module, _ = PermissionModule.objects.get_or_create(
            code="users",
            defaults={"name": "Users"},
        )
        AccessPermission.objects.get_or_create(
            module=self.category_module,
            code="categories.view",
            defaults={"action": "view", "name": "View categories"},
        )
        AccessPermission.objects.get_or_create(
            module=self.category_module,
            code="categories.create",
            defaults={"action": "create", "name": "Create categories"},
        )

    def tearDown(self):
        connection.set_schema_to_public()

    def test_platform_admin_can_create_tenant_with_admin_user(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.post(
            "/api/tenants/",
            {
                "name": "Radha Catering",
                "schema_name": "radha",
                "subscription_status": "active",
                "enabled_modules": ["categories", "users"],
                "admin": {
                    "username": "radha-admin",
                    "email": "admin@radha.example",
                    "password": "admin1234",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["schema_name"], "radha")
        self.assertEqual(response.data["data"]["schema_status"], "ready")

        tenant = Client.objects.get(schema_name="radha")
        self.assertEqual(tenant.get_primary_domain().domain, "radha.localhost")
        self.assertFalse(UserModel.objects.filter(username="radha-admin").exists())
        with schema_context("radha"):
            tenant_admin = UserModel.objects.get(username="radha-admin")
            self.assertTrue(tenant_admin.is_staff)

    def test_platform_admin_can_create_tenant_with_explicit_domain(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.post(
            "/api/tenants/",
            {
                "name": "EV Catering",
                "schema_name": "ev_catering",
                "subscription_status": "active",
                "domains": [
                    {
                        "domain": "evcatering",
                        "is_primary": True,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["schema_name"], "ev_catering")
        self.assertEqual(
            response.data["data"]["primary_domain"],
            "evcatering.localhost",
        )

        tenant = Client.objects.get(schema_name="ev_catering")
        self.assertEqual(tenant.get_primary_domain().domain, "evcatering.localhost")
        self.assertFalse(
            Domain.objects.filter(domain="ev_catering.localhost").exists()
        )

    def test_tenant_admin_can_login_with_schema_name_from_public_host(self):
        tenant = Client.objects.create(
            name="Radha",
            schema_name="radha",
            subscription_status=Client.STATUS_ACTIVE,
        )
        Domain.objects.create(
            tenant=tenant,
            domain=f"radha.{settings.SAAS_ROOT_DOMAIN}",
            is_primary=True,
        )

        with schema_context("radha"):
            UserModel.objects.create_user(
                username="radha-admin",
                password="admin1234",
                is_staff=True,
            )

        response = self.client.post(
            "/api/login/",
            {
                "username": "radha-admin",
                "password": "admin1234",
                "schema_name": "radha",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["data"]["tenant"]["schema_name"], "radha")
        access_token = AccessToken(response.data["data"]["tokens"]["access"])
        self.assertEqual(access_token["schema_name"], "radha")

    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=[],
        CORS_ALLOWED_ORIGIN_REGEXES=[r"^http://.*\.localhost:5173$"],
    )
    def test_local_admin_subdomain_cors_preflight_does_not_require_tenant(self):
        response = self.client.options(
            "/api/login/",
            HTTP_HOST="admin.localhost",
            HTTP_ORIGIN="http://admin.localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["access-control-allow-origin"],
            "http://admin.localhost:5173",
        )

    def test_tenant_admin_can_login_from_public_host_when_credentials_are_unique(self):
        tenant = Client.objects.create(
            name="Radha",
            schema_name="radha",
            subscription_status=Client.STATUS_ACTIVE,
        )
        Domain.objects.create(
            tenant=tenant,
            domain=f"radha.{settings.SAAS_ROOT_DOMAIN}",
            is_primary=True,
        )

        with schema_context("radha"):
            UserModel.objects.create_user(
                username="unique-radha-admin",
                password="admin1234",
                is_staff=True,
            )

        response = self.client.post(
            "/api/login/",
            {
                "username": "unique-radha-admin",
                "password": "admin1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["data"]["tenant"]["schema_name"], "radha")

    def test_tenant_admin_can_create_module_scoped_user(self):
        tenant = Client.objects.create(
            name="Radha",
            schema_name="radha",
            subscription_status=Client.STATUS_ACTIVE,
        )
        Domain.objects.create(
            tenant=tenant,
            domain=f"radha.{settings.SAAS_ROOT_DOMAIN}",
            is_primary=True,
        )
        tenant.enabled_modules.set([self.category_module, self.users_module])

        with schema_context("radha"):
            category_module, _ = PermissionModule.objects.get_or_create(
                code="categories",
                defaults={"name": "Categories"},
            )
            AccessPermission.objects.get_or_create(
                module=category_module,
                code="categories.view",
                defaults={"action": "view", "name": "View categories"},
            )
            tenant_admin = UserModel.objects.create_user(
                username="radha-admin",
                password="admin1234",
                is_staff=True,
            )

        self.client.force_authenticate(user=tenant_admin)

        response = self.client.post(
            "/api/users/",
            {
                "username": "radha-manager",
                "email": "manager@radha.example",
                "password": "manager1234",
                "module_codes": ["categories"],
            },
            format="json",
            HTTP_HOST=f"radha.{settings.SAAS_ROOT_DOMAIN}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context("radha"):
            created_user = UserModel.objects.get(username="radha-manager")
            self.assertTrue(
                UserPermissionAssignment.objects.filter(
                    user=created_user,
                    permission__code="categories.view",
                    is_allowed=True,
                ).exists()
            )
