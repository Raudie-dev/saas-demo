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
    ai_platform_key_included = models.BooleanField(default=False, verbose_name="Incluye API Key de IA de la Plataforma")
    show_on_landing = models.BooleanField(default=True, verbose_name="Mostrar en Landing Page / Index")
    is_active = models.BooleanField(default=True, verbose_name="Plan Activo")

    class Meta:
        verbose_name = "Plan de Suscripción"
        verbose_name_plural = "Planes de Suscripción"

    def __str__(self):
        return f"{self.name} (${self.monthly_price}/mes)"

    @property
    def edit_data(self):
        region_prices_dict = {}
        for rp in self.region_prices.all():
            region_prices_dict[str(rp.region_id)] = {
                'monthly': str(rp.monthly_price),
                'annual': str(rp.annual_price),
                'active': bool(rp.is_active)
            }
        return {
            'id': str(self.id),
            'name': self.name,
            'code': self.code,
            'monthly_price': str(self.monthly_price),
            'annual_price': str(self.annual_price),
            'max_users': self.max_users,
            'max_branches': self.max_branches,
            'show_on_landing': self.show_on_landing,
            'is_active': self.is_active,
            'ai_platform_key_included': bool(self.ai_platform_key_included),
            'included_modules': self.included_modules if isinstance(self.included_modules, list) else [],
            'region_prices': region_prices_dict
        }

    @property
    def edit_json(self):
        import json
        return json.dumps(self.edit_data)

class BusinessSubscription(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Licencia Activa'),
        ('TRIAL', 'En Período de Prueba'),
        ('EXPIRED', 'Licencia Vencida'),
        ('SUSPENDED', 'Cuenta Suspendida'),
    ]

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="subscription", verbose_name="Agencia / Negocio")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions", verbose_name="Plan Contratado")
    pending_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="pending_subscriptions", verbose_name="Plan Solicitado (Pendiente Aprobar)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TRIAL', verbose_name="Estado de Licencia")
    license_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name="Clave Token de Licencia")
    start_date = models.DateField(default=timezone.now, verbose_name="Fecha de Inicio")
    expiration_date = models.DateField(verbose_name="Fecha de Expiración")
    auto_renew = models.BooleanField(default=True, verbose_name="Renovación Automática")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas Internas de Administración")
    gateway_provider = models.CharField(max_length=50, blank=True, null=True, verbose_name="Pasarela de Cobro Recurrente")
    gateway_subscription_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="ID Suscripción en Pasarela")
    recurring_status = models.CharField(max_length=30, blank=True, null=True, verbose_name="Estado Débito Automático")

    @property
    def has_active_recurring(self):
        return bool(self.gateway_subscription_id) and self.recurring_status in ('pending', 'authorized')

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.business and self.plan:
            try:
                self.business.sync_modules_with_plan()
            except Exception as e:
                pass

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

class GlobalPaymentMethod(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Método de Pago")
    code = models.CharField(max_length=50, unique=True, verbose_name="Código Identificador (ej: CASH, CARD, MERCADOPAGO)")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción o Instrucciones Generales")
    provider = models.CharField(max_length=50, blank=True, default='', verbose_name="Integración (pasarela por código)")
    is_active = models.BooleanField(default=True, verbose_name="Habilitado Globalmente")

    class Meta:
        verbose_name = "Método de Pago Global"
        verbose_name_plural = "Métodos de Pago Globales"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({'Activo' if self.is_active else 'Inactivo'})"

    @property
    def is_integrated(self):
        return bool(self.provider)

class Region(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Región")
    code = models.CharField(max_length=50, unique=True, verbose_name="Código (ej: AR, CL, GLOBAL)")
    country_codes = models.CharField(max_length=200, blank=True, null=True, verbose_name="Códigos de País para Auto-detección (ej: AR, CL, UY)")
    currency_symbol = models.CharField(max_length=10, default="$", verbose_name="Símbolo de Moneda Default")
    currency_code = models.CharField(max_length=3, blank=True, default='', verbose_name="Moneda ISO para pasarelas (ej: ARS, CLP, MXN)")
    is_active = models.BooleanField(default=True, verbose_name="Región Activa")
    is_default = models.BooleanField(default=False, verbose_name="Región por Defecto")

    class Meta:
        verbose_name = "Región"
        verbose_name_plural = "Regiones"
        ordering = ['name']

    def __str__(self):
        return self.name

class PlanRegionPricing(TimeStampedModel):
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="region_prices", verbose_name="Plan")
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="plan_prices", verbose_name="Región")
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Mensual Regional ($)")
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Anual Regional ($)")
    is_active = models.BooleanField(default=True, verbose_name="Activo en esta Región")

    class Meta:
        verbose_name = "Precio Regional de Plan"
        verbose_name_plural = "Precios Regionales de Planes"
        unique_together = ('plan', 'region')

    def __str__(self):
        return f"{self.plan.name} - {self.region.name} (${self.monthly_price}/mes)"

class RegionPaymentMethod(TimeStampedModel):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="payment_methods", verbose_name="Región")
    payment_method = models.ForeignKey(GlobalPaymentMethod, on_delete=models.CASCADE, related_name="region_configurations", verbose_name="Método de Pago Global")
    instructions = models.TextField(blank=True, null=True, verbose_name="Instrucciones para la Región (CBU, Alias, Link)")
    payment_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="Enlace de Pago Directo (Checkout/Link)")
    use_for_sales = models.BooleanField(default=True, verbose_name="Usar en Ventas (POS) de las Agencias")
    use_for_billing = models.BooleanField(default=False, verbose_name="Usar para Pagar Suscripción del SaaS")
    is_active = models.BooleanField(default=True, verbose_name="Activo en esta Región")

    class Meta:
        verbose_name = "Método de Pago por Región"
        verbose_name_plural = "Métodos de Pago por Región"
        unique_together = ('region', 'payment_method')

    def __str__(self):
        return f"{self.payment_method.name} en {self.region.name}"

class SubscriptionPayment(TimeStampedModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Revisión'),
        ('APPROVED', 'Pago Aprobado'),
        ('REJECTED', 'Pago Rechazado'),
    ]

    CYCLE_CHOICES = [
        ('MONTHLY', 'Mensual'),
        ('ANNUAL', 'Anual'),
    ]

    business = models.ForeignKey('business.Business', on_delete=models.CASCADE, related_name="subscription_payments", verbose_name="Agencia")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Plan Abonado")
    region_payment_method = models.ForeignKey(RegionPaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Método de Pago Utilizado")
    billing_cycle = models.CharField(max_length=20, choices=CYCLE_CHOICES, default='MONTHLY', verbose_name="Ciclo de Facturación")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto Informado")
    reference = models.CharField(max_length=255, blank=True, null=True, verbose_name="N° Referencia / Comprobante")
    receipt_file = models.FileField(upload_to='subscription_receipts/', blank=True, null=True, verbose_name="Comprobante Adjunto")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="Estado del Pago")
    paid_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Pago Informada")
    reviewed_at = models.DateTimeField(blank=True, null=True, verbose_name="Fecha de Revisión")
    reviewed_by = models.ForeignKey('SuperAdminUser', on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_payments")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas del Administrador")
    mp_preference_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Preferencia Mercado Pago")
    mp_payment_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="ID Pago Mercado Pago")
    mp_status = models.CharField(max_length=30, blank=True, null=True, verbose_name="Estado en Mercado Pago")

    class Meta:
        verbose_name = "Pago de Suscripción"
        verbose_name_plural = "Pagos de Suscripciones"
        ordering = ['-created_at']

    def __str__(self):
        return f"Pago {self.id} - {self.business.name} ({self.get_status_display()})"
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager

class SuperAdminUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El Email es obligatorio para SuperAdminUser")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser debe tener is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class SuperAdminUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name="Correo Electrónico")
    username = models.CharField(max_length=150, unique=True, verbose_name="Nombre de Usuario")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Nombre")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Apellido")
    is_staff = models.BooleanField(default=True, verbose_name="Es Staff")
    is_active = models.BooleanField(default=True, verbose_name="Usuario Activo")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última Actualización")

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='grupos',
        blank=True,
        help_text='Los grupos a los que pertenece este superadmin.',
        related_name="superadmin_user_set",
        related_query_name="superadmin_user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='permisos de usuario',
        blank=True,
        help_text='Permisos específicos para este superadmin.',
        related_name="superadmin_user_permissions_set",
        related_query_name="superadmin_user",
    )

    objects = SuperAdminUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = "Super Administrador"
        verbose_name_plural = "Super Administradores"
        db_table = 'superadmin_users'

    def __str__(self):
        return f"{self.email} ({self.username})"

    @property
    def full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username or self.email


class PlatformGlobalConfig(TimeStampedModel):
    deepseek_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="API Key de DeepSeek (Global)")
    deepseek_model = models.CharField(max_length=100, default="deepseek-chat", verbose_name="Modelo de DeepSeek")
    openai_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="API Key de OpenAI (Fallback Global)")
    default_system_prompt = models.TextField(
        blank=True,
        null=True,
        verbose_name="Instrucciones Globales de IA",
        help_text="Directivas y prompt base que se aplican al bot de forma global."
    )
    is_deepseek_active = models.BooleanField(default=True, verbose_name="Habilitar DeepSeek Global")

    class Meta:
        verbose_name = "Configuración Global de Plataforma"
        verbose_name_plural = "Configuraciones Globales de Plataforma"

    def __str__(self):
        status = "Configurada" if self.deepseek_api_key else "Sin API Key"
        return f"Configuración Global DeepSeek ({status})"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create(
                deepseek_model="deepseek-chat",
                is_deepseek_active=True
            )
        return obj



