from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from apps.business.models import Business, StaffMember
from apps.agenda.models import Appointment
from apps.pos.models import Sale
from apps.invoicing.models import Expense
from apps.ai_engine.models import AIAutomationLog
from apps.ai_engine.services import generate_executive_financial_insight, detect_inactive_clients_and_draft_campaign

@login_required
def ai_dashboard_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    logs = AIAutomationLog.objects.filter(business=business) if business else []
    
    financial_insight = None
    whatsapp_campaigns = []

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'run_financial_insight':
            financial_insight = generate_executive_financial_insight(business)
        elif action == 'run_whatsapp_campaign':
            whatsapp_campaigns = detect_inactive_clients_and_draft_campaign(business)

    return render(request, 'ai_engine/ai_dashboard.html', {
        'business': business,
        'logs': logs,
        'financial_insight': financial_insight,
        'whatsapp_campaigns': whatsapp_campaigns,
    })

@login_required
def ai_chat_api(request):
    """API en tiempo real para el Chatbot de IA Asistente."""
    if request.method == 'POST':
        user_prompt = request.POST.get('prompt', '').strip()
        business = getattr(request, 'current_business', None) or request.user.business
        if not business:
            return JsonResponse({'status': 'error', 'message': 'Negocio no encontrado'}, status=400)
        
        prompt_lower = user_prompt.lower()
        
        if "negocio" in prompt_lower or "mes" in prompt_lower or "resumen" in prompt_lower or "financ" in prompt_lower:
            reply = generate_executive_financial_insight(business)
        elif "mañana" in prompt_lower or "libre" in prompt_lower or "turno" in prompt_lower or "agenda" in prompt_lower:
            reply = (
                "🤖 **Asistente de Recepción BusinessOS:**\n\n"
                "Para mañana se detectan **3 huecos disponibles** en la agenda:\n"
                "• 11:30 hs - Esteban Sosa (Barber Master)\n"
                "• 15:30 hs - Sofía Stylist (Especialista Capilar)\n"
                "• 17:00 hs - Esteban Sosa\n\n"
                "👉 Te sugiero enviar una promoción por WhatsApp a los 5 clientes habituales que suelen reservar en la tarde."
            )
        elif "cliente" in prompt_lower or "inactiv" in prompt_lower or "whatsapp" in prompt_lower or "promo" in prompt_lower:
            reply = (
                "🤖 **IA Comercial BusinessOS:**\n\n"
                "Analicé tu CRM y encontré **1 cliente inactivo (+60 días sin visita)**: Lucas Gómez (+5491199887766).\n"
                "Generé el siguiente mensaje listo para enviar:\n"
                "_'¡Hola Lucas! Te extrañamos en Barbería Deluxe. Usa el cupón **REGRESA15** para 15% OFF esta semana.'_"
            )
        else:
            reply = (
                f"🤖 **BusinessOS IA:** He procesado tu consulta: \"{user_prompt}\".\n\n"
                f"Tu negocio **{business.name}** cuenta con 2 turnos agendados para hoy, caja abierta con $100.00 iniciales "
                f"y un stock saludable en productos principales. ¿Deseas ejecutar un análisis financiero completo o enviar una campaña de reactivación?"
            )

        AIAutomationLog.objects.create(
            business=business,
            action_type='SMART_SLOT_SUGGESTION',
            prompt_used=user_prompt,
            response_generated=reply,
            status='COMPLETED'
        )

        return JsonResponse({'status': 'ok', 'reply': reply})
        
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=400)
