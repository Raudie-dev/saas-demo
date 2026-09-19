from decimal import Decimal, InvalidOperation

def parse_decimal(value, default="0.00"):
    """
    Safely parse a string or number into a Decimal.
    Returns Decimal(default) if value is empty, invalid, or None.
    Normalizes ',' to '.' for Spanish locale decimal inputs.
    """
    if value is None:
        return Decimal(str(default))
    val_str = str(value).strip().replace(',', '.')
    if not val_str:
        return Decimal(str(default))
    try:
        return Decimal(val_str)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))

def parse_int(value, default=0):
    """
    Safely parse a value into an integer.
    Returns default if value is empty, invalid, or None.
    """
    if value is None:
        return default
    val_str = str(value).strip()
    if not val_str:
        return default
    try:
        return int(val_str)
    except (TypeError, ValueError):
        return default
