import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from apps.business.models import Business
from apps.invoicing.models import Invoice, InvoiceItem, Quote, Expense, ExpenseCategory
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
    expenses = Expense.objects.filter(business=business).select_related('category', 'supplier').order_by('-date') if business else []

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
        
        category = ExpenseCategory.objects.filter(id=category_id, business=business).first() if category_id else None
        supplier = Supplier.objects.filter(id=supplier_id, business=business).first() if supplier_id else None
        
        Expense.objects.create(
            business=business,
            category=category,
            supplier=supplier,
            concept=concept,
            amount=amount,
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
