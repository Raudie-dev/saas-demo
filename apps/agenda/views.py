from decimal import Decimal
import datetime
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.business.models import Business, StaffMember
from apps.agenda.models import Service, ServiceCategory, Appointment, ScheduleBlock, AppointmentService
from apps.crm.models import Client
from django.contrib import messages
from apps.core.utils import parse_decimal, parse_int
from apps.agenda.utils import (
    calculate_available_slots,
    get_allowed_staff_ids_for_service,
    get_ineligible_services_for_staff,
    find_overlapping_appointment,
    expire_overdue_pending_appointments,
    send_booking_notification_to_client,
)

@login_required
def agenda_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not request.user.has_module_access('agenda'):
        messages.error(request, "No tienes permiso para acceder a la Agenda.")
        return redirect('dashboard')

    expire_overdue_pending_appointments(business)

    selected_date_str = request.GET.get('date', datetime.date.today().isoformat())
    selected_staff_id = request.GET.get('staff', '')
    
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = datetime.date.today()
        
    staff_members = StaffMember.objects.filter(business=business, is_active=True) if business else []
    services = Service.objects.filter(business=business, is_active=True) if business else []
    clients = Client.objects.filter(business=business) if business else []
    
    appointments = Appointment.objects.filter(business=business, date=selected_date).select_related('client', 'staff', 'service').prefetch_related('appointment_services__service')

    # Aislamiento para Profesionales (Solo sus propias citas)
    user_scope = getattr(request.user, 'appointment_scope', 'ALL')
    user_staff = getattr(request.user, 'staff_profile', None)

    if user_scope == 'OWN':
        if user_staff:
            appointments = appointments.filter(staff=user_staff)
            staff_members = [user_staff]
            selected_staff_id = str(user_staff.id)
        else:
            appointments = appointments.none()
            staff_members = []
    elif selected_staff_id:
        appointments = appointments.filter(staff_id=selected_staff_id)

    wa_templates = list(business.whatsapp_templates.filter(category__in=['APPOINTMENT', 'GENERAL']).values('id', 'title', 'content', 'is_default')) if business else []

    return render(request, 'agenda/agenda.html', {
        'business': business,
        'selected_date': selected_date,
        'staff_members': staff_members,
        'services': services,
        'clients': clients,
        'appointments': appointments,
        'selected_staff_id': selected_staff_id,
        'is_restricted_scope': (user_scope == 'OWN'),
        'wa_templates': wa_templates,
    })

def _parse_services_from_post(request, business):
    services_items = []
    services_data = request.POST.get('services_data')
    if services_data:
        try:
            parsed = json.loads(services_data)
            if isinstance(parsed, list):
                for item in parsed:
                    s_id = item.get('id')
                    try:
                        qty = max(1, int(item.get('quantity', 1)))
                    except (ValueError, TypeError):
                        qty = 1
                    srv = Service.objects.filter(id=s_id, business=business).first()
                    if srv:
                        services_items.append((srv, qty))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if not services_items:
        service_id = request.POST.get('service_id')
        if service_id:
            srv = Service.objects.filter(id=service_id, business=business).first()
            if srv:
                services_items.append((srv, 1))

    return services_items


def _calculate_appointment_deposit(business, services_items, total_price, post_data=None):
    """
    Calcula (deposit_percentage, deposit_amount) para una cita en base a:
    - Los porcentajes configurados en cada servicio (`srv.effective_deposit_percentage`)
    - O los valores enviados explícitamente en el formulario de la cita (`deposit_percentage` / `deposit_amount`).
    """
    default_dep_amount = sum(
        (srv.effective_deposit_amount * qty) for srv, qty in services_items
    ) if services_items else Decimal('0.00')
    default_dep_amount = min(total_price, default_dep_amount.quantize(Decimal('0.01')))
    if total_price > 0:
        default_dep_pct = ((default_dep_amount / total_price) * Decimal('100.00')).quantize(Decimal('0.01'))
    else:
        default_dep_pct = getattr(business, 'default_deposit_percentage', Decimal('30.00')) or Decimal('0.00')

    if not post_data:
        return default_dep_pct, default_dep_amount

    raw_pct = (post_data.get('deposit_percentage') or '').strip()
    raw_amt = (post_data.get('deposit_amount') or '').strip()

    if raw_amt != '':
        dep_amt = max(Decimal('0.00'), min(total_price, parse_decimal(raw_amt, default_dep_amount)))
        if raw_pct != '':
            dep_pct = max(Decimal('0.00'), min(Decimal('100.00'), parse_decimal(raw_pct, default_dep_pct)))
        elif total_price > 0:
            dep_pct = ((dep_amt / total_price) * Decimal('100.00')).quantize(Decimal('0.01'))
        else:
            dep_pct = Decimal('0.00')
        return dep_pct, dep_amt

    if raw_pct != '':
        dep_pct = max(Decimal('0.00'), min(Decimal('100.00'), parse_decimal(raw_pct, default_dep_pct)))
        dep_amt = ((total_price * dep_pct) / Decimal('100.00')).quantize(Decimal('0.01'))
        return dep_pct, dep_amt

    return default_dep_pct, default_dep_amount


@login_required
def appointment_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not request.user.has_module_access('agenda'):
        messages.error(request, "No tienes permiso para agendar citas.")
        return redirect('dashboard')

    clients = Client.objects.filter(business=business) if business else []
    all_active_staff = list(StaffMember.objects.filter(business=business, is_active=True).prefetch_related('services')) if business else []
    staff_members = all_active_staff
    services = list(Service.objects.filter(business=business, is_active=True).select_related('business').prefetch_related('staff_members')) if business else []
    for srv in services:
        srv.allowed_staff_ids_json = json.dumps(
            get_allowed_staff_ids_for_service(srv, all_active_staff=all_active_staff)
        )

    user_scope = getattr(request.user, 'appointment_scope', 'ALL')
    user_staff = getattr(request.user, 'staff_profile', None)

    if user_scope == 'OWN':
        if user_staff:
            staff_members = [user_staff]
            selected_staff_id = str(user_staff.id)
        else:
            staff_members = []
            selected_staff_id = ''
    else:
        selected_staff_id = request.GET.get('staff_id', '')

    selected_client_id = request.GET.get('client_id', '')
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
        app_date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        end_time_input = request.POST.get('end_time')
        status = request.POST.get('status', 'CONFIRMED')
        notes = request.POST.get('notes', '')
        
        client = get_object_or_404(Client, id=client_id, business=business)
        
        if user_scope == 'OWN' and user_staff:
            staff = user_staff
        else:
            staff = get_object_or_404(StaffMember, id=staff_id, business=business)

        services_items = _parse_services_from_post(request, business)
        if not services_items:
            messages.error(request, "Debes seleccionar al menos un servicio para la cita.")
            return redirect(request.path)

        total_duration = sum(srv.duration_minutes * qty for srv, qty in services_items)
        total_price = sum(srv.price * qty for srv, qty in services_items)
        primary_service = services_items[0][0]
        dep_pct, dep_amt = _calculate_appointment_deposit(business, services_items, total_price, request.POST)

        # Calcular automáticamente la hora de fin en base a la duración de los servicios
        try:
            st = datetime.datetime.strptime(start_time, "%H:%M")
            et = st + datetime.timedelta(minutes=max(total_duration, 15))
            computed_end_time = et.strftime("%H:%M")
        except (ValueError, TypeError):
            computed_end_time = "10:45"

        end_time = computed_end_time
        if end_time_input:
            try:
                st_dt = datetime.datetime.strptime(start_time, "%H:%M")
                et_in_dt = datetime.datetime.strptime(end_time_input, "%H:%M")
                if et_in_dt >= st_dt + datetime.timedelta(minutes=max(total_duration, 15)):
                    end_time = end_time_input
            except (ValueError, TypeError):
                pass

        # 1. Validar que el profesional seleccionado esté anclado al servicio
        ineligible_services = get_ineligible_services_for_staff(
            staff, [srv for srv, _ in services_items], all_active_staff=all_active_staff
        )
        if ineligible_services:
            bad_names = ", ".join(s.name for s in ineligible_services)
            messages.error(
                request,
                f"El profesional {staff.full_name} ({staff.role_title}) no está habilitado para realizar: {bad_names}. "
                f"Selecciona un especialista asignado a ese servicio."
            )
            return redirect(f"{request.path}?client_id={client.id}&date={app_date}&start_time={start_time}")

        # 2. Validar que no exista superposición horaria con otra cita activa del profesional
        if status not in ['CANCELLED', 'NO_SHOW']:
            conflict_obj, conflict_start, conflict_end = find_overlapping_appointment(
                business=business,
                staff=staff,
                booking_date=app_date,
                start_time_val=start_time,
                end_time_val=end_time,
            )
            if conflict_obj:
                messages.error(
                    request,
                    f"El horario ({start_time} a {end_time}) se superpone con otro turno de {staff.full_name} "
                    f"({conflict_start} a {conflict_end}). El próximo cupo disponible después de ese turno es a las {conflict_end}."
                )
                return redirect(f"{request.path}?client_id={client.id}&staff_id={staff.id}&date={app_date}&start_time={conflict_end}")

        appointment = Appointment.objects.create(
            business=business,
            client=client,
            staff=staff,
            service=primary_service,
            date=app_date,
            start_time=start_time,
            end_time=end_time,
            total_price=total_price,
            deposit_percentage=dep_pct,
            deposit_amount=dep_amt,
            status=status,
            notes=notes
        )

        for srv, qty in services_items:
            AppointmentService.objects.create(
                appointment=appointment,
                service=srv,
                quantity=qty,
                unit_price=srv.price,
                duration_minutes=srv.duration_minutes
            )

        messages.success(request, f"¡Cita registrada correctamente ({start_time} a {end_time} · {total_duration} min)!")
        return redirect('agenda')

    existing_services = []
    if selected_service_id:
        srv = Service.objects.filter(id=selected_service_id, business=business).first()
        if srv:
            existing_services.append({
                'id': str(srv.id),
                'name': srv.name,
                'price': float(srv.price),
                'duration': srv.duration_minutes,
                'deposit_percentage': float(srv.effective_deposit_percentage),
                'quantity': 1,
                'allowed_staff_ids': get_allowed_staff_ids_for_service(srv, all_active_staff=all_active_staff),
            })
    existing_services_json = json.dumps(existing_services)

    return render(request, 'agenda/appointment_form.html', {
        'business': business,
        'appointment': None,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'existing_services_json': existing_services_json,
        'today_date': selected_date,
        'selected_client_id': selected_client_id,
        'selected_staff_id': selected_staff_id,
        'selected_service_id': selected_service_id,
        'selected_time': selected_time,
        'rebook_info': rebook_info,
        'title': 'Agendar Nueva Cita',
        'is_restricted_scope': (user_scope == 'OWN'),
    })

@login_required
def appointment_edit_view(request, appointment_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    appointment = get_object_or_404(Appointment, id=appointment_id, business=business)

    user_scope = getattr(request.user, 'appointment_scope', 'ALL')
    user_staff = getattr(request.user, 'staff_profile', None)

    if user_scope == 'OWN' and user_staff and appointment.staff != user_staff:
        messages.error(request, "No tienes permiso para ver ni editar citas asignadas a otros profesionales.")
        return redirect('agenda')

    clients = Client.objects.filter(business=business)
    all_active_staff = list(StaffMember.objects.filter(business=business, is_active=True).prefetch_related('services'))
    staff_members = [user_staff] if (user_scope == 'OWN' and user_staff) else all_active_staff
    services = list(Service.objects.filter(business=business, is_active=True).select_related('business').prefetch_related('staff_members'))
    for srv in services:
        srv.allowed_staff_ids_json = json.dumps(
            get_allowed_staff_ids_for_service(srv, all_active_staff=all_active_staff)
        )

    if request.method == 'POST':
        client = get_object_or_404(Client, id=request.POST.get('client_id'), business=business)
        if user_scope == 'OWN' and user_staff:
            staff = user_staff
        else:
            staff = get_object_or_404(StaffMember, id=request.POST.get('staff_id'), business=business)

        services_items = _parse_services_from_post(request, business)
        if not services_items:
            messages.error(request, "Debes seleccionar al menos un servicio para la cita.")
            return redirect(request.path)

        total_duration = sum(srv.duration_minutes * qty for srv, qty in services_items)
        total_price = sum(srv.price * qty for srv, qty in services_items)
        primary_service = services_items[0][0]
        dep_pct, dep_amt = _calculate_appointment_deposit(business, services_items, total_price, request.POST)

        app_date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        end_time_input = request.POST.get('end_time')
        status = request.POST.get('status')

        try:
            st = datetime.datetime.strptime(start_time, "%H:%M")
            et = st + datetime.timedelta(minutes=max(total_duration, 15))
            computed_end_time = et.strftime("%H:%M")
        except (ValueError, TypeError):
            computed_end_time = (
                appointment.end_time.strftime("%H:%M")
                if hasattr(appointment.end_time, 'strftime')
                else str(appointment.end_time or "10:45")[:5]
            )

        end_time = computed_end_time
        if end_time_input:
            try:
                st_dt = datetime.datetime.strptime(start_time, "%H:%M")
                et_in_dt = datetime.datetime.strptime(end_time_input, "%H:%M")
                if et_in_dt >= st_dt + datetime.timedelta(minutes=max(total_duration, 15)):
                    end_time = end_time_input
            except (ValueError, TypeError):
                pass

        # 1. Validar elegibilidad profesional ↔ servicio
        ineligible_services = get_ineligible_services_for_staff(
            staff, [srv for srv, _ in services_items], all_active_staff=all_active_staff
        )
        if ineligible_services:
            bad_names = ", ".join(s.name for s in ineligible_services)
            messages.error(
                request,
                f"El profesional {staff.full_name} ({staff.role_title}) no está habilitado para realizar: {bad_names}. "
                f"Selecciona un especialista asignado a ese servicio."
            )
            return redirect(request.path)

        # 2. Validar superposición horaria excluyendo esta misma cita
        if status not in ['CANCELLED', 'NO_SHOW']:
            conflict_obj, conflict_start, conflict_end = find_overlapping_appointment(
                business=business,
                staff=staff,
                booking_date=app_date,
                start_time_val=start_time,
                end_time_val=end_time,
                exclude_appointment_id=appointment.id,
            )
            if conflict_obj:
                messages.error(
                    request,
                    f"El horario ({start_time} a {end_time}) se superpone con otro turno de {staff.full_name} "
                    f"({conflict_start} a {conflict_end}). El próximo cupo disponible después de ese turno es a las {conflict_end}."
                )
                return redirect(request.path)

        appointment.client = client
        appointment.staff = staff
        appointment.service = primary_service
        appointment.date = app_date
        appointment.start_time = start_time
        appointment.end_time = end_time
        appointment.total_price = total_price
        appointment.deposit_percentage = dep_pct
        appointment.deposit_amount = dep_amt
        appointment.status = status
        appointment.notes = request.POST.get('notes', '')
        appointment.save()

        appointment.appointment_services.all().delete()
        for srv, qty in services_items:
            AppointmentService.objects.create(
                appointment=appointment,
                service=srv,
                quantity=qty,
                unit_price=srv.price,
                duration_minutes=srv.duration_minutes
            )

        messages.success(request, f"Cita actualizada correctamente ({start_time} a {end_time} · {total_duration} min).")
        return redirect('agenda')

    existing_services = []
    items = list(appointment.appointment_services.select_related('service').all())
    if items:
        for it in items:
            existing_services.append({
                'id': str(it.service.id),
                'name': it.service.name,
                'price': float(it.unit_price),
                'duration': it.duration_minutes,
                'deposit_percentage': float(it.service.effective_deposit_percentage),
                'quantity': it.quantity,
                'allowed_staff_ids': get_allowed_staff_ids_for_service(it.service, all_active_staff=all_active_staff),
            })
    elif appointment.service:
        existing_services.append({
            'id': str(appointment.service.id),
            'name': appointment.service.name,
            'price': float(appointment.service.price),
            'duration': appointment.service.duration_minutes,
            'deposit_percentage': float(appointment.service.effective_deposit_percentage),
            'quantity': 1,
            'allowed_staff_ids': get_allowed_staff_ids_for_service(appointment.service, all_active_staff=all_active_staff),
        })
    existing_services_json = json.dumps(existing_services)

    return render(request, 'agenda/appointment_form.html', {
        'business': business,
        'appointment': appointment,
        'clients': clients,
        'staff_members': staff_members,
        'services': services,
        'existing_services_json': existing_services_json,
        'title': f'Editar Cita: {appointment.client.full_name}',
        'is_restricted_scope': (user_scope == 'OWN'),
    })

@login_required
def agenda_available_slots_api(request):
    from django.http import JsonResponse
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'is_open': False, 'slots': [], 'message': 'Negocio no encontrado'}, status=400)

    date_str = request.GET.get('date', datetime.date.today().isoformat())
    staff_id = request.GET.get('staff_id')
    duration_param = request.GET.get('duration', '45')
    exclude_appointment_id = request.GET.get('exclude_appointment_id')

    try:
        booking_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        booking_date = datetime.date.today()

    staff = StaffMember.objects.filter(id=staff_id, business=business).first() if staff_id else None
    if not staff:
        staff = StaffMember.objects.filter(business=business, is_active=True).first()

    try:
        duration_minutes = max(int(duration_param), 15)
    except (ValueError, TypeError):
        duration_minutes = 45

    result = calculate_available_slots(
        business=business,
        booking_date=booking_date,
        staff=staff,
        duration_minutes=duration_minutes,
        exclude_appointment_id=exclude_appointment_id or None,
    )
    return JsonResponse(result)

@login_required
def service_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST' and request.POST.get('action') == 'UPDATE_DEFAULT_DEPOSIT':
        raw_pct = request.POST.get('default_deposit_percentage', '30').strip()
        pct_val = max(Decimal('0.00'), min(Decimal('100.00'), parse_decimal(raw_pct, '30.00')))
        business.default_deposit_percentage = pct_val
        business.save(update_fields=['default_deposit_percentage'])

        if request.POST.get('apply_to_all_services') == '1':
            Service.objects.filter(business=business).update(deposit_percentage=pct_val)
            messages.success(
                request,
                f"¡Porcentaje de seña/anticipo actualizado a {pct_val}% y aplicado a todos los servicios!"
            )
        else:
            messages.success(
                request,
                f"¡Porcentaje de seña/anticipo general actualizado a {pct_val}%!"
            )
        return redirect('service_list')

    categories = ServiceCategory.objects.filter(business=business).prefetch_related('services__staff_members') if business else []
    services_without_category = Service.objects.filter(business=business, category__isnull=True).prefetch_related('staff_members') if business else []
    all_services = Service.objects.filter(business=business).select_related('category').prefetch_related('staff_members').order_by('name') if business else []

    from django.core.paginator import Paginator
    paginator = Paginator(all_services, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'agenda/service_list.html', {
        'business': business,
        'categories': categories,
        'services_without_category': services_without_category,
        'all_services': page_obj,
        'page_obj': page_obj,
    })

@login_required
def service_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    categories = ServiceCategory.objects.filter(business=business) if business else []
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name') if business else []

    if request.method == 'POST':
        name = request.POST.get('name')
        category_id = request.POST.get('category_id')
        price = parse_decimal(request.POST.get('price'), '0.00')
        duration = parse_int(request.POST.get('duration_minutes'), 45)
        description = request.POST.get('description', '')
        commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        raw_deposit = (request.POST.get('deposit_percentage') or '').strip()
        deposit_pct = (
            max(Decimal('0.00'), min(Decimal('100.00'), parse_decimal(raw_deposit, '0.00')))
            if raw_deposit != '' else None
        )
        staff_ids = request.POST.getlist('staff_ids')
        
        category = ServiceCategory.objects.filter(id=category_id, business=business).first() if category_id else None
        
        srv = Service.objects.create(
            business=business,
            name=name,
            category=category,
            price=price,
            duration_minutes=duration,
            description=description,
            commission_rate=commission_rate,
            deposit_percentage=deposit_pct,
            is_active=True
        )
        if staff_ids:
            selected_staff = StaffMember.objects.filter(id__in=staff_ids, business=business)
            srv.staff_members.set(selected_staff)
        return redirect('service_list')

    return render(request, 'agenda/service_form.html', {
        'business': business,
        'service': None,
        'categories': categories,
        'staff_members': staff_members,
        'title': 'Crear Nuevo Servicio'
    })

@login_required
def service_edit_view(request, service_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    service = get_object_or_404(Service, id=service_id, business=business)
    categories = ServiceCategory.objects.filter(business=business)
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        name = request.POST.get('name')
        if name and name.strip():
            service.name = name.strip()

        category_id = request.POST.get('category_id')
        if category_id is not None:
            if category_id.strip():
                service.category = ServiceCategory.objects.filter(id=category_id, business=business).first()
            else:
                service.category = None

        price_raw = request.POST.get('price')
        if price_raw and price_raw.strip():
            service.price = parse_decimal(price_raw, service.price)

        duration_raw = request.POST.get('duration_minutes')
        if duration_raw and duration_raw.strip():
            service.duration_minutes = parse_int(duration_raw, service.duration_minutes)

        description_raw = request.POST.get('description')
        if description_raw is not None:
            service.description = description_raw.strip()

        comm_raw = request.POST.get('commission_rate')
        if comm_raw and comm_raw.strip():
            service.commission_rate = parse_decimal(comm_raw, service.commission_rate)
        elif comm_raw is not None and comm_raw.strip() == '':
            service.commission_rate = Decimal('0.00')

        dep_raw = request.POST.get('deposit_percentage')
        if dep_raw is not None:
            if dep_raw.strip() != '':
                service.deposit_percentage = max(Decimal('0.00'), min(Decimal('100.00'), parse_decimal(dep_raw, '0.00')))
            else:
                service.deposit_percentage = None

        service.save()

        staff_ids = request.POST.getlist('staff_ids')
        selected_staff = StaffMember.objects.filter(id__in=staff_ids, business=business)
        service.staff_members.set(selected_staff)

        messages.success(request, f"Servicio '{service.name}' actualizado exitosamente.")
        return redirect('service_list')

    return render(request, 'agenda/service_form.html', {
        'business': business,
        'service': service,
        'categories': categories,
        'staff_members': staff_members,
        'title': f'Editar Servicio: {service.name}'
    })

@login_required
def service_category_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

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

@login_required
def appointment_calendar_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff_members = StaffMember.objects.filter(business=business, is_active=True) if business else []

    slot_min_time = "00:00:00"
    slot_max_time = "24:00:00"

    return render(request, 'agenda/calendar.html', {
        'business': business,
        'staff_members': staff_members,
        'slot_min_time': slot_min_time,
        'slot_max_time': slot_max_time,
    })

@login_required
def appointment_events_api(request):
    from django.http import JsonResponse
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse([], safe=False)

    expire_overdue_pending_appointments(business)

    staff_id = request.GET.get('staff_id', '')

    appointments = Appointment.objects.filter(business=business).select_related('client', 'staff', 'service').prefetch_related('appointment_services__service')
    if staff_id:
        appointments = appointments.filter(staff_id=staff_id)

    events = []
    for app in appointments:
        start_dt = f"{app.date.isoformat()}T{app.start_time.strftime('%H:%M:%S')}"
        end_dt = f"{app.date.isoformat()}T{app.end_time.strftime('%H:%M:%S')}"
        color = "#10b981" if app.status == 'COMPLETED' else ("#6366f1" if app.status == 'CONFIRMED' else ("#94a3b8" if app.status == 'CANCELLED' else "#f59e0b"))
        srv_name = app.services_summary
        
        events.append({
            'id': str(app.id),
            'title': f"{app.client.full_name} - {srv_name}",
            'start': start_dt,
            'end': end_dt,
            'url': f"/agenda/{app.id}/editar/",
            'backgroundColor': color,
            'borderColor': color,
            'extendedProps': {
                'client': app.client.full_name,
                'service': srv_name,
                'staff': app.staff.full_name,
                'status': app.get_status_display(),
                'price': str(app.total_price)
            }
        })

    return JsonResponse(events, safe=False)


@login_required
def appointment_quick_status_view(request, appointment_id):
    """
    Permite confirmar o cancelar rápidamente una cita pendiente desde la vista de Agenda
    y notifica automáticamente al cliente sobre la actualización de su cita.
    """
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method != 'POST':
        return redirect('agenda')

    appointment = get_object_or_404(Appointment, id=appointment_id, business=business)
    new_status = (request.POST.get('status') or '').strip().upper()
    next_date = request.POST.get('next_date') or appointment.date.isoformat()

    if new_status in ('CONFIRMED', 'CANCELLED', 'PENDING'):
        appointment.status = new_status
        appointment.save(update_fields=['status'])

        if new_status == 'CONFIRMED':
            send_booking_notification_to_client(
                business=business,
                appointment=appointment,
                event_type='CONFIRMED',
                request=request
            )
            messages.success(request, f"✅ Cita de {appointment.client.full_name} confirmada y notificación enviada.")
        elif new_status == 'CANCELLED':
            send_booking_notification_to_client(
                business=business,
                appointment=appointment,
                event_type='CANCELLED',
                request=request
            )
            messages.info(request, f"❌ Cita de {appointment.client.full_name} cancelada y horario liberado.")
        else:
            messages.success(request, f"Estado de la cita actualizado a {appointment.get_status_display()}.")

    return redirect(f"/agenda/?date={next_date}")

