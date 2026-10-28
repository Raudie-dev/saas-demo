from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business
from apps.crm.models import Client

class AIAutomationLog(TimeStampedModel):
    ACTION_CHOICES = [
        ('WHATSAPP_REMINDER', 'Recordatorio de Cita por WhatsApp'),
        ('WHATSAPP_BOT_REPLY', 'Respuesta de Bot WhatsApp'),
        ('REACTIVATION_CAMPAIGN', 'Reactivación de Cliente Inactivo'),
        ('FINANCIAL_INSIGHT', 'Análisis Ejecutivo Financiero'),
        ('SMART_SLOT_SUGGESTION', 'Recomendación de Huecos de Agenda'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_logs")
    target_client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    sender_phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono Emisor")
    sender_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nombre Emisor")
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    prompt_used = models.TextField(blank=True, null=True)
    response_generated = models.TextField()
    status = models.CharField(max_length=20, default='SIMULATED')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"IA Log: {self.get_action_type_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class WhatsAppBotConfig(TimeStampedModel):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="whatsapp_bot_config", verbose_name="Negocio")
    is_active = models.BooleanField(default=True, verbose_name="Bot de WhatsApp Activo")
    bot_name = models.CharField(max_length=100, default="Asistente Virtual", verbose_name="Nombre del Bot")
    welcome_message = models.TextField(
        default="¡Hola! 👋 Gracias por comunicarte con nosotros. Soy tu asistente virtual. ¿En qué te puedo ayudar hoy?",
        verbose_name="Mensaje de Bienvenida / Saludo"
    )
    system_prompt = models.TextField(
        default=(
            "Eres el asistente virtual inteligente de {business_name}. "
            "Atiende a los clientes de forma amable, profesional y rápida. "
            "Responde dudas sobre nuestros servicios, horarios y precios. "
            "Si el cliente quiere reservar un turno o cita, ofrécele el enlace directo de reservas online: {booking_url}. "
            "Mantén tus respuestas breves y claras, ideales para WhatsApp."
        ),
        verbose_name="Instrucciones del Sistema (Prompt de IA)"
    )
    auto_booking_link = models.BooleanField(default=True, verbose_name="Incluir link del portal de reservas al consultar citas")
    ai_provider = models.CharField(
        max_length=20,
        choices=[('deepseek', 'DeepSeek AI'), ('openai', 'OpenAI')],
        default='deepseek',
        verbose_name="Proveedor de Inteligencia Artificial"
    )
    deepseek_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="API Key de DeepSeek (Propia)")
    deepseek_model = models.CharField(max_length=50, default='deepseek-chat', verbose_name="Modelo DeepSeek")
    openai_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="API Key de OpenAI (Opcional)")
    custom_knowledge = models.TextField(
        blank=True,
        null=True,
        verbose_name="Base de Conocimientos / Contexto de la Agencia",
        help_text="Políticas, FAQs, promociones, reglas de atención o información especial que el bot consultará al responder."
    )
    auto_register_clients = models.BooleanField(default=True, verbose_name="Registrar clientes nuevos automáticamente en el CRM")
    auto_create_appointments = models.BooleanField(default=True, verbose_name="Agendar citas automáticamente según disponibilidad de la agenda")

    class Meta:
        verbose_name = "Configuración del Bot WhatsApp"
        verbose_name_plural = "Configuraciones del Bot WhatsApp"

    def __str__(self):
        return f"Bot WhatsApp - {self.business.name} ({'Activo' if self.is_active else 'Inactivo'})"

    @classmethod
    def get_for_business(cls, business):
        config, _ = cls.objects.get_or_create(
            business=business,
            defaults={
                'bot_name': f"Asistente {business.name}",
                'welcome_message': f"¡Hola! 👋 Gracias por comunicarte con {business.name}. ¿En qué te podemos ayudar hoy?",
                'system_prompt': (
                    f"Eres el asistente virtual de {business.name}. "
                    "Atiende a los clientes de forma amable, profesional y rápida. "
                    "Responde dudas sobre nuestros servicios, horarios y precios. "
                    "Si el cliente quiere reservar un turno o cita, ofrécele el enlace directo de reservas online: {booking_url}. "
                    "Mantén tus respuestas breves y claras, ideales para WhatsApp."
                ),
            }
        )
        return config
