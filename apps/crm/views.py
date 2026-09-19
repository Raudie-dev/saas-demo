from django.shortcuts import render, get_object_or_404, redirect
from apps.business.models import Business
from apps.crm.models import Client, ClientNote, Supplier

def client_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    query = request.GET.get('q', '')
    
    clients = Client.objects.filter(business=business) if business else []
    if query:
        clients = clients.filter(first_name__icontains=query) | clients.filter(last_name__icontains=query) | clients.filter(phone__icontains=query)
        
    return render(request, 'crm/client_list.html', {
        'business': business,
        'clients': clients,
        'query': query
    })

def client_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email', '')
        tax_id = request.POST.get('tax_id', '')
        address = request.POST.get('address', '')
        status = request.POST.get('status', 'ACTIVE')
        notes = request.POST.get('notes', '')
        
        Client.objects.create(
            business=business,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            tax_id=tax_id,
            address=address,
            status=status,
            notes=notes
        )
        return redirect('client_list')
        
    return render(request, 'crm/client_form.html', {
        'business': business,
        'client': None,
        'title': 'Crear Nuevo Cliente'
    })

def client_edit_view(request, client_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    client = get_object_or_404(Client, id=client_id, business=business)
    
    if request.method == 'POST':
        client.first_name = request.POST.get('first_name')
        client.last_name = request.POST.get('last_name')
        client.phone = request.POST.get('phone')
        client.email = request.POST.get('email', '')
        client.tax_id = request.POST.get('tax_id', '')
        client.address = request.POST.get('address', '')
        client.status = request.POST.get('status', 'ACTIVE')
        client.notes = request.POST.get('notes', '')
        client.save()
        return redirect('client_detail', client_id=client.id)
        
    return render(request, 'crm/client_form.html', {
        'business': business,
        'client': client,
        'title': f'Editar Cliente: {client.full_name}'
    })

def client_detail_view(request, client_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    client = get_object_or_404(Client, id=client_id, business=business)
    
    appointments = client.appointments.all().order_by('-date')
    sales = client.sales.all().order_by('-created_at')
    invoices = client.invoices.all().order_by('-issue_date')
    notes = client.client_notes.all().order_by('-created_at')
    
    return render(request, 'crm/client_detail.html', {
        'business': business,
        'client': client,
        'appointments': appointments,
        'sales': sales,
        'invoices': invoices,
        'notes': notes,
    })

def supplier_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    return render(request, 'crm/supplier_list.html', {
        'business': business,
        'suppliers': suppliers
    })

def supplier_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    
    if request.method == 'POST':
        company_name = request.POST.get('company_name')
        contact_name = request.POST.get('contact_name', '')
        tax_id = request.POST.get('tax_id', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        category = request.POST.get('category', 'Insumos Generales')
        
        Supplier.objects.create(
            business=business,
            company_name=company_name,
            contact_name=contact_name,
            tax_id=tax_id,
            email=email,
            phone=phone,
            address=address,
            category=category
        )
        return redirect('supplier_list')
        
    return render(request, 'crm/supplier_form.html', {
        'business': business,
        'supplier': None,
        'title': 'Crear Nuevo Proveedor'
    })

def supplier_edit_view(request, supplier_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    supplier = get_object_or_404(Supplier, id=supplier_id, business=business)
    
    if request.method == 'POST':
        supplier.company_name = request.POST.get('company_name')
        supplier.contact_name = request.POST.get('contact_name', '')
        supplier.tax_id = request.POST.get('tax_id', '')
        supplier.email = request.POST.get('email', '')
        supplier.phone = request.POST.get('phone', '')
        supplier.address = request.POST.get('address', '')
        supplier.category = request.POST.get('category', 'Insumos Generales')
        supplier.save()
        return redirect('supplier_list')
        
    return render(request, 'crm/supplier_form.html', {
        'business': business,
        'supplier': supplier,
        'title': f'Editar Proveedor: {supplier.company_name}'
    })
