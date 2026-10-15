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

COUNTRY_PREFIXES = [
    ('+54', 'Argentina (+54)'),
    ('+56', 'Chile (+56)'),
    ('+598', 'Uruguay (+598)'),
    ('+595', 'Paraguay (+595)'),
    ('+51', 'Perú (+51)'),
    ('+57', 'Colombia (+57)'),
    ('+52', 'México (+52)'),
    ('+58', 'Venezuela (+58)'),
    ('+34', 'España (+34)'),
    ('+1', 'EE.UU. / Canadá (+1)'),
    ('+55', 'Brasil (+55)'),
    ('+591', 'Bolivia (+591)'),
    ('+593', 'Ecuador (+593)'),
    ('+507', 'Panamá (+507)'),
    ('+506', 'Costa Rica (+506)'),
    ('+502', 'Guatemala (+502)'),
    ('+503', 'El Salvador (+503)'),
    ('+504', 'Honduras (+504)'),
    ('+505', 'Nicaragua (+505)'),
    ('+1809', 'Rep. Dominicana (+1809)'),
    ('+1829', 'Rep. Dominicana (+1829)'),
    ('+1849', 'Rep. Dominicana (+1849)'),
    ('+592', 'Guyana (+592)'),
    ('+597', 'Surinam (+597)'),
]

def split_phone_number(phone_str, default_prefix='+54'):
    if not phone_str:
        return default_prefix, ''
    phone_clean = str(phone_str).strip()
    sorted_prefixes = sorted([p[0] for p in COUNTRY_PREFIXES], key=len, reverse=True)
    for p in sorted_prefixes:
        if phone_clean.startswith(p):
            return p, phone_clean[len(p):].strip()
    return default_prefix, phone_clean

def format_phone_with_prefix(prefix, number, default_prefix='+54'):
    prefix = (prefix or default_prefix).strip()
    if not prefix.startswith('+'):
        prefix = f"+{prefix}"
    number = (number or '').strip()
    if not number:
        return ''
    if number.startswith('+'):
        return number
    clean_num = ''.join(filter(str.isdigit, number))
    if not clean_num:
        return ''
    return f"{prefix}{clean_num}"
