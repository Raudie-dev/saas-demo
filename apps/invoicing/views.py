import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import models

from apps.business.models import Business, StaffMember
from apps.invoicing.models import Invoice, InvoiceItem, Quote, QuoteItem, Expense, ExpenseCategory, PaymentPlan, PaymentInstallment
from apps.crm.models import Client, Supplier
from apps.agenda.models import Service
from apps.inventory.models import Product
from apps.core.utils import parse_decimal

@login_required
def invoice_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    from django.db.models import Q
    from decimal import Decimal

    status_filter = request.GET.get('status', 'ALL')
    search_query = request.GET.get('q', '').strip()

    base_invoices = Invoice.objects.filter(business=business).select_related(
        'client', 'sale', 'payment_plan', 'installment', 'quote'
    ).order_by('-issue_date', '-created_at')

    # Métricas enfocadas en Facturación & Gastos
    total_invoiced_amount = sum((inv.total_amount for inv in base_invoices.filter(status='PAID')), Decimal('0.00'))
    total_pending_amount = sum((inv.total_amount for inv in base_invoices.filter(status__in=['ISSUED', 'DRAFT', 'PARTIAL'])), Decimal('0.00'))
    
    expenses_qs = Expense.objects.filter(business=business, status='PAID')
    total_expenses_amount = sum((exp.amount for exp in expenses_qs), Decimal('0.00'))
    net_balance = total_invoiced_amount - total_expenses_amount

    # Filtrado
    filtered_qs = base_invoices
    if search_query:
        filtered_qs = filtered_qs.filter(
            Q(invoice_number__icontains=search_query) |
            Q(client__full_name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    if status_filter == 'PAID':
        filtered_qs = filtered_qs.filter(status='PAID')
    elif status_filter == 'PENDING':
        filtered_qs = filtered_qs.filter(status__in=['ISSUED', 'DRAFT', 'PARTIAL'])

    from django.core.paginator import Paginator
    inv_paginator = Paginator(filtered_qs, 15)
    invoices_page_obj = inv_paginator.get_page(request.GET.get('page', 1))

    return render(request, 'invoicing/invoice_list.html', {
        'business': business,
        'invoices': invoices_page_obj,
        'page_obj': invoices_page_obj,
        'total_invoiced_amount': total_invoiced_amount,
        'total_pending_amount': total_pending_amount,
        'total_expenses_amount': total_expenses_amount,
        'net_balance': net_balance,
        'status_filter': status_filter,
        'search_query': search_query,
    })

@login_required
def invoice_detail_view(request, invoice_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    invoice = get_object_or_404(Invoice, id=invoice_id, business=business)
    return render(request, 'invoicing/invoice_detail.html', {'business': business, 'invoice': invoice})

@login_required
def expense_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    expenses = Expense.objects.filter(business=business).select_related('category', 'supplier').order_by('-issue_date') if business else []

    from django.core.paginator import Paginator
    exp_paginator = Paginator(expenses, 10)
    expenses_page_obj = exp_paginator.get_page(request.GET.get('page', 1))
    
    return render(request, 'invoicing/expense_list.html', {
        'business': business,
        'expenses': expenses_page_obj,
        'page_obj': expenses_page_obj,
    })

@login_required
def expense_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    categories = ExpenseCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        concept = request.POST.get('concept', '').strip()
        amount = parse_decimal(request.POST.get('amount'), '0.00')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        status = request.POST.get('status', 'PAID')
        notes = request.POST.get('notes', '')
        issue_date = request.POST.get('issue_date') or timezone.now().date()
        
        category = ExpenseCategory.objects.filter(id=category_id, business=business).first() if category_id else None
        supplier = Supplier.objects.filter(id=supplier_id, business=business).first() if supplier_id else None
        
        Expense.objects.create(
            business=business,
            category=category,
            supplier=supplier,
            concept=concept,
            amount=amount,
            issue_date=issue_date,
            status=status,
            notes=notes
        )
        return redirect('expense_list')
        
    return render(request, 'invoicing/expense_form.html', {
        'business': business,
        'expense': None,
        'categories': categories,
        'suppliers': suppliers,
        'title': 'Registrar Nuevo Gasto'
    })

@login_required
def expense_edit_view(request, expense_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    expense = get_object_or_404(Expense, id=expense_id, business=business)
    categories = ExpenseCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        expense.concept = request.POST.get('concept', '').strip()
        expense.amount = parse_decimal(request.POST.get('amount'), '0.00')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        expense.status = request.POST.get('status', 'PAID')
        expense.notes = request.POST.get('notes', '')
        issue_date = request.POST.get('issue_date')
        if issue_date:
            expense.issue_date = issue_date
        
        expense.category = ExpenseCategory.objects.filter(id=category_id, business=business).first() if category_id else None
        expense.supplier = Supplier.objects.filter(id=supplier_id, business=business).first() if supplier_id else None
        expense.save()
        return redirect('expense_list')
        
    return render(request, 'invoicing/expense_form.html', {
        'business': business,
        'expense': expense,
        'categories': categories,
        'suppliers': suppliers,
        'title': f'Editar Gasto: {expense.concept}'
    })

@login_required
def export_expenses_excel(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    expenses = Expense.objects.filter(business=business).select_related('category', 'supplier')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"reporte_gastos_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['REPORTE DE GASTOS OPERATIVOS', business.name if business else ''])
    writer.writerow(['Fecha de Generación', timezone.now().strftime('%d/%m/%Y %H:%M hs')])
    writer.writerow([])
    writer.writerow(['ID Gasto', 'Fecha', 'Concepto', 'Categoría', 'Proveedor', 'Estado', 'Monto'])
    
    for exp in expenses:
        cat_name = exp.category.name if exp.category else 'General'
        sup_name = exp.supplier.company_name if exp.supplier else '-'
        writer.writerow([
            f"#{str(exp.id)[:8]}",
            exp.created_at.strftime('%d/%m/%Y %H:%M'),
            exp.concept,
            cat_name,
            sup_name,
            exp.get_status_display(),
            f"{business.currency}{exp.amount:.2f}"
        ])
        
    return response

@login_required
def export_expenses_pdf(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    expenses = Expense.objects.filter(business=business).select_related('category', 'supplier')
    total_exp = sum(e.amount for e in expenses)

    return render(request, 'analytics/pdf_report.html', {
        'business': business,
        'report_title': 'Reporte de Gastos y Egresos Operativos',
        'generated_at': timezone.now(),
        'total_sales': Decimal('0.00'),
        'total_expenses': total_exp,
        'net_profit': -total_exp,
    })


# ==========================================
# GESTIÓN INTEGRAL DE COTIZACIONES / PRESUPUESTOS
# (PRECIO FIJO, POR HORAS Y POR DESEMPEÑO)
# ==========================================

@login_required
def quote_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    status_filter = request.GET.get('status', '').strip()
    pricing_filter = request.GET.get('pricing_type', '').strip()
    search_query = request.GET.get('q', '').strip()

    quotes = Quote.objects.filter(business=business).select_related('client', 'converted_to_invoice')

    if status_filter:
        quotes = quotes.filter(status=status_filter)
    if pricing_filter:
        quotes = quotes.filter(pricing_type=pricing_filter)
    if search_query:
        quotes = quotes.filter(
            models.Q(quote_number__icontains=search_query) |
            models.Q(client__first_name__icontains=search_query) |
            models.Q(client__last_name__icontains=search_query)
        )

    quotes = quotes.order_by('-date', '-created_at')

    # Métricas resumen
    all_biz_quotes = Quote.objects.filter(business=business)
    total_quotes_count = all_biz_quotes.count()
    accepted_amount = sum(q.total_amount for q in all_biz_quotes.filter(status='ACCEPTED'))
    pending_amount = sum(q.total_amount for q in all_biz_quotes.filter(status__in=['DRAFT', 'SENT']))
    total_hours_quoted = sum(q.estimated_hours for q in all_biz_quotes if q.estimated_hours)

    from django.core.paginator import Paginator
    paginator = Paginator(quotes, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'invoicing/quote_list.html', {
        'business': business,
        'quotes': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'pricing_filter': pricing_filter,
        'search_query': search_query,
        'total_quotes_count': total_quotes_count,
        'accepted_amount': accepted_amount,
        'pending_amount': pending_amount,
        'total_hours_quoted': total_hours_quoted,
        'pricing_type_choices': Quote.PRICING_TYPE_CHOICES,
    })


@login_required
def quote_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        client = get_object_or_404(Client, id=client_id, business=business)

        quote_date = request.POST.get('date') or timezone.now().date()
        valid_until = request.POST.get('valid_until') or (timezone.now() + timezone.timedelta(days=15)).date()
        status = request.POST.get('status', 'SENT')
        pricing_type = request.POST.get('pricing_type', 'FIXED')
        hourly_rate = parse_decimal(request.POST.get('hourly_rate'), '0.00')
        performance_terms = request.POST.get('performance_terms', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Generar número de cotización correlativo
        today_year = timezone.now().year
        count = Quote.objects.filter(business=business).count() + 1
        quote_number = f"COT-{today_year}-{count:04d}"

        quote = Quote.objects.create(
            business=business,
            client=client,
            quote_number=quote_number,
            date=quote_date,
            valid_until=valid_until,
            status=status,
            pricing_type=pricing_type,
            hourly_rate=hourly_rate,
            performance_terms=performance_terms,
            notes=notes,
            subtotal=Decimal('0.00'),
            tax_amount=Decimal('0.00'),
            total_amount=Decimal('0.00')
        )

        item_types = request.POST.getlist('item_type[]')
        descriptions = request.POST.getlist('item_description[]')
        quantities = request.POST.getlist('item_quantity[]')
        unit_labels = request.POST.getlist('item_unit_label[]')
        prices = request.POST.getlist('item_unit_price[]')
        kpis = request.POST.getlist('item_performance_kpi[]')

        subtotal = Decimal('0.00')
        total_hours = Decimal('0.00')

        for i, desc in enumerate(descriptions):
            desc = desc.strip()
            if not desc:
                continue
            itype = item_types[i] if i < len(item_types) else 'FIXED'
            qty_str = quantities[i] if i < len(quantities) else '1'
            qty = parse_decimal(qty_str, '1.00')
            ulabel = (unit_labels[i] if i < len(unit_labels) else 'unid').strip() or 'unid'
            price_str = prices[i] if i < len(prices) else '0.00'
            price = parse_decimal(price_str, '0.00')
            kpi = (kpis[i] if i < len(kpis) else '').strip()

            line_total = qty * price
            subtotal += line_total

            if itype == 'HOURLY':
                total_hours += qty

            QuoteItem.objects.create(
                quote=quote,
                item_type=itype,
                description=desc,
                quantity=qty,
                unit_label=ulabel,
                unit_price=price,
                total_price=line_total,
                performance_kpi=kpi
            )

        tax_percent = parse_decimal(request.POST.get('tax_percent', '0'), '0')
        tax_amount = (subtotal * tax_percent) / Decimal('100.0') if tax_percent > 0 else Decimal('0.00')
        total_amount = subtotal + tax_amount

        quote.subtotal = subtotal
        quote.tax_amount = tax_amount
        quote.total_amount = total_amount
        quote.estimated_hours = total_hours if total_hours > 0 else parse_decimal(request.POST.get('estimated_hours'), '0.00')
        quote.save(update_fields=['subtotal', 'tax_amount', 'total_amount', 'estimated_hours'])

        return redirect('quote_detail', quote_id=quote.id)

    # Pre-llenar cliente si viene en URL
    preselected_client_id = request.GET.get('client_id')
    preselected_pricing_type = request.GET.get('pricing_type', 'FIXED')

    services = Service.objects.filter(business=business, is_active=True).order_by('name')
    products = Product.objects.filter(business=business, is_active=True).order_by('name')

    return render(request, 'invoicing/quote_form.html', {
        'business': business,
        'clients': clients,
        'services': services,
        'products': products,
        'quote': None,
        'preselected_client_id': preselected_client_id,
        'preselected_pricing_type': preselected_pricing_type,
        'today': timezone.now().date(),
        'default_valid': (timezone.now() + timezone.timedelta(days=15)).date(),
        'pricing_type_choices': Quote.PRICING_TYPE_CHOICES,
        'item_type_choices': QuoteItem.ITEM_TYPE_CHOICES,
    })


@login_required
def quote_edit_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        if client_id:
            quote.client = get_object_or_404(Client, id=client_id, business=business)

        quote.date = request.POST.get('date') or quote.date
        quote.valid_until = request.POST.get('valid_until') or quote.valid_until
        quote.status = request.POST.get('status', quote.status)
        quote.pricing_type = request.POST.get('pricing_type', quote.pricing_type)
        quote.hourly_rate = parse_decimal(request.POST.get('hourly_rate'), str(quote.hourly_rate))
        quote.performance_terms = request.POST.get('performance_terms', '').strip()
        quote.notes = request.POST.get('notes', '').strip()

        quote.items.all().delete()

        item_types = request.POST.getlist('item_type[]')
        descriptions = request.POST.getlist('item_description[]')
        quantities = request.POST.getlist('item_quantity[]')
        unit_labels = request.POST.getlist('item_unit_label[]')
        prices = request.POST.getlist('item_unit_price[]')
        kpis = request.POST.getlist('item_performance_kpi[]')

        subtotal = Decimal('0.00')
        total_hours = Decimal('0.00')

        for i, desc in enumerate(descriptions):
            desc = desc.strip()
            if not desc:
                continue
            itype = item_types[i] if i < len(item_types) else 'FIXED'
            qty_str = quantities[i] if i < len(quantities) else '1'
            qty = parse_decimal(qty_str, '1.00')
            ulabel = (unit_labels[i] if i < len(unit_labels) else 'unid').strip() or 'unid'
            price_str = prices[i] if i < len(prices) else '0.00'
            price = parse_decimal(price_str, '0.00')
            kpi = (kpis[i] if i < len(kpis) else '').strip()

            line_total = qty * price
            subtotal += line_total

            if itype == 'HOURLY':
                total_hours += qty

            QuoteItem.objects.create(
                quote=quote,
                item_type=itype,
                description=desc,
                quantity=qty,
                unit_label=ulabel,
                unit_price=price,
                total_price=line_total,
                performance_kpi=kpi
            )

        tax_percent = parse_decimal(request.POST.get('tax_percent', '0'), '0')
        tax_amount = (subtotal * tax_percent) / Decimal('100.0') if tax_percent > 0 else Decimal('0.00')
        total_amount = subtotal + tax_amount

        quote.subtotal = subtotal
        quote.tax_amount = tax_amount
        quote.total_amount = total_amount
        quote.estimated_hours = total_hours if total_hours > 0 else parse_decimal(request.POST.get('estimated_hours'), str(quote.estimated_hours))
        quote.save()

        return redirect('quote_detail', quote_id=quote.id)

    services = Service.objects.filter(business=business, is_active=True).order_by('name')
    products = Product.objects.filter(business=business, is_active=True).order_by('name')

    return render(request, 'invoicing/quote_form.html', {
        'business': business,
        'clients': clients,
        'services': services,
        'products': products,
        'quote': quote,
        'items': quote.items.all(),
        'today': quote.date,
        'default_valid': quote.valid_until,
        'pricing_type_choices': Quote.PRICING_TYPE_CHOICES,
        'item_type_choices': QuoteItem.ITEM_TYPE_CHOICES,
    })


@login_required
def quote_detail_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote.objects.select_related('client', 'business'), id=quote_id, business=business)
    items = quote.items.all()

    # Preparar texto de WhatsApp enriquecido
    client_phone = (quote.client.phone or '').replace(' ', '').replace('-', '').replace('+', '')
    
    lines = []
    for it in items:
        if it.item_type == 'HOURLY':
            lines.append(f"• {it.description} ({it.quantity} hrs @ {business.currency}{it.unit_price}/hr): {business.currency}{it.total_price:,.2f}")
        elif it.item_type == 'PERFORMANCE':
            kpi_txt = f" [Meta: {it.performance_kpi}]" if it.performance_kpi else ""
            lines.append(f"• {it.description}{kpi_txt}: {business.currency}{it.total_price:,.2f}")
        else:
            lines.append(f"• {it.description} x{it.quantity} {it.unit_label}: {business.currency}{it.total_price:,.2f}")
            
    items_summary = "\n".join(lines)
    
    pricing_info = ""
    if quote.pricing_type == 'HOURLY':
        pricing_info = f"\n*Modalidad:* Por Horas ({quote.estimated_hours} hrs estimadas @ {business.currency}{quote.hourly_rate}/hr)"
    elif quote.pricing_type == 'PERFORMANCE':
        pricing_info = f"\n*Modalidad:* Por Desempeño / Resultados"
    elif quote.pricing_type == 'HYBRID':
        pricing_info = f"\n*Modalidad:* Mixta (Horas + Entregables + Desempeño)"

    whatsapp_msg = (
        f"Hola {quote.client.first_name}! Te compartimos la cotización *#{quote.quote_number}* de *{business.name}*:\n"
        f"{pricing_info}\n\n"
        f"{items_summary}\n\n"
        f"*Total:* {business.currency}{quote.total_amount:,.2f}\n"
        f"*Válido hasta:* {quote.valid_until.strftime('%d/%m/%Y')}\n\n"
        f"Quedamos atentos a cualquier consulta para avanzar con el proyecto!"
    )
    import urllib.parse
    whatsapp_url = f"https://wa.me/{client_phone}?text={urllib.parse.quote(whatsapp_msg)}" if client_phone else None

    # Conteo de tipos de ítems
    hourly_items_count = items.filter(item_type='HOURLY').count()
    performance_items_count = items.filter(item_type='PERFORMANCE').count()

    # Vínculos existentes originados desde esta cotización
    linked_project = quote.projects.first()
    linked_payment_plan = quote.payment_plans.first()
    
    from apps.agenda.models import Service, Appointment
    linked_appointments = Appointment.objects.filter(business=business, client=quote.client, notes__icontains=quote.quote_number).order_by('-date')
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')
    services = Service.objects.filter(business=business, is_active=True).order_by('name')

    return render(request, 'invoicing/quote_detail.html', {
        'business': business,
        'quote': quote,
        'items': items,
        'whatsapp_url': whatsapp_url,
        'hourly_items_count': hourly_items_count,
        'performance_items_count': performance_items_count,
        'linked_project': linked_project,
        'linked_payment_plan': linked_payment_plan,
        'linked_appointments': linked_appointments,
        'staff_members': staff_members,
        'services': services,
    })


@login_required
def quote_status_update_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Quote.STATUS_CHOICES):
            quote.status = new_status
            quote.save(update_fields=['status'])

    return redirect('quote_detail', quote_id=quote.id)


@login_required
def quote_convert_to_invoice_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)

    if not quote.converted_to_invoice:
        today_year = timezone.now().year
        count = Invoice.objects.filter(business=business).count() + 1
        invoice_number = f"FAC-{today_year}-{count:04d}"

        invoice = Invoice.objects.create(
            business=business,
            client=quote.client,
            quote=quote,
            invoice_number=invoice_number,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=10),
            status='ISSUED',
            subtotal=quote.subtotal,
            tax_amount=quote.tax_amount,
            total_amount=quote.total_amount,
            notes=f"Factura generada automáticamente desde Cotización #{quote.quote_number} (Modalidad: {quote.get_pricing_type_display()})."
        )

        for item in quote.items.all():
            qty_int = int(round(item.quantity)) if item.quantity else 1
            unit_display = f" ({item.quantity} {item.unit_label})" if item.item_type != 'FIXED' else ""
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"{item.description}{unit_display}",
                quantity=max(1, qty_int),
                unit_price=item.unit_price,
                total_price=item.total_price
            )

        quote.status = 'ACCEPTED'
        quote.converted_to_invoice = invoice
        quote.save(update_fields=['status', 'converted_to_invoice'])

        return redirect('invoice_detail', invoice_id=invoice.id)

    return redirect('invoice_detail', invoice_id=quote.converted_to_invoice.id)


@login_required
def quote_charge_view(request, quote_id):
    """Registra el cobro completo de una cotización y genera su factura pagada e ingresos oficiales."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    if request.method == 'POST':
        from apps.invoicing.services import charge_and_invoice_quote
        payment_method = request.POST.get('payment_method', 'Transferencia')
        reference = request.POST.get('reference', '').strip()
        paid_date = request.POST.get('paid_date') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()

        invoice = charge_and_invoice_quote(
            quote=quote,
            payment_method=payment_method,
            reference=reference,
            paid_date=paid_date,
            notes=notes
        )
        return redirect('invoice_detail', invoice_id=invoice.id)

    return redirect('quote_detail', quote_id=quote.id)


@login_required
def invoice_charge_view(request, invoice_id):
    """Permite registrar el cobro de una factura emitida o pendiente, marcándola como Pagada."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    invoice = get_object_or_404(Invoice, id=invoice_id, business=business)
    if request.method == 'POST':
        from apps.invoicing.services import mark_invoice_as_paid
        payment_method = request.POST.get('payment_method', 'Transferencia')
        reference = request.POST.get('reference', '').strip()
        paid_date = request.POST.get('paid_date') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()

        mark_invoice_as_paid(
            invoice=invoice,
            payment_method=payment_method,
            reference=reference,
            paid_date=paid_date,
            notes=notes
        )
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('invoice_list')

    return redirect('invoice_detail', invoice_id=invoice.id)


@login_required
def quote_convert_to_project_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    from apps.projects.models import Project, ProjectTask

    # Crear proyecto heredando horas y modalidad
    project = Project.objects.create(
        business=business,
        client=quote.client,
        quote=quote,
        name=f"Proyecto: {quote.client.full_name} (#{quote.quote_number})",
        description=(
            f"Proyecto iniciado desde Cotización #{quote.quote_number}.\n"
            f"Modalidad: {quote.get_pricing_type_display()}.\n"
            f"Horas Estimadas: {quote.estimated_hours} hrs.\n\n"
            f"Condiciones comerciales:\n{quote.notes or 'Sin notas'}\n\n"
            f"Términos de Desempeño / Bonos:\n{quote.performance_terms or 'Sin términos de desempeño adicionales'}"
        ),
        project_type='SOCIAL_MEDIA' if business.is_marketing_agency else 'OTHER',
        status='IN_PROGRESS',
        pricing_type=quote.pricing_type,
        estimated_hours=quote.estimated_hours,
        hourly_rate=quote.hourly_rate,
        start_date=timezone.now().date(),
        due_date=quote.valid_until,
        budget=quote.total_amount,
        progress_percent=0
    )

    # Crear tareas iniciales basadas en los ítems de la cotización
    for item in quote.items.all():
        task_hours = item.quantity if item.item_type == 'HOURLY' else Decimal('0.00')
        desc_extra = f" [{item.item_type}]: {item.quantity} {item.unit_label}"
        if item.performance_kpi:
            desc_extra += f" | Meta de Desempeño: {item.performance_kpi}"

        ProjectTask.objects.create(
            project=project,
            title=f"Entregable: {item.description}",
            description=f"Alcance especificado en cotización: {desc_extra}",
            status='TODO',
            priority='MEDIUM',
            due_date=project.due_date,
            estimated_hours=task_hours
        )

    quote.status = 'ACCEPTED'
    quote.save(update_fields=['status'])

    return redirect('project_detail', project_id=project.id)


@login_required
def quote_delete_view(request, quote_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    if request.method == 'POST':
        quote.delete()
        return redirect('quote_list')

    return redirect('quote_detail', quote_id=quote.id)


# ==============================================================
# DERIVACIÓN DE COTIZACIONES (A CITAS & PLANES DE PAGO)
# ==============================================================

@login_required
def quote_convert_to_appointment_view(request, quote_id):
    """Deriva una cotización a una cita en la agenda del negocio."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    from apps.agenda.models import Appointment, Service
    from apps.business.models import StaffMember

    if request.method == 'POST':
        staff_id = request.POST.get('staff_id')
        staff = get_object_or_404(StaffMember, id=staff_id, business=business)
        service_id = request.POST.get('service_id')
        service = Service.objects.filter(id=service_id, business=business).first() if service_id else None

        date = request.POST.get('date') or timezone.now().date()
        start_time = request.POST.get('start_time') or '10:00'
        end_time = request.POST.get('end_time') or '11:00'
        deposit_amount = parse_decimal(request.POST.get('deposit_amount'), '0.00')

        appointment = Appointment.objects.create(
            business=business,
            client=quote.client,
            staff=staff,
            service=service,
            date=date,
            start_time=start_time,
            end_time=end_time,
            status='CONFIRMED',
            total_price=quote.total_amount,
            deposit_amount=deposit_amount,
            notes=(
                f"Cita derivada de Presupuesto #{quote.quote_number}.\n"
                f"Ítems cotizados: {quote.items.count()} entregables/servicios.\n"
                f"{quote.notes or ''}"
            )
        )

        quote.status = 'ACCEPTED'
        quote.save(update_fields=['status'])

        return redirect('quote_detail', quote_id=quote.id)

    return redirect('quote_detail', quote_id=quote.id)


@login_required
def quote_create_payment_plan_view(request, quote_id):
    """Crea un plan de cobro con cuotas e hitos a partir de la cotización."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    quote = get_object_or_404(Quote, id=quote_id, business=business)
    linked_project = quote.projects.first()

    if request.method == 'POST':
        plan_type = request.POST.get('plan_type', '2_PARTS') # 2_PARTS, 3_PARTS, CUSTOM
        notes = request.POST.get('notes', '').strip()

        plan = PaymentPlan.objects.create(
            business=business,
            client=quote.client,
            quote=quote,
            project=linked_project,
            title=f"Plan de Cobros: Cotización #{quote.quote_number} - {quote.client.full_name}",
            total_amount=quote.total_amount,
            notes=notes or f"Plan generado automáticamente desde Presupuesto #{quote.quote_number}"
        )

        if plan_type == '2_PARTS':
            # 50% anticipo al iniciar y 50% contra entrega
            part1 = (quote.total_amount * Decimal('0.50')).quantize(Decimal('0.01'))
            part2 = quote.total_amount - part1
            PaymentInstallment.objects.create(
                plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                installment_number=1, concept="Anticipo 50% al Iniciar", amount=part1,
                due_date=timezone.now().date(), status='PENDING'
            )
            PaymentInstallment.objects.create(
                plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                installment_number=2, concept="Finiquito 50% Contra Entrega Final", amount=part2,
                due_date=quote.valid_until, status='PENDING'
            )
        elif plan_type == '3_PARTS':
            # 40% inicio, 30% intermedio, 30% entrega
            p1 = (quote.total_amount * Decimal('0.40')).quantize(Decimal('0.01'))
            p2 = (quote.total_amount * Decimal('0.30')).quantize(Decimal('0.01'))
            p3 = quote.total_amount - p1 - p2
            mid_date = timezone.now().date() + timezone.timedelta(days=15)
            PaymentInstallment.objects.create(
                plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                installment_number=1, concept="Anticipo 40% Inicio de Proyecto", amount=p1,
                due_date=timezone.now().date(), status='PENDING'
            )
            PaymentInstallment.objects.create(
                plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                installment_number=2, concept="Hito 30% Aprobación de Entregas Parciales", amount=p2,
                due_date=mid_date, status='PENDING'
            )
            PaymentInstallment.objects.create(
                plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                installment_number=3, concept="Finiquito 30% Entrega y Cierre", amount=p3,
                due_date=quote.valid_until, status='PENDING'
            )
        else:
            # Cuotas personalizadas
            concepts = request.POST.getlist('concept[]')
            amounts = request.POST.getlist('amount[]')
            due_dates = request.POST.getlist('due_date[]')
            for idx, c in enumerate(concepts):
                c_amt = parse_decimal(amounts[idx] if idx < len(amounts) else '0.00', '0.00')
                c_dt = due_dates[idx] if (idx < len(due_dates) and due_dates[idx]) else timezone.now().date()
                PaymentInstallment.objects.create(
                    plan=plan, business=business, client=quote.client, project=linked_project, quote=quote,
                    installment_number=idx + 1, concept=c or f"Cuota #{idx + 1}", amount=c_amt,
                    due_date=c_dt, status='PENDING'
                )

        quote.status = 'ACCEPTED'
        quote.save(update_fields=['status'])

        return redirect('payment_plan_list')

    return redirect('quote_detail', quote_id=quote.id)


# ==============================================================
# MÓDULO DE COBRANZAS, CUOTAS & PLANIFICACIÓN FINANCIERA FUTURA
# ==============================================================

@login_required
def payment_plan_list_view(request):
    """Módulo de cobranzas independiente del POS que impacta las finanzas."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    status_filter = request.GET.get('status', 'ALL').strip()
    search_query = request.GET.get('q', '').strip()
    client_id = request.GET.get('client_id', '').strip()
    project_id = request.GET.get('project_id', '').strip()

    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    # Cuotas base
    installments_qs = PaymentInstallment.objects.filter(business=business).select_related('client', 'project', 'plan', 'quote', 'invoice', 'sale__invoice')

    if status_filter == 'PENDING':
        installments_qs = installments_qs.filter(status='PENDING', due_date__gte=today)
    elif status_filter == 'OVERDUE':
        installments_qs = installments_qs.filter(status__in=['PENDING', 'PARTIAL'], due_date__lt=today)
    elif status_filter == 'PAID':
        installments_qs = installments_qs.filter(status='PAID')
    elif status_filter == 'PARTIAL':
        installments_qs = installments_qs.filter(status='PARTIAL')

    if search_query:
        installments_qs = installments_qs.filter(
            models.Q(concept__icontains=search_query) |
            models.Q(client__first_name__icontains=search_query) |
            models.Q(client__last_name__icontains=search_query) |
            models.Q(project__name__icontains=search_query) |
            models.Q(reference__icontains=search_query)
        )

    if client_id:
        installments_qs = installments_qs.filter(client_id=client_id)
    if project_id:
        installments_qs = installments_qs.filter(project_id=project_id)

    installments = installments_qs.order_by('due_date', 'installment_number')

    # Métricas Globales de Cobranzas
    all_inst = PaymentInstallment.objects.filter(business=business)
    total_receivable = sum((i.balance for i in all_inst.exclude(status__in=['PAID', 'CANCELLED'])), Decimal('0.00'))
    collected_month = sum((i.amount_paid for i in all_inst.filter(paid_date__gte=start_of_month)), Decimal('0.00'))
    overdue_count = all_inst.filter(status__in=['PENDING', 'PARTIAL'], due_date__lt=today).count()
    overdue_amount = sum((i.balance for i in all_inst.filter(status__in=['PENDING', 'PARTIAL'], due_date__lt=today)), Decimal('0.00'))
    upcoming_30_days = sum((i.balance for i in all_inst.filter(status__in=['PENDING', 'PARTIAL'], due_date__gte=today, due_date__lte=today + timezone.timedelta(days=30))), Decimal('0.00'))

    # Planes de cobro activos
    plans_qs = PaymentPlan.objects.filter(business=business).select_related('client', 'project', 'quote').prefetch_related('installments')
    if client_id:
        plans_qs = plans_qs.filter(client_id=client_id)
    if project_id:
        plans_qs = plans_qs.filter(project_id=project_id)

    clients = Client.objects.filter(business=business).order_by('first_name')
    from apps.projects.models import Project
    projects = Project.objects.filter(business=business).order_by('-created_at')
    from apps.agenda.models import Service
    services = Service.objects.filter(business=business, is_active=True).order_by('name')

    # Generar eventos de cuotas para el calendario de cobranzas
    import json
    calendar_events = []
    for inst in installments:
        if inst.due_date:
            is_overdue = inst.is_overdue
            if inst.status == 'PAID':
                color = '#059669' # Emerald
                bg_color = '#ecfdf5'
                text_color = '#065f46'
                status_label = 'Pagada'
            elif is_overdue:
                color = '#e11d48' # Rose
                bg_color = '#fff1f2'
                text_color = '#9f1239'
                status_label = 'Vencida'
            elif inst.status == 'PARTIAL':
                color = '#2563eb' # Blue
                bg_color = '#eff6ff'
                text_color = '#1e40af'
                status_label = 'Parcial'
            else:
                color = '#d97706' # Amber
                bg_color = '#fffbeb'
                text_color = '#92400e'
                status_label = 'Pendiente'

            client_name = inst.client.full_name if inst.client else "Cliente General"
            display_amt = f"{business.currency}{inst.balance if inst.balance > 0 else inst.amount:.2f}"
            calendar_events.append({
                'id': str(inst.id),
                'title': f"{display_amt} • {inst.concept} ({client_name})",
                'start': inst.due_date.isoformat(),
                'color': color,
                'backgroundColor': bg_color,
                'borderColor': color,
                'textColor': text_color,
                'extendedProps': {
                    'installmentId': str(inst.id),
                    'concept': inst.concept,
                    'clientName': client_name,
                    'clientPhone': inst.client.phone if (inst.client and inst.client.phone) else '',
                    'planTitle': inst.plan.title if inst.plan else '',
                    'amount': float(inst.amount),
                    'amountPaid': float(inst.amount_paid),
                    'balance': float(inst.balance),
                    'status': inst.status,
                    'statusLabel': status_label,
                    'dueDate': inst.due_date.strftime('%d/%m/%Y'),
                    'paidDate': inst.paid_date.strftime('%d/%m/%Y') if inst.paid_date else '',
                    'paymentMethod': inst.payment_method or '',
                    'reference': inst.reference or '',
                    'notes': inst.notes or '',
                    'projectName': inst.project.name if inst.project else '',
                    'projectId': str(inst.project.id) if inst.project else '',
                    'quoteNumber': str(inst.quote.quote_number) if inst.quote else '',
                    'quoteId': str(inst.quote.id) if inst.quote else '',
                    'invoiceId': str(inst.invoice.id) if inst.invoice else (str(inst.sale.invoice.id) if (inst.sale and hasattr(inst.sale, 'invoice') and inst.sale.invoice) else ''),
                    'isPaid': inst.status == 'PAID',
                    'isOverdue': is_overdue
                }
            })

    calendar_events_json = json.dumps(calendar_events)

    return render(request, 'invoicing/payment_plans.html', {
        'business': business,
        'installments': installments,
        'plans': plans_qs,
        'clients': clients,
        'projects': projects,
        'services': services,
        'calendar_events_json': calendar_events_json,
        'status_filter': status_filter,
        'search_query': search_query,
        'client_id': client_id,
        'project_id': project_id,
        'total_receivable': total_receivable,
        'collected_month': collected_month,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'upcoming_30_days': upcoming_30_days,
        'today': today,
        'payment_methods': PaymentInstallment.PAYMENT_METHOD_CHOICES,
    })


@login_required
def payment_direct_charge_view(request):
    """
    Registra un cobro directo e inmediato sin necesidad de pasar por el mostrador/lotes POS ni abrir caja.
    Impacta inmediatamente en Finanzas y crea el registro de venta y cobro en el sistema.
    """
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        from apps.pos.models import Sale, SalePayment, SaleItem
        from apps.agenda.models import Service
        from apps.projects.models import Project

        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None

        service_id = request.POST.get('service_id')
        service = Service.objects.filter(id=service_id, business=business).first() if service_id else None

        project_id = request.POST.get('project_id')
        project = Project.objects.filter(id=project_id, business=business).first() if project_id else None

        concept = request.POST.get('concept', '').strip()
        if not concept:
            if service:
                concept = service.name
            elif project:
                concept = f"Servicio / Entrega: {project.name}"
            else:
                concept = "Cobro de Servicio Profesional"

        amount = parse_decimal(request.POST.get('amount'), '0.00')
        payment_method = request.POST.get('payment_method', 'Transferencia')
        reference = request.POST.get('reference', '').strip()
        paid_date = request.POST.get('paid_date') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()

        if amount > Decimal('0.00'):
            # 1. Crear venta oficial (impacto directo en finanzas sin caja registradora ni lotes POS)
            client_label = client.full_name if client else "Cliente General"
            sale = Sale.objects.create(
                business=business,
                client=client,
                total_amount=amount,
                subtotal=amount,
                status='COMPLETED',
                payment_method=payment_method,
                notes=(
                    f"Cobro Directo (Cobranzas): {concept}. "
                    f"Cliente: {client_label}. Ref: {reference or 'S/R'}. {notes or ''}"
                ).strip()
            )

            # 2. Registrar forma de pago
            SalePayment.objects.create(
                sale=sale,
                payment_method=payment_method,
                amount=amount
            )

            # 3. Registrar ítem de venta
            SaleItem.objects.create(
                sale=sale,
                item_type='SERVICE',
                service=service,
                quantity=1,
                unit_price=amount,
                total_price=amount
            )

            # 4. Registrar en Cobranzas como plan y cuota pagada al instante
            plan = PaymentPlan.objects.create(
                business=business,
                client=client,
                project=project,
                title=f"Cobro Directo: {concept}",
                total_amount=amount,
                status='PAID',
                notes=notes or f"Cobro directo al instante registrado el {paid_date}"
            )

            installment = PaymentInstallment.objects.create(
                plan=plan,
                business=business,
                client=client,
                project=project,
                installment_number=1,
                concept=concept,
                amount=amount,
                amount_paid=amount,
                due_date=paid_date,
                paid_date=paid_date,
                status='PAID',
                payment_method=payment_method,
                reference=reference,
                sale=sale,
                notes=notes
            )

            # 5. Generar Factura Oficial pagada para que figure en la sección Facturación
            from apps.invoicing.services import create_invoice_for_installment
            create_invoice_for_installment(
                installment=installment,
                charge_amount=amount,
                payment_method=payment_method,
                paid_date=paid_date,
                reference=reference,
                notes=notes
            )

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        if project:
            return redirect('project_detail', project_id=project.id)
        return redirect('payment_plan_list')

    return redirect('payment_plan_list')


@login_required
def payment_plan_create_view(request):
    """Crea un nuevo plan de cuotas vinculado a cliente, proyecto o libre."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None
        project_id = request.POST.get('project_id')
        from apps.projects.models import Project
        project = Project.objects.filter(id=project_id, business=business).first() if project_id else None
        
        quote_id = request.POST.get('quote_id')
        quote = Quote.objects.filter(id=quote_id, business=business).first() if quote_id else None

        title = request.POST.get('title', '').strip()
        if not title:
            title = f"Plan de Cobro - {client.full_name}" if client else "Plan de Cobro"
        total_amount = parse_decimal(request.POST.get('total_amount'), '0.00')
        notes = request.POST.get('notes', '').strip()

        plan = PaymentPlan.objects.create(
            business=business,
            client=client,
            project=project,
            quote=quote,
            title=title,
            total_amount=total_amount,
            notes=notes
        )

        concepts = request.POST.getlist('concept[]')
        amounts = request.POST.getlist('amount[]')
        due_dates = request.POST.getlist('due_date[]')

        for idx, concept in enumerate(concepts):
            c_text = concept.strip() or f"Cuota #{idx + 1}"
            c_amount = parse_decimal(amounts[idx] if idx < len(amounts) else '0.00', '0.00')
            c_date = due_dates[idx] if (idx < len(due_dates) and due_dates[idx]) else timezone.now().date()

            PaymentInstallment.objects.create(
                plan=plan,
                business=business,
                client=client,
                project=project,
                quote=quote,
                installment_number=idx + 1,
                concept=c_text,
                amount=c_amount,
                due_date=c_date,
                status='PENDING'
            )

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        if project:
            return redirect('project_detail', project_id=project.id)
        if quote:
            return redirect('quote_detail', quote_id=quote.id)

        return redirect('payment_plan_list')

    return redirect('payment_plan_list')


@login_required
def payment_installment_charge_view(request, installment_id):
    """Registra el cobro de una cuota e impacta inmediatamente en las finanzas del negocio."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    installment = get_object_or_404(PaymentInstallment, id=installment_id, business=business)
    next_url = request.POST.get('next')

    if request.method == 'POST':
        # Protección contra cobro duplicado o doble clic:
        if installment.status == 'PAID' or installment.balance <= Decimal('0.00'):
            if next_url:
                return redirect(next_url)
            if installment.project:
                return redirect('project_detail', project_id=installment.project.id)
            return redirect('payment_plan_list')

        from apps.pos.models import Sale, SalePayment, SaleItem
        raw_amount = parse_decimal(request.POST.get('charge_amount'), str(installment.balance))
        charge_amount = min(raw_amount, installment.balance)

        if charge_amount <= Decimal('0.00'):
            if next_url:
                return redirect(next_url)
            return redirect('payment_plan_list')

        payment_method = request.POST.get('payment_method', 'Transferencia')
        reference = request.POST.get('reference', '').strip()
        paid_date = request.POST.get('paid_date') or timezone.now().date()
        notes = request.POST.get('notes', '').strip()

        if charge_amount > Decimal('0.00'):
            # 1. Crear venta financiera oficial (sin caja registradora ni lotes POS)
            sale = Sale.objects.create(
                business=business,
                client=installment.client,
                total_amount=charge_amount,
                subtotal=charge_amount,
                status='COMPLETED',
                payment_method=payment_method,
                notes=(
                    f"Cobro Cuota #{installment.installment_number} ({installment.concept}) - "
                    f"Plan: {installment.plan.title}. Ref: {reference or 'S/R'}"
                )
            )

            SalePayment.objects.create(
                sale=sale,
                payment_method=payment_method,
                amount=charge_amount
            )

            SaleItem.objects.create(
                sale=sale,
                item_type='SERVICE',
                quantity=1,
                unit_price=charge_amount,
                total_price=charge_amount
            )

            # 2. Actualizar cuota asegurando que el total pagado nunca exceda el valor de la cuota
            installment.amount_paid = min(installment.amount, installment.amount_paid + charge_amount)
            installment.paid_date = paid_date
            installment.payment_method = payment_method
            installment.reference = reference
            installment.sale = sale
            if notes:
                if not installment.notes:
                    installment.notes = notes
                elif notes not in installment.notes:
                    installment.notes = f"{installment.notes}\n{notes}".strip()

            if installment.amount_paid >= installment.amount:
                installment.status = 'PAID'
            else:
                installment.status = 'PARTIAL'

            installment.save()

            # 3. Actualizar estado del plan
            installment.plan.update_status()

            # 4. Generar Factura Oficial pagada para que figure inmediatamente en Facturación
            from apps.invoicing.services import create_invoice_for_installment
            create_invoice_for_installment(
                installment=installment,
                charge_amount=charge_amount,
                payment_method=payment_method,
                paid_date=paid_date,
                reference=reference,
                notes=notes
            )

    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    if installment.project:
        return redirect('project_detail', project_id=installment.project.id)
    return redirect('payment_plan_list')


@login_required
def payment_installment_delete_view(request, installment_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    installment = get_object_or_404(PaymentInstallment, id=installment_id, business=business)
    plan = installment.plan
    if request.method == 'POST':
        installment.delete()
        plan.update_status()

    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('payment_plan_list')


@login_required
def payment_plan_delete_view(request, plan_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    plan = get_object_or_404(PaymentPlan, id=plan_id, business=business)
    if request.method == 'POST':
        plan.delete()

    return redirect('payment_plan_list')
