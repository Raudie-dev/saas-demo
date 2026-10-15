"""
Integración con Mercado Pago para el cobro de suscripciones del SaaS.
  - Checkout Pro (pago único por período)
  - Preapproval (suscripción con débito automático)

Credenciales por región (fallback a la global):
    MERCADOPAGO_ACCESS_TOKEN_<CODIGO_REGION>   ej: MERCADOPAGO_ACCESS_TOKEN_AR
    MERCADOPAGO_ACCESS_TOKEN
Moneda: Region.currency_code (ISO: ARS, CLP, MXN, UYU, COP, PEN, BRL) o MERCADOPAGO_CURRENCY (default ARS).
SITE_URL: URL pública base (https) para back_urls y webhook.
"""
import datetime
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

MP_API_BASE = "https://api.mercadopago.com"


class MercadoPagoError(Exception):
    pass


# ---------------------------------------------------------------- config

def _region_code(region):
    if region is None:
        return ''
    return region if isinstance(region, str) else (region.code or '')


def get_access_token(region=None):
    if region:
        # 1. Probar por código directo de región (ej: 54, AR, VE, etc.)
        code = _region_code(region).upper().replace('-', '_')
        if code:
            token = os.getenv(f'MERCADOPAGO_ACCESS_TOKEN_{code}')
            if token:
                return token
        # 2. Si la región tiene códigos de país asignados (ej: AR, VE)
        country_codes = getattr(region, 'country_codes', '') or ''
        if country_codes:
            for c in country_codes.split(','):
                c_clean = c.strip().upper().replace('-', '_')
                if c_clean:
                    token = os.getenv(f'MERCADOPAGO_ACCESS_TOKEN_{c_clean}')
                    if token:
                        return token
    # 3. Fallback al token global
    return os.getenv('MERCADOPAGO_ACCESS_TOKEN', '')


def is_configured(region=None):
    return bool(get_access_token(region))


def get_currency(region=None):
    code = getattr(region, 'currency_code', None) if region is not None and not isinstance(region, str) else None
    return (code or os.getenv('MERCADOPAGO_CURRENCY', 'ARS')).upper()


def site_url(request=None):
    base = os.getenv('SITE_URL', '').rstrip('/')
    if not base and request is not None:
        base = request.build_absolute_uri('/').rstrip('/')
    return base


def _webhook_url(base, region):
    url = base + reverse('mercadopago_webhook')
    code = _region_code(region)
    return f"{url}?{urllib.parse.urlencode({'region': code})}" if code else url


def _request(method, path, payload=None, region=None):
    token = get_access_token(region)
    if not token:
        raise MercadoPagoError("Mercado Pago no está configurado para esta región.")
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(
        f"{MP_API_BASE}{path}", data=data, method=method,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error("Mercado Pago HTTP %s en %s: %s", e.code, path, body)
        raise MercadoPagoError(f"Error de Mercado Pago ({e.code}).")
    except urllib.error.URLError as e:
        logger.error("Mercado Pago sin conexión: %s", e)
        raise MercadoPagoError("No se pudo conectar con Mercado Pago.")


# ---------------------------------------------------------------- licencia

def apply_approved_payment(payment, reviewer=None, actor_email="mercadopago@system"):
    """Marca el pago como aprobado y extiende la licencia. Idempotente."""
    from apps.superadmin.models import BusinessSubscription, SystemAuditLog

    if payment.status == 'APPROVED':
        return None

    payment.status = 'APPROVED'
    payment.reviewed_at = timezone.now()
    payment.reviewed_by = reviewer
    payment.save()

    today = timezone.now().date()
    subscription, _ = BusinessSubscription.objects.get_or_create(
        business=payment.business,
        defaults={'status': 'TRIAL', 'start_date': today, 'expiration_date': today},
    )
    subscription.status = 'ACTIVE'
    if payment.plan:
        subscription.plan = payment.plan
        subscription.pending_plan = None

    base_date = subscription.expiration_date if (subscription.expiration_date and subscription.expiration_date >= today) else today
    days = 365 if payment.billing_cycle == 'ANNUAL' else 30
    subscription.expiration_date = base_date + datetime.timedelta(days=days)
    subscription.save()

    SystemAuditLog.objects.create(
        actor_email=actor_email,
        action="PAGO_APROBADO",
        details=f"Pago #{payment.id} de {payment.amount} aprobado para {payment.business.name}. Licencia extendida a {subscription.expiration_date}.",
    )
    return subscription


# ---------------------------------------------------------------- Checkout Pro (pago único)

def start_checkout(request, business, plan, billing_cycle, amount, rpm=None):
    from apps.superadmin.models import SubscriptionPayment

    region = business.region
    payment = SubscriptionPayment.objects.create(
        business=business, plan=plan, region_payment_method=rpm,
        billing_cycle=billing_cycle, amount=amount,
        reference="MP-PENDIENTE", notes="Pago iniciado vía Mercado Pago Checkout Pro",
    )
    base = site_url(request)
    return_url = base + reverse('mercadopago_return')
    cycle = payment.get_billing_cycle_display()
    payload = {
        "items": [{
            "id": str(plan.id),
            "title": f"{plan.name} - {cycle}",
            "description": f"Licencia {plan.name} ({cycle}) para {business.name}",
            "quantity": 1,
            "currency_id": get_currency(region),
            "unit_price": float(amount),
        }],
        "external_reference": str(payment.id),
        "back_urls": {"success": return_url, "pending": return_url, "failure": return_url},
        "notification_url": _webhook_url(base, region),
        "statement_descriptor": "SUSCRIPCION",
    }
    if base.startswith('https://'):
        payload["auto_return"] = "approved"

    try:
        data = _request('POST', '/checkout/preferences', payload, region)
    except MercadoPagoError as e:
        payment.status = 'REJECTED'
        payment.notes = f"No se pudo iniciar el checkout: {e}"
        payment.save(update_fields=['status', 'notes', 'updated_at'])
        raise

    payment.mp_preference_id = data.get('id')
    payment.save(update_fields=['mp_preference_id', 'updated_at'])
    if get_access_token(region).startswith('TEST-') and data.get('sandbox_init_point'):
        return data['sandbox_init_point']
    return data.get('init_point')


def sync_payment_from_mp(mp_payment_id, region=None):
    """Consulta un pago de Checkout Pro en MP (fuente de verdad) y actualiza el SubscriptionPayment."""
    from apps.superadmin.models import SubscriptionPayment, SystemAuditLog

    data = _request('GET', f'/v1/payments/{mp_payment_id}', region=region)
    ext_ref = str(data.get('external_reference') or '')
    if not ext_ref.isdigit():
        return None  # no es un pago de Checkout Pro de este sistema

    with transaction.atomic():
        payment = SubscriptionPayment.objects.select_for_update().filter(id=int(ext_ref)).first()
        if not payment:
            return None
        mp_status = data.get('status')
        payment.mp_payment_id = str(data.get('id'))
        payment.mp_status = mp_status
        payment.reference = f"MP-{data.get('id')}"
        payment.save(update_fields=['mp_payment_id', 'mp_status', 'reference', 'updated_at'])

        if mp_status == 'approved':
            paid = float(data.get('transaction_amount') or 0)
            if paid + 0.01 < float(payment.amount):
                SystemAuditLog.objects.create(
                    actor_email="mercadopago@system", action="PAGO_MP_MONTO_INVALIDO",
                    details=f"Pago MP {data.get('id')} por {paid} no cubre {payment.amount} (pago #{payment.id}).",
                )
                return payment
            apply_approved_payment(payment)
        elif mp_status in ('rejected', 'cancelled', 'refunded', 'charged_back') and payment.status != 'APPROVED':
            payment.status = 'REJECTED'
            payment.notes = f"Mercado Pago: {mp_status} ({data.get('status_detail', '')})"
            payment.save(update_fields=['status', 'notes', 'updated_at'])
    return payment


# ---------------------------------------------------------------- Preapproval (débito automático)

def _sub_reference(business, plan, billing_cycle):
    return f"SUB-{business.id}-{plan.id}-{billing_cycle}"


def _parse_sub_reference(ref):
    try:
        prefix, business_id, plan_id, cycle = str(ref).split('-', 3)
        if prefix == 'SUB':
            return int(business_id), int(plan_id), cycle
    except (ValueError, AttributeError):
        pass
    return None


def start_subscription(request, business, plan, billing_cycle, amount, rpm=None):
    from apps.superadmin.models import BusinessSubscription, SystemAuditLog

    region = business.region
    sub = BusinessSubscription.objects.filter(business=business).first()
    if sub and sub.gateway_subscription_id and sub.recurring_status in ('pending', 'authorized'):
        # Cancelar la suscripción recurrente anterior antes de crear una nueva (cambio de plan)
        cancel_subscription(sub)

    payer_email = (request.user.email or business.email or '').strip()
    base = site_url(request)
    payload = {
        "reason": f"{plan.name} ({'Anual' if billing_cycle == 'ANNUAL' else 'Mensual'}) - {business.name}",
        "external_reference": _sub_reference(business, plan, billing_cycle),
        "payer_email": payer_email,
        "auto_recurring": {
            "frequency": 12 if billing_cycle == 'ANNUAL' else 1,
            "frequency_type": "months",
            "transaction_amount": float(amount),
            "currency_id": get_currency(region),
        },
        "back_url": base + reverse('mercadopago_return') + "?type=subscription",
        "notification_url": _webhook_url(base, region),
        "status": "pending",
    }
    data = _request('POST', '/preapproval', payload, region)

    if sub:
        sub.gateway_provider = 'MERCADOPAGO_SUBSCRIPTION'
        sub.gateway_subscription_id = data.get('id')
        sub.recurring_status = data.get('status', 'pending')
        sub.save(update_fields=['gateway_provider', 'gateway_subscription_id', 'recurring_status', 'updated_at'])

    SystemAuditLog.objects.create(
        actor_email=request.user.email or request.user.username, action="SUSCRIPCION_MP_INICIADA",
        details=f"'{business.name}' inició débito automático {plan.name} ({billing_cycle}) por {amount}. Preapproval {data.get('id')}.",
    )
    return data.get('init_point')


def sync_preapproval(preapproval_id, region=None):
    """Actualiza el estado de la suscripción recurrente (authorized / paused / cancelled)."""
    from apps.superadmin.models import BusinessSubscription, SubscriptionPlan

    data = _request('GET', f'/preapproval/{preapproval_id}', region=region)
    ref = _parse_sub_reference(data.get('external_reference'))
    if not ref:
        return None
    business_id, plan_id, _cycle = ref
    sub = BusinessSubscription.objects.filter(business_id=business_id).first()
    if not sub:
        return None

    status = data.get('status')
    # Ignorar notificaciones de una preapproval anterior ya reemplazada
    if sub.gateway_subscription_id and sub.gateway_subscription_id != data.get('id') and status != 'authorized':
        return sub

    sub.gateway_provider = 'MERCADOPAGO_SUBSCRIPTION'
    sub.gateway_subscription_id = data.get('id')
    sub.recurring_status = status
    if status == 'authorized':
        sub.auto_renew = True
        plan = SubscriptionPlan.objects.filter(id=plan_id).first()
        if plan and sub.plan_id != plan.id:
            sub.pending_plan = plan
    elif status in ('cancelled', 'paused'):
        sub.auto_renew = False
    sub.save()
    return sub


def sync_authorized_payment(authorized_payment_id, region=None):
    """Cada cobro recurrente: si fue aprobado, registra el pago y extiende la licencia."""
    from apps.business.models import Business
    from apps.superadmin.models import SubscriptionPayment, SubscriptionPlan, RegionPaymentMethod

    data = _request('GET', f'/authorized_payments/{authorized_payment_id}', region=region)
    payment_info = data.get('payment') or {}
    if payment_info.get('status') != 'approved':
        return None

    preapproval = _request('GET', f"/preapproval/{data.get('preapproval_id')}", region=region)
    ref = _parse_sub_reference(preapproval.get('external_reference'))
    if not ref:
        return None
    business_id, plan_id, cycle = ref
    business = Business.objects.filter(id=business_id).first()
    if not business:
        return None

    mp_id = f"AP-{data.get('id')}"
    with transaction.atomic():
        if SubscriptionPayment.objects.select_for_update().filter(mp_payment_id=mp_id).exists():
            return None  # ya procesado
        rpm = RegionPaymentMethod.objects.filter(
            region=business.region, payment_method__provider='MERCADOPAGO_SUBSCRIPTION'
        ).first() if business.region else None
        payment = SubscriptionPayment.objects.create(
            business=business,
            plan=SubscriptionPlan.objects.filter(id=plan_id).first(),
            region_payment_method=rpm,
            billing_cycle='ANNUAL' if cycle == 'ANNUAL' else 'MONTHLY',
            amount=data.get('transaction_amount') or 0,
            reference=f"MP-{payment_info.get('id')}",
            mp_payment_id=mp_id,
            mp_status='approved',
            notes=f"Cobro automático Mercado Pago (preapproval {data.get('preapproval_id')})",
        )
        apply_approved_payment(payment)
    return payment


def cancel_subscription(subscription):
    """Cancela el débito automático en Mercado Pago."""
    if not subscription.gateway_subscription_id:
        return
    region = subscription.business.region
    _request('PUT', f'/preapproval/{subscription.gateway_subscription_id}', {"status": "cancelled"}, region)
    subscription.recurring_status = 'cancelled'
    subscription.auto_renew = False
    subscription.save(update_fields=['recurring_status', 'auto_renew', 'updated_at'])
