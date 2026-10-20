import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import models

from apps.business.models import Business
from apps.invoicing.models import Invoice, InvoiceItem, Quote, QuoteItem, Expense, ExpenseCategory
from apps.crm.models import Client, Supplier
from apps.core.utils import parse_decimal

@login_required
def invoice_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    invoices = Invoice.objects.filter(business=business).order_by('-issue_date') if business else []
    quotes = Quote.objects.filter(business=business).order_by('-valid_until') if business else []
    
    from django.core.paginator import Paginator
    inv_paginator = Paginator(invoices, 10)
    invoices_page_obj = inv_paginator.get_page(request.GET.get('page', 1))

    return render(request, 'invoicing/invoice_list.html', {
        'business': business,
        'invoices': invoices_page_obj,
        'page_obj': invoices_page_obj,
        'quotes': quotes,
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

    return render(request, 'invoicing/quote_form.html', {
        'business': business,
        'clients': clients,
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

    return render(request, 'invoicing/quote_form.html', {
        'business': business,
        'clients': clients,
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

    return render(request, 'invoicing/quote_detail.html', {
        'business': business,
        'quote': quote,
        'items': items,
        'whatsapp_url': whatsapp_url,
        'hourly_items_count': hourly_items_count,
        'performance_items_count': performance_items_count,
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
