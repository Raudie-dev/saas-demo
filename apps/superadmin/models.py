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
    pending_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="pending_subscriptions", verbose_name="Plan Solicitado (Pendiente Aprobar)")
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

class GlobalPaymentMethod(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Método de Pago")
    code = models.CharField(max_length=50, unique=True, verbose_name="Código Identificador (ej: CASH, CARD, MERCADOPAGO)")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción o Instrucciones Generales")
    is_active = models.BooleanField(default=True, verbose_name="Habilitado Globalmente")

    class Meta:
        verbose_name = "Método de Pago Global"
        verbose_name_plural = "Métodos de Pago Globales"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({'Activo' if self.is_active else 'Inactivo'})"


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

