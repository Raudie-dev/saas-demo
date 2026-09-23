import datetime
import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.db import transaction
from apps.business.models import Business, StaffMember
from apps.pos.models import CashRegister, CashMovement, Sale, SaleItem
from apps.crm.models import Client
from apps.agenda.models import Service, Appointment
from apps.inventory.models import Product, StockMovement
from apps.commissions.models import CommissionRecord
from apps.core.utils import parse_decimal

from django.contrib import messages

@ensure_csrf_cookie
def pos_terminal_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    active_register = CashRegister.objects.filter(business=business, status='OPEN').first()
    
    clients = Client.objects.filter(business=business)
    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    services = Service.objects.filter(business=business, is_active=True)
    products = Product.objects.filter(business=business, is_active=True, stock__gt=0)
    pending_appointments = Appointment.objects.filter(business=business, status='CONFIRMED')
    
    appointment_id = request.GET.get('appointment_id', '')
    appointment = None
    selected_client_id = request.GET.get('client_id', '')
    selected_service_id = request.GET.get('service_id', '')
    selected_staff_id = request.GET.get('staff_id', '')

    if appointment_id:
        appointment = Appointment.objects.filter(id=appointment_id, business=business).first()
        if appointment:
            selected_client_id = str(appointment.client_id)
            selected_service_id = str(appointment.service_id)
            selected_staff_id = str(appointment.staff_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'close_register' and active_register:
            active_register.status = 'CLOSED'
            active_register.closed_at = timezone.now()
            completed_sales = active_register.sales.filter(status='COMPLETED')
            cash_sales = sum(s.total_amount for s in completed_sales if s.payment_method == 'Efectivo')
            active_register.final_amount_system = active_register.initial_amount + cash_sales
            active_register.final_amount_cash = active_register.initial_amount + cash_sales
            active_register.save()
            messages.success(request, "¡Caja cerrada correctamente!")
            return redirect('pos_terminal')

        client_id = request.POST.get('client_id')
        staff_id = request.POST.get('staff_id')
        service_id = request.POST.get('service_id')
        product_id = request.POST.get('product_id')
        post_app_id = request.POST.get('appointment_id')
        payment_method = request.POST.get('payment_method', 'Efectivo')
        tip_amount = parse_decimal(request.POST.get('tip_amount'), '0.00')
        discount_amount = parse_decimal(request.POST.get('discount_amount'), '0.00')

        # Fallback if processing an appointment checkout without explicit service selection
        if post_app_id and not service_id and not product_id:
            app_obj = Appointment.objects.filter(id=post_app_id, business=business).first()
            if app_obj:
                service_id = str(app_obj.service_id)
                if not client_id:
                    client_id = str(app_obj.client_id)
                if not staff_id:
                    staff_id = str(app_obj.staff_id)

        if not service_id and not product_id:
            messages.error(request, "Debes seleccionar al menos un Servicio o un Producto para procesar la venta.")
            return redirect('pos_terminal')
        
        client = Client.objects.filter(id=client_id).first() if client_id else None
        staff = StaffMember.objects.filter(id=staff_id).first() if staff_id else None
        
        with transaction.atomic():
            # Auto-open cash register if none is active
            if not active_register:
                default_user = request.user if (request.user and request.user.is_authenticated) else (business.users.first() if business else None)
                active_register = CashRegister.objects.create(
                    business=business,
                    opened_by=default_user,
                    initial_amount=Decimal('0.00'),
                    status='OPEN'
                )

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
                srv = Service.objects.filter(id=service_id).first()
                if srv:
                    subtotal += srv.price
                    SaleItem.objects.create(
                        sale=sale,
                        item_type='SERVICE',
                        service=srv,
                        unit_price=srv.price,
                        quantity=1,
                        total_price=srv.price
                    )
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
                prod = Product.objects.filter(id=product_id).first()
                if prod:
                    subtotal += prod.sale_price
                    SaleItem.objects.create(
                        sale=sale,
                        item_type='PRODUCT',
                        product=prod,
                        unit_price=prod.sale_price,
                        quantity=1,
                        total_price=prod.sale_price
                    )
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
            
            if client:
                client.total_spent += total
                client.save()

            if post_app_id:
                app_obj = Appointment.objects.filter(id=post_app_id, business=business).first()
                if app_obj:
                    app_obj.status = 'COMPLETED'
                    app_obj.save()

            # Record cash movement in cash register
            CashMovement.objects.create(
                cash_register=active_register,
                movement_type='INCOME',
                amount=total,
                concept=f"Venta POS #{str(sale.id)[:8]} ({payment_method})"
            )

            messages.success(request, f"¡Venta #{str(sale.id)[:8]} registrada correctamente por {business.currency}{total}!")

            if client:
                request.session['completed_sale_client_id'] = str(client.id)
                request.session['completed_sale_client_name'] = client.full_name
                request.session['completed_sale_service_id'] = str(service_id) if service_id else ''
                request.session['completed_sale_staff_id'] = str(staff_id) if staff_id else ''

        return redirect('pos_terminal')

    completed_rebook_client = None
    if 'completed_sale_client_id' in request.session:
        completed_rebook_client = {
            'client_id': request.session.pop('completed_sale_client_id'),
            'client_name': request.session.pop('completed_sale_client_name', 'Cliente'),
            'service_id': request.session.pop('completed_sale_service_id', ''),
            'staff_id': request.session.pop('completed_sale_staff_id', ''),
        }

    if active_register:
        completed_sales = list(active_register.sales.filter(status='COMPLETED'))
        active_register.sales_count = len(completed_sales)
        active_register.total_sales = sum(s.total_amount for s in completed_sales)
        active_register.cash_total = sum(s.total_amount for s in completed_sales if s.payment_method == 'Efectivo')
        active_register.expected_cash = active_register.initial_amount + active_register.cash_total

    recent_sales = Sale.objects.filter(business=business).select_related('client', 'staff', 'cash_register').prefetch_related('items', 'items__service', 'items__product')[:15]

    return render(request, 'pos/terminal.html', {
        'business': business,
        'active_register': active_register,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'products': products,
        'pending_appointments': pending_appointments,
        'appointment': appointment,
        'selected_client_id': selected_client_id,
        'selected_service_id': selected_service_id,
        'selected_staff_id': selected_staff_id,
        'completed_rebook_client': completed_rebook_client,
        'recent_sales': recent_sales,
    })

@ensure_csrf_cookie
def cash_register_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    registers = list(CashRegister.objects.filter(business=business).order_by('-opened_at'))
    active_register = next((r for r in registers if r.status == 'OPEN'), None)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'open':
            initial = parse_decimal(request.POST.get('initial_amount'), '0.00')
            CashRegister.objects.create(
                business=business,
                opened_by=request.user if (request.user and request.user.is_authenticated) else (business.users.first() if business else None),
                initial_amount=initial,
                status='OPEN'
            )
            messages.success(request, f"¡Caja abierta correctamente con monto inicial {business.currency}{initial}!")
        elif action == 'close' and active_register:
            active_register.status = 'CLOSED'
            active_register.closed_at = timezone.now()
            # Calculate final amounts for close record
            completed_sales = active_register.sales.filter(status='COMPLETED')
            cash_sales = sum(s.total_amount for s in completed_sales if s.payment_method == 'Efectivo')
            active_register.final_amount_system = active_register.initial_amount + cash_sales
            active_register.final_amount_cash = active_register.initial_amount + cash_sales
            active_register.save()
            messages.success(request, "¡Caja cerrada correctamente!")
        return redirect('cash_register')

    # Filter by specific register if requested in GET
    filter_register_id = request.GET.get('register_id', '')
    selected_filter_register = None
    if filter_register_id:
        selected_filter_register = next((r for r in registers if str(r.id) == filter_register_id), None)

    # Compute summary metrics and attach pre-fetched sales list for each cash register shift
    for reg in registers:
        reg_sales = list(reg.sales.filter(status='COMPLETED').select_related('client', 'staff').prefetch_related('items', 'items__service', 'items__product'))
        reg.sales_list = reg_sales
        reg.total_sales = sum(s.total_amount for s in reg_sales)
        reg.sales_count = len(reg_sales)
        reg.cash_total = sum(s.total_amount for s in reg_sales if s.payment_method == 'Efectivo')
        reg.card_total = sum(s.total_amount for s in reg_sales if s.payment_method == 'Tarjeta')
        reg.qr_total = sum(s.total_amount for s in reg_sales if 'QR' in s.payment_method or 'Mercado' in s.payment_method)
        reg.transfer_total = sum(s.total_amount for s in reg_sales if s.payment_method == 'Transferencia')
        reg.expected_cash = reg.initial_amount + reg.cash_total

    sales_query = Sale.objects.filter(business=business)
    if selected_filter_register:
        sales_query = sales_query.filter(cash_register=selected_filter_register)

    recent_sales = sales_query.select_related('client', 'staff', 'cash_register').prefetch_related('items', 'items__service', 'items__product')[:50]

    return render(request, 'pos/cash_register.html', {
        'business': business,
        'registers': registers,
        'active_register': active_register,
        'recent_sales': recent_sales,
        'filter_register_id': filter_register_id,
        'selected_filter_register': selected_filter_register,
    })

@ensure_csrf_cookie
def api_quick_create_client_view(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    business = getattr(request, 'current_business', None) or Business.objects.first()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone_prefix = request.POST.get('phone_prefix', '+54').strip()
    phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    tax_id = request.POST.get('tax_id', '').strip()

    if not first_name:
        return JsonResponse({'success': False, 'error': 'El nombre del cliente es obligatorio.'}, status=400)

    if phone_number.startswith('+'):
        phone = phone_number
    else:
        clean_num = ''.join(filter(str.isdigit, phone_number))
        phone = f"{phone_prefix}{clean_num}" if clean_num else "Sin teléfono"

    try:
        client = Client.objects.create(
            business=business,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email if email else None,
            tax_id=tax_id if tax_id else None,
            status='ACTIVE'
        )
        return JsonResponse({
            'success': True,
            'client_id': client.id,
            'full_name': client.full_name,
            'phone': client.phone or ''
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def export_sales_excel(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    sales = Sale.objects.filter(business=business, status='COMPLETED').select_related('client', 'staff', 'cash_register').prefetch_related('items')
    
    filter_reg_id = request.GET.get('register_id')
    if filter_reg_id:
        sales = sales.filter(cash_register_id=filter_reg_id)
        
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"reporte_ventas_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['REPORTE DE VENTAS POS', business.name if business else ''])
    writer.writerow(['Fecha de Generación', timezone.now().strftime('%d/%m/%Y %H:%M hs')])
    writer.writerow([])
    writer.writerow(['ID Venta', 'Fecha / Hora', 'Turno Caja ID', 'Cliente', 'Profesional', 'Ítems / Detalle', 'Método Pago', 'Total'])
    
    for s in sales:
        client_name = s.client.full_name if s.client else 'Cliente Mostrador'
        staff_name = s.staff.full_name if s.staff else '-'
        reg_id = f"#{str(s.cash_register.id)[:8]}" if s.cash_register else '-'
        items_str = ", ".join([f"{item.item_name} ({item.quantity})" for item in s.items.all()]) or 'Cobro de servicio'
        writer.writerow([
            f"#{str(s.id)[:8]}",
            s.created_at.strftime('%d/%m/%Y %H:%M'),
            reg_id,
            client_name,
            staff_name,
            items_str,
            s.payment_method,
            f"{business.currency}{s.total_amount:.2f}"
        ])
        
    return response

def export_sales_pdf(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    sales = Sale.objects.filter(business=business, status='COMPLETED').select_related('client', 'staff', 'cash_register').prefetch_related('items')[:100]
    
    filter_reg_id = request.GET.get('register_id')
    selected_reg = None
    if filter_reg_id:
        sales = sales.filter(cash_register_id=filter_reg_id)
        selected_reg = CashRegister.objects.filter(id=filter_reg_id).first()
        
    total_sales = sum(s.total_amount for s in sales)

    return render(request, 'analytics/pdf_report.html', {
        'business': business,
        'report_title': f"Reporte de Ventas POS {'(Turno #' + str(selected_reg.id)[:8] + ')' if selected_reg else ''}",
        'generated_at': timezone.now(),
        'total_sales': total_sales,
        'total_expenses': Decimal('0.00'),
        'net_profit': total_sales,
        'recent_sales': sales,
    })


