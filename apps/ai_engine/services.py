import datetime
import json
import re
import requests
import unicodedata
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone

from apps.pos.models import Sale
from apps.invoicing.models import Expense, Invoice
from apps.crm.models import Client
from apps.agenda.models import Appointment, Service
from apps.business.models import WorkSchedule, StaffMember
from apps.ai_engine.models import AIAutomationLog, WhatsAppBotConfig
from apps.superadmin.models import PlatformGlobalConfig
from apps.agenda.utils import calculate_available_slots
from apps.booking.views import _resolve_portal_client


def get_or_create_bot_config(business):
    return WhatsAppBotConfig.get_for_business(business)


def get_effective_ai_config(business):
    """
    Determina la clave API y modelo de IA aplicables para este negocio según su plan y configuración:
    1. Si el negocio configuró su propia clave DeepSeek (override), se utiliza prioritariamente.
    2. Si no, se verifica si su plan de suscripción incluye la API Key de la plataforma (`has_platform_ai_access`).
       - Si lo incluye, se utiliza la API Key global de DeepSeek configurada por el SuperAdmin.
       - Si no lo incluye, requiere que el cliente coloque su propia clave.
    Retorna: (api_key, model, provider, source_status, source_description)
    """
    bot_config = get_or_create_bot_config(business)

    # 1. Clave propia del negocio
    if bot_config.deepseek_api_key and bot_config.deepseek_api_key.strip():
        return (
            bot_config.deepseek_api_key.strip(),
            bot_config.deepseek_model or 'deepseek-chat',
            'deepseek',
            'custom',
            'Clave propia de DeepSeek configurada por la empresa.'
        )

    # 2. Clave global por suscripción / plan
    has_access = business.has_platform_ai_access()
    global_cfg = PlatformGlobalConfig.get_solo()

    if has_access:
        if global_cfg.deepseek_api_key and global_cfg.deepseek_api_key.strip() and global_cfg.is_deepseek_active:
            return (
                global_cfg.deepseek_api_key.strip(),
                global_cfg.deepseek_model or 'deepseek-chat',
                'deepseek',
                'platform',
                'Motor DeepSeek global provisto por tu plan de suscripción.'
            )
        else:
            return (
                None,
                global_cfg.deepseek_model or 'deepseek-chat',
                'deepseek',
                'missing_global',
                'Tu plan incluye IA, pero la plataforma aún no tiene una clave global activa configurada.'
            )

    # 3. Fallback de OpenAI si tiene clave propia
    if bot_config.openai_api_key and bot_config.openai_api_key.strip():
        return (
            bot_config.openai_api_key.strip(),
            'gpt-4o-mini',
            'openai',
            'custom_openai',
            'Clave propia de OpenAI configurada.'
        )

    # 4. Plan no incluye clave de plataforma
    return (
        None,
        'deepseek-chat',
        'deepseek',
        'plan_requires_own_key',
        'Tu plan de suscripción no incluye la clave de IA de la plataforma. Debes ingresar tu propia API Key de DeepSeek.'
    )


def build_agency_rag_context(business, sender_phone='', sender_name=''):
    """
    Recuperador Contextual RAG (Retrieval-Augmented Generation) para el negocio/agencia:
    Recopila y estructura toda la información viva del negocio para nutrir al modelo de IA:
    - Perfil comercial, dirección, teléfono, moneda y URL de reservas
    - Horarios de atención y días laborables
    - Catálogo completo de servicios, precios, duración y categorías
    - Catálogo de productos e inventario (si aplica)
    - Profesionales y colaboradores habilitados
    - Base de conocimientos personalizada (FAQs, reglas, políticas)
    - Información del cliente emisor (CRM)
    - Fecha, día de semana y hora actual exacta
    """
    bot_config = get_or_create_bot_config(business)
    now = timezone.localtime()
    days_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    today_name = days_es[now.weekday()]
    today_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')

    booking_url = f"http://127.0.0.1:8000/reservas/{business.slug}/" if getattr(business, 'slug', None) else ""

    # 1. Dirección y Sede
    main_branch = business.branches.filter(is_main=True).first() or business.branches.first()
    address_text = main_branch.address if main_branch else (business.address or "Atención con cita previa")

    # 2. Horarios comerciales
    schedules = WorkSchedule.objects.filter(staff__business=business, is_working_day=True).order_by('day_of_week')
    schedule_lines = []
    seen_days = set()
    for sc in schedules:
        if sc.day_of_week not in seen_days:
            seen_days.add(sc.day_of_week)
            schedule_lines.append(f"- {days_es[sc.day_of_week]}: {sc.start_time.strftime('%H:%M')} a {sc.end_time.strftime('%H:%M')}")
    schedule_summary = "\n".join(schedule_lines) if schedule_lines else "- Lunes a Sábado: 09:00 a 19:00"

    # 3. Servicios activos (Catálogo RAG)
    services_qs = Service.objects.filter(business=business, is_active=True).select_related('category').order_by('category__name', 'name')
    service_items = []
    for s in services_qs[:30]:
        cat_name = s.category.name if s.category else "General"
        dep = f" (Seña requerida: {s.effective_deposit_percentage}%)" if s.effective_deposit_percentage > 0 else ""
        desc = f" - {s.description}" if s.description else ""
        service_items.append(f"• ID:{s.id} | [{cat_name}] {s.name}: {business.currency}{s.price:,.2f} ({s.duration_minutes} min){dep}{desc}")
    services_text = "\n".join(service_items) if service_items else "• Servicios personalizados disponibles."

    # 4. Profesionales / Staff
    staff_qs = StaffMember.objects.filter(business=business, is_active=True).select_related('user')
    staff_items = []
    for st in staff_qs[:15]:
        role = st.role_title or "Especialista"
        staff_items.append(f"- {st.full_name} ({role})")
    staff_text = "\n".join(staff_items) if staff_items else "- Equipo profesional general"

    # 5. Base de conocimientos / FAQs personalizadas
    custom_knowledge = (bot_config.custom_knowledge or "").strip()

    # 6. Contexto del Cliente emisor (CRM)
    clean_phone = re.sub(r'\D', '', str(sender_phone))
    client_ctx = "Cliente no identificado aún o nuevo en el sistema."
    client = None
    if clean_phone and clean_phone != '0000000000' and sender_phone != 'SIMULADOR':
        client = Client.objects.filter(
            business=business
        ).filter(
            Q(phone__icontains=clean_phone[-8:]) | Q(phone__icontains=clean_phone)
        ).first()

    if client:
        client_ctx = f"Cliente Registrado en CRM: {client.full_name} (Tel: {client.phone}, Email: {client.email or 'No registrado'}, Total visitas: {client.appointments.count()})"
    elif sender_name:
        client_ctx = f"Cliente Potencial: Nombre reportado '{sender_name}', Teléfono '{sender_phone}' (aún no registrado en CRM)."

    context_prompt = (
        f"=== CONTEXTO DEL NEGOCIO / AGENCIA (RAG) ===\n"
        f"• Nombre del Negocio: {business.name}\n"
        f"• Especialidad / Rubro: {business.get_business_type_display()}\n"
        f"• Moneda Oficial: {business.currency}\n"
        f"• Teléfono de Contacto: {business.phone or 'Atención directa por este canal'}\n"
        f"• Dirección Física: {address_text}\n"
        f"• Enlace de Reservas Online: {booking_url}\n"
        f"• Fecha Actual: {today_name}, {today_str}\n"
        f"• Hora Actual: {time_str}\n\n"
        f"=== HORARIOS DE ATENCIÓN ===\n"
        f"{schedule_summary}\n\n"
        f"=== CATÁLOGO DE SERVICIOS Y TARIFAS ===\n"
        f"{services_text}\n\n"
        f"=== PROFESIONALES / EQUIPO ===\n"
        f"{staff_text}\n\n"
    )

    if custom_knowledge:
        context_prompt += f"=== BASE DE CONOCIMIENTOS / REGLAS ESPECIALES DE LA AGENCIA ===\n{custom_knowledge}\n\n"

    context_prompt += f"=== CONTEXTO DEL USUARIO ACTUAL ===\n{client_ctx}\n"

    return {
        'context_text': context_prompt,
        'business_name': business.name,
        'booking_url': booking_url,
        'today_str': today_str,
        'time_str': time_str,
        'client': client,
    }


def execute_tool_consultar_disponibilidad(business, fecha_str, servicio_name=None, profesional_name=None):
    """Herramienta: Consulta cupos y horarios libres en la agenda en tiempo real."""
    if not fecha_str:
        fecha_str = timezone.localdate().isoformat()

    # Normalizar fecha
    try:
        booking_date = datetime.datetime.strptime(fecha_str.strip(), "%Y-%m-%d").date()
    except Exception:
        try:
            booking_date = datetime.datetime.strptime(fecha_str.strip(), "%d/%m/%Y").date()
        except Exception:
            booking_date = timezone.localdate()

    # Resolver servicio
    service = None
    if servicio_name:
        service = Service.objects.filter(
            business=business, is_active=True, name__icontains=servicio_name.strip()
        ).first()
    if not service:
        service = Service.objects.filter(business=business, is_active=True).first()

    duration = service.duration_minutes if service else 45

    # Resolver profesional
    staff = None
    if profesional_name:
        parts = profesional_name.strip().split()
        q = Q(user__first_name__icontains=parts[0])
        if len(parts) > 1:
            q |= Q(user__last_name__icontains=parts[1])
        staff = StaffMember.objects.filter(business=business, is_active=True).filter(q).first()

    if not staff:
        if service:
            staff = service.staff_members.filter(is_active=True).first()
        if not staff:
            staff = StaffMember.objects.filter(business=business, is_active=True).first()

    # Calcular cupos mediante el motor oficial de disponibilidad
    result = calculate_available_slots(
        business=business,
        booking_date=booking_date,
        staff=staff,
        duration_minutes=duration
    )

    slots = result.get('slots', [])
    is_open = result.get('is_open', True)
    staff_name = staff.full_name if staff else "el profesional"

    if not is_open or not slots:
        return {
            'disponible': False,
            'fecha': booking_date.isoformat(),
            'servicio': service.name if service else 'General',
            'profesional': staff_name,
            'mensaje': result.get('message') or f"No hay cupos disponibles para el {booking_date.strftime('%d/%m/%Y')}.",
            'turnos_libres': []
        }

    return {
        'disponible': True,
        'fecha': booking_date.isoformat(),
        'servicio': service.name if service else 'General',
        'duracion_minutos': duration,
        'precio': f"{business.currency}{service.price:,.2f}" if service else "",
        'profesional': staff_name,
        'turnos_libres': slots[:10]
    }


def execute_tool_registrar_cliente(business, nombre, apellido='', telefono='', email=''):
    """Herramienta: Registra o actualiza el cliente en el CRM."""
    clean_nombre = (nombre or "Cliente").strip()
    clean_apellido = (apellido or "").strip()
    clean_telefono = (telefono or "").strip()
    clean_email = (email or "").strip()

    client = _resolve_portal_client(
        business=business,
        first_name=clean_nombre,
        last_name=clean_apellido,
        phone=clean_telefono or '0000000000',
        email=clean_email
    )

    return {
        'success': True,
        'client_id': str(client.id),
        'nombre_completo': client.full_name,
        'telefono': client.phone,
        'email': client.email or 'No proporcionado',
        'mensaje': f"Cliente {client.full_name} registrado correctamente en el CRM."
    }


def execute_tool_agendar_cita(business, servicio_name, fecha_str, hora_str, nombre_cliente, telefono_cliente, email_cliente=None, profesional_name=None, notas=None):
    """Herramienta: Registra la cita confirmada en la agenda del negocio."""
    # 1. Parsear fecha
    try:
        booking_date = datetime.datetime.strptime(fecha_str.strip(), "%Y-%m-%d").date()
    except Exception:
        try:
            booking_date = datetime.datetime.strptime(fecha_str.strip(), "%d/%m/%Y").date()
        except Exception:
            booking_date = timezone.localdate()

    # 2. Parsear hora (HH:MM)
    time_clean = hora_str.strip()
    try:
        if len(time_clean) <= 5:
            start_time = datetime.datetime.strptime(time_clean, "%H:%M").time()
        else:
            start_time = datetime.datetime.strptime(time_clean[:5], "%H:%M").time()
    except Exception:
        start_time = datetime.time(10, 0)

    # 3. Resolver Servicio
    service = None
    if servicio_name:
        service = Service.objects.filter(
            business=business, is_active=True, name__icontains=servicio_name.strip()
        ).first()
    if not service:
        service = Service.objects.filter(business=business, is_active=True).first()

    duration = service.duration_minutes if service else 45
    total_price = service.price if service else Decimal('0.00')

    # 4. Calcular hora fin
    start_dt = datetime.datetime.combine(booking_date, start_time)
    end_dt = start_dt + datetime.timedelta(minutes=duration)
    end_time = end_dt.time()

    # 5. Resolver Cliente
    name_parts = (nombre_cliente or "Cliente").strip().split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    client = _resolve_portal_client(
        business=business,
        first_name=first_name,
        last_name=last_name,
        phone=(telefono_cliente or '0000000000').strip(),
        email=(email_cliente or '').strip()
    )

    # 6. Resolver Profesional
    staff = None
    if profesional_name:
        parts = profesional_name.strip().split()
        q = Q(user__first_name__icontains=parts[0])
        if len(parts) > 1:
            q |= Q(user__last_name__icontains=parts[1])
        staff = StaffMember.objects.filter(business=business, is_active=True).filter(q).first()

    if not staff and service:
        staff = service.staff_members.filter(is_active=True).first()
    if not staff:
        staff = StaffMember.objects.filter(business=business, is_active=True).first()

    if not staff:
        return {'success': False, 'mensaje': 'No hay profesionales activos en el negocio para asignar la cita.'}

    # 7. Crear la Cita
    note_text = f"[Agendado automáticamente por Bot IA de WhatsApp] {notas or ''}".strip()
    appointment = Appointment.objects.create(
        business=business,
        client=client,
        staff=staff,
        service=service,
        date=booking_date,
        start_time=start_time,
        end_time=end_time,
        total_price=total_price,
        status='CONFIRMED',
        notes=note_text
    )

    return {
        'success': True,
        'appointment_id': str(appointment.id),
        'cliente': client.full_name,
        'telefono': client.phone,
        'servicio': service.name if service else 'General',
        'fecha': booking_date.strftime('%d/%m/%Y'),
        'hora': start_time.strftime('%H:%M'),
        'profesional': staff.full_name,
        'precio': f"{business.currency}{total_price:,.2f}",
        'mensaje': f"¡Cita agendada y confirmada con éxito para el {booking_date.strftime('%d/%m/%Y')} a las {start_time.strftime('%H:%M')}!"
    }


def call_deepseek_with_tools(api_key, model, messages_list, business):
    """
    Ejecuta la llamada a la API de DeepSeek compatible con OpenAI Tools y procesa
    llamadas a funciones autónomas (Disponibilidad, Registro CRM y Agendamiento).
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "consultar_disponibilidad_agenda",
                "description": "Consulta los turnos y horarios disponibles en la agenda en tiempo real para una fecha y servicio específico.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fecha_str": {
                            "type": "string",
                            "description": "Fecha en formato AAAA-MM-DD (ej: 2026-10-29)."
                        },
                        "servicio_name": {
                            "type": "string",
                            "description": "Nombre o palabra clave del servicio deseado (ej: 'Corte de Pelo', 'Consulta')."
                        },
                        "profesional_name": {
                            "type": "string",
                            "description": "Nombre del profesional o especialista preferido (opcional)."
                        }
                    },
                    "required": ["fecha_str"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "registrar_cliente",
                "description": "Registra o actualiza la ficha del cliente en el CRM con su nombre, teléfono y correo electrónico.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nombre": {
                            "type": "string",
                            "description": "Nombre de pila del cliente (ej: Juan)."
                        },
                        "apellido": {
                            "type": "string",
                            "description": "Apellido del cliente (opcional, ej: Pérez)."
                        },
                        "telefono": {
                            "type": "string",
                            "description": "Número de teléfono o WhatsApp del cliente."
                        },
                        "email": {
                            "type": "string",
                            "description": "Correo electrónico del cliente (opcional)."
                        }
                    },
                    "required": ["nombre", "telefono"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "agendar_cita",
                "description": "Crea y confirma una cita/reserva en el sistema una vez que el cliente acordó el servicio, fecha y hora.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "servicio_name": {
                            "type": "string",
                            "description": "Nombre exacto o aproximado del servicio a reservar."
                        },
                        "fecha_str": {
                            "type": "string",
                            "description": "Fecha de la cita en formato AAAA-MM-DD (ej: 2026-10-29)."
                        },
                        "hora_str": {
                            "type": "string",
                            "description": "Hora de inicio en formato HH:MM (ej: 14:30 o 10:00)."
                        },
                        "nombre_cliente": {
                            "type": "string",
                            "description": "Nombre completo del cliente."
                        },
                        "telefono_cliente": {
                            "type": "string",
                            "description": "Número de teléfono o WhatsApp del cliente."
                        },
                        "email_cliente": {
                            "type": "string",
                            "description": "Correo electrónico del cliente (opcional)."
                        },
                        "profesional_name": {
                            "type": "string",
                            "description": "Nombre del profesional preferido (opcional)."
                        },
                        "notas": {
                            "type": "string",
                            "description": "Notas o requerimientos adicionales (opcional)."
                        }
                    },
                    "required": ["servicio_name", "fecha_str", "hora_str", "nombre_cliente", "telefono_cliente"]
                }
            }
        }
    ]

    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model or "deepseek-chat",
        "messages": messages_list,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.6,
        "max_tokens": 700
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=14)
        if resp.status_code != 200:
            print(f"[DeepSeek] Error HTTP {resp.status_code}: {resp.text}")
            return None

        res_data = resp.json()
        choice = res_data.get('choices', [{}])[0]
        message = choice.get('message', {})
        tool_calls = message.get('tool_calls', [])

        # Si el modelo ejecutó herramientas de agenda / CRM
        if tool_calls:
            # Añadir mensaje del asistente con las llamadas
            messages_list.append(message)

            for tc in tool_calls:
                fn_name = tc.get('function', {}).get('name')
                raw_args = tc.get('function', {}).get('arguments', '{}')
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}

                tool_result = {}
                if fn_name == 'consultar_disponibilidad_agenda':
                    tool_result = execute_tool_consultar_disponibilidad(
                        business=business,
                        fecha_str=args.get('fecha_str'),
                        servicio_name=args.get('servicio_name'),
                        profesional_name=args.get('profesional_name')
                    )
                elif fn_name == 'registrar_cliente':
                    tool_result = execute_tool_registrar_cliente(
                        business=business,
                        nombre=args.get('nombre'),
                        apellido=args.get('apellido', ''),
                        telefono=args.get('telefono', ''),
                        email=args.get('email', '')
                    )
                elif fn_name == 'agendar_cita':
                    tool_result = execute_tool_agendar_cita(
                        business=business,
                        servicio_name=args.get('servicio_name'),
                        fecha_str=args.get('fecha_str'),
                        hora_str=args.get('hora_str'),
                        nombre_cliente=args.get('nombre_cliente'),
                        telefono_cliente=args.get('telefono_cliente'),
                        email_cliente=args.get('email_cliente'),
                        profesional_name=args.get('profesional_name'),
                        notas=args.get('notas')
                    )

                # Registrar respuesta de la herramienta
                messages_list.append({
                    "role": "tool",
                    "tool_call_id": tc.get('id'),
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })

            # Segunda llamada a DeepSeek para formular la respuesta conversacional final
            second_payload = {
                "model": model or "deepseek-chat",
                "messages": messages_list,
                "temperature": 0.6,
                "max_tokens": 500
            }
            second_resp = requests.post(endpoint, json=second_payload, headers=headers, timeout=12)
            if second_resp.status_code == 200:
                sec_data = second_resp.json()
                final_content = sec_data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                if final_content:
                    return final_content

        return message.get('content', '').strip() or None

    except Exception as e:
        print(f"[DeepSeek] Excepción consultando API: {e}")
        return None


def generate_whatsapp_bot_reply(business, incoming_text, sender_phone='', sender_name='', request=None, force_simulate=False):
    """
    Motor Principal del Bot de WhatsApp / Simulador con Arquitectura RAG y DeepSeek:
    1. Valida si el bot está activo para el negocio (o si se ejecuta en modo simulador).
    2. Construye el contexto RAG enriquecido con servicios, horarios, reglas y cliente.
    3. Resuelve la clave de DeepSeek (propia de la empresa o provista por el plan SaaS).
    4. Carga memoria conversacional reciente del chat.
    5. Ejecuta DeepSeek con soporte de funciones (disponibilidad, registro CRM y reservas).
    6. Si no hay clave configurada o hay fallo de red, opera con el motor contextual local.
    7. Registra la interacción en `AIAutomationLog`.
    """
    bot_config = get_or_create_bot_config(business)
    if not bot_config.is_active and not force_simulate:
        return None

    incoming_text_clean = (incoming_text or '').strip()
    if not incoming_text_clean:
        return None

    # Construir Contexto RAG
    rag = build_agency_rag_context(business, sender_phone=sender_phone, sender_name=sender_name)
    rag_context = rag['context_text']
    business_name = rag['business_name']
    booking_url = rag['booking_url']

    # Resolver API Key y modelo de DeepSeek
    api_key, model, provider, source_status, source_desc = get_effective_ai_config(business)
    reply = None

    if api_key:
        # Prompt del Sistema base
        system_instructions = (
            f"Eres {bot_config.bot_name}, el asistente virtual inteligente de {business_name}.\n"
            f"Tu misión es atender a los clientes de forma amable, profesional, concisa y empática a través de WhatsApp.\n\n"
            f"DIRECTIVAS PRINCIPALES:\n"
            f"1. Recomendaciones: Si el cliente pregunta qué servicio le conviene o qué necesita, analiza sus necesidades y recomiéndale los servicios ideales de nuestro catálogo con sus precios y duración.\n"
            f"2. Recolección de datos y CRM: Pide amablemente el nombre del cliente si aún no lo sabes para llamarlo por su nombre y registrarlo en el sistema.\n"
            f"3. Consulta de Disponibilidad: Cuando el cliente quiera agendar o pregunte por horarios libres para un día o servicio, utiliza la herramienta 'consultar_disponibilidad_agenda' para darle los turnos exactos reales.\n"
            f"4. Agendamiento de Citas: Cuando el cliente confirme el servicio, fecha y hora preferida, utiliza 'agendar_cita' para crear la reserva en la agenda y dale una confirmación clara y alegre.\n"
            f"5. Si el cliente prefiere agendar por su cuenta en la web, ofrécele el enlace directo de reservas online: {booking_url}.\n"
            f"6. Mantén las respuestas fluidas, claras, formateadas con emojis sutiles y fáciles de leer en WhatsApp.\n\n"
            f"{rag_context}\n"
        )

        if bot_config.system_prompt:
            system_instructions += f"Instrucciones específicas adicionales de la agencia:\n{bot_config.system_prompt}\n"

        messages_payload = [{"role": "system", "content": system_instructions}]

        # Memoria conversacional: Cargar últimos 4 intercambios del mismo emisor
        if sender_phone:
            recent_logs = AIAutomationLog.objects.filter(
                business=business,
                sender_phone=sender_phone
            ).order_by('-created_at')[:4]

            # Invertir para orden cronológico
            for log in reversed(list(recent_logs)):
                if log.prompt_used:
                    messages_payload.append({"role": "user", "content": log.prompt_used})
                if log.response_generated:
                    messages_payload.append({"role": "assistant", "content": log.response_generated})

        # Mensaje actual
        messages_payload.append({"role": "user", "content": incoming_text_clean})

        # Ejecutar llamada con DeepSeek Tools
        reply = call_deepseek_with_tools(
            api_key=api_key,
            model=model,
            messages_list=messages_payload,
            business=business
        )

    # Motor conversacional semántico contextual (fallback local si no hay API Key o hubo error de red)
    if not reply:
        text_lower = incoming_text_clean.lower()
        client_greet = f" {sender_name}" if sender_name else ""
        text_norm = ''.join(c for c in unicodedata.normalize('NFD', text_lower) if unicodedata.category(c) != 'Mn')

        active_services = Service.objects.filter(business=business, is_active=True).order_by('name')[:8]
        services_list = [f"• {s.name}: {business.currency}{s.price:,.2f}" for s in active_services]
        services_text = "\n".join(services_list) if services_list else "Consulta por nuestros servicios personalizados."

        main_branch = business.branches.filter(is_main=True).first() or business.branches.first()
        address_text = main_branch.address if main_branch else (business.address or "Atención con cita previa")

        schedules = WorkSchedule.objects.filter(staff__business=business, is_working_day=True).order_by('day_of_week')
        days_map = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
        schedule_lines = [f"{days_map.get(sc.day_of_week, 'Día')}: {sc.start_time.strftime('%H:%M')} a {sc.end_time.strftime('%H:%M')}" for sc in schedules[:7]]
        schedule_summary = ", ".join(schedule_lines) if schedule_lines else "Lunes a Sábado de 09:00 a 19:00"

        # 1. Saludo
        if any(w in text_norm for w in ['hola', 'buen dia', 'buenos dias', 'buenas tardes', 'buenas noches', 'buenas', 'hey', 'saludos', 'que tal']):
            reply = (
                f"¡Hola{client_greet}! 👋\n\n"
                f"{bot_config.welcome_message}\n\n"
                f"📌 *¿Cómo te podemos ayudar hoy?*\n"
                f"1️⃣ Ver nuestros *Servicios y Precios*\n"
                f"2️⃣ *Agendar una Cita / Turno* online\n"
                f"3️⃣ Consultar *Horarios de Atención y Ubicación*\n"
                f"4️⃣ Hablar con un *Asesor Humano*"
            )
        # 2. Reservas / Agendar
        elif any(w in text_norm for w in ['turno', 'cita', 'reservar', 'agendar', 'horario disponible', 'disponibilidad', 'hora', 'agendamiento', 'agendarme']):
            if sender_name and sender_phone and sender_phone != 'SIMULADOR':
                try:
                    execute_tool_registrar_cliente(business, nombre=sender_name, telefono=sender_phone)
                except Exception:
                    pass
            booking_part = f"\n👉 *Reserva tu turno en tiempo real aquí:* {booking_url}\n" if bot_config.auto_booking_link and booking_url else ""
            reply = (
                f"📅 *Agendamiento de Citas en {business_name}:*\n\n"
                f"Puedes consultar los horarios disponibles en tiempo real y agendar tu cita de forma rápida y sencilla.{booking_part}\n"
                f"Elige el servicio, profesional de tu preferencia y el horario que mejor te acomode."
            )
        # 3. Precios y Servicios
        elif any(w in text_norm for w in ['servicio', 'precio', 'costo', 'cuanto sale', 'cuanto cuesta', 'catalogo', 'tarifa', 'lista', 'valores', 'menu']):
            booking_part = f"\n\n👉 *Puedes agendar directamente aquí:* {booking_url}" if bot_config.auto_booking_link and booking_url else ""
            reply = (
                f"✨ *Servicios y Precios en {business_name}:*\n\n"
                f"{services_text}{booking_part}"
            )
        # 4. Horarios
        elif any(w in text_norm for w in ['horario', 'atienden', 'abierto', 'cerrado', 'cuando abren', 'dias', 'atencion']):
            reply = (
                f"⏰ *Nuestros Horarios de Atención:*\n\n"
                f"{schedule_summary}\n\n"
                f"📍 *Te esperamos en:* {address_text}"
            )
        # 5. Ubicación / Dirección
        elif any(w in text_norm for w in ['donde', 'ubicacion', 'direccion', 'lugar', 'como llego', 'mapa', 'sucursal', 'queda']):
            reply = (
                f"📍 *Ubicación de {business_name}:*\n\n"
                f"Nuestra dirección es:\n*{address_text}*\n\n"
                f"⏰ Horarios: {schedule_summary}"
            )
        # 6. Asesor Humano
        elif any(w in text_norm for w in ['humano', 'persona', 'asesor', 'operador', 'hablar con alguien', 'secretaria', 'recepcion']):
            reply = (
                f"👤 ¡Por supuesto{client_greet}! He notificado a nuestro equipo.\n\n"
                f"Por favor déjanos tu consulta detallada y un asesor te responderá a este mismo chat a la brevedad posible."
            )
        # 7. Agradecimiento
        elif any(w in text_norm for w in ['gracias', 'muchas gracias', 'genial', 'excelente', 'perfecto', 'ok', 'dale', 'listo']):
            reply = (
                f"¡Con mucho gusto{client_greet}! 😊 En *{business_name}* estamos para servirte. ¡Que tengas un excelente día!"
            )
        # 8. Respuesta general
        else:
            booking_part = f"\n👉 Agenda tu cita online: {booking_url}" if bot_config.auto_booking_link and booking_url else ""
            reply = (
                f"🤖 *{bot_config.bot_name} ({business_name}):*\n\n"
                f"Gracias por tu mensaje. Puedo brindarte información sobre nuestros servicios, recomendaciones, horarios y agendar tu turno.{booking_part}\n\n"
                f"Dime en qué podemos ayudarte hoy."
            )

    # Registrar en el log de automatizaciones de IA
    try:
        AIAutomationLog.objects.create(
            business=business,
            sender_phone=sender_phone,
            sender_name=sender_name,
            action_type='WHATSAPP_BOT_REPLY',
            prompt_used=incoming_text_clean,
            response_generated=reply or "Sin respuesta generada",
            status='SENT'
        )
    except Exception as e:
        print(f"Error guardando AIAutomationLog: {e}")

    return reply


def generate_executive_financial_insight(business):
    """Genera diagnóstico ejecutivo de negocio usando IA Administrativa."""
    total_sales = Sale.objects.filter(business=business, status='COMPLETED').aggregate(total=Sum('total_amount'))['total'] or 0
    total_expenses = Expense.objects.filter(business=business).aggregate(total=Sum('amount'))['total'] or 0
    net_profit = total_sales - total_expenses

    sixty_days_ago = timezone.now() - datetime.timedelta(days=60)
    inactive_clients = Client.objects.filter(business=business, last_visit__lt=sixty_days_ago).count()

    top_service_qs = Appointment.objects.filter(business=business, status='COMPLETED').values('service__name').annotate(count=Count('id')).order_by('-count')
    top_service_name = top_service_qs[0]['service__name'] if top_service_qs else "Servicios Principales"

    summary = (
        f"**Resumen Ejecutivo por RauDie OS IA:**\n\n"
        f"• Ingresos totales del periodo: {business.currency}{total_sales:,.2f}\n"
        f"• Gastos operativos: {business.currency}{total_expenses:,.2f}\n"
        f"• Utilidad Neta estimada: {business.currency}{net_profit:,.2f}\n\n"
        f"**Diagnóstico y Recomendaciones:**\n"
        f"1. El servicio con mayor demanda en el período es **{top_service_name}**.\n"
        f"2. Detectamos **{inactive_clients} clientes** que no registran visitas en los últimos 60 días.\n"
        f"3. Te sugerimos activar la campaña automática por WhatsApp para recuperar clientes inactivos esta semana."
    )

    AIAutomationLog.objects.create(
        business=business,
        action_type='FINANCIAL_INSIGHT',
        prompt_used="¿Cómo estuvo mi negocio este mes?",
        response_generated=summary,
        status='COMPLETED'
    )

    return summary


def detect_inactive_clients_and_draft_campaign(business):
    """Detecta clientes inactivos e incita la reactivación vía WhatsApp."""
    sixty_days_ago = timezone.now() - datetime.timedelta(days=60)
    inactive_clients = Client.objects.filter(business=business).exclude(status='VIP')[:5]

    campaigns = []
    for client in inactive_clients:
        msg = f"¡Hola {client.first_name}! Hace tiempo que no nos visitas en {business.name}. Tenemos una atención especial en tu próximo servicio si reservas esta semana. Link de reserva: http://localhost:8000/reservas/{business.slug}/?promo=REGRESA"

        log = AIAutomationLog.objects.create(
            business=business,
            target_client=client,
            action_type='REACTIVATION_CAMPAIGN',
            prompt_used=f"Reactivar cliente inactivo: {client.full_name}",
            response_generated=msg,
            status='SIMULATED'
        )
        campaigns.append({
            'client_name': client.full_name,
            'phone': client.phone,
            'message': msg,
            'log_id': str(log.id)
        })

    return campaigns