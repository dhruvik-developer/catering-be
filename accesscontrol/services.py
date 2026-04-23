from accesscontrol.catalog import build_permission_catalog, iter_catalog_permissions
from accesscontrol.models import AccessPermission, PermissionModule


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
    AccessPermission.objects.exclude(code__in=active_permission_codes).filter(
        user_assignments__isnull=True,
        staff_role_assignments__isnull=True,
    ).delete()
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
