from accesscontrol.catalog import iter_catalog_permissions
from accesscontrol.models import AccessPermission, PermissionModule


def sync_permission_catalog():
    for row in iter_catalog_permissions():
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
