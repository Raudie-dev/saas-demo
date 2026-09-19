from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business
from apps.crm.models import Client

class AIAutomationLog(TimeStampedModel):
    ACTION_CHOICES = [
        ('WHATSAPP_REMINDER', 'Recordatorio de Cita por WhatsApp'),
        ('REACTIVATION_CAMPAIGN', 'Reactivación de Cliente Inactivo'),
        ('FINANCIAL_INSIGHT', 'Análisis Ejecutivo Financiero'),
        ('SMART_SLOT_SUGGESTION', 'Recomendación de Huecos de Agenda'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_logs")
    target_client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    prompt_used = models.TextField(blank=True, null=True)
    response_generated = models.TextField()
    status = models.CharField(max_length=20, default='SIMULATED')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"IA Log: {self.get_action_type_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
