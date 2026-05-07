from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import tenant_context

from tenancy.models import Domain
from tenancy.utils import build_tenant_domain, normalize_tenant_domain


def _iter_domain_inputs(domain="", domains=None):
    if domains is not None:
        if not isinstance(domains, list):
            raise ValueError("Domains must be a list.")

        for item in domains:
            if isinstance(item, str):
                yield {"domain": item, "is_primary": False}
                continue
            if not isinstance(item, dict):
                raise ValueError("Each domain must be an object or string.")
            yield {
                "domain": item.get("domain", ""),
                "is_primary": bool(item.get("is_primary", False)),
            }
        return

    if domain:
        yield {"domain": domain, "is_primary": True}


def build_tenant_domain_rows(schema_name, domain="", domains=None):
    rows = []
    for item in _iter_domain_inputs(domain=domain, domains=domains):
        normalized_domain = normalize_tenant_domain(item["domain"])
        if not normalized_domain:
            continue
        rows.append(
            {
                "domain": normalized_domain,
                "is_primary": item["is_primary"],
            }
        )

    if not rows:
        rows.append(
            {
                "domain": build_tenant_domain(schema_name),
                "is_primary": True,
            }
        )

    seen_domains = set()
    for row in rows:
        if row["domain"] in seen_domains:
            raise ValueError(f"Duplicate domain '{row['domain']}' in request.")
        seen_domains.add(row["domain"])

    primary_seen = False
    for row in rows:
        if row["is_primary"] and not primary_seen:
            primary_seen = True
        else:
            row["is_primary"] = False
    if not primary_seen:
        rows[0]["is_primary"] = True

    return rows


def validate_tenant_domain_rows(rows, tenant=None):
    domains = [row["domain"] for row in rows]
    duplicate_query = Domain.objects.filter(domain__in=domains)
    if tenant is not None:
        duplicate_query = duplicate_query.exclude(tenant=tenant)

    duplicate = duplicate_query.order_by("domain").first()
    if duplicate is not None:
        raise ValueError(f"Domain '{duplicate.domain}' is already assigned.")


def create_tenant_domains(tenant, domain="", domains=None):
    rows = build_tenant_domain_rows(
        schema_name=tenant.schema_name,
        domain=domain,
        domains=domains,
    )
    validate_tenant_domain_rows(rows)
    return [Domain.objects.create(tenant=tenant, **row) for row in rows]


def replace_tenant_domains(tenant, domain="", domains=None):
    rows = build_tenant_domain_rows(
        schema_name=tenant.schema_name,
        domain=domain,
        domains=domains,
    )
    validate_tenant_domain_rows(rows, tenant=tenant)
    Domain.objects.filter(tenant=tenant).delete()
    return [Domain.objects.create(tenant=tenant, **row) for row in rows]


def create_tenant_admin_user(tenant, admin_data):
    if not admin_data:
        return None

    with tenant_context(tenant):
        if getattr(connection, "schema_name", "public") != tenant.schema_name:
            raise RuntimeError("Tenant admin user creation did not enter tenant schema.")

        username = admin_data["username"]
        UserModel = get_user_model()
        if UserModel.objects.filter(username=username).exists():
            raise ValueError("Username already exists in this tenant.")

        user = UserModel.objects.create_user(
            username=username,
            email=admin_data.get("email", ""),
            password=admin_data["password"],
            first_name=admin_data.get("first_name", ""),
            last_name=admin_data.get("last_name", ""),
            is_active=True,
            is_staff=True,
            is_superuser=admin_data.get("is_superuser", False),
        )
        from user.branching import ensure_main_branch_profile

        ensure_main_branch_profile(tenant=tenant, admin_user=user)
        return user
