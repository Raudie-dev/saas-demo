import os
import json
import urllib.request
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.business.models import Business, StaffMember
from apps.agenda.models import Appointment
from apps.pos.models import Sale
from apps.invoicing.models import Expense
from apps.ai_engine.models import AIAutomationLog, WhatsAppBotConfig
from apps.ai_engine.services import (
    generate_executive_financial_insight,
    detect_inactive_clients_and_draft_campaign,
    generate_whatsapp_bot_reply,
    get_or_create_bot_config
)

GATEWAY_BASE_URL = getattr(settings, 'WHATSAPP_GATEWAY_URL', None) or os.environ.get('WHATSAPP_GATEWAY_URL', 'http://127.0.0.1:3000').rstrip('/')

@login_required
def ai_dashboard_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not business.is_module_enabled('ai_engine'):
        messages.error(request, "El módulo de Inteligencia Artificial & Automatización no está contratado en tu plan o está deshabilitado.")
        return redirect('dashboard')

    bot_config = get_or_create_bot_config(business)
    logs = AIAutomationLog.objects.filter(business=business).order_by('-created_at')[:50]
    
    financial_insight = None
    whatsapp_campaigns = []

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_bot_status':
            if not business.is_module_enabled('whatsapp'):
                messages.error(request, "El Bot de WhatsApp requiere que el módulo de WhatsApp esté activo en tu empresa.")
                return redirect('ai_dashboard')
            bot_config.is_active = not bot_config.is_active
            bot_config.save()
            estado_txt = "activado" if bot_config.is_active else "pausado / apagado"
            messages.success(request, f"El Bot de WhatsApp ha sido {estado_txt} correctamente.")
            return redirect('ai_dashboard')
        elif action == 'save_bot_config':
            if not business.is_module_enabled('whatsapp'):
                messages.error(request, "La configuración del Bot de WhatsApp requiere que el módulo de WhatsApp esté activo en tu empresa.")
                return redirect('ai_dashboard')
            bot_config.is_active = request.POST.get('is_active') in ['1', 'true', 'on', True]
            bot_config.bot_name = request.POST.get('bot_name', bot_config.bot_name).strip()
            bot_config.welcome_message = request.POST.get('welcome_message', bot_config.welcome_message).strip()
            bot_config.system_prompt = request.POST.get('system_prompt', bot_config.system_prompt).strip()
            bot_config.auto_booking_link = request.POST.get('auto_booking_link') in ['1', 'true', 'on', True]
            bot_config.openai_api_key = request.POST.get('openai_api_key', '').strip() or None
            bot_config.save()
            messages.success(request, "¡Configuración del Bot de WhatsApp guardada con éxito!")
            return redirect('ai_dashboard')
        elif action == 'run_financial_insight':
            financial_insight = generate_executive_financial_insight(business)
        elif action == 'run_whatsapp_campaign':
            whatsapp_campaigns = detect_inactive_clients_and_draft_campaign(business)

    # Check WhatsApp connection status
    gw_status = {'online': False, 'status': 'offline'}
    try:
        url = f"{GATEWAY_BASE_URL}/status?user={business.id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            gw_status = {'online': True, 'status': data.get('status', 'disconnected')}
    except Exception:
        gw_status = {'online': False, 'status': 'offline'}

    return render(request, 'ai_engine/ai_dashboard.html', {
        'business': business,
        'bot_config': bot_config,
        'gw_status': gw_status,
        'logs': logs,
        'financial_insight': financial_insight,
        'whatsapp_campaigns': whatsapp_campaigns,
    })

@csrf_exempt
def whatsapp_webhook_api(request):
    """
    Webhook receptor de mensajes entrantes desde el microservicio whatsapp-gateway.
    Procesa el mensaje mediante la IA / motor contextual del bot y retorna la respuesta para WhatsApp.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        body = request.POST

    remote_jid = body.get('remoteJid', '')
    push_name = body.get('pushName', '')
    message_text = body.get('messageText', '')
    owner_id = body.get('owner') or body.get('session', '').split('_')[0]

    business = None
    if owner_id and owner_id != 'default':
        business = Business.objects.filter(id=owner_id).first()

    if not business:
        # Fallback al primer negocio activo
        business = Business.objects.first()

    if not business:
        return JsonResponse({'status': 'error', 'reply': None, 'message': 'Negocio no encontrado'})

    # Generar respuesta usando la configuración del bot del negocio
    reply = generate_whatsapp_bot_reply(
        business=business,
        incoming_text=message_text,
        sender_phone=remote_jid.replace('@s.whatsapp.net', ''),
        sender_name=push_name
    )

    return JsonResponse({'status': 'ok', 'reply': reply})

@login_required
def ai_chat_api(request):
    """API en tiempo real para el Simulador / Chatbot de IA Asistente."""
    if request.method == 'POST':
        user_prompt = request.POST.get('prompt', '').strip()
        business = getattr(request, 'current_business', None) or request.user.business
        if not business:
            return JsonResponse({'status': 'error', 'message': 'Negocio no encontrado'}, status=400)
        
        mode = request.POST.get('mode', 'bot')
        if mode == 'bot':
            # Simular respuesta exacta del Bot de WhatsApp
            reply = generate_whatsapp_bot_reply(
                business=business,
                incoming_text=user_prompt,
                sender_phone='SIMULADOR',
                sender_name=request.user.first_name or 'Cliente Demo'
            )
            return JsonResponse({'status': 'ok', 'reply': reply})

        prompt_lower = user_prompt.lower()
        if "negocio" in prompt_lower or "mes" in prompt_lower or "resumen" in prompt_lower or "financ" in prompt_lower:
            reply = generate_executive_financial_insight(business)
        else:
            reply = generate_whatsapp_bot_reply(
                business=business,
                incoming_text=user_prompt,
                sender_phone='SIMULADOR',
                sender_name=request.user.first_name or 'Cliente'
            )

        return JsonResponse({'status': 'ok', 'reply': reply})
        
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=400)
