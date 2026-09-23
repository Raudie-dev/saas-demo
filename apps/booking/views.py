import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from apps.business.models import Business, StaffMember, WorkSchedule
from apps.agenda.models import Service, Appointment
from apps.crm.models import Client
from apps.ai_engine.models import AIAutomationLog

def api_available_slots_view(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    date_str = request.GET.get('date', datetime.date.today().isoformat())
    staff_id = request.GET.get('staff_id')

    try:
        booking_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        booking_date = datetime.date.today()

    weekday = booking_date.weekday()

    staff = None
    if staff_id:
        staff = StaffMember.objects.filter(id=staff_id, business=business).first()
    if not staff:
        staff = StaffMember.objects.filter(business=business, is_active=True).first()

    schedule = None
    if staff:
        schedule = WorkSchedule.objects.filter(staff=staff, day_of_week=weekday).first()

    staff_name = staff.full_name if staff else "el profesional"

    if schedule and not schedule.is_working_day:
        return JsonResponse({
            'is_open': False, 
            'staff_name': staff_name,
            'message': f'{staff_name} no atiende en la fecha seleccionada.', 
            'slots': []
        })

    start_hour = 9
    end_hour = 14 if weekday == 5 else (0 if weekday == 6 else 19)
    if weekday == 6 and not (schedule and schedule.is_working_day):
        return JsonResponse({
            'is_open': False, 
            'staff_name': staff_name,
            'message': f'{staff_name} no atiende los domingos.', 
            'slots': []
        })

    if schedule:
        start_hour = schedule.start_time.hour
        end_hour = schedule.end_time.hour

    slots = []
    curr_time = datetime.datetime.combine(booking_date, datetime.time(hour=start_hour))
    end_time_dt = datetime.datetime.combine(booking_date, datetime.time(hour=end_hour))

    existing_appointments = Appointment.objects.filter(
        business=business,
        date=booking_date.isoformat()
    )
    if staff:
        existing_appointments = existing_appointments.filter(staff=staff)

    booked_times = set()
    for app in existing_appointments:
        t_key = app.start_time[:5] if isinstance(app.start_time, str) else app.start_time.strftime('%H:%M')
        booked_times.add(t_key)

    while curr_time + datetime.timedelta(minutes=30) <= end_time_dt:
        time_str = curr_time.strftime("%H:%M")
        is_booked = time_str in booked_times
        
        # Staff specific slot availability
        is_disabled = is_booked

        slots.append({
            'time': time_str,
            'disabled': is_disabled
        })

        curr_time += datetime.timedelta(minutes=60)

    return JsonResponse({
        'is_open': True,
        'staff_name': staff_name,
        'date': booking_date.isoformat(),
        'slots': slots
    })

@ensure_csrf_cookie
def public_booking_view(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
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

    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    if not staff_members.exists() and hasattr(request, 'user') and request.user.is_authenticated:
        # Fallback staff profile
        StaffMember.objects.get_or_create(
            business=business,
            first_name=request.user.first_name or "Especialista",
            last_name=request.user.last_name or "Principal",
            defaults={'role_title': 'Director / Asesor'}
        )
        staff_members = StaffMember.objects.filter(business=business, is_active=True)
    
    booking_success = False
    appointment_created = None

    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        staff_id = request.POST.get('staff_id')
        date_str = request.POST.get('date', datetime.date.today().isoformat())
        time_str = request.POST.get('time', '10:00')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        
        service = Service.objects.filter(id=service_id, business=business).first() if service_id else services.first()
        if not service:
            service = services.first()

        staff = StaffMember.objects.filter(id=staff_id, business=business).first() if staff_id else staff_members.first()
        if not staff:
            staff = staff_members.first()
        
        # Get or create client
        client, _ = Client.objects.get_or_create(
            phone=phone or "0000000000",
            business=business,
            defaults={
                'first_name': first_name or "Cliente",
                'last_name': last_name or "Reservas",
                'email': email,
                'status': 'ACTIVE'
            }
        )
        
        # calculate end time
        try:
            st = datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            st = datetime.datetime.strptime("10:00", "%H:%M")

        duration = service.duration_minutes if service else 45
        et = st + datetime.timedelta(minutes=duration)
        end_time = et.strftime("%H:%M")
        
        appointment_created = Appointment.objects.create(
            business=business,
            client=client,
            staff=staff,
            service=service,
            date=date_str,
            start_time=time_str,
            end_time=end_time,
            total_price=service.price if service else Decimal("0.00"),
            deposit_amount=(service.price * Decimal('0.30')) if service and hasattr(service, 'price') else Decimal("0.00"),
            status='CONFIRMED'
        )
        
        # Trigger simulated WhatsApp confirmation message
        wa_msg = f"✅ *¡Cita Confirmada en {business.name}!*\n📅 Fecha: {date_str} a las {time_str} hs.\n💇‍♂️ Especialista: {staff.full_name if staff else 'Equipo'}\n💈 Servicio: {service.name if service else 'Reserva'}\n📍 Dirección: {business.address}"
        AIAutomationLog.objects.create(
            business=business,
            target_client=client,
            action_type='WHATSAPP_REMINDER',
            prompt_used=f"Confirmación de Reserva para {client.full_name}",
            response_generated=wa_msg,
            status='SIMULATED'
        )
        
        booking_success = True

    return render(request, 'booking/public_booking.html', {
        'business': business,
        'services': services,
        'staff_members': staff_members,
        'booking_success': booking_success,
        'appointment': appointment_created,
        'today_date': datetime.date.today().isoformat()
    })
