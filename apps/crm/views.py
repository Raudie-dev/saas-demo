import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.business.models import Business
from apps.crm.models import Client, ClientNote, Supplier

@login_required
def client_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    query = request.GET.get('q', '')
    
    clients = Client.objects.filter(business=business).order_by('-created_at') if business else []
    if query:
        clients = clients.filter(first_name__icontains=query) | clients.filter(last_name__icontains=query) | clients.filter(phone__icontains=query)

    from django.core.paginator import Paginator
    paginator = Paginator(clients, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'crm/client_list.html', {
        'business': business,
        'clients': page_obj,
        'page_obj': page_obj,
        'query': query
    })

def split_phone_number(phone_str):
    if not phone_str:
        return '+54', ''
    prefixes = ['+598', '+595', '+591', '+593', '+507', '+506', '+502', '+503', '+504', '+505', '+592', '+597', '+54', '+56', '+51', '+57', '+52', '+58', '+34', '+55', '+1']
    for p in prefixes:
        if phone_str.startswith(p):
            return p, phone_str[len(p):]
    return '+54', phone_str

@login_required
def client_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_prefix = request.POST.get('phone_prefix', '+54').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        if phone_number.startswith('+'):
            phone = phone_number
        else:
            clean_num = ''.join(filter(str.isdigit, phone_number))
            phone = f"{phone_prefix}{clean_num}" if clean_num else "Sin teléfono"

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
        'phone_prefix': '+54',
        'phone_number': '',
        'title': 'Crear Nuevo Cliente'
    })

@login_required
def client_edit_view(request, client_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    client = get_object_or_404(Client, id=client_id, business=business)
    
    if request.method == 'POST':
        client.first_name = request.POST.get('first_name', '').strip()
        client.last_name = request.POST.get('last_name', '').strip()
        
        phone_prefix = request.POST.get('phone_prefix', '+54').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        if phone_number.startswith('+'):
            client.phone = phone_number
        else:
            clean_num = ''.join(filter(str.isdigit, phone_number))
            client.phone = f"{phone_prefix}{clean_num}" if clean_num else "Sin teléfono"

        client.email = request.POST.get('email', '')
        client.tax_id = request.POST.get('tax_id', '')
        client.address = request.POST.get('address', '')
        client.status = request.POST.get('status', 'ACTIVE')
        client.notes = request.POST.get('notes', '')
        client.save()
        return redirect('client_detail', client_id=client.id)

    phone_prefix, phone_number = split_phone_number(client.phone)
        
    return render(request, 'crm/client_form.html', {
        'business': business,
        'client': client,
        'phone_prefix': phone_prefix,
        'phone_number': phone_number,
        'title': f'Editar Cliente: {client.full_name}'
    })

from apps.crm.models import Client, ClientNote, Supplier, ServiceHistoryNote
from django.contrib import messages

@login_required
def client_detail_view(request, client_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    client = get_object_or_404(Client, id=client_id, business=business)
    
    appointments = client.appointments.select_related('staff', 'service').order_by('-date', '-start_time')
    sales = client.sales.select_related('staff').order_by('-created_at')
    invoices = client.invoices.order_by('-issue_date')
    notes = client.client_notes.all().order_by('-created_at')
    service_notes = client.service_notes.select_related('appointment').order_by('-created_at')
    
    allow_editing_history = getattr(business, 'allow_editing_client_history', True)
    
    return render(request, 'crm/client_detail.html', {
        'business': business,
        'client': client,
        'appointments': appointments,
        'sales': sales,
        'invoices': invoices,
        'notes': notes,
        'service_notes': service_notes,
        'allow_editing_history': allow_editing_history,
    })

@login_required
def add_client_service_note_view(request, client_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    client = get_object_or_404(Client, id=client_id, business=business)
    
    if not getattr(business, 'allow_editing_client_history', True):
        messages.warning(request, "La edición del historial de servicios está bloqueada en la configuración de la empresa.")
        return redirect('client_detail', client_id=client.id)
        
    if request.method == 'POST':
        service_name = request.POST.get('service_name', '').strip()
        content = request.POST.get('content', '').strip()
        appointment_id = request.POST.get('appointment_id')
        author = request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Staff"
        
        if service_name and content:
            ServiceHistoryNote.objects.create(
                client=client,
                service_name=service_name,
                content=content,
                author=author,
                appointment_id=appointment_id if appointment_id else None
            )
            messages.success(request, "Anotación de servicio agregada a la ficha del cliente.")
        else:
            messages.error(request, "Por favor ingresa el servicio y el detalle de la anotación.")
            
    return redirect('client_detail', client_id=client.id)

@login_required
def delete_client_service_note_view(request, note_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    note = get_object_or_404(ServiceHistoryNote, id=note_id, client__business=business)
    client_id = note.client.id
    
    if not getattr(business, 'allow_editing_client_history', True):
        messages.warning(request, "No se pueden eliminar anotaciones porque el historial está en modo Solo Lectura.")
        return redirect('client_detail', client_id=client_id)
        
    note.delete()
    messages.success(request, "Anotación de servicio eliminada.")
    return redirect('client_detail', client_id=client_id)

@login_required
def supplier_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    suppliers = Supplier.objects.filter(business=business).order_by('-created_at') if business else []

    from django.core.paginator import Paginator
    paginator = Paginator(suppliers, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'crm/supplier_list.html', {
        'business': business,
        'suppliers': page_obj,
        'page_obj': page_obj,
    })

@login_required
def supplier_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    
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

@login_required
def supplier_edit_view(request, supplier_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
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
        'title': 'Editar Proveedor'
    })

@login_required
def export_clients_excel(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    clients = Client.objects.filter(business=business) if business else []
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="clientes_reporte.csv"'
    
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Nombre', 'Apellido', 'Teléfono', 'Email', 'Documento/Tax ID', 'Dirección', 'Estado', 'Fecha Registro'])
    
    for c in clients:
        writer.writerow([
            c.first_name,
            c.last_name,
            c.phone or '',
            c.email or '',
            c.tax_id or '',
            c.address or '',
            c.status,
            c.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(c, 'created_at') and c.created_at else ''
        ])
        
    return response

@login_required
def export_clients_pdf(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    clients = Client.objects.filter(business=business) if business else []
    
    rows = []
    for c in clients:
        rows.append({
            'col1': c.full_name,
            'col2': c.phone or 'Sin teléfono',
            'col3': c.email or '-',
            'col4': c.address or '-',
            'col5': c.status
        })
        
    return render(request, 'analytics/pdf_report.html', {
        'title': 'Reporte de Clientes',
        'subtitle': f'Base de Datos de Clientes - {business.name if business else ""}',
        'business': business,
        'headers': ['Cliente', 'Teléfono', 'Email', 'Dirección', 'Estado'],
        'rows': rows,
        'summary': f'Total Clientes: {len(rows)}'
    })

