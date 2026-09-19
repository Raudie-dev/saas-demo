import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from apps.business.models import Business, StaffMember
from apps.agenda.models import Service, Appointment
from apps.crm.models import Client
from apps.ai_engine.models import AIAutomationLog

def public_booking_view(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    services = Service.objects.filter(business=business, is_active=True)
    staff_members = StaffMember.objects.filter(business=business, is_active=True)
    
    booking_success = False
    appointment_created = None

    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        staff_id = request.POST.get('staff_id')
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email', '')
        
        service = get_object_or_404(Service, id=service_id, business=business)
        staff = get_object_or_404(StaffMember, id=staff_id, business=business)
        
        # Get or create client
        client, _ = Client.objects.get_or_create(
            phone=phone,
            business=business,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'status': 'ACTIVE'
            }
        )
        
        # calculate end time
        st = datetime.datetime.strptime(time_str, "%H:%M")
        et = st + datetime.timedelta(minutes=service.duration_minutes)
        end_time = et.strftime("%H:%M")
        
        appointment_created = Appointment.objects.create(
            business=business,
            client=client,
            staff=staff,
            service=service,
            date=date_str,
            start_time=time_str,
            end_time=end_time,
            total_price=service.price,
            deposit_amount=service.price * Decimal('0.30') if hasattr(service, 'price') else 0,
            status='CONFIRMED'
        )
        
        # Trigger simulated WhatsApp confirmation message
        wa_msg = f"✅ *¡Cita Confirmada en {business.name}!*\n📅 Fecha: {date_str} a las {time_str} hs.\n💇‍♂️ Especialista: {staff.full_name}\n💈 Servicio: {service.name}\n📍 Dirección: {business.address}"
        AIAutomationLog.objects.create(
            business=business,
            target_client=client,
            action_type='WHATSAPP_REMINDER',
            prompt_used=f"Confirmación de Reserva 24/7 para {client.full_name}",
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
