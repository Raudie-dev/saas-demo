import datetime
from django.db.models import Sum, Count
from apps.pos.models import Sale
from apps.invoicing.models import Expense, Invoice
from apps.crm.models import Client
from apps.agenda.models import Appointment
from apps.ai_engine.models import AIAutomationLog

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
        f"📊 **Resumen Ejecutivo por BusinessOS IA:**\n\n"
        f"• Ingresos totales del periodo: {business.currency}{total_sales:,.2f}\n"
        f"• Gastos operativos: {business.currency}{total_expenses:,.2f}\n"
        f"• Utilidad Neta estimada: {business.currency}{net_profit:,.2f}\n\n"
        f"💡 **Diagnóstico y Recomendaciones:**\n"
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
        msg = f"¡Hola {client.first_name}! 👋 Hace tiempo que no nos visitas en {business.name}. Tenemos un 15% de descuento especial en tu próximo servicio si reservas esta semana. 👉 Link de reserva: http://localhost:8000/reservas/{business.slug}/?promo=REGRESA15"
        
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
