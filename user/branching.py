from django.db import connection


def ensure_main_branch_profile(tenant=None, admin_user=None):
    from user.models import BranchProfile, BusinessProfile

    branch = BranchProfile.objects.filter(is_main=True).first()
    if branch is None:
        branch = BranchProfile.objects.order_by("id").first()
        if branch is not None and not branch.is_main:
            branch.is_main = True
            branch.save(update_fields=["is_main", "updated_at"])

    if branch is None:
        profile = BusinessProfile.objects.order_by("id").first()
        branch_name = (
            getattr(profile, "caters_name", "")
            or getattr(tenant, "name", "")
            or "Main Branch"
        )
        phone_number = (
            getattr(profile, "phone_number", "")
            or getattr(tenant, "contact_phone", "")
            or ""
        )
        branch = BranchProfile.objects.create(
            name=branch_name[:150],
            branch_code="main",
            phone_number=phone_number[:20],
            is_main=True,
            manager=admin_user if getattr(admin_user, "is_authenticated", True) else None,
            created_by=admin_user if getattr(admin_user, "is_authenticated", True) else None,
        )

    if admin_user is not None and getattr(connection, "schema_name", "public") != "public":
        update_fields = []
        if getattr(admin_user, "branch_profile_id", None) is None:
            admin_user.branch_profile = branch
            update_fields.append("branch_profile")

        if update_fields:
            admin_user.save(update_fields=update_fields)

        if branch.manager_id is None:
            branch.manager = admin_user
            branch.save(update_fields=["manager", "updated_at"])

    return branch
