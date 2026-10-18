import datetime
import re
import urllib.parse
import requests
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from apps.business.models import StaffMember, WorkSchedule
from apps.agenda.models import Appointment, ScheduleBlock, Service
from apps.ai_engine.models import AIAutomationLog


GATEWAY_BASE_URL = "http://127.0.0.1:3000"


def expire_overdue_pending_appointments(business):
    """
    Revisa todas las citas en estado PENDING del negocio y, si ya superaron las horas de espera
    configuradas (`business.pending_booking_expiry_hours`, por defecto 24h), las pasa automáticamente
    a CANCELLED para liberar el cupo en la agenda y en el portal de reservas.
    """
    if not business:
        return 0
    expiry_hours = getattr(business, 'pending_booking_expiry_hours', 24) or 24
    cutoff = timezone.now() - datetime.timedelta(hours=expiry_hours)
    overdue_qs = Appointment.objects.filter(
        business=business,
        status='PENDING',
        created_at__lte=cutoff
    ).select_related('client')

    expired_count = 0
    for app in overdue_qs:
        app.status = 'CANCELLED'
        expiry_note = f"[Auto-Cancelada: No se confirmó dentro de las {expiry_hours}h de espera]"
        app.notes = f"{app.notes}\n{expiry_note}".strip() if app.notes else expiry_note
        app.save(update_fields=['status', 'notes'])
        expired_count += 1
    return expired_count


def send_booking_notification_to_client(business, appointment, event_type='PENDING', request=None, branch_address=None):
    """
    Envía notificación al cliente cuando:
    - event_type='PENDING': Hace una reserva desde el portal (queda Pendiente por X horas)
    - event_type='CONFIRMED': Su reserva pasa a Confirmada
    - event_type='CANCELLED': Su reserva es Cancelada
    Intenta envío real por WhatsApp Gateway (si está conectado), por Email (si tiene correo),
    y registra el evento en AIAutomationLog. Retorna dict con mensaje y enlaces.
    """
    client = appointment.client
    staff_name = appointment.staff.full_name if appointment.staff else "Equipo"
    branch_addr = branch_address or getattr(business, 'address', '') or 'Sucursal Principal'
    expiry_hours = getattr(business, 'pending_booking_expiry_hours', 24) or 24
    date_str = appointment.date.strftime("%Y-%m-%d") if isinstance(appointment.date, datetime.date) else str(appointment.date)
    time_str = appointment.start_time.strftime("%H:%M") if isinstance(appointment.start_time, datetime.time) else str(appointment.start_time)[:5]
    services_text = appointment.services_summary

    confirm_url = ""
    cancel_url = ""
    if request:
        base_host = f"{request.scheme}://{request.get_host()}"
        confirm_url = f"{base_host}/reservas/{business.slug}/cita/{appointment.id}/confirmar/"
        cancel_url = f"{base_host}/reservas/{business.slug}/cita/{appointment.id}/cancelar/"

    if event_type == 'PENDING':
        if appointment.related_property:
            prop = appointment.related_property
            msg = (
                f"⏳ *¡Hola {client.first_name}! Tu solicitud de visita en {business.name} está PENDIENTE DE CONFIRMACIÓN*\n\n"
                f"📅 *Fecha:* {date_str} a las {time_str} hs.\n"
                f"👤 *Asesor:* {staff_name}\n"
                f"🏠 *Propiedad:* {prop.title}\n"
                f"📍 *Ubicación:* {prop.address} ({prop.zone})\n\n"
                f"⚠️ *Importante:* Tu cupo ha sido reservado temporalmente por *{expiry_hours} horas*. "
                f"Por favor confirma tu asistencia dentro de este plazo para asegurar tu turno, de lo contrario el cupo se liberará automáticamente."
            )
        else:
            deposit_line = ""
            if appointment.deposit_amount and appointment.deposit_amount > 0:
                deposit_line = (
                    f"💳 *Total:* {business.currency}{appointment.total_price} "
                    f"(Seña / Anticipo {appointment.deposit_percentage:.0f}%: *{business.currency}{appointment.deposit_amount}* · "
                    f"Saldo restante: {business.currency}{appointment.balance_due})\n"
                )
            msg = (
                f"⏳ *¡Hola {client.first_name}! Tu reserva en {business.name} está PENDIENTE DE CONFIRMACIÓN*\n\n"
                f"📅 *Fecha:* {date_str} a las {time_str} hs.\n"
                f"💇‍♂️ *Especialista:* {staff_name}\n"
                f"💈 *Servicios:* {services_text}\n"
                f"{deposit_line}"
                f"📍 *Dirección:* {branch_addr}\n\n"
                f"⚠️ *Importante:* Tu puesto se mantendrá reservado por *{expiry_hours} horas*. "
                f"Por favor confirma tu cita antes de que venza el plazo para asegurar tu lugar."
            )
        if confirm_url:
            msg += f"\n\n✅ *Confirmar cita aquí:* {confirm_url}\n❌ *Cancelar cita:* {cancel_url}"
        subject = f"⏳ Reserva Pendiente de Confirmación - {business.name}"
        prompt_label = f"Notificación de Reserva Pendiente ({expiry_hours}h) enviada a {client.full_name}"

    elif event_type == 'CONFIRMED':
        deposit_line = ""
        if not prop and appointment.deposit_amount and appointment.deposit_amount > 0:
            deposit_line = (
                f"💳 *Seña / Anticipo ({appointment.deposit_percentage:.0f}%):* {business.currency}{appointment.deposit_amount} "
                f"(Saldo restante: {business.currency}{appointment.balance_due})\n"
            )
        msg = (
            f"✅ *¡Hola {client.first_name}! Tu cita en {business.name} ha sido CONFIRMADA*\n\n"
            f"📅 *Fecha:* {date_str} a las {time_str} hs.\n"
            f"👤 *Especialista:* {staff_name}\n"
            f"✨ *Detalle:* {services_text}\n"
            f"{deposit_line}"
            f"📍 *Dirección:* {branch_addr}\n\n"
            f"¡Te esperamos!"
        )
        subject = f"✅ Cita Confirmada - {business.name}"
        prompt_label = f"Notificación de Cita Confirmada enviada a {client.full_name}"

    else:  # CANCELLED
        msg = (
            f"❌ *Hola {client.first_name}, tu reserva en {business.name} para el {date_str} a las {time_str} hs ha sido CANCELADA.*\n\n"
            f"Si deseas reprogramar tu turno, puedes hacerlo nuevamente desde nuestro portal de reservas."
        )
        subject = f"❌ Reserva Cancelada - {business.name}"
        prompt_label = f"Notificación de Cita Cancelada enviada a {client.full_name}"

    delivery_channels = []
    log_status = 'SIMULATED'

    # 1. Intentar envío por WhatsApp Gateway si está activo
    raw_phone = client.phone or ''
    clean_phone = re.sub(r'\D', '', raw_phone)
    if clean_phone:
        try:
            res = requests.post(
                f"{GATEWAY_BASE_URL}/send",
                params={'user': str(business.id)},
                json={'number': clean_phone, 'message': msg},
                timeout=3
            )
            if res.status_code == 200 and res.json().get('success'):
                delivery_channels.append('WhatsApp')
                log_status = 'SUCCESS'
        except Exception:
            pass

    # 2. Intentar envío por Email si el cliente dejó su correo
    if client.email:
        try:
            plain_msg = msg.replace('*', '')
            send_mail(
                subject=subject,
                message=plain_msg,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'notificaciones@neuralbot.io'),
                recipient_list=[client.email],
                fail_silently=True,
            )
            delivery_channels.append('Email')
            if log_status != 'SUCCESS':
                log_status = 'SUCCESS'
        except Exception:
            pass

    # 3. Registrar en AIAutomationLog para trazabilidad en el panel del negocio
    AIAutomationLog.objects.create(
        business=business,
        target_client=client,
        action_type='WHATSAPP_REMINDER',
        prompt_used=prompt_label,
        response_generated=msg,
        status=log_status
    )

    # Generar link directo de WhatsApp para confirmación manual con 1 clic
    biz_phone = re.sub(r'\D', '', business.phone or '')
    client_reply_text = (
        f"Hola {business.name}, soy {client.full_name}. "
        f"Confirmo mi asistencia para la cita del {date_str} a las {time_str} hs ({services_text})."
    )
    wa_confirm_link = (
        f"https://wa.me/{biz_phone}?text={urllib.parse.quote(client_reply_text)}"
        if biz_phone else f"https://wa.me/?text={urllib.parse.quote(client_reply_text)}"
    )

    wa_to_client_link = (
        f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"
        if clean_phone else ""
    )

    return {
        'message': msg,
        'channels': delivery_channels,
        'confirm_url': confirm_url,
        'cancel_url': cancel_url,
        'wa_confirm_link': wa_confirm_link,
        'wa_to_client_link': wa_to_client_link,
    }


def parse_time_str(val, default_time=datetime.time(9, 0)):
    if isinstance(val, datetime.time):
        return val
    if isinstance(val, str):
        val = val.strip()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.datetime.strptime(val[:8] if len(val) >= 8 else val[:5], fmt).time()
            except ValueError:
                continue
    return default_time


def get_allowed_staff_ids_for_service(service, all_active_staff=None):
    """
    Devuelve la lista de IDs (como strings) de los profesionales habilitados para un servicio.
    Regla de anclaje bidireccional:
    1. Si el servicio tiene profesionales explícitamente asignados (`service.staff_members`),
       solo esos profesionales están habilitados.
    2. Si el servicio NO tiene profesionales explícitamente asignados, están habilitados
       aquellos profesionales que NO estén restringidos exclusivamente a otros servicios
       (`not staff.services.exists()`). Si todos los profesionales tienen servicios asignados,
       se permiten todos como fallback para no bloquear un servicio recién creado sin configurar.
    """
    if all_active_staff is None:
        all_active_staff = list(
            StaffMember.objects.filter(business=service.business, is_active=True).prefetch_related('services')
        )

    explicit_staff_ids = {str(s.id) for s in service.staff_members.all()}
    if explicit_staff_ids:
        return [str(st.id) for st in all_active_staff if str(st.id) in explicit_staff_ids]

    unrestricted_staff_ids = [
        str(st.id) for st in all_active_staff
        if not st.services.exists()
    ]
    if unrestricted_staff_ids:
        return unrestricted_staff_ids

    return [str(st.id) for st in all_active_staff]


def get_ineligible_services_for_staff(staff, services_list, all_active_staff=None):
    """
    Retorna la lista de servicios dentro de `services_list` que `staff` NO puede realizar.
    """
    if not staff:
        return []
    if all_active_staff is None:
        all_active_staff = list(
            StaffMember.objects.filter(business=staff.business, is_active=True).prefetch_related('services')
        )
    staff_id_str = str(staff.id)
    ineligible = []
    for srv in services_list:
        allowed_ids = get_allowed_staff_ids_for_service(srv, all_active_staff=all_active_staff)
        if allowed_ids and staff_id_str not in allowed_ids:
            ineligible.append(srv)
    return ineligible


def get_appointment_interval(booking_date, app):
    """
    Calcula el intervalo real (start_dt, end_dt) de una cita considerando la duración de sus servicios.
    """
    st_time = parse_time_str(app.start_time, datetime.time(9, 0))
    start_dt = datetime.datetime.combine(booking_date, st_time)

    srv_duration = 0
    if hasattr(app, 'appointment_services'):
        srv_duration = sum(item.duration_minutes * item.quantity for item in app.appointment_services.all())
    if not srv_duration and app.service_id and app.service:
        srv_duration = app.service.duration_minutes

    if app.end_time:
        et_time = parse_time_str(app.end_time, None)
        if et_time:
            end_dt = datetime.datetime.combine(booking_date, et_time)
            if srv_duration > 0:
                expected_end_dt = start_dt + datetime.timedelta(minutes=srv_duration)
                if end_dt < expected_end_dt:
                    end_dt = expected_end_dt
            if end_dt > start_dt:
                return start_dt, end_dt

    fallback_mins = max(srv_duration or 45, 15)
    return start_dt, start_dt + datetime.timedelta(minutes=fallback_mins)


def find_overlapping_appointment(business, staff, booking_date, start_time_val, end_time_val, exclude_appointment_id=None):
    """
    Verifica si [start_time_val, end_time_val) se solapa con otra cita activa o bloqueo de agenda
    del mismo profesional en esa fecha.
    Retorna una tupla (conflict_obj, conflict_start_str, conflict_end_str) o (None, None, None).
    """
    expire_overdue_pending_appointments(business)

    if isinstance(booking_date, str):
        try:
            booking_date = datetime.date.fromisoformat(booking_date)
        except ValueError:
            booking_date = datetime.date.today()

    st_time = parse_time_str(start_time_val, datetime.time(9, 0))
    et_time = parse_time_str(end_time_val, datetime.time(9, 45))
    cand_start = datetime.datetime.combine(booking_date, st_time)
    cand_end = datetime.datetime.combine(booking_date, et_time)
    if cand_end <= cand_start:
        cand_end = cand_start + datetime.timedelta(minutes=15)

    qs = Appointment.objects.filter(
        business=business,
        date=booking_date,
        staff=staff
    ).exclude(status__in=['CANCELLED', 'NO_SHOW']).select_related('service').prefetch_related('appointment_services')

    if exclude_appointment_id:
        qs = qs.exclude(id=exclude_appointment_id)

    for app in qs:
        b_start, b_end = get_appointment_interval(booking_date, app)
        if cand_start < b_end and cand_end > b_start:
            return app, b_start.strftime("%H:%M"), b_end.strftime("%H:%M")

    if staff:
        blocks = ScheduleBlock.objects.filter(staff=staff, date=booking_date)
        for blk in blocks:
            b_start = datetime.datetime.combine(booking_date, parse_time_str(blk.start_time))
            b_end = datetime.datetime.combine(booking_date, parse_time_str(blk.end_time))
            if b_end > b_start and cand_start < b_end and cand_end > b_start:
                return blk, b_start.strftime("%H:%M"), b_end.strftime("%H:%M")

    return None, None, None


def calculate_available_slots(business, booking_date, staff, duration_minutes=45, exclude_appointment_id=None):
    """
    Calcula dinámicamente los cupos horarios disponibles según:
    - El horario laboral del profesional (`WorkSchedule`)
    - La duración total de los servicios seleccionados (`duration_minutes`)
    - Los intervalos reales `[start_time, end_time)` de las citas agendadas y bloqueos (`ScheduleBlock`)
      (ej. si un servicio de 1h 20m se agenda a las 14:00, bloquea de 14:00 a 15:20 y el siguiente cupo
      disponible es exactamente a las 15:20, nunca a las 15:00).
    """
    expire_overdue_pending_appointments(business)

    if isinstance(booking_date, str):
        try:
            booking_date = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        except ValueError:
            booking_date = datetime.date.today()

    weekday = booking_date.weekday()
    staff_name = staff.full_name if staff else "el profesional"

    schedule = None
    if staff:
        schedule = WorkSchedule.objects.filter(staff=staff, day_of_week=weekday).first()

    if schedule and not schedule.is_working_day:
        return {
            'is_open': False,
            'staff_name': staff_name,
            'date': booking_date.isoformat(),
            'duration_minutes': duration_minutes,
            'message': f'{staff_name} no atiende en la fecha seleccionada.',
            'slots': []
        }

    if weekday == 6 and not (schedule and schedule.is_working_day):
        return {
            'is_open': False,
            'staff_name': staff_name,
            'date': booking_date.isoformat(),
            'duration_minutes': duration_minutes,
            'message': f'{staff_name} no atiende los domingos.',
            'slots': []
        }

    if schedule:
        start_time_obj = parse_time_str(schedule.start_time, datetime.time(9, 0))
        end_time_obj = parse_time_str(schedule.end_time, datetime.time(19, 0))
    else:
        start_time_obj = datetime.time(9, 0)
        end_time_obj = datetime.time(14, 0) if weekday == 5 else datetime.time(19, 0)

    work_start_dt = datetime.datetime.combine(booking_date, start_time_obj)
    work_end_dt = datetime.datetime.combine(booking_date, end_time_obj)

    try:
        duration = max(int(duration_minutes), 15)
    except (ValueError, TypeError):
        duration = 45

    duration_delta = datetime.timedelta(minutes=duration)
    # Si el servicio dura <= 60 min (ej. 30 o 45 min), los turnos avanzan según la duración del servicio.
    # Si dura > 60 min (ej. 80 min = 1h 20m), en tramos libres permite iniciar en horas en punto (cada 60m)
    # y al encontrar cualquier cita ocupada salta exactamente a la hora de finalización de esa cita (ej. 15:20).
    step_minutes = duration if duration <= 60 else 60
    step_delta = datetime.timedelta(minutes=step_minutes)

    existing_appointments = Appointment.objects.filter(
        business=business,
        date=booking_date
    ).exclude(status__in=['CANCELLED', 'NO_SHOW']).select_related('service').prefetch_related('appointment_services')

    if staff:
        existing_appointments = existing_appointments.filter(staff=staff)
    if exclude_appointment_id:
        existing_appointments = existing_appointments.exclude(id=exclude_appointment_id)

    busy_intervals = []
    for app in existing_appointments:
        b_start, b_end = get_appointment_interval(booking_date, app)
        if b_end > b_start:
            busy_intervals.append((b_start, b_end))

    if staff:
        blocks = ScheduleBlock.objects.filter(staff=staff, date=booking_date)
        for blk in blocks:
            b_start = datetime.datetime.combine(booking_date, parse_time_str(blk.start_time))
            b_end = datetime.datetime.combine(booking_date, parse_time_str(blk.end_time))
            if b_end > b_start:
                busy_intervals.append((b_start, b_end))

    busy_intervals.sort(key=lambda x: (x[0], x[1]))

    slots = []
    added_disabled_starts = set()
    curr_time = work_start_dt

    while curr_time + duration_delta <= work_end_dt:
        cand_start = curr_time
        cand_end = curr_time + duration_delta

        # Buscar el primer intervalo ocupado que se superponga con [cand_start, cand_end)
        overlapping_busy = None
        for b_start, b_end in busy_intervals:
            if cand_start < b_end and cand_end > b_start:
                overlapping_busy = (b_start, b_end)
                break

        if overlapping_busy:
            b_start, b_end = overlapping_busy
            b_start_str = b_start.strftime("%H:%M")
            b_end_str = b_end.strftime("%H:%M")
            if b_start_str not in added_disabled_starts and b_start >= work_start_dt:
                slots.append({
                    'time': b_start_str,
                    'end_time': b_end_str,
                    'disabled': True
                })
                added_disabled_starts.add(b_start_str)
            # Saltar exactamente al fin de la reserva ocupada (ej. 14:00 + 1h20m -> 15:20)
            curr_time = b_end
        else:
            slots.append({
                'time': cand_start.strftime("%H:%M"),
                'end_time': cand_end.strftime("%H:%M"),
                'disabled': False
            })
            curr_time += step_delta

    return {
        'is_open': True,
        'staff_name': staff_name,
        'date': booking_date.isoformat(),
        'duration_minutes': duration,
        'slots': slots
    }
