from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from apps.business.models import Business, StaffMember
from apps.agenda.models import Service, ServiceCategory, Appointment, ScheduleBlock
from apps.crm.models import Client
from apps.core.utils import parse_decimal, parse_int

def agenda_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    selected_date_str = request.GET.get('date', datetime.date.today().isoformat())
    selected_staff_id = request.GET.get('staff', '')
    
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = datetime.date.today()
        
    staff_members = StaffMember.objects.filter(business=business, is_active=True) if business else []
    services = Service.objects.filter(business=business, is_active=True) if business else []
    clients = Client.objects.filter(business=business) if business else []
    
    appointments = Appointment.objects.filter(business=business, date=selected_date).select_related('client', 'staff', 'service')
    if selected_staff_id:
        appointments = appointments.filter(staff_id=selected_staff_id)

    return render(request, 'agenda/agenda.html', {
        'business': business,
        'selected_date': selected_date,
        'staff_members': staff_members,
        'services': services,
        'clients': clients,
        'appointments': appointments,
        'selected_staff_id': selected_staff_id,
    })

def appointment_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    clients = Client.objects.filter(business=business) if business else []
    staff_members = StaffMember.objects.filter(business=business, is_active=True) if business else []
    services = Service.objects.filter(business=business, is_active=True) if business else []

    selected_client_id = request.GET.get('client_id', '')
    selected_staff_id = request.GET.get('staff_id', '')
    selected_service_id = request.GET.get('service_id', '')
    selected_date = request.GET.get('date', datetime.date.today().isoformat())
    selected_time = request.GET.get('start_time', '')

    days_param = request.GET.get('days')
    rebook_info = None
    if days_param and days_param.isdigit():
        num_days = int(days_param)
        calc_date = datetime.date.today() + datetime.timedelta(days=num_days)
        selected_date = calc_date.isoformat()
        rebook_info = f"Reagendando cita en {num_days} días (Fecha calculada: {calc_date.strftime('%d/%m/%Y')})"

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        staff_id = request.POST.get('staff_id')
        service_id = request.POST.get('service_id')
        app_date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        status = request.POST.get('status', 'CONFIRMED')
        notes = request.POST.get('notes', '')
        
        client = get_object_or_404(Client, id=client_id, business=business)
        staff = get_object_or_404(StaffMember, id=staff_id, business=business)
        service = get_object_or_404(Service, id=service_id, business=business)
        
        st = datetime.datetime.strptime(start_time, "%H:%M")
        et = st + datetime.timedelta(minutes=service.duration_minutes)
        end_time = et.strftime("%H:%M")
        
        Appointment.objects.create(
            business=business,
            client=client,
            staff=staff,
            service=service,
            date=app_date,
            start_time=start_time,
            end_time=end_time,
            total_price=service.price,
            status=status,
            notes=notes
        )
        return redirect('agenda')

    return render(request, 'agenda/appointment_form.html', {
        'business': business,
        'appointment': None,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'today_date': selected_date,
        'selected_client_id': selected_client_id,
        'selected_staff_id': selected_staff_id,
        'selected_service_id': selected_service_id,
        'selected_time': selected_time,
        'rebook_info': rebook_info,
        'title': 'Agendar Nueva Cita'
    })

def appointment_edit_view(request, appointment_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    appointment = get_object_or_404(Appointment, id=appointment_id, business=business)
    clients = Client.objects.filter(business=business)
    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    services = Service.objects.filter(business=business, is_active=True)

    if request.method == 'POST':
        appointment.client = get_object_or_404(Client, id=request.POST.get('client_id'), business=business)
        appointment.staff = get_object_or_404(StaffMember, id=request.POST.get('staff_id'), business=business)
        service = get_object_or_404(Service, id=request.POST.get('service_id'), business=business)
        appointment.service = service
        appointment.date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        appointment.start_time = start_time
        
        st = datetime.datetime.strptime(start_time, "%H:%M")
        et = st + datetime.timedelta(minutes=service.duration_minutes)
        appointment.end_time = et.strftime("%H:%M")
        appointment.total_price = service.price
        appointment.status = request.POST.get('status')
        appointment.notes = request.POST.get('notes', '')
        appointment.save()
        return redirect('agenda')

    return render(request, 'agenda/appointment_form.html', {
        'business': business,
        'appointment': appointment,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'title': f'Editar Cita: {appointment.client.full_name}'
    })

def service_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    categories = ServiceCategory.objects.filter(business=business).prefetch_related('services') if business else []
    services_without_category = Service.objects.filter(business=business, category__isnull=True) if business else []

    return render(request, 'agenda/service_list.html', {
        'business': business,
        'categories': categories,
        'services_without_category': services_without_category,
    })

def service_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    categories = ServiceCategory.objects.filter(business=business) if business else []

    if request.method == 'POST':
        name = request.POST.get('name')
        category_id = request.POST.get('category_id')
        price = parse_decimal(request.POST.get('price'), '0.00')
        duration = parse_int(request.POST.get('duration_minutes'), 45)
        description = request.POST.get('description', '')
        commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        
        category = ServiceCategory.objects.filter(id=category_id).first() if category_id else None
        
        Service.objects.create(
            business=business,
            name=name,
            category=category,
            price=price,
            duration_minutes=duration,
            description=description,
            commission_rate=commission_rate,
            is_active=True
        )
        return redirect('service_list')

    return render(request, 'agenda/service_form.html', {
        'business': business,
        'service': None,
        'categories': categories,
        'title': 'Crear Nuevo Servicio'
    })

def service_edit_view(request, service_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    service = get_object_or_404(Service, id=service_id, business=business)
    categories = ServiceCategory.objects.filter(business=business)

    if request.method == 'POST':
        service.name = request.POST.get('name')
        category_id = request.POST.get('category_id')
        service.category = ServiceCategory.objects.filter(id=category_id).first() if category_id else None
        service.price = parse_decimal(request.POST.get('price'), '0.00')
        service.duration_minutes = parse_int(request.POST.get('duration_minutes'), 45)
        service.description = request.POST.get('description', '')
        service.commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        service.save()
        return redirect('service_list')

    return render(request, 'agenda/service_form.html', {
        'business': business,
        'service': service,
        'categories': categories,
        'title': f'Editar Servicio: {service.name}'
    })

def service_category_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()

    if request.method == 'POST':
        name = request.POST.get('name')
        color = request.POST.get('color', '#6366f1')
        if name:
            ServiceCategory.objects.create(
                business=business,
                name=name,
                color=color
            )
        return redirect('service_list')

    return render(request, 'agenda/service_category_form.html', {
        'business': business,
        'title': 'Crear Nueva Categoría de Servicio'
    })

from apps.business.models import Business, StaffMember, WorkSchedule

def appointment_calendar_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    staff_members = StaffMember.objects.filter(business=business, is_active=True) if business else []

    slot_min_time = "00:00:00"
    slot_max_time = "24:00:00"

    return render(request, 'agenda/calendar.html', {
        'business': business,
        'staff_members': staff_members,
        'slot_min_time': slot_min_time,
        'slot_max_time': slot_max_time,
    })

def appointment_events_api(request):
    from django.http import JsonResponse
    business = getattr(request, 'current_business', None) or Business.objects.first()
    staff_id = request.GET.get('staff_id', '')

    appointments = Appointment.objects.filter(business=business).select_related('client', 'staff', 'service')
    if staff_id:
        appointments = appointments.filter(staff_id=staff_id)

    events = []
    for app in appointments:
        start_dt = f"{app.date.isoformat()}T{app.start_time.strftime('%H:%M:%S')}"
        end_dt = f"{app.date.isoformat()}T{app.end_time.strftime('%H:%M:%S')}"
        color = "#10b981" if app.status == 'COMPLETED' else ("#6366f1" if app.status == 'CONFIRMED' else "#f59e0b")
        
        events.append({
            'id': str(app.id),
            'title': f"{app.client.full_name} - {app.service.name}",
            'start': start_dt,
            'end': end_dt,
            'url': f"/agenda/{app.id}/editar/",
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'client': app.client.full_name,
                'service': app.service.name,
                'staff': app.staff.full_name,
                'status': app.get_status_display(),
                'price': str(app.total_price)
            }
        })

    return JsonResponse(events, safe=False)
