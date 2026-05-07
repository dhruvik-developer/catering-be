from django.db import connection
from rest_framework.exceptions import PermissionDenied


BRANCH_QUERY_PARAM_NAMES = ("branch_profile_id", "branch_id", "branch")


def is_tenant_schema():
    return getattr(connection, "schema_name", "public") != "public"


def is_main_tenant_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return bool(
        user.is_staff
        and getattr(user, "branch_role", "") == "main_admin"
    )


def is_branch_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if is_main_tenant_admin(user):
        return True
    return bool(
        user.is_staff
        and getattr(user, "branch_role", "") == "branch_admin"
        and getattr(user, "branch_profile_id", None)
    )


def get_request_branch_id(request):
    for param_name in BRANCH_QUERY_PARAM_NAMES:
        value = request.query_params.get(param_name)
        if value not in (None, ""):
            return value
    return None


def get_payload_branch_id(data):
    for field_name in ("branch_profile_id", "branch_profile", "branch_id", "branch"):
        value = data.get(field_name) if hasattr(data, "get") else None
        if value not in (None, ""):
            return value
    return None


def get_payload_branch(data):
    branch_id = get_payload_branch_id(data)
    if not branch_id:
        return None

    from user.models import BranchProfile

    try:
        return BranchProfile.objects.get(id=branch_id, is_active=True)
    except BranchProfile.DoesNotExist as exc:
        raise PermissionDenied("Branch profile not found or inactive.") from exc


def get_write_branch(request, requested_branch=None):
    if not is_tenant_schema():
        return None

    if is_main_tenant_admin(request.user):
        return requested_branch or getattr(request.user, "branch_profile", None)

    user_branch = getattr(request.user, "branch_profile", None)
    if user_branch is None:
        raise PermissionDenied("You are not assigned to a branch.")

    if requested_branch is not None and requested_branch.id != user_branch.id:
        raise PermissionDenied("You can create data only for your own branch.")

    return user_branch


def get_branch_save_kwargs(request, field_name="branch_profile", requested_branch=None):
    if requested_branch is None:
        requested_branch = get_payload_branch(getattr(request, "data", {}))
    branch = get_write_branch(request, requested_branch=requested_branch)
    return {field_name: branch} if branch is not None else {}


def filter_branch_queryset(queryset, request, field_name="branch_profile"):
    if not is_tenant_schema():
        return queryset

    if is_main_tenant_admin(request.user):
        requested_branch_id = get_request_branch_id(request)
        if requested_branch_id:
            return queryset.filter(**{f"{field_name}_id": requested_branch_id})
        return queryset

    branch_id = getattr(request.user, "branch_profile_id", None)
    if not branch_id:
        return queryset.none()
    return queryset.filter(**{f"{field_name}_id": branch_id})


def ensure_object_in_user_branch(obj, request, field_name="branch_profile"):
    if not is_tenant_schema() or is_main_tenant_admin(request.user):
        return

    branch_id = getattr(request.user, "branch_profile_id", None)
    obj_branch_id = getattr(obj, f"{field_name}_id", None)
    if not branch_id or obj_branch_id != branch_id:
        raise PermissionDenied("You can access only your own branch data.")


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
        had_no_branch = getattr(admin_user, "branch_profile_id", None) is None
        if had_no_branch:
            admin_user.branch_profile = branch
            update_fields.append("branch_profile")
        if had_no_branch and getattr(admin_user, "branch_role", "") != "main_admin":
            admin_user.branch_role = "main_admin"
            update_fields.append("branch_role")

        if update_fields:
            admin_user.save(update_fields=update_fields)

        if branch.manager_id is None:
            branch.manager = admin_user
            branch.save(update_fields=["manager", "updated_at"])

    return branch
