from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.business.models import Business
from apps.marketing.models import Coupon, GiftCard, EmailCampaign, LoyaltyProgram, LoyaltyCard
from apps.crm.models import Client
from apps.core.utils import parse_decimal, parse_int

@login_required
def marketing_dashboard_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    coupons = Coupon.objects.filter(business=business) if business else []
    giftcards = GiftCard.objects.filter(business=business) if business else []
    clients = Client.objects.filter(business=business) if business else []
    
    return render(request, 'marketing/marketing_dashboard.html', {
        'business': business,
        'coupons': coupons,
        'giftcards': giftcards,
        'clients': clients,
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
        return redirect('marketing_dashboard')

    return render(request, 'marketing/coupon_form.html', {
        'business': business,
        'coupon': None,
        'today_plus_30': (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
        'title': 'Crear Nuevo Cupón Promocional'
    })

@login_required
def coupon_edit_view(request, coupon_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    coupon = get_object_or_404(Coupon, id=coupon_id, business=business)

    if request.method == 'POST':
        coupon.code = request.POST.get('code').upper()
        coupon.discount_percentage = parse_decimal(request.POST.get('discount_percentage'), '15.00')
        coupon.valid_until = request.POST.get('valid_until')
        coupon.max_uses = parse_int(request.POST.get('max_uses'), 50)
        coupon.is_active = request.POST.get('is_active') == 'on'
        coupon.save()
        return redirect('marketing_dashboard')

    return render(request, 'marketing/coupon_form.html', {
        'business': business,
        'coupon': coupon,
        'title': f'Editar Cupón: {coupon.code}'
    })

@login_required
def giftcard_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    clients = Client.objects.filter(business=business) if business else []

    if request.method == 'POST':
        code = request.POST.get('code').upper()
        amount = parse_decimal(request.POST.get('amount'), '50.00')
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None
        
        GiftCard.objects.create(
            business=business,
            code=code,
            client=client,
            initial_balance=amount,
            current_balance=amount,
            is_active=True
        )
        return redirect('marketing_dashboard')

    return render(request, 'marketing/giftcard_form.html', {
        'business': business,
        'clients': clients,
        'title': 'Emitir Nueva Gift Card'
    })

@login_required
def email_marketing_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    campaigns = EmailCampaign.objects.filter(business=business).order_by('-created_at')
    return render(request, 'marketing/email_list.html', {
        'business': business,
        'campaigns': campaigns
    })

@login_required
def email_campaign_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        audience = request.POST.get('audience', 'ALL')
        
        EmailCampaign.objects.create(
            business=business,
            name=name,
            subject=subject,
            body=body,
            audience=audience,
            status='DRAFT'
        )
        return redirect('email_marketing_list')
        
    return render(request, 'marketing/email_form.html', {
        'business': business,
        'audiences': EmailCampaign.AUDIENCE_CHOICES
    })

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
        
        if program:
            program.name = name
            program.points_per_currency = points_per_currency
            program.minimum_points_to_redeem = minimum_points_to_redeem
            program.save()
        else:
            program = LoyaltyProgram.objects.create(
                business=business,
                name=name,
                points_per_currency=points_per_currency,
                minimum_points_to_redeem=minimum_points_to_redeem
            )
        return redirect('loyalty_program_view')

    cards = LoyaltyCard.objects.filter(program=program).select_related('client') if program else []
    clients = Client.objects.filter(business=business)
    
    return render(request, 'marketing/loyalty_dashboard.html', {
        'business': business,
        'program': program,
        'cards': cards,
        'clients': clients
    })
