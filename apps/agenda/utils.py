import datetime
from apps.business.models import StaffMember, WorkSchedule
from apps.agenda.models import Appointment, ScheduleBlock, Service


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
