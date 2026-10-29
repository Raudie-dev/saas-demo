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
from apps.superadmin.models import PlatformGlobalConfig
from apps.ai_engine.services import (
    generate_executive_financial_insight,
    detect_inactive_clients_and_draft_campaign,
    generate_whatsapp_bot_reply,
    get_or_create_bot_config,
    get_effective_ai_config
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
            bot_config.ai_provider = request.POST.get('ai_provider', 'deepseek')
            bot_config.deepseek_api_key = request.POST.get('deepseek_api_key', '').strip() or None
            bot_config.deepseek_model = request.POST.get('deepseek_model', 'deepseek-chat').strip() or 'deepseek-chat'
            bot_config.auto_register_clients = request.POST.get('auto_register_clients') in ['1', 'true', 'on', True]
            bot_config.auto_create_appointments = request.POST.get('auto_create_appointments') in ['1', 'true', 'on', True]

            # Gestión de archivo de contexto (PDF, Excel, Word)
            if request.POST.get('remove_knowledge_file') == '1':
                if bot_config.knowledge_file:
                    bot_config.knowledge_file.delete(save=False)
                bot_config.knowledge_file = None
                bot_config.knowledge_filename = None
                bot_config.custom_knowledge = None

            uploaded_doc = request.FILES.get('knowledge_file')
            if uploaded_doc:
                from apps.ai_engine.document_parser import validate_knowledge_file, extract_text_from_knowledge_file
                is_valid, err_msg, _ = validate_knowledge_file(uploaded_doc)
                if not is_valid:
                    messages.error(request, err_msg)
                    return redirect('ai_dashboard')
                extracted_text = extract_text_from_knowledge_file(uploaded_doc)
                bot_config.knowledge_file = uploaded_doc
                bot_config.knowledge_filename = uploaded_doc.name
                bot_config.custom_knowledge = extracted_text or f"Archivo adjunto: {uploaded_doc.name}"

            bot_config.save()
            messages.success(request, "¡Configuración del Bot y Motor DeepSeek guardada con éxito!")
            return redirect('ai_dashboard')
        elif action == 'run_financial_insight':
            financial_insight = generate_executive_financial_insight(business)
        elif action == 'run_whatsapp_campaign':
            whatsapp_campaigns = detect_inactive_clients_and_draft_campaign(business)

    # Check effective AI access and config
    effective_key, effective_model, effective_provider, source_status, source_desc = get_effective_ai_config(business)
    has_platform_key_access = business.has_platform_ai_access()
    global_cfg = PlatformGlobalConfig.get_solo()

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
        'has_platform_key_access': has_platform_key_access,
        'effective_key': effective_key,
        'effective_model': effective_model,
        'source_status': source_status,
        'source_desc': source_desc,
        'global_cfg_ready': bool(global_cfg.deepseek_api_key and global_cfg.is_deepseek_active),
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
    sender_pn = body.get('senderPn', '') or remote_jid
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

    clean_sender = (
        str(sender_pn)
        .replace('@s.whatsapp.net', '')
        .replace('@lid', '')
        .split(':')[0]
    )

    # Generar respuesta usando la configuración del bot del negocio
    reply = generate_whatsapp_bot_reply(
        business=business,
        incoming_text=message_text,
        sender_phone=clean_sender,
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
            # Simular respuesta exacta del Bot de WhatsApp (incluso si está pausado para WhatsApp real)
            reply = generate_whatsapp_bot_reply(
                business=business,
                incoming_text=user_prompt,
                sender_phone='SIMULADOR',
                sender_name=request.user.first_name or 'Cliente Demo',
                force_simulate=True
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
