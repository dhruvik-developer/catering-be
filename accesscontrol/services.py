from django.apps import apps
from django.db import connection

from accesscontrol.catalog import build_permission_catalog, iter_catalog_permissions
from accesscontrol.models import AccessPermission, PermissionModule


def _table_exists(model):
    return model._meta.db_table in connection.introspection.table_names()


def _raw_delete_by_ids(model, ids):
    ids = list(ids)
    if not ids:
        return

    table = connection.ops.quote_name(model._meta.db_table)
    pk_column = connection.ops.quote_name(model._meta.pk.column)
    placeholders = ", ".join(["%s"] * len(ids))
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {table} WHERE {pk_column} IN ({placeholders})",
            ids,
        )


def _delete_unassigned_stale_permissions(active_permission_codes):
    stale_permissions = AccessPermission.objects.exclude(
        code__in=active_permission_codes
    ).filter(user_assignments__isnull=True)

    StaffRolePermissionAssignment = apps.get_model(
        "eventstaff",
        "StaffRolePermissionAssignment",
    )
    if _table_exists(StaffRolePermissionAssignment):
        stale_permissions.filter(staff_role_assignments__isnull=True).delete()
        return

    # In the public schema, tenant-only eventstaff tables do not exist. Avoid
    # Django's delete collector touching that missing reverse relation.
    _raw_delete_by_ids(
        AccessPermission,
        stale_permissions.values_list("id", flat=True),
    )


def sync_permission_catalog(catalog=None):
    catalog_rows = catalog if catalog is not None else build_permission_catalog()

    active_module_codes = set()
    active_permission_codes = set()

    for row in iter_catalog_permissions(catalog_rows):
        active_module_codes.add(row["module_code"])
        active_permission_codes.add(row["permission_code"])

        module, _ = PermissionModule.objects.update_or_create(
            code=row["module_code"],
            defaults={
                "name": row["module_name"],
                "description": row["module_description"],
                "sort_order": row["module_sort_order"],
                "is_active": True,
            },
        )
        AccessPermission.objects.update_or_create(
            code=row["permission_code"],
            defaults={
                "module": module,
                "action": row["permission_action"],
                "name": row["permission_name"],
                "description": row["permission_description"],
                "sort_order": row["permission_sort_order"],
                "is_active": True,
            },
        )

    # Stale permissions with no assignments get deleted (prevents duplicate
    # codes from previous catalog versions piling up in the DB). Stale
    # permissions that ARE referenced by assignments stay, marked inactive,
    # so history is preserved.
    _delete_unassigned_stale_permissions(active_permission_codes)
    AccessPermission.objects.exclude(code__in=active_permission_codes).update(
        is_active=False
    )

    PermissionModule.objects.exclude(code__in=active_module_codes).filter(
        permissions__isnull=True,
    ).delete()
    PermissionModule.objects.exclude(code__in=active_module_codes).update(is_active=False)

    return {
        "active_modules": len(active_module_codes),
        "active_permissions": len(active_permission_codes),
    }
