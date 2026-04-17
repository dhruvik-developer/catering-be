import re
from decimal import Decimal, InvalidOperation


WEIGHT_UNITS = {"KG", "G"}
LIQUID_UNITS = {"L", "ML"}


def normalize_unit(unit):
    return str(unit or "").strip().upper()


def get_unit_type(unit):
    normalized = normalize_unit(unit)
    if normalized in WEIGHT_UNITS:
        return "weight"
    if normalized in LIQUID_UNITS:
        return "liquid"
    return "other"


def to_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def to_base_unit(value, unit):
    amount = to_decimal(value)
    normalized = normalize_unit(unit)
    if normalized in {"KG", "L"}:
        return amount * Decimal("1000")
    return amount


def from_base_unit(value, unit_type):
    amount = to_decimal(value)
    if unit_type in {"weight", "liquid"}:
        return amount / Decimal("1000")
    return amount


def to_storage_unit(unit):
    unit_type = get_unit_type(unit)
    if unit_type == "weight":
        return "G"
    if unit_type == "liquid":
        return "ML"
    return normalize_unit(unit)


def normalize_quantity_unit(value, unit):
    normalized = normalize_unit(unit)
    return to_base_unit(value, normalized), to_storage_unit(normalized)


def to_readable_quantity_unit(value, stored_unit):
    normalized = normalize_unit(stored_unit)
    unit_type = get_unit_type(normalized)
    readable_value = from_base_unit(value, unit_type)

    if unit_type == "weight":
        return readable_value, "KG"
    if unit_type == "liquid":
        return readable_value, "L"
    return to_decimal(value), normalized


def default_display_unit(stored_unit):
    normalized = normalize_unit(stored_unit)
    if normalized == "G":
        return "KG"
    if normalized == "ML":
        return "L"
    return normalized


def parse_threshold_to_base(alert_text, fallback_unit=""):
    match = re.search(r"([-+]?\d*\.?\d+)\s*([a-zA-Z]+)?", str(alert_text or "").strip())
    if not match:
        return Decimal("0")

    value = to_decimal(match.group(1))
    unit = normalize_unit(match.group(2) or fallback_unit)
    return to_base_unit(value, unit)


def to_number(value, digits=4):
    amount = float(to_decimal(value))
    if amount.is_integer():
        return int(amount)
    return round(amount, digits)
