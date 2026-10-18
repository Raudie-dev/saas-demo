import datetime
from decimal import Decimal
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from apps.business.models import Business, StaffMember, WorkSchedule, Branch
from apps.agenda.models import Service, Appointment, ServiceCategory, AppointmentService
from apps.crm.models import Client
from apps.ai_engine.models import AIAutomationLog
from apps.core.utils import format_phone_with_prefix, split_phone_number

from apps.agenda.utils import (
    calculate_available_slots,
    get_allowed_staff_ids_for_service,
    get_ineligible_services_for_staff,
    find_overlapping_appointment,
    expire_overdue_pending_appointments,
    send_booking_notification_to_client,
)


def _resolve_portal_client(business, first_name, last_name, phone, email):
    """
    Resuelve o crea el cliente que agenda desde el portal público sin anclarlo
    únicamente por el número de teléfono.
    Si se ingresa un nombre distinto o un correo distinto (aunque el teléfono
    ya pertenezca a otro cliente registrado), se crea/asocia a la persona que
    se está registrando y no al dueño original del teléfono.
    """
    clean_first = (first_name or "Cliente").strip()
    clean_last = (last_name or "").strip()
    clean_phone = (phone or "0000000000").strip()
    clean_email = (email or "").strip()

    name_matches = Client.objects.filter(
        business=business,
        first_name__iexact=clean_first,
        last_name__iexact=clean_last,
    )

    client = None
    if clean_email:
        client = name_matches.filter(email__iexact=clean_email).first()
        if not client:
            same_phone_cand = name_matches.filter(phone=clean_phone).first()
            if same_phone_cand and (not same_phone_cand.email or same_phone_cand.email.lower() == clean_email.lower()):
                client = same_phone_cand
    else:
        client = name_matches.filter(phone=clean_phone).first()

    if client:
        updated_fields = []
        if clean_email and not client.email:
            client.email = clean_email
            updated_fields.append('email')
        if clean_phone and client.phone != clean_phone:
            client.phone = clean_phone
            updated_fields.append('phone')
        if updated_fields:
            client.save(update_fields=updated_fields)
        return client

    return Client.objects.create(
        business=business,
        first_name=clean_first,
        last_name=clean_last,
        phone=clean_phone,
        email=clean_email or None,
        status='ACTIVE',
    )


def api_available_slots_view(request, business_slug):
    from django.http import Http404
    business = get_object_or_404(Business, slug=business_slug)

    if not business.is_booking_enabled and not (hasattr(request, 'user') and request.user.is_authenticated):
        raise Http404("El portal de reservas se encuentra desactivado.")

    date_str = request.GET.get('date', datetime.date.today().isoformat())
    staff_id = request.GET.get('staff_id')
    duration_param = request.GET.get('duration')
    service_ids_param = request.GET.get('service_ids', '')
    exclude_appointment_id = request.GET.get('exclude_appointment_id')

    try:
        booking_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        booking_date = datetime.date.today()

    staff = None
    if staff_id:
        staff = StaffMember.objects.filter(id=staff_id, business=business).first()
    if not staff:
        staff = StaffMember.objects.filter(business=business, is_active=True).first()

    duration_minutes = 0
    if duration_param:
        try:
            duration_minutes = int(duration_param)
        except (ValueError, TypeError):
            duration_minutes = 0

    if duration_minutes <= 0 and service_ids_param:
        s_ids = [s.strip() for s in service_ids_param.split(',') if s.strip()]
        if s_ids:
            duration_minutes = sum(
                srv.duration_minutes for srv in Service.objects.filter(id__in=s_ids, business=business)
            )

    if duration_minutes <= 0:
        default_srv = Service.objects.filter(business=business, is_active=True).first()
        duration_minutes = default_srv.duration_minutes if default_srv else 45

    result = calculate_available_slots(
        business=business,
        booking_date=booking_date,
        staff=staff,
        duration_minutes=duration_minutes,
        exclude_appointment_id=exclude_appointment_id or None,
    )
    return JsonResponse(result)

@ensure_csrf_cookie
def public_booking_view(request, business_slug):
    from django.db.models import Q
    from django.http import Http404

    business = get_object_or_404(Business, slug=business_slug)

    # Si el portal está desactivado, arrojar error 404
    if not business.is_booking_enabled:
        raise Http404("El portal de reservas se encuentra desactivado.")

    branches = Branch.objects.filter(business=business)
    branch_id = request.GET.get('branch_id') or request.POST.get('branch_id')
    selected_branch = None
    if branch_id:
        selected_branch = branches.filter(id=branch_id).first()
    if not selected_branch:
        selected_branch = branches.filter(is_main=True).first() or branches.first()
        # Si es la sucursal principal y business.address fue actualizado en Configuración, sincronizarla automáticamente
        if selected_branch and business.address and selected_branch.address != business.address and (selected_branch.is_main or branches.count() == 1):
            selected_branch.address = business.address
            selected_branch.save(update_fields=['address'])

    services = Service.objects.filter(business=business, is_active=True)
    
    # Auto-create default service if business has no active services
    if not services.exists():
        Service.objects.create(
            business=business,
            name="Asesoría / Servicio General",
            description="Atención personalizada y desarrollo de proyecto",
            duration_minutes=45,
            price=Decimal("50.00"),
            is_active=True
        )
        services = Service.objects.filter(business=business, is_active=True)

    # Group services by category
    categories = ServiceCategory.objects.filter(business=business).order_by('name')
    uncategorized_services = services.filter(category__isnull=True)
    
    # Pre-fetch services per category
    category_data = []
    for cat in categories:
        cat_services = services.filter(category=cat)
        if cat_services.exists():
            category_data.append({
                'category': cat,
                'services': cat_services
            })

    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    if selected_branch:
        # Filter staff assigned to selected branch
        staff_in_branch = staff_members.filter(Q(branch=selected_branch) | Q(branches=selected_branch)).distinct()
        if staff_in_branch.exists():
            staff_members = staff_in_branch

    if not staff_members.exists() and hasattr(request, 'user') and request.user.is_authenticated:
        # Fallback staff profile
        StaffMember.objects.get_or_create(
            business=business,
            first_name=request.user.first_name or "Especialista",
            last_name=request.user.last_name or "Principal",
            defaults={'role_title': 'Director / Asesor'}
        )
        staff_members = StaffMember.objects.filter(business=business, is_active=True)
    
    # Check if business is real estate or has properties module enabled
    from apps.properties.models import Property
    is_real_estate = (business.business_type == 'REAL_ESTATE') or business.is_module_enabled('properties') or Property.objects.filter(business=business).exists()
    
    properties_qs = Property.objects.none()
    properties_catalog_json = "[]"
    if is_real_estate or business.is_module_enabled('properties'):
        properties_qs = Property.objects.filter(business=business, status='AVAILABLE').order_by('-is_featured', '-created_at')
        properties_catalog_json = json.dumps([
            {
                'id': str(p.id),
                'title': p.title,
                'reference_code': p.reference_code or '',
                'operation_type': p.operation_type,
                'operation_display': p.get_operation_type_display(),
                'property_type': p.property_type,
                'type_display': p.get_property_type_display(),
                'price': float(p.price),
                'formatted_price': p.formatted_price,
                'currency': p.currency,
                'expenses': p.formatted_expenses or '',
                'address': p.address,
                'zone': p.zone,
                'bedrooms': p.bedrooms,
                'bathrooms': p.bathrooms,
                'garages': p.garages,
                'total_surface': float(p.total_surface) if p.total_surface else 0,
                'covered_surface': float(p.covered_surface) if p.covered_surface else 0,
                'portal_url': p.portal_url or '',
                'portal_display_name': p.portal_display_name,
                'photos': [photo['url'] for photo in p.photos_list],
                'main_photo': p.main_photo_url or '/static/images/property_placeholder.png',
                'description': p.description or '',
            }
            for p in properties_qs
        ])

    expire_overdue_pending_appointments(business)

    booking_success = False
    appointment_created = None
    notification_info = None
    portal_error_message = None

    default_phone_prefix, _ = split_phone_number(business.phone if business else '')

    if request.method == 'POST':
        staff_id = request.POST.get('staff_id')
        date_str = request.POST.get('date') or request.POST.get('booking_date') or datetime.date.today().isoformat()
        time_str = request.POST.get('time') or request.POST.get('booking_time') or '10:00'
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        client_name = request.POST.get('client_name', '').strip()
        if not first_name and client_name:
            parts = client_name.split(' ', 1)
            first_name = parts[0]
            if len(parts) > 1 and not last_name:
                last_name = parts[1]
        
        client_phone_prefix = request.POST.get('client_phone_prefix', '').strip() or default_phone_prefix
        raw_phone = (request.POST.get('phone') or request.POST.get('client_phone', '')).strip()
        phone = format_phone_with_prefix(client_phone_prefix, raw_phone)
        email = (request.POST.get('email') or request.POST.get('client_email', '')).strip()

        # Check for property booking (inmobiliaria visit)
        property_id = request.POST.get('property_id')
        selected_property = None
        if property_id:
            selected_property = Property.objects.filter(id=property_id, business=business).first()
        
        # Parse multiple services or same service multiple times
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
            except Exception:
                pass

        # Fallback to single service_id
        if not services_items and not selected_property:
            service_id = request.POST.get('service_id')
            service = Service.objects.filter(id=service_id, business=business).first() if service_id else services.first()
            if service:
                services_items.append((service, 1))

        # Real estate visit fallback service if no services provided
        if not services_items and selected_property:
            visit_service, _ = Service.objects.get_or_create(
                business=business,
                name="Visita a Propiedad",
                defaults={
                    'description': f"Coordinación de visita a {selected_property.title}",
                    'duration_minutes': 45,
                    'price': Decimal('0.00'),
                    'is_active': True
                }
            )
            services_items.append((visit_service, 1))

        if not services_items and services.exists():
            services_items.append((services.first(), 1))

        staff = StaffMember.objects.filter(id=staff_id, business=business).first() if staff_id else None
        all_staff_list = list(staff_members.prefetch_related('services'))
        selected_srv_objs = [srv for srv, _ in services_items]

        # Si no se especificó profesional o el profesional no es elegible, buscar el primero elegible si no vino forzado
        if not staff and selected_srv_objs:
            for st_cand in all_staff_list:
                if not get_ineligible_services_for_staff(st_cand, selected_srv_objs, all_active_staff=all_staff_list):
                    staff = st_cand
                    break
        if not staff:
            staff = staff_members.first()

        total_duration = sum(srv.duration_minutes * qty for srv, qty in services_items)
        total_price = sum(srv.price * qty for srv, qty in services_items)
        primary_service = services_items[0][0] if services_items else None

        # calculate end time
        try:
            st = datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            st = datetime.datetime.strptime("10:00", "%H:%M")

        duration = max(total_duration, 15)
        et = st + datetime.timedelta(minutes=duration)
        end_time = et.strftime("%H:%M")

        # 1. Validar que el profesional esté anclado/habilitado para todos los servicios seleccionados
        ineligible_services = []
        if staff and not selected_property and selected_srv_objs:
            ineligible_services = get_ineligible_services_for_staff(
                staff, selected_srv_objs, all_active_staff=all_staff_list
            )

        # 2. Validar que el horario [time_str, end_time) no se superponga con otra cita del profesional
        conflict_obj, conflict_start, conflict_end = (None, None, None)
        if staff and not ineligible_services:
            conflict_obj, conflict_start, conflict_end = find_overlapping_appointment(
                business=business,
                staff=staff,
                booking_date=date_str,
                start_time_val=time_str,
                end_time_val=end_time,
            )

        if ineligible_services:
            bad_names = ", ".join(s.name for s in ineligible_services)
            portal_error_message = (
                f"El profesional {staff.full_name} ({staff.role_title}) no está asignado para realizar: {bad_names}. "
                f"Por favor selecciona un especialista habilitado para ese servicio."
            )
        elif conflict_obj:
            portal_error_message = (
                f"El horario seleccionado ({time_str} a {end_time}) se superpone con una reserva existente de "
                f"{staff.full_name} ({conflict_start} a {conflict_end}). "
                f"El próximo cupo disponible después de ese turno es a las {conflict_end}."
            )
        else:
            # Resolver o crear el cliente por nombre/correo/teléfono sin anclarlo solo al teléfono
            client = _resolve_portal_client(
                business=business,
                first_name=first_name or "Cliente",
                last_name=last_name or "",
                phone=phone or "0000000000",
                email=email,
            )
            
            client_notes = (request.POST.get('client_notes') or request.POST.get('notes') or '').strip()
            notes_text = f"Visita a propiedad: {selected_property.title} ({selected_property.address})" if selected_property else None
            if client_notes:
                notes_text = f"{notes_text}\nConsulta/Comentarios: {client_notes}" if notes_text else client_notes

            if selected_property:
                calc_deposit_amount = Decimal('0.00')
                calc_deposit_pct = Decimal('0.00')
            else:
                calc_deposit_amount = sum(
                    (srv.effective_deposit_amount * qty for srv, qty in services_items),
                    Decimal('0.00')
                ).quantize(Decimal('0.01'))
                if total_price > 0:
                    calc_deposit_pct = ((calc_deposit_amount / total_price) * Decimal('100.00')).quantize(Decimal('0.01'))
                else:
                    calc_deposit_pct = Decimal(str(getattr(business, 'default_deposit_percentage', Decimal('30.00')) or '0.00'))

            appointment_created = Appointment.objects.create(
                business=business,
                client=client,
                staff=staff,
                service=primary_service,
                related_property=selected_property,
                date=date_str,
                start_time=time_str,
                end_time=end_time,
                total_price=total_price,
                deposit_percentage=calc_deposit_pct,
                deposit_amount=calc_deposit_amount,
                status='PENDING',
                notes=notes_text
            )

            if selected_property:
                from apps.properties.models import PropertyInquiry
                PropertyInquiry.objects.create(
                    business=business,
                    client=client,
                    property=selected_property,
                    inquiry_type='BUYER',
                    operation_type=selected_property.get_operation_type_display(),
                    property_type=selected_property.get_property_type_display(),
                    address_zone=f"{selected_property.address} ({selected_property.zone})",
                    estimated_price=selected_property.formatted_price,
                    notes=client_notes or f"Visita coordinada para el {date_str} a las {time_str} hs (Pendiente de confirmación).",
                    status='VISITING',
                    agent=staff
                )

            for srv, qty in services_items:
                AppointmentService.objects.create(
                    appointment=appointment_created,
                    service=srv,
                    quantity=qty,
                    unit_price=srv.price,
                    duration_minutes=srv.duration_minutes
                )
            
            branch_addr = selected_branch.address if selected_branch else business.address
            
            notification_info = send_booking_notification_to_client(
                business=business,
                appointment=appointment_created,
                event_type='PENDING',
                request=request,
                branch_address=branch_addr
            )
            
            booking_success = True

    all_active_staff_for_catalog = list(staff_members.prefetch_related('services'))
    services_with_staff = services.prefetch_related('staff_members')
    services_catalog_json = json.dumps([
        {
            'id': str(s.id),
            'name': s.name,
            'price': float(s.price),
            'deposit_percentage': float(s.effective_deposit_percentage),
            'deposit_amount': float(s.effective_deposit_amount),
            'duration': s.duration_minutes,
            'description': s.description or '',
            'category': s.category.name if s.category else 'Otros',
            'allowed_staff_ids': get_allowed_staff_ids_for_service(s, all_active_staff=all_active_staff_for_catalog),
        }
        for s in services_with_staff
    ])

    return render(request, 'booking/public_booking.html', {
        'business': business,
        'branches': branches,
        'selected_branch': selected_branch,
        'is_real_estate': is_real_estate,
        'properties': properties_qs,
        'properties_catalog_json': properties_catalog_json,
        'services': services,
        'services_catalog_json': services_catalog_json,
        'total_services_count': services.count(),
        'category_data': category_data,
        'uncategorized_services': uncategorized_services,
        'staff_members': staff_members,
        'booking_success': booking_success,
        'appointment': appointment_created,
        'notification_info': notification_info,
        'today_date': datetime.date.today().isoformat(),
        'default_phone_prefix': default_phone_prefix,
        'portal_error_message': portal_error_message
    })


def api_seller_register_view(request, business_slug):
    """
    Endpoint AJAX para registrar solicitudes de propietarios interesados
    en vender, alquilar o tasar su inmueble a través de la inmobiliaria.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    business = get_object_or_404(Business, slug=business_slug)

    full_name = request.POST.get('name', '').strip()
    phone_prefix = request.POST.get('phone_prefix', '+54').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    email = request.POST.get('email', '').strip()
    operation_type = request.POST.get('operation_type', 'Vender').strip()
    property_type = request.POST.get('property_type', 'Departamento').strip()
    address_zone = request.POST.get('address_zone', '').strip()
    rooms = request.POST.get('rooms', '').strip()
    estimated_price = request.POST.get('estimated_price', '').strip()
    comments = request.POST.get('comments', '').strip()

    if not full_name:
        return JsonResponse({'success': False, 'error': 'Por favor ingresa tu nombre completo.'})
    if not phone_number:
        return JsonResponse({'success': False, 'error': 'Por favor ingresa tu número de WhatsApp / teléfono.'})
    if not address_zone:
        return JsonResponse({'success': False, 'error': 'Por favor ingresa la ubicación o barrio del inmueble.'})

    formatted_phone = format_phone_with_prefix(phone_prefix, phone_number)

    # Split name
    name_parts = full_name.split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    lead_details = [
        f"Operación: {operation_type}",
        f"Tipo: {property_type}",
        f"Ubicación: {address_zone}",
    ]
    if rooms:
        lead_details.append(f"Ambientes: {rooms}")
    if estimated_price:
        lead_details.append(f"Precio estimado: {estimated_price}")
    if comments:
        lead_details.append(f"Comentarios: {comments}")

    lead_note = f"[PROPIETARIO - SOLICITUD DE {operation_type.upper()}]: " + " · ".join(lead_details)

    # Create or update Client in CRM without anchoring solely by phone
    client = _resolve_portal_client(
        business=business,
        first_name=first_name,
        last_name=last_name,
        phone=formatted_phone,
        email=email,
    )
    existing_notes = client.notes or ''
    client.notes = f"{existing_notes}\n\n{lead_note}".strip()
    client.save(update_fields=['notes'])

    # Create structured PropertyInquiry
    from apps.properties.models import PropertyInquiry
    PropertyInquiry.objects.create(
        business=business,
        client=client,
        inquiry_type='SELLER',
        operation_type=operation_type,
        property_type=property_type,
        address_zone=address_zone,
        rooms=rooms or None,
        estimated_price=estimated_price or None,
        notes=comments or "Solicitud enviada a través del portal inmobiliario.",
        status='PENDING'
    )

    # Log automation / lead notification
    wa_notification = (
        f"🏡 *¡Nuevo Propietario para {operation_type.upper()} en {business.name}!* \n"
        f"👤 Propietario: {client.full_name}\n"
        f"📞 WhatsApp: {formatted_phone}\n"
        f"🏢 Inmueble: {property_type} en {address_zone}\n"
        f"📝 Detalles: {' · '.join(lead_details)}"
    )

    AIAutomationLog.objects.create(
        business=business,
        target_client=client,
        action_type='LEAD_GENERATED',
        prompt_used=f"Propietario registrado para {operation_type} ({client.full_name})",
        response_generated=wa_notification,
        status='SUCCESS'
    )

    return JsonResponse({
        'success': True,
        'first_name': client.first_name,
        'message': f'¡Gracias {client.first_name}! Recibimos la información de tu propiedad. Un asesor de {business.name} se contactará contigo a la brevedad.'
    })


def public_appointment_action_view(request, business_slug, appointment_id, action):
    """
    Permite al cliente confirmar o cancelar su reserva pendiente desde el enlace
    enviado en su notificación (o desde la pantalla posterior a la reserva),
    siempre que no haya vencido el plazo de espera configurado por el negocio.
    """
    business = get_object_or_404(Business, slug=business_slug)
    expire_overdue_pending_appointments(business)

    appointment = get_object_or_404(Appointment, id=appointment_id, business=business)
    action_clean = (action or '').strip().lower()
    action_feedback = None

    if action_clean in ('confirmar', 'confirm'):
        if appointment.status == 'CANCELLED':
            action_feedback = {
                'type': 'expired',
                'title': 'Reserva Vencida o Cancelada',
                'message': f'El plazo de espera de {business.pending_booking_expiry_hours} horas venció o la cita fue cancelada previamente. Por favor realiza una nueva reserva.'
            }
        else:
            if appointment.status != 'CONFIRMED':
                appointment.status = 'CONFIRMED'
                appointment.save(update_fields=['status'])
                send_booking_notification_to_client(
                    business=business,
                    appointment=appointment,
                    event_type='CONFIRMED',
                    request=request
                )
            action_feedback = {
                'type': 'confirmed',
                'title': '¡Cita Confirmada con Éxito!',
                'message': 'Tu asistencia ha sido confirmada y tu lugar ya está 100% asegurado en nuestra agenda.'
            }

    elif action_clean in ('cancelar', 'cancel'):
        if appointment.status != 'CANCELLED':
            appointment.status = 'CANCELLED'
            cancel_note = "[Cancelada por el cliente desde el portal/notificación]"
            appointment.notes = f"{appointment.notes}\n{cancel_note}".strip() if appointment.notes else cancel_note
            appointment.save(update_fields=['status', 'notes'])
            send_booking_notification_to_client(
                business=business,
                appointment=appointment,
                event_type='CANCELLED',
                request=request
            )
        action_feedback = {
            'type': 'cancelled',
            'title': 'Reserva Cancelada',
            'message': 'Tu reserva ha sido cancelada y el horario ha quedado liberado.'
        }

    branches = Branch.objects.filter(business=business, is_active=True)
    selected_branch = branches.filter(is_main=True).first() or branches.first()
    branch_addr = selected_branch.address if selected_branch else business.address

    notification_info = {
        'confirm_url': f"{request.scheme}://{request.get_host()}/reservas/{business.slug}/cita/{appointment.id}/confirmar/",
        'cancel_url': f"{request.scheme}://{request.get_host()}/reservas/{business.slug}/cita/{appointment.id}/cancelar/",
    }

    return render(request, 'booking/public_booking.html', {
        'business': business,
        'branches': branches,
        'selected_branch': selected_branch,
        'booking_success': True,
        'appointment': appointment,
        'notification_info': notification_info,
        'action_feedback': action_feedback,
        'today_date': datetime.date.today().isoformat(),
    })

