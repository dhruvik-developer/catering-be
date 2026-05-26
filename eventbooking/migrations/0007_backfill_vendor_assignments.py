# Data migration: walks existing EventSession rows and creates the matching
# EventVendorAssignment rows so vendors who log in after this lands can see
# bookings that were created BEFORE the vendor workflow was introduced.
#
# Idempotent — uses get_or_create — so re-running the migrate command (e.g.
# during a tenant data sync) won't double-insert.
from django.db import migrations


def _vendor_ids_from_session(session):
    vendor_ids = set()

    assigned = session.assigned_vendors or {}
    if isinstance(assigned, dict):
        for entry in assigned.values():
            if isinstance(entry, dict):
                raw = entry.get("id") or entry.get("vendor_id")
                if raw is not None:
                    try:
                        vendor_ids.add(int(raw))
                    except (TypeError, ValueError):
                        pass

    outsourced = session.outsourced_items or []
    if isinstance(outsourced, list):
        for item in outsourced:
            if isinstance(item, dict):
                vend = item.get("vendor")
                if isinstance(vend, dict):
                    raw = vend.get("id") or vend.get("vendor_id")
                    if raw is not None:
                        try:
                            vendor_ids.add(int(raw))
                        except (TypeError, ValueError):
                            pass

    # Relational source — covers ingredient-vendor assignments admins set
    # via the dedicated endpoint instead of the JSON blob.
    try:
        ids = session.ingredient_vendor_assignments.values_list(
            "vendor_id", flat=True
        )
        vendor_ids.update(int(v) for v in ids if v is not None)
    except Exception:
        pass

    return vendor_ids


def backfill(apps, schema_editor):
    EventSession = apps.get_model("eventbooking", "EventSession")
    EventVendorAssignment = apps.get_model("eventbooking", "EventVendorAssignment")
    Vendor = apps.get_model("vendor", "Vendor")

    valid_vendor_ids = set(Vendor.objects.values_list("id", flat=True))
    for session in EventSession.objects.iterator():
        for vendor_id in _vendor_ids_from_session(session):
            if vendor_id not in valid_vendor_ids:
                continue
            EventVendorAssignment.objects.get_or_create(
                session_id=session.id,
                vendor_id=vendor_id,
            )


def noop_reverse(apps, schema_editor):
    # No reverse migration — rows created here are indistinguishable from
    # rows the runtime creates, and the table-drop in 0006 handles the
    # rollback if anyone needs to unmigrate that far.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("eventbooking", "0006_event_vendor_assignment"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
