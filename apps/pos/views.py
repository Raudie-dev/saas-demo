from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from apps.business.models import Business, StaffMember
from apps.pos.models import CashRegister, CashMovement, Sale, SaleItem
from apps.crm.models import Client
from apps.agenda.models import Service, Appointment
from apps.inventory.models import Product, StockMovement
from apps.commissions.models import CommissionRecord
from apps.core.utils import parse_decimal

def pos_terminal_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    active_register = CashRegister.objects.filter(business=business, status='OPEN').first()
    
    clients = Client.objects.filter(business=business)
    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    services = Service.objects.filter(business=business, is_active=True)
    products = Product.objects.filter(business=business, is_active=True, stock__gt=0)
    pending_appointments = Appointment.objects.filter(business=business, status='CONFIRMED')
    
    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        staff_id = request.POST.get('staff_id')
        service_id = request.POST.get('service_id')
        product_id = request.POST.get('product_id')
        payment_method = request.POST.get('payment_method', 'Efectivo')
        tip_amount = parse_decimal(request.POST.get('tip_amount'), '0.00')
        discount_amount = parse_decimal(request.POST.get('discount_amount'), '0.00')
        
        client = Client.objects.filter(id=client_id).first() if client_id else None
        staff = StaffMember.objects.filter(id=staff_id).first() if staff_id else None
        
        with transaction.atomic():
            subtotal = Decimal('0.00')
            sale = Sale.objects.create(
                business=business,
                cash_register=active_register,
                client=client,
                staff=staff,
                payment_method=payment_method,
                tip_amount=tip_amount,
                discount_amount=discount_amount,
                status='COMPLETED'
            )
            
            if service_id:
                srv = Service.objects.get(id=service_id)
                subtotal += srv.price
                SaleItem.objects.create(
                    sale=sale,
                    item_type='SERVICE',
                    service=srv,
                    unit_price=srv.price,
                    quantity=1,
                    total_price=srv.price
                )
                # Commission calculation
                if staff:
                    comm_rate = srv.commission_rate if srv.commission_rate > 0 else staff.commission_rate
                    if comm_rate > 0:
                        comm_amt = (srv.price * (comm_rate / Decimal('100.00')))
                        CommissionRecord.objects.create(
                            business=business,
                            staff=staff,
                            sale=sale,
                            amount=comm_amt,
                            concept=f"Comisión Servicio: {srv.name}"
                        )
                        
            if product_id:
                prod = Product.objects.get(id=product_id)
                subtotal += prod.sale_price
                SaleItem.objects.create(
                    sale=sale,
                    item_type='PRODUCT',
                    product=prod,
                    unit_price=prod.sale_price,
                    quantity=1,
                    total_price=prod.sale_price
                )
                # Stock deduction & movement
                old_stock = prod.stock
                prod.stock -= 1
                prod.save()
                StockMovement.objects.create(
                    product=prod,
                    movement_type='SALE',
                    quantity=1,
                    previous_stock=old_stock,
                    new_stock=prod.stock,
                    notes=f"Venta POS #{str(sale.id)[:8]}"
                )

            total = (subtotal - discount_amount) + tip_amount
            sale.subtotal = subtotal
            sale.total_amount = total
            sale.save()
            
            # Update client total spent
            if client:
                client.total_spent += total
                client.save()

        return redirect('pos_terminal')

    return render(request, 'pos/terminal.html', {
        'business': business,
        'active_register': active_register,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'products': products,
        'pending_appointments': pending_appointments,
    })

def cash_register_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    registers = CashRegister.objects.filter(business=business).order_by('-opened_at')
    active_register = registers.filter(status='OPEN').first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'open':
            initial = parse_decimal(request.POST.get('initial_amount'), '0.00')
            CashRegister.objects.create(
                business=business,
                opened_by=request.user if request.user.is_authenticated else Business.objects.first().users.first(),
                initial_amount=initial,
                status='OPEN'
            )
        elif action == 'close' and active_register:
            active_register.status = 'CLOSED'
            active_register.closed_at = datetime.datetime.now()
            active_register.save()
        return redirect('cash_register')

    return render(request, 'pos/cash_register.html', {
        'business': business,
        'registers': registers,
        'active_register': active_register,
    })
