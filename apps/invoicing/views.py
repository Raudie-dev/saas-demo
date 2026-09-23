import csv
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.utils import timezone
from apps.business.models import Business
from apps.invoicing.models import Invoice, InvoiceItem, Quote, Expense, ExpenseCategory, AccountReceivable
from apps.crm.models import Client, Supplier
from apps.core.utils import parse_decimal

def invoice_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    invoices = Invoice.objects.filter(business=business) if business else []
    quotes = Quote.objects.filter(business=business) if business else []
    
    return render(request, 'invoicing/invoice_list.html', {
        'business': business,
        'invoices': invoices,
        'quotes': quotes,
    })

def invoice_detail_view(request, invoice_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    invoice = get_object_or_404(Invoice, id=invoice_id, business=business)
    return render(request, 'invoicing/invoice_detail.html', {'business': business, 'invoice': invoice})

def expense_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    expenses = Expense.objects.filter(business=business).select_related('category', 'supplier') if business else []
    
    return render(request, 'invoicing/expense_list.html', {
        'business': business,
        'expenses': expenses
    })

def expense_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    categories = ExpenseCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        concept = request.POST.get('concept', '').strip()
        amount = parse_decimal(request.POST.get('amount'), '0.00')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        status = request.POST.get('status', 'PAID')
        notes = request.POST.get('notes', '')
        
        category = ExpenseCategory.objects.filter(id=category_id).first() if category_id else None
        supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        
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

def expense_edit_view(request, expense_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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
        
        expense.category = ExpenseCategory.objects.filter(id=category_id).first() if category_id else None
        expense.supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        expense.save()
        return redirect('expense_list')
        
    return render(request, 'invoicing/expense_form.html', {
        'business': business,
        'expense': expense,
        'categories': categories,
        'suppliers': suppliers,
        'title': f'Editar Gasto: {expense.concept}'
    })

def export_expenses_excel(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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

def export_expenses_pdf(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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
