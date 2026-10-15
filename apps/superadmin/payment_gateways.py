"""
Registro de pasarelas de pago integradas por código.

Cada pasarela declarada aquí se crea automáticamente como GlobalPaymentMethod
(con `provider` = clave del registro). Luego el SuperAdmin la habilita por región
desde "Regiones" (checkbox "Cobro de Suscripción"). Las credenciales se resuelven
por región vía variables de entorno (ver cada módulo de pasarela).

Para agregar una pasarela nueva:
  1. Crear un módulo con las funciones `is_configured(region)` y
     `start(request, business, plan, billing_cycle, amount, rpm)` -> URL de redirección.
  2. Registrarla en PROVIDERS.
"""
from importlib import import_module

PROVIDERS = {
    'MERCADOPAGO': {
        'name': 'Mercado Pago',
        'description': 'Pasarela de pago online Mercado Pago. Permite a las agencias pagar con tarjeta, dinero en cuenta o medios locales con activación automática.',
        'module': 'apps.superadmin.mercadopago',
        'start': 'start_checkout',
        'recurring': False,
        'button_label': 'Pagar con Mercado Pago',
    },
}

PROVIDER_CHOICES = [('', 'Manual (informar comprobante)')] + [(k, v['name']) for k, v in PROVIDERS.items()]


def get_provider(code):
    return PROVIDERS.get(code or '')


def _module(code):
    return import_module(PROVIDERS[code]['module'])


def is_available(code, region):
    if code not in PROVIDERS:
        return False
    return _module(code).is_configured(region)


def start(code, **kwargs):
    """Inicia el flujo de la pasarela y devuelve la URL a la que redirigir al usuario."""
    return getattr(_module(code), PROVIDERS[code]['start'])(**kwargs)


def ensure_integrated_methods():
    """Crea/actualiza los GlobalPaymentMethod de cada pasarela registrada (idempotente)."""
    from apps.superadmin.models import GlobalPaymentMethod
    for code, cfg in PROVIDERS.items():
        GlobalPaymentMethod.objects.update_or_create(
            code=code,
            defaults={'name': cfg['name'], 'provider': code, 'description': cfg['description']},
        )
    # Desactivar o limpiar proveedores integrados viejos que ya no están en PROVIDERS
    GlobalPaymentMethod.objects.exclude(provider='').exclude(provider__in=PROVIDERS.keys()).delete()
