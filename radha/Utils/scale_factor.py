import re

def parse_quantity(qty_string):
    """
    Convert '100g' → (100, 'g')
    Convert '2kg' → (2, 'kg')
    """
    match = re.match(r"([\d.]+)\s*(\D+)", qty_string.strip().lower())
    if not match:
        return 0, ""
    return float(match.group(1)), match.group(2)


def convert_unit(value, unit):
    """
    Auto convert:
    1000g -> 1kg
    1000ml -> 1liter
    """

    if unit == "g":
        if value >= 1000:
            return round(value / 1000, 2), "kg"
        return round(value, 2), "g"

    if unit == "ml":
        if value >= 1000:
            return round(value / 1000, 2), "liter"
        return round(value, 2), "ml"

    # already kg or liter
    return round(value, 2), unit