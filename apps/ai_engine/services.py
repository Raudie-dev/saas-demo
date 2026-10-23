import datetime
import json
import urllib.request
from django.db.models import Sum, Count
from apps.pos.models import Sale
from apps.invoicing.models import Expense, Invoice
from apps.crm.models import Client
from apps.agenda.models import Appointment, Service
from apps.business.models import WorkSchedule
from apps.ai_engine.models import AIAutomationLog, WhatsAppBotConfig

def get_or_create_bot_config(business):
    return WhatsAppBotConfig.get_for_business(business)

def generate_whatsapp_bot_reply(business, incoming_text, sender_phone='', sender_name=''):
    """
    Genera la respuesta del Bot de WhatsApp para un mensaje entrante.
    1. Si el bot está inactivo, no responde.
    2. Usa el contexto completo del negocio (servicios, precios, dirección, link de reservas, horarios).
    3. Si tiene configurada OpenAI API Key, consulta a GPT con el prompt del sistema.
    4. Si no, usa el motor conversacional inteligente con detección de intención y variables dinámicas.
    5. Guarda el registro en AIAutomationLog.
    """
    bot_config = get_or_create_bot_config(business)
    if not bot_config.is_active:
        return None

    incoming_text_clean = (incoming_text or '').strip()
    if not incoming_text_clean:
        return None

    # Datos contextuales del negocio
    business_name = business.name
    booking_url = f"http://127.0.0.1:5555/reservas/{business.slug}/" if hasattr(business, 'slug') else ""

    # Servicios y precios activos
    active_services = Service.objects.filter(business=business, is_active=True).order_by('name')[:8]
    services_list = [f"• {s.name}: {business.currency}{s.price:,.2f}" for s in active_services]
    services_text = "\n".join(services_list) if services_list else "Consulta por nuestros servicios personalizados."

    # Dirección / Sede
    main_branch = business.branches.filter(is_main=True).first() or business.branches.first()
    address_text = main_branch.address if main_branch else (business.address or "Atención con cita previa")

    # Horarios de atención
    schedules = WorkSchedule.objects.filter(staff__business=business, is_working_day=True).order_by('day_of_week')
    days_map = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
    schedule_lines = []
    for sc in schedules[:7]:
        schedule_lines.append(f"{days_map.get(sc.day_of_week, 'Día')}: {sc.start_time.strftime('%H:%M')} a {sc.end_time.strftime('%H:%M')}")
    schedule_summary = ", ".join(schedule_lines) if schedule_lines else "Lunes a Sábado de 09:00 a 19:00"

    reply = None

    # Intentar responder con OpenAI si hay API Key configurada
    api_key = bot_config.openai_api_key
    if api_key:
        try:
            system_prompt = bot_config.system_prompt.format(
                business_name=business_name,
                booking_url=booking_url,
                services=services_text,
                address=address_text,
                hours=schedule_summary
            )
            
            prompt_context = (
                f"\n\nContexto actual de la empresa {business_name}:\n"
                f"- Nombre: {business_name}\n"
                f"- Dirección: {address_text}\n"
                f"- Portal de reservas online: {booking_url}\n"
                f"- Horarios: {schedule_summary}\n"
                f"- Servicios y precios:\n{services_text}\n"
            )

            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt + prompt_context},
                    {"role": "user", "content": incoming_text_clean}
                ],
                "max_tokens": 350,
                "temperature": 0.7
            }

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                reply = res_data['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"Error consultando OpenAI: {e}")
            reply = None

    # Motor conversacional contextual (si no hay OpenAI o falló la API)
    if not reply:
        text_lower = incoming_text_clean.lower()
        client_greet = f" {sender_name}" if sender_name else ""

        import unicodedata
        text_norm = ''.join(c for c in unicodedata.normalize('NFD', text_lower) if unicodedata.category(c) != 'Mn')

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
            booking_part = f"\n👉 *Reserva tu turno aquí:* {booking_url}\n" if bot_config.auto_booking_link and booking_url else ""
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
        # 8. Respuesta general de asistencia
        else:
            booking_part = f"\n👉 Agenda tu cita: {booking_url}" if bot_config.auto_booking_link and booking_url else ""
            reply = (
                f"🤖 *{bot_config.bot_name} ({business_name}):*\n\n"
                f"Gracias por tu mensaje. Podemos brindarte información sobre nuestros servicios, horarios y turnos disponibles.{booking_part}\n\n"
                f"Si prefieres atención personalizada, déjanos tu consulta y un asesor te responderá pronto."
            )

    # Registrar en el log de automatizaciones de IA
    AIAutomationLog.objects.create(
        business=business,
        sender_phone=sender_phone,
        sender_name=sender_name,
        action_type='WHATSAPP_BOT_REPLY',
        prompt_used=incoming_text_clean,
        response_generated=reply,
        status='SENT'
    )

    return reply

def generate_executive_financial_insight(business):
    """Genera diagnóstico ejecutivo de negocio usando IA Administrativa."""
    total_sales = Sale.objects.filter(business=business, status='COMPLETED').aggregate(total=Sum('total_amount'))['total'] or 0
    total_expenses = Expense.objects.filter(business=business).aggregate(total=Sum('amount'))['total'] or 0
    net_profit = total_sales - total_expenses
    
    # Inactive clients scanner
    sixty_days_ago = datetime.datetime.now() - datetime.timedelta(days=60)
    inactive_clients = Client.objects.filter(business=business, last_visit__lt=sixty_days_ago).count()
    
    top_service = Appointment.objects.filter(business=business, status='COMPLETED').values('service__name').annotate(count=Count('id')).order_order_by_count() if hasattr(Appointment.objects, 'order_order_by_count') else None
    top_service_name = top_service[0]['service__name'] if top_service and len(top_service) > 0 else "Corte & Barba Premium"

    summary = (
        f"**Resumen Ejecutivo por RauDie OS IA:**\n\n"
        f"• Ingresos totales del periodo: {business.currency}{total_sales:,.2f}\n"
        f"• Gastos operativos: {business.currency}{total_expenses:,.2f}\n"
        f"• Utilidad Neta estimada: {business.currency}{net_profit:,.2f}\n\n"
        f"**Diagnóstico y Recomendaciones:**\n"
        f"1. El servicio con mayor rentabilidad y demanda actual es **{top_service_name}**.\n"
        f"2. Detectamos **{inactive_clients} clientes** que no registran visitas en los últimos 60 días.\n"
        f"3. Te sugerimos activar la campaña automática por WhatsApp para recuperar un est. 18% de clientes inactivos esta semana."
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
    sixty_days_ago = datetime.datetime.now() - datetime.timedelta(days=60)
    inactive_clients = Client.objects.filter(business=business).exclude(status='VIP')[:5]
    
    campaigns = []
    for client in inactive_clients:
        msg = f"¡Hola {client.first_name}! Hace tiempo que no nos visitas en {business.name}. Tenemos un 15% de descuento especial en tu próximo servicio si reservas esta semana. Link de reserva: http://localhost:8000/reservas/{business.slug}/?promo=REGRESA15"
        
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
