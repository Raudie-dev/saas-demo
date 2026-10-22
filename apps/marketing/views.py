from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from apps.business.models import Business
from apps.marketing.models import Coupon, GiftCard, EmailCampaign, LoyaltyProgram, LoyaltyCard
from apps.crm.models import Client
from apps.core.utils import parse_decimal, parse_int
from apps.marketing.utils import (
    get_audience_clients,
    render_campaign_email_content,
    send_email_campaign_dispatch,
)

@login_required
def marketing_dashboard_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    coupons = Coupon.objects.filter(business=business).order_by('-created_at') if business else []
    giftcards = GiftCard.objects.filter(business=business).select_related('client').order_by('-created_at') if business else []
    clients = Client.objects.filter(business=business) if business else []

    active_coupons = [c for c in coupons if c.is_active]
    total_coupon_uses = sum(c.uses_count for c in coupons)

    active_giftcards = [g for g in giftcards if g.is_active]
    total_giftcards_balance = sum(g.current_balance for g in active_giftcards)

    program = LoyaltyProgram.objects.filter(business=business).first() if business else None
    cards = LoyaltyCard.objects.filter(program=program) if program else []
    total_loyalty_members = len(cards)
    total_loyalty_points = sum(c.points for c in cards)

    campaigns = EmailCampaign.objects.filter(business=business).order_by('-created_at') if business else []
    sent_campaigns_count = sum(1 for c in campaigns if c.status == 'SENT')

    return render(request, 'marketing/marketing_dashboard.html', {
        'business': business,
        'coupons': coupons,
        'active_coupons': active_coupons,
        'total_coupon_uses': total_coupon_uses,
        'giftcards': giftcards,
        'active_giftcards': active_giftcards,
        'total_giftcards_balance': total_giftcards_balance,
        'clients': clients,
        'program': program,
        'total_loyalty_members': total_loyalty_members,
        'total_loyalty_points': total_loyalty_points,
        'campaigns': campaigns,
        'sent_campaigns_count': sent_campaigns_count,
    })

@login_required
def coupon_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        code = request.POST.get('code').upper()
        pct = parse_decimal(request.POST.get('discount_percentage'), '15.00')
        valid_until = request.POST.get('valid_until')
        max_uses = parse_int(request.POST.get('max_uses'), 50)
        
        Coupon.objects.create(
            business=business,
            code=code,
            discount_percentage=pct,
            valid_until=valid_until,
            max_uses=max_uses,
            is_active=True
        )
        messages.success(request, f"¡Cupón {code} creado exitosamente!")
        return redirect('marketing_dashboard')

    return render(request, 'marketing/coupon_form.html', {
        'business': business
    })

@login_required
def coupon_edit_view(request, coupon_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    coupon = get_object_or_404(Coupon, id=coupon_id, business=business)
    
    if request.method == 'POST':
        coupon.code = request.POST.get('code').upper()
        coupon.discount_percentage = parse_decimal(request.POST.get('discount_percentage'), coupon.discount_percentage)
        coupon.valid_until = request.POST.get('valid_until')
        coupon.max_uses = parse_int(request.POST.get('max_uses'), coupon.max_uses)
        coupon.is_active = request.POST.get('is_active') == 'on'
        coupon.save()
        messages.success(request, f"Cupón {coupon.code} actualizado correctamente.")
        return redirect('marketing_dashboard')
        
    return render(request, 'marketing/coupon_form.html', {
        'business': business,
        'coupon': coupon
    })

@login_required
def giftcard_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        code = request.POST.get('code').upper()
        initial_balance = parse_decimal(request.POST.get('initial_balance'), '50.00')
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None
        
        GiftCard.objects.create(
            business=business,
            code=code,
            initial_balance=initial_balance,
            current_balance=initial_balance,
            client=client,
            is_active=True
        )
        messages.success(request, f"¡Gift Card #{code} emitida por {business.currency}{initial_balance}!")
        return redirect('marketing_dashboard')
        
    clients = Client.objects.filter(business=business)
    return render(request, 'marketing/giftcard_form.html', {
        'business': business,
        'clients': clients
    })

# ==============================================================================
# EMAIL MARKETING VIEWS
# ==============================================================================

@login_required
def email_marketing_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    campaigns = EmailCampaign.objects.filter(business=business).order_by('-created_at')

    # Filtros
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    if q:
        campaigns = campaigns.filter(name__icontains=q) | campaigns.filter(subject__icontains=q)
    if status_filter in ['DRAFT', 'SENT', 'FAILED']:
        campaigns = campaigns.filter(status=status_filter)

    # Métricas
    all_campaigns = EmailCampaign.objects.filter(business=business)
    total_campaigns = all_campaigns.count()
    sent_campaigns = all_campaigns.filter(status='SENT').count()
    total_sent_emails = sum(c.recipients_count for c in all_campaigns)
    clients_with_email = Client.objects.filter(business=business, email__isnull=False).exclude(email='').count()

    return render(request, 'marketing/email_list.html', {
        'business': business,
        'campaigns': campaigns,
        'q': q,
        'status_filter': status_filter,
        'total_campaigns': total_campaigns,
        'sent_campaigns': sent_campaigns,
        'total_sent_emails': total_sent_emails,
        'clients_with_email': clients_with_email,
    })

@login_required
def email_campaign_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    # Conteos de audiencia en tiempo real
    audience_counts = {
        'ALL': get_audience_clients(business, 'ALL').count(),
        'VIP': get_audience_clients(business, 'VIP').count(),
        'INACTIVE': get_audience_clients(business, 'INACTIVE').count(),
        'PROSPECT': get_audience_clients(business, 'PROSPECT').count(),
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'save_draft')
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '').strip()
        audience = request.POST.get('audience', 'ALL')

        if not name or not subject or not body:
            messages.error(request, "Por favor completa el nombre, asunto y contenido del correo.")
            return render(request, 'marketing/email_form.html', {
                'business': business,
                'audiences': EmailCampaign.AUDIENCE_CHOICES,
                'audience_counts': audience_counts,
                'form_data': request.POST,
            })

        campaign = EmailCampaign.objects.create(
            business=business,
            name=name,
            subject=subject,
            body=body,
            audience=audience,
            status='DRAFT'
        )

        if action == 'send_now':
            result = send_email_campaign_dispatch(campaign)
            if result['success']:
                messages.success(request, f"¡{result['message']}")
            else:
                messages.warning(request, f"Campaña guardada pero con alerta en el envío: {result['message']}")
        else:
            messages.success(request, f"Borrador de campaña '{campaign.name}' guardado exitosamente.")

        return redirect('email_marketing_list')

    return render(request, 'marketing/email_form.html', {
        'business': business,
        'audiences': EmailCampaign.AUDIENCE_CHOICES,
        'audience_counts': audience_counts,
        'form_data': {},
        'campaign': None,
    })

@login_required
def email_campaign_edit_view(request, campaign_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    campaign = get_object_or_404(EmailCampaign, id=campaign_id, business=business)

    audience_counts = {
        'ALL': get_audience_clients(business, 'ALL').count(),
        'VIP': get_audience_clients(business, 'VIP').count(),
        'INACTIVE': get_audience_clients(business, 'INACTIVE').count(),
        'PROSPECT': get_audience_clients(business, 'PROSPECT').count(),
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'save_draft')
        campaign.name = request.POST.get('name', campaign.name).strip()
        campaign.subject = request.POST.get('subject', campaign.subject).strip()
        campaign.body = request.POST.get('body', campaign.body).strip()
        campaign.audience = request.POST.get('audience', campaign.audience)
        campaign.save()

        if action == 'send_now':
            result = send_email_campaign_dispatch(campaign)
            if result['success']:
                messages.success(request, f"¡{result['message']}")
            else:
                messages.warning(request, f"Campaña actualizada con alerta de envío: {result['message']}")
        else:
            messages.success(request, f"Campaña '{campaign.name}' actualizada.")

        return redirect('email_marketing_list')

    return render(request, 'marketing/email_form.html', {
        'business': business,
        'campaign': campaign,
        'audiences': EmailCampaign.AUDIENCE_CHOICES,
        'audience_counts': audience_counts,
        'form_data': {},
        'campaign': None,
    })

@login_required
def email_campaign_send_view(request, campaign_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    campaign = get_object_or_404(EmailCampaign, id=campaign_id, business=business)

    if request.method == 'POST':
        is_test = request.POST.get('is_test') == 'true'
        test_email = request.POST.get('test_email', '').strip()

        if is_test:
            if not test_email:
                messages.error(request, "Ingresa un correo electrónico de prueba válido.")
                return redirect('email_marketing_list')
            result = send_email_campaign_dispatch(campaign, test_email=test_email)
            if result['success']:
                messages.success(request, f"¡{result['message']}")
            else:
                messages.error(request, f"Error al enviar correo de prueba: {result['message']}")
            return redirect('email_marketing_list')

        # Envío masivo a la audiencia completa
        result = send_email_campaign_dispatch(campaign)
        if result['success']:
            messages.success(request, f"¡{result['message']}")
        else:
            messages.error(request, f"Alerta en el envío: {result['message']}")

    return redirect('email_marketing_list')

@login_required
def email_campaign_preview_view(request, campaign_id):
    """
    Renderiza la vista previa del correo HTML con datos de prueba
    para inspección antes de enviar.
    """
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return HttpResponse("No autorizado", status=401)

    campaign = get_object_or_404(EmailCampaign, id=campaign_id, business=business)
    sample_client = Client.objects.filter(business=business).first()

    subj, text_body, html_body = render_campaign_email_content(
        business=business,
        subject=campaign.subject,
        body_text=campaign.body,
        client=sample_client
    )
    return HttpResponse(html_body, content_type='text/html')

@login_required
def email_campaign_delete_view(request, campaign_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    campaign = get_object_or_404(EmailCampaign, id=campaign_id, business=business)
    if request.method == 'POST':
        name = campaign.name
        campaign.delete()
        messages.success(request, f"Campaña '{name}' eliminada correctamente.")
    return redirect('email_marketing_list')

# ==============================================================================
# LOYALTY PROGRAM VIEWS
# ==============================================================================

@login_required
def loyalty_program_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    program = LoyaltyProgram.objects.filter(business=business).first()

    if request.method == 'POST':
        name = request.POST.get('name', 'Programa VIP')
        points_per_currency = parse_decimal(request.POST.get('points_per_currency'), '1.00')
        minimum_points_to_redeem = parse_int(request.POST.get('minimum_points_to_redeem'), 100)
        is_active = request.POST.get('is_active') == 'on'

        if program:
            program.name = name
            program.points_per_currency = points_per_currency
            program.minimum_points_to_redeem = minimum_points_to_redeem
            program.is_active = is_active
            program.save()
            messages.success(request, "Programa de fidelización actualizado.")
        else:
            program = LoyaltyProgram.objects.create(
                business=business,
                name=name,
                points_per_currency=points_per_currency,
                minimum_points_to_redeem=minimum_points_to_redeem,
                is_active=is_active
            )
            messages.success(request, "¡Programa de fidelización activado con éxito!")
        return redirect('loyalty_program_view')

    cards = LoyaltyCard.objects.filter(program=program).select_related('client') if program else []
    clients = Client.objects.filter(business=business)

    return render(request, 'marketing/loyalty_dashboard.html', {
        'business': business,
        'program': program,
        'cards': cards,
        'clients': clients
    })
