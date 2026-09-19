from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
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
    items = invoice.items.all()
    
    return render(request, 'invoicing/invoice_detail.html', {
        'business': business,
        'invoice': invoice,
        'items': items,
    })

def expense_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    expenses = Expense.objects.filter(business=business) if business else []
    
    return render(request, 'invoicing/expense_list.html', {
        'business': business,
        'expenses': expenses,
    })

def expense_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    categories = ExpenseCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []

    if request.method == 'POST':
        concept = request.POST.get('concept')
        amount = parse_decimal(request.POST.get('amount'), '0.00')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        issue_date = request.POST.get('issue_date')
        receipt_number = request.POST.get('receipt_number', '')
        status = request.POST.get('status', 'PAID')
        
        category = ExpenseCategory.objects.filter(id=category_id).first() if category_id else None
        supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        
        Expense.objects.create(
            business=business,
            concept=concept,
            amount=amount,
            category=category,
            supplier=supplier,
            issue_date=issue_date,
            receipt_number=receipt_number,
            status=status
        )
        return redirect('expense_list')

    return render(request, 'invoicing/expense_form.html', {
        'business': business,
        'expense': None,
        'categories': categories,
        'suppliers': suppliers,
        'title': 'Registrar Nuevo Gasto Operativo'
    })

def expense_edit_view(request, expense_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    expense = get_object_or_404(Expense, id=expense_id, business=business)
    categories = ExpenseCategory.objects.filter(business=business)
    suppliers = Supplier.objects.filter(business=business)

    if request.method == 'POST':
        expense.concept = request.POST.get('concept')
        expense.amount = parse_decimal(request.POST.get('amount'), '0.00')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        expense.category = ExpenseCategory.objects.filter(id=category_id).first() if category_id else None
        expense.supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        expense.issue_date = request.POST.get('issue_date')
        expense.receipt_number = request.POST.get('receipt_number', '')
        expense.status = request.POST.get('status', 'PAID')
        expense.save()
        return redirect('expense_list')

    return render(request, 'invoicing/expense_form.html', {
        'business': business,
        'expense': expense,
        'categories': categories,
        'suppliers': suppliers,
        'title': f'Editar Gasto: {expense.concept}'
    })
