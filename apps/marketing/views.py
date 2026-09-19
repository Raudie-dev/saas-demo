from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from apps.business.models import Business
from apps.marketing.models import Coupon, GiftCard
from apps.crm.models import Client
from apps.core.utils import parse_decimal, parse_int

def marketing_dashboard_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    coupons = Coupon.objects.filter(business=business) if business else []
    giftcards = GiftCard.objects.filter(business=business) if business else []
    clients = Client.objects.filter(business=business) if business else []
    
    return render(request, 'marketing/marketing_dashboard.html', {
        'business': business,
        'coupons': coupons,
        'giftcards': giftcards,
        'clients': clients,
    })

def coupon_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()

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

def coupon_edit_view(request, coupon_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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

def giftcard_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    clients = Client.objects.filter(business=business) if business else []

    if request.method == 'POST':
        code = request.POST.get('code').upper()
        amount = parse_decimal(request.POST.get('amount'), '50.00')
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id).first() if client_id else None
        
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
