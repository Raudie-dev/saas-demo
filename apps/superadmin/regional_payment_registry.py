"""
apps/superadmin/regional_payment_registry.py

Catálogo Centralizado y Sistema de Anclaje Multi-Región de Métodos de Pago.

Arquitectura:
1. Catálogo Maestro de Desarrollos (PAYMENT_METHOD_CATALOG):
   Guarda de forma independiente y autónoma el desarrollo de cada método de pago:
   sus campos estructurados para copiado individual (1 clic), códigos QR recortados,
   instrucciones, badges, configuración de pasarela y datos bancarios reales.

2. Sistema de Anclaje Multi-Región (REGIONAL_METHOD_ANCHORS):
   Permite anclar cada desarrollo a múltiples regiones (ej: Binance Pay a VE, AR, CL, CO, etc.;
   Mercado Pago a AR, CL, UY, MX, etc.; Transferencia Internacional a GLOBAL, etc.).

3. Fusión Inteligente con Base de Datos (RegionPaymentMethod):
   Cuando un Superadmin ancla un método a una región desde el panel de SuperAdmin,
   el sistema hereda automáticamente todo el desarrollo del catálogo (QR, copiado 1 a 1),
   preservando cualquier instrucción o enlace personalizado que se haya guardado.
"""
import os
import re
from types import SimpleNamespace
from django.conf import settings


def parse_instructions_into_fields(instructions_text, region_code='GLOBAL'):
    """
    Convierte cualquier bloque de texto de instrucciones bancarias
    (separadas por dos puntos ':' o viñetas '•') en una lista de campos
    estructurados con indicador de copiado individual (can_copy, copy_value).

    Reglas de negocio:
    - Alias, CVU, CBU, Cuenta, Cédula, Teléfono, Correo/Email, Banco son copiables (can_copy=True).
    - Titular, Nombre, Billetera, Moneda, Tasa BCV NO son copiables (can_copy=False).
    - Para Cédula se extrae solo el número limpio (sin 'V-' ni guiones).
    - Para Teléfono y Cuentas se limpia para facilitar el pegado en banca móvil.
    - Para Banco BNC con código se extrae el código '0191' como copy_value preferente.
    """
    if not instructions_text:
        return []

    lines = str(instructions_text).splitlines()
    fields = []

    for raw_line in lines:
        line = raw_line.strip().lstrip('•-* \t')
        if not line or ':' not in line:
            continue

        label_part, _, val_part = line.partition(':')
        label = label_part.strip()
        val = val_part.strip()
        if not label or not val:
            continue

        label_lower = label.lower()

        # Determinación de campos que NO deben tener botón de copiar
        no_copy_keywords = ('titular', 'nombre', 'billetera', 'moneda', 'tasa', 'tipo', 'concepto', 'nota')
        is_no_copy = any(k in label_lower for k in no_copy_keywords)

        can_copy = not is_no_copy
        copy_val = val

        if can_copy:
            if 'cedula' in label_lower or 'cédula' in label_lower or 'rif' in label_lower or 'dni' in label_lower or 'cuit' in label_lower:
                # Extraer números limpios para la banca online
                clean_num = re.sub(r'[^0-9]', '', val)
                copy_val = clean_num if clean_num else val
            elif 'telefono' in label_lower or 'teléfono' in label_lower:
                clean_tel = re.sub(r'[^0-9]', '', val)
                copy_val = clean_tel if clean_tel else val
            elif 'cuenta' in label_lower or 'cvu' in label_lower or 'cbu' in label_lower:
                clean_acc = val.replace('-', '').replace(' ', '').strip()
                copy_val = clean_acc if clean_acc else val
            elif 'banco' in label_lower:
                # Si contiene un código como (Código 0191), extraerlo para banca móvil
                code_match = re.search(r'0\d{3}', val)
                if code_match:
                    copy_val = code_match.group(0)
                else:
                    copy_val = val
            elif 'correo' in label_lower or 'email' in label_lower or 'alias' in label_lower:
                copy_val = val.strip()

        fields.append({
            'label': label,
            'value': val,
            'copy_value': copy_val if can_copy else '',
            'can_copy': can_copy,
        })

    return fields


class CodeGatewayInfo:
    """Emula el objeto gateway esperado por los templates."""
    def __init__(self, provider, button_label):
        self.provider = provider
        self.button_label = button_label

    def __getitem__(self, item):
        return getattr(self, item, '')


class CodePaymentMethod:
    """
    Objeto adaptador que representa un método de pago registrado por código.
    Compatible con las plantillas de Django que acceden a atributos como:
    .id, .code, .name, .type, .instructions, .payment_url, .payment_method, .gateway, .qr_image, .fields, .fields_json
    """
    def __init__(
        self,
        code,
        name,
        method_type,
        instructions="",
        provider="",
        button_label="",
        payment_url="",
        badge="",
        region_code="",
        qr_image="",
        fields=None,
    ):
        self.id = code
        self.code = code
        self.name = name
        self.type = method_type  # 'GATEWAY' o 'MANUAL'
        self.instructions = (instructions or "").strip()
        self.provider = provider
        self.payment_url = payment_url
        self.badge = badge
        self.region_code = region_code
        self.qr_image = qr_image
        
        # Si no se suministran campos estructurados pero hay instrucciones con ':',
        # parseamos automáticamente para garantizar copiado 1 a 1 y visualización limpia.
        if fields:
            self.fields = fields
        elif self.instructions and ':' in self.instructions:
            self.fields = parse_instructions_into_fields(self.instructions, self.region_code)
        else:
            self.fields = []

        self.is_active = True

        # Compatibilidad con accesos en plantillas: rm.payment_method.name / rm.payment_method.code
        self.payment_method = self

        # Si es pasarela (GATEWAY), emulamos el objeto gm.gateway
        if self.type == 'GATEWAY':
            label = button_label or f"Pagar con {self.name}"
            self.gateway = CodeGatewayInfo(provider=provider, button_label=label)
        else:
            self.gateway = None

    @property
    def fields_json(self):
        import json
        return json.dumps(self.fields)

    def clone_for_region(self, region_code="", custom_instructions=None, custom_payment_url=None, custom_badge=None):
        """
        Crea una copia del desarrollo de este método para anclarlo a una región específica,
        permitiendo sobreescribir instrucciones o enlaces si la región lo requiere.
        """
        target_instructions = custom_instructions if custom_instructions is not None else self.instructions
        if custom_instructions is not None and custom_instructions != self.instructions:
            parsed = parse_instructions_into_fields(target_instructions, region_code or self.region_code)
            fields_copy = parsed if parsed else [dict(f) for f in self.fields]
        else:
            fields_copy = [dict(f) for f in self.fields]

        return CodePaymentMethod(
            code=self.code,
            name=self.name,
            method_type=self.type,
            instructions=target_instructions,
            provider=self.provider,
            button_label=self.gateway.button_label if self.gateway else '',
            payment_url=custom_payment_url if custom_payment_url is not None else self.payment_url,
            badge=custom_badge if custom_badge is not None else self.badge,
            region_code=region_code or self.region_code,
            qr_image=self.qr_image,
            fields=fields_copy,
        )

    def __str__(self):
        return f"{self.name} ({self.code})"

    def __repr__(self):
        return f"<CodePaymentMethod {self.code} - {self.type}>"


# ---------------------------------------------------------------------------
# DATOS BANCARIOS REALES DEL SISTEMA
# ---------------------------------------------------------------------------

# ARGENTINA (Mercado Pago Pesos)
ALIAS_ARGENTINA = getattr(settings, 'SUBSCRIPTION_ALIAS_AR', os.getenv('SUBSCRIPTION_ALIAS_AR', 'isabella.deabreu'))
CVU_ARGENTINA = getattr(settings, 'SUBSCRIPTION_CVU_AR', os.getenv('SUBSCRIPTION_CVU_AR', '0000003100066158325774'))
TITULAR_ARGENTINA = getattr(settings, 'SUBSCRIPTION_TITULAR_AR', os.getenv('SUBSCRIPTION_TITULAR_AR', 'Raulymar De Abreu'))
BANCO_ARGENTINA = getattr(settings, 'SUBSCRIPTION_BANCO_AR', os.getenv('SUBSCRIPTION_BANCO_AR', 'Mercado Pago'))

# VENEZUELA (BNC Pago Móvil y Cuenta)
PAGOMOVIL_BANCO = getattr(settings, 'SUBSCRIPTION_PM_BANCO_VE', os.getenv('SUBSCRIPTION_PM_BANCO_VE', 'Banco Nacional de Crédito (BNC - 0191)'))
PAGOMOVIL_TELEFONO = getattr(settings, 'SUBSCRIPTION_PM_TELEFONO_VE', os.getenv('SUBSCRIPTION_PM_TELEFONO_VE', '0412-7360431'))
PAGOMOVIL_CEDULA = getattr(settings, 'SUBSCRIPTION_PM_CEDULA_VE', os.getenv('SUBSCRIPTION_PM_CEDULA_VE', 'V-31473363'))
PAGOMOVIL_CUENTA = getattr(settings, 'SUBSCRIPTION_PM_CUENTA_VE', os.getenv('SUBSCRIPTION_PM_CUENTA_VE', '0191-0025-11-2125078240'))
PAGOMOVIL_TITULAR = getattr(settings, 'SUBSCRIPTION_PM_TITULAR_VE', os.getenv('SUBSCRIPTION_PM_TITULAR_VE', 'Raulymar De Abreu'))

# BINANCE PAY & CRYPTO
BINANCE_EMAIL = getattr(settings, 'SUBSCRIPTION_BINANCE_EMAIL', os.getenv('SUBSCRIPTION_BINANCE_EMAIL', 'raudie.dev@gmail.com'))
BINANCE_USER = getattr(settings, 'SUBSCRIPTION_BINANCE_USER', os.getenv('SUBSCRIPTION_BINANCE_USER', 'RauDie Web Developpers'))

# INTERNACIONAL / SOPORTE
SOPORTE_EMAIL = getattr(settings, 'SUBSCRIPTION_SUPPORT_EMAIL', os.getenv('SUBSCRIPTION_SUPPORT_EMAIL', 'raudie.dev@gmail.com'))
SOPORTE_TITULAR = getattr(settings, 'SUBSCRIPTION_SUPPORT_TITULAR', os.getenv('SUBSCRIPTION_SUPPORT_TITULAR', 'RauDie Web Developers'))


# ---------------------------------------------------------------------------
# CATÁLOGO MAESTRO DE MÉTODOS DE PAGO DESARROLLADOS
# Guarda el desarrollo completo de cada método listo para ser anclado
# ---------------------------------------------------------------------------

PAYMENT_METHOD_CATALOG = {
    # 1. MERCADO PAGO (Pasarela Online Automática)
    'MERCADOPAGO': CodePaymentMethod(
        code='MERCADOPAGO',
        name='Mercado Pago',
        method_type='GATEWAY',
        provider='MERCADOPAGO',
        button_label='Pagar con Mercado Pago',
        badge='Acreditación Inmediata',
        instructions='Pago seguro e instantáneo con tarjeta de débito/crédito, dinero en cuenta de Mercado Pago o medios locales. Tu licencia se activa de forma automática al confirmarse.',
        fields=[],
    ),

    # 2. TRANSFERENCIA BANCARIA / ALIAS (Argentina)
    'ALIAS_CBU': CodePaymentMethod(
        code='ALIAS_CBU',
        name='Transferencia Bancaria / Alias',
        method_type='MANUAL',
        badge='Transferencia ARS',
        instructions=(
            f"• Alias: {ALIAS_ARGENTINA}\n"
            f"• CVU: {CVU_ARGENTINA}\n"
            f"• Billetera / Banco: {BANCO_ARGENTINA}\n"
            f"• Titular: {TITULAR_ARGENTINA}"
        ),
        fields=[
            {'label': 'Alias', 'value': ALIAS_ARGENTINA, 'copy_value': ALIAS_ARGENTINA, 'can_copy': True},
            {'label': 'CVU', 'value': CVU_ARGENTINA, 'copy_value': CVU_ARGENTINA, 'can_copy': True},
            {'label': 'Titular', 'value': TITULAR_ARGENTINA, 'copy_value': '', 'can_copy': False},
            {'label': 'Billetera / Banco', 'value': BANCO_ARGENTINA, 'copy_value': '', 'can_copy': False},
        ],
    ),

    # 3. PAGO MÓVIL BNC (Venezuela)
    'PAGOMOVIL': CodePaymentMethod(
        code='PAGOMOVIL',
        name='Pago Móvil (BNC al Instante)',
        method_type='MANUAL',
        badge='Pago Móvil Bs.',
        qr_image='/static/images/qr/pagomovil_bnc_qr.jpg',
        instructions=(
            f"• Banco: {PAGOMOVIL_BANCO}\n"
            f"• Teléfono: {PAGOMOVIL_TELEFONO}\n"
            f"• Cédula: {PAGOMOVIL_CEDULA}\n"
            f"• Titular: {PAGOMOVIL_TITULAR}\n"
            f"• Moneda: Bolívares (Bs.)"
        ),
        fields=[
            {'label': 'Banco', 'value': 'Banco BNC (Código 0191)', 'copy_value': '0191', 'can_copy': True},
            {'label': 'Teléfono', 'value': PAGOMOVIL_TELEFONO, 'copy_value': PAGOMOVIL_TELEFONO.replace('-', ''), 'can_copy': True},
            {'label': 'Cédula', 'value': PAGOMOVIL_CEDULA, 'copy_value': PAGOMOVIL_CEDULA.replace('V-', '').replace('V', '').replace('-', ''), 'can_copy': True},
            {'label': 'Titular', 'value': PAGOMOVIL_TITULAR, 'copy_value': '', 'can_copy': False},
        ],
    ),

    # 4. TRANSFERENCIA BANCARIA BNC Bs. (Venezuela)
    'TRANSFERENCIA_BS': CodePaymentMethod(
        code='TRANSFERENCIA_BS',
        name='Transferencia Bancaria BNC (Bs.)',
        method_type='MANUAL',
        badge='Transferencia Nacional',
        instructions=(
            f"• Banco: {PAGOMOVIL_BANCO}\n"
            f"• Cuenta Corriente: {PAGOMOVIL_CUENTA}\n"
            f"• Cédula: {PAGOMOVIL_CEDULA}\n"
            f"• Titular: {PAGOMOVIL_TITULAR}\n"
            f"• Moneda: Bolívares (Bs.)"
        ),
        fields=[
            {'label': 'Banco', 'value': 'Banco BNC (Código 0191)', 'copy_value': '0191', 'can_copy': True},
            {'label': 'Cuenta Corriente', 'value': PAGOMOVIL_CUENTA, 'copy_value': PAGOMOVIL_CUENTA.replace('-', ''), 'can_copy': True},
            {'label': 'Cédula', 'value': PAGOMOVIL_CEDULA, 'copy_value': PAGOMOVIL_CEDULA.replace('V-', '').replace('V', '').replace('-', ''), 'can_copy': True},
            {'label': 'Titular', 'value': PAGOMOVIL_TITULAR, 'copy_value': '', 'can_copy': False},
        ],
    ),

    # 5. BINANCE PAY (USDT / Cripto)
    'BINANCE_PAY': CodePaymentMethod(
        code='BINANCE_PAY',
        name='Binance Pay / USDT',
        method_type='MANUAL',
        badge='Cripto / USDT',
        qr_image='/static/images/qr/binance_pay_qr.jpg',
        instructions=(
            f"• Correo Binance: {BINANCE_EMAIL}\n"
            f"• Nombre en Binance: {BINANCE_USER}\n"
            f"• Moneda: USDT"
        ),
        fields=[
            {'label': 'Correo Binance Pay', 'value': BINANCE_EMAIL, 'copy_value': BINANCE_EMAIL, 'can_copy': True},
            {'label': 'Nombre en Binance', 'value': BINANCE_USER, 'copy_value': '', 'can_copy': False},
        ],
    ),

    # 6. TRANSFERENCIA BANCARIA INTERNACIONAL (Global / Swift)
    'TRANSFERENCIA_INTL': CodePaymentMethod(
        code='TRANSFERENCIA_INTL',
        name='Transferencia Bancaria Internacional',
        method_type='MANUAL',
        badge='Swift / Transferencia',
        instructions=(
            f"• Titular: {SOPORTE_TITULAR}\n"
            f"• Contacto: {SOPORTE_EMAIL}"
        ),
        fields=[
            {'label': 'Titular', 'value': SOPORTE_TITULAR, 'copy_value': '', 'can_copy': False},
            {'label': 'Correo de Contacto', 'value': SOPORTE_EMAIL, 'copy_value': SOPORTE_EMAIL, 'can_copy': True},
        ],
    ),
}


# ---------------------------------------------------------------------------
# ANCLAJE DE MÉTODOS A MÚLTIPLES REGIONES
# Mapeo que define qué métodos del catálogo están anclados a cada región
# ---------------------------------------------------------------------------

REGIONAL_METHOD_ANCHORS = {
    # ARGENTINA (54 / AR): Mercado Pago y Alias/CVU
    'AR': ['MERCADOPAGO', 'ALIAS_CBU'],

    # VENEZUELA (58 / VE): Pago Móvil BNC, Transferencia BNC, Binance Pay
    'VE': ['PAGOMOVIL', 'TRANSFERENCIA_BS', 'BINANCE_PAY'],

    # CHILE (56 / CL): Mercado Pago y Binance Pay
    'CL': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # URUGUAY (598 / UY): Mercado Pago y Binance Pay
    'UY': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # COLOMBIA (57 / CO): Mercado Pago y Binance Pay
    'CO': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # MÉXICO (52 / MX): Mercado Pago y Binance Pay
    'MX': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # PERÚ (51 / PE): Mercado Pago y Binance Pay
    'PE': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # BRASIL (55 / BR): Mercado Pago y Binance Pay
    'BR': ['MERCADOPAGO', 'BINANCE_PAY', 'TRANSFERENCIA_INTL'],

    # GLOBAL / RESTO DEL MUNDO (Fallback transversal)
    'GLOBAL': ['BINANCE_PAY', 'TRANSFERENCIA_INTL'],
}


# ---------------------------------------------------------------------------
# FUNCIONES DE GESTIÓN Y ANCLAJE MULTI-REGIÓN
# ---------------------------------------------------------------------------

def normalize_region_key(region):
    """
    Normaliza el objeto Region, código o nombre a una clave regional estándar:
    'AR', 'VE', 'CL', 'UY', 'CO', 'MX', 'PE', 'BR', 'GLOBAL', etc.
    """
    if not region:
        return 'AR'

    if isinstance(region, str):
        raw = region.strip().upper()
        name_raw = raw
    else:
        raw = (getattr(region, 'code', '') or '').strip().upper()
        country_codes = (getattr(region, 'country_codes', '') or '').strip().upper()
        name_raw = (getattr(region, 'name', '') or '').strip().upper()
        if country_codes:
            raw_codes = [c.strip() for c in country_codes.replace(';', ',').split(',') if c.strip()]
            for rc in raw_codes:
                if rc in REGIONAL_METHOD_ANCHORS:
                    return rc

    if raw in ('54', 'AR') or 'ARGENTINA' in name_raw:
        return 'AR'
    if raw in ('58', 'VE') or 'VENEZUELA' in name_raw:
        return 'VE'
    if raw in ('56', 'CL') or 'CHILE' in name_raw:
        return 'CL'
    if raw in ('598', 'UY') or 'URUGUAY' in name_raw:
        return 'UY'
    if raw in ('57', 'CO') or 'COLOMBIA' in name_raw:
        return 'CO'
    if raw in ('52', 'MX') or 'MEXICO' in name_raw or 'MÉXICO' in name_raw:
        return 'MX'
    if raw in ('51', 'PE') or 'PERU' in name_raw or 'PERÚ' in name_raw:
        return 'PE'
    if raw in ('55', 'BR') or 'BRASIL' in name_raw:
        return 'BR'

    if raw in REGIONAL_METHOD_ANCHORS:
        return raw

    return 'GLOBAL'


def anchor_method_to_region(method_code, region_code):
    """
    Ancla el desarrollo de un método de pago a una región específica.
    """
    key = normalize_region_key(region_code)
    code_up = str(method_code).strip().upper()
    if code_up not in PAYMENT_METHOD_CATALOG:
        return False

    if key not in REGIONAL_METHOD_ANCHORS:
        REGIONAL_METHOD_ANCHORS[key] = []
    if code_up not in REGIONAL_METHOD_ANCHORS[key]:
        REGIONAL_METHOD_ANCHORS[key].append(code_up)
    _sync_legacy_config()
    return True


def anchor_method_to_regions(method_code, region_codes_list):
    """
    Ancla un método de pago a múltiples regiones a la vez.
    """
    results = {}
    for r in region_codes_list:
        results[r] = anchor_method_to_region(method_code, r)
    return results


def unanchor_method_from_region(method_code, region_code):
    """
    Desancla un método de pago de una región específica.
    """
    key = normalize_region_key(region_code)
    code_up = str(method_code).strip().upper()
    if key in REGIONAL_METHOD_ANCHORS and code_up in REGIONAL_METHOD_ANCHORS[key]:
        REGIONAL_METHOD_ANCHORS[key].remove(code_up)
        _sync_legacy_config()
        return True
    return False


def get_anchored_regions(method_code):
    """
    Retorna la lista de regiones donde un método está actualmente anclado.
    """
    code_up = str(method_code).strip().upper()
    return [r for r, methods in REGIONAL_METHOD_ANCHORS.items() if code_up in methods]


def get_payment_method_catalog():
    """
    Retorna el catálogo completo con el desarrollo de cada método de pago.
    """
    return PAYMENT_METHOD_CATALOG


def get_payment_method_definition(method_code):
    """
    Obtiene la definición del método desde el catálogo por su código.
    """
    if not method_code:
        return None
    code_up = str(method_code).strip().upper()
    return PAYMENT_METHOD_CATALOG.get(code_up)


def register_payment_method(code, name, method_type, **kwargs):
    """
    Registra o actualiza el desarrollo de un nuevo método de pago en el catálogo
    y opcionalmente lo ancla a una lista de regiones proporcionada en `regions`.
    """
    code_up = str(code).strip().upper()
    regions = kwargs.pop('regions', None)
    method = CodePaymentMethod(
        code=code_up,
        name=name,
        method_type=method_type,
        **kwargs
    )
    PAYMENT_METHOD_CATALOG[code_up] = method
    if regions:
        anchor_method_to_regions(code_up, regions)
    _sync_legacy_config()
    return method


# ---------------------------------------------------------------------------
# RESOLUCIÓN REGIONAL DE MÉTODOS DE PAGO
# ---------------------------------------------------------------------------

def get_regional_payment_methods(region):
    """
    Devuelve la lista de métodos de pago autorizados para la región dada.
    1. Resuelve los métodos anclados en código para la región.
    2. Si existe configuración en la base de datos (RegionPaymentMethod con use_for_billing=True),
       incorpora esos métodos heredando automáticamente el desarrollo maestro del catálogo.
    3. Si la región es Venezuela ('VE'), inyecta la tasa oficial BCV del día en las instrucciones.
    """
    key = normalize_region_key(region)
    method_codes = REGIONAL_METHOD_ANCHORS.get(key)
    if not method_codes:
        method_codes = REGIONAL_METHOD_ANCHORS.get('GLOBAL', ['BINANCE_PAY', 'TRANSFERENCIA_INTL'])

    result_methods = []
    seen_codes = set()

    # 1. Métodos anclados por código en el catálogo
    for code in method_codes:
        catalog_def = PAYMENT_METHOD_CATALOG.get(code)
        if catalog_def:
            m = catalog_def.clone_for_region(region_code=key)
            result_methods.append(m)
            seen_codes.add(code)

    # 2. Métodos anclados dinámicamente en la base de datos (RegionPaymentMethod con use_for_billing=True)
    try:
        from apps.superadmin.models import RegionPaymentMethod, Region
        db_region = None
        if isinstance(region, Region):
            db_region = region
        elif hasattr(region, 'id'):
            db_region = Region.objects.filter(id=region.id).first()
        elif isinstance(region, str):
            db_region = (
                Region.objects.filter(code__iexact=region).first() or
                Region.objects.filter(name__iexact=region).first() or
                Region.objects.filter(country_codes__icontains=region).first()
            )

        if db_region:
            active_rpms = RegionPaymentMethod.objects.filter(
                region=db_region,
                use_for_billing=True,
                is_active=True
            ).select_related('payment_method')

            for rpm in active_rpms:
                raw_code = (rpm.payment_method.code or '').strip().upper()
                # Excluir métodos que no son de cobro de suscripción
                if raw_code in ('ZELLE', 'EFECTIVO', 'TARJETA'):
                    continue

                # Normalizar códigos genéricos al catálogo maestro
                code_up = raw_code
                if code_up == 'TRANSFERENCIA':
                    if key == 'VE':
                        code_up = 'TRANSFERENCIA_BS'
                    elif key == 'AR':
                        code_up = 'ALIAS_CBU'
                    else:
                        code_up = 'TRANSFERENCIA_INTL'
                elif code_up in ('BINANCE', 'BINANCEPAY'):
                    code_up = 'BINANCE_PAY'

                # Si ya fue registrado en el paso 1 (código maestro anclado):
                # asociamos el ID real de la BD para que el formulario reporte a ese registro
                if code_up in seen_codes:
                    for existing_m in result_methods:
                        if existing_m.code == code_up:
                            existing_m.db_rpm_id = str(rpm.id)
                            if rpm.payment_url:
                                existing_m.payment_url = rpm.payment_url
                    continue

                if code_up in PAYMENT_METHOD_CATALOG:
                    # Hereda automáticamente todo el desarrollo maestro (QR, copiado 1 a 1, etc.)
                    catalog_def = PAYMENT_METHOD_CATALOG[code_up]
                    # Solo sobreescribir instrucciones si no contienen texto dummy (ej. Banesco)
                    custom_instr = rpm.instructions if (rpm.instructions and rpm.instructions != catalog_def.instructions and 'banesco' not in rpm.instructions.lower()) else None
                    m = catalog_def.clone_for_region(
                        region_code=key,
                        custom_instructions=custom_instr,
                        custom_payment_url=rpm.payment_url if rpm.payment_url else None
                    )
                    m.db_rpm_id = str(rpm.id)
                else:
                    # Método registrado exclusivamente en la BD
                    m_type = 'GATEWAY' if rpm.payment_method.provider else 'MANUAL'
                    instr = rpm.instructions or rpm.payment_method.description or ''
                    m = CodePaymentMethod(
                        code=code_up or f"RPM_{rpm.id}",
                        name=rpm.payment_method.name,
                        method_type=m_type,
                        instructions=instr,
                        provider=rpm.payment_method.provider or '',
                        payment_url=rpm.payment_url or '',
                        badge=f"Habilitado en {key}",
                        region_code=key,
                        fields=parse_instructions_into_fields(instr, key) if instr else [],
                    )
                    m.db_rpm_id = str(rpm.id)

                result_methods.append(m)
                seen_codes.add(code_up)
    except Exception:
        # Fallback seguro si la base de datos no está disponible
        pass

    # 3. Tratamiento dinámico para Venezuela con la tasa BCV del día
    if key == 'VE':
        try:
            from apps.superadmin.bcv_service import get_bcv_info
            bcv = get_bcv_info()
            rate_txt = bcv.get('rate_formatted', '886,23')
            dynamic_methods = []
            for m in result_methods:
                if m.code in ('PAGOMOVIL', 'TRANSFERENCIA_BS'):
                    instr = m.instructions
                    if '• Tasa Oficial BCV:' not in instr:
                        instr = instr.replace(
                            "• Moneda: Bolívares (Bs.)",
                            f"• Tasa Oficial BCV del día: Bs. {rate_txt} por USD\n• Moneda: Bolívares (Bs.)"
                        )
                    dynamic_methods.append(m.clone_for_region(
                        region_code='VE',
                        custom_instructions=instr
                    ))
                else:
                    dynamic_methods.append(m)
            return dynamic_methods
        except Exception:
            pass

    return result_methods


def get_payment_method_by_code(method_code, region=None):
    """
    Busca un método registrado por código por su ID/code.
    1. Si se especifica region, busca primero en los métodos activos de esa región.
    2. Busca en el catálogo maestro PAYMENT_METHOD_CATALOG.
    3. Si es un alias conocido (ej. 'TRANSFERENCIA'), mapea según la región.
    4. Busca en la base de datos RegionPaymentMethod.
    """
    if not method_code:
        return None

    target = str(method_code).strip().upper()

    if region:
        for m in get_regional_payment_methods(region):
            if m.code.upper() == target or m.id.upper() == target:
                return m

    if target in PAYMENT_METHOD_CATALOG:
        return PAYMENT_METHOD_CATALOG[target]

    for code, m in PAYMENT_METHOD_CATALOG.items():
        if code.upper() == target or m.id.upper() == target:
            return m

    # Aliases
    if target == 'TRANSFERENCIA':
        reg_key = normalize_region_key(region)
        if reg_key == 'AR' and 'ALIAS_CBU' in PAYMENT_METHOD_CATALOG:
            return PAYMENT_METHOD_CATALOG['ALIAS_CBU']
        if reg_key == 'VE' and 'TRANSFERENCIA_BS' in PAYMENT_METHOD_CATALOG:
            return PAYMENT_METHOD_CATALOG['TRANSFERENCIA_BS']
        if 'TRANSFERENCIA_INTL' in PAYMENT_METHOD_CATALOG:
            return PAYMENT_METHOD_CATALOG['TRANSFERENCIA_INTL']

    try:
        from apps.superadmin.models import RegionPaymentMethod
        rpm = RegionPaymentMethod.objects.filter(id=method_code).select_related('payment_method', 'region').first()
        if rpm:
            code_up = (rpm.payment_method.code or '').strip().upper()
            if code_up in PAYMENT_METHOD_CATALOG:
                return PAYMENT_METHOD_CATALOG[code_up].clone_for_region(
                    region_code=getattr(rpm.region, 'code', 'GLOBAL'),
                    custom_instructions=rpm.instructions or None,
                    custom_payment_url=rpm.payment_url or None
                )
            m_type = 'GATEWAY' if rpm.payment_method.provider else 'MANUAL'
            return CodePaymentMethod(
                code=code_up or f"RPM_{rpm.id}",
                name=rpm.payment_method.name,
                method_type=m_type,
                instructions=rpm.instructions or rpm.payment_method.description or '',
                provider=rpm.payment_method.provider or '',
                payment_url=rpm.payment_url or '',
                badge=f"Habilitado en {getattr(rpm.region, 'code', 'GLOBAL')}",
                region_code=getattr(rpm.region, 'code', 'GLOBAL'),
                fields=[],
            )
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# DICCIONARIO LEGACY PARA COMPATIBILIDAD HACIA ATRÁS
# ---------------------------------------------------------------------------

REGIONAL_PAYMENT_CONFIG = {}

def _sync_legacy_config():
    global REGIONAL_PAYMENT_CONFIG
    for r_key, codes in REGIONAL_METHOD_ANCHORS.items():
        REGIONAL_PAYMENT_CONFIG[r_key] = [
            PAYMENT_METHOD_CATALOG[c].clone_for_region(region_code=r_key)
            for c in codes if c in PAYMENT_METHOD_CATALOG
        ]

_sync_legacy_config()
