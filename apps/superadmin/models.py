import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel
from apps.business.models import Business

class SubscriptionPlan(TimeStampedModel):
    PLAN_CODE_CHOICES = [
        ('STARTER', 'Plan Inicial (Starter)'),
        ('PRO', 'Plan Profesional (Pro)'),
        ('ENTERPRISE', 'Plan Corporativo (Enterprise)'),
    ]

    name = models.CharField(max_length=100, verbose_name="Nombre del Plan")
    code = models.CharField(max_length=50, choices=PLAN_CODE_CHOICES, unique=True, verbose_name="Código de Plan")
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('29.00'), verbose_name="Precio Mensual ($)")
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('290.00'), verbose_name="Precio Anual ($)")
    max_users = models.IntegerField(default=5, verbose_name="Límite de Usuarios")
    max_branches = models.IntegerField(default=2, verbose_name="Límite de Sucursales")
    included_modules = models.JSONField(default=list, blank=True, verbose_name="Módulos Incluidos")
    show_on_landing = models.BooleanField(default=True, verbose_name="Mostrar en Landing Page / Index")
    is_active = models.BooleanField(default=True, verbose_name="Plan Activo")

    class Meta:
        verbose_name = "Plan de Suscripción"
        verbose_name_plural = "Planes de Suscripción"

    def __str__(self):
        return f"{self.name} (${self.monthly_price}/mes)"

class BusinessSubscription(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Licencia Activa'),
        ('TRIAL', 'En Período de Prueba'),
        ('EXPIRED', 'Licencia Vencida'),
        ('SUSPENDED', 'Cuenta Suspendida'),
    ]

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="subscription", verbose_name="Agencia / Negocio")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions", verbose_name="Plan Contratado")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TRIAL', verbose_name="Estado de Licencia")
    license_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name="Clave Token de Licencia")
    start_date = models.DateField(default=timezone.now, verbose_name="Fecha de Inicio")
    expiration_date = models.DateField(verbose_name="Fecha de Expiración")
    auto_renew = models.BooleanField(default=True, verbose_name="Renovación Automática")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas Internas de Administración")

    class Meta:
        verbose_name = "Suscripción de Agencia"
        verbose_name_plural = "Suscripciones de Agencias"

    def __str__(self):
        return f"{self.business.name} - {self.get_status_display()} ({self.plan.name if self.plan else 'Sin Plan'})"

    @property
    def is_valid(self):
        if self.status in ['EXPIRED', 'SUSPENDED']:
            return False
        if self.expiration_date and self.expiration_date < timezone.now().date():
            return False
        return True

    @property
    def days_remaining(self):
        if not self.expiration_date:
            return 0
        diff = (self.expiration_date - timezone.now().date()).days
        return max(0, diff)

class SystemAuditLog(TimeStampedModel):
    actor_email = models.CharField(max_length=150, verbose_name="Usuario Ejecutor")
    action = models.CharField(max_length=100, verbose_name="Acción Realizada")
    details = models.TextField(verbose_name="Detalles de la Operación")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Dirección IP")

    class Meta:
        verbose_name = "Registro de Auditoría de Sistema"
        verbose_name_plural = "Registros de Auditoría de Sistema"

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.actor_email}: {self.action}"
