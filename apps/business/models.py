import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.core.models import TimeStampedModel

class Business(TimeStampedModel):
    BUSINESS_TYPE_CHOICES = [
        ('MARKETING', 'Agencia Digital & Marketing'),
        ('REAL_ESTATE', 'Agencia Inmobiliaria / Bienes Raíces'),
        ('TRAVEL', 'Agencia de Viajes & Turismo'),
        ('CONSULTING', 'Agencia de Consultoría & Servicios'),
        ('HEALTH_BEAUTY', 'Salud, Estética & Spa'),
        ('RETAIL_OTHER', 'Comercio & Servicios Generales'),
    ]

    name = models.CharField(max_length=200, verbose_name="Nombre del Negocio")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="URL de Reservas (Slug)")
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="RUT / RFC / NIF")
    email = models.EmailField(verbose_name="Email de contacto")
    phone = models.CharField(max_length=50, verbose_name="Teléfono / WhatsApp")
    address = models.TextField(blank=True, null=True, verbose_name="Dirección Principal")
    logo_url = models.URLField(blank=True, null=True, verbose_name="URL de Logo")
    currency = models.CharField(max_length=10, default="$", verbose_name="Símbolo de Moneda")
    branding_color = models.CharField(max_length=20, default="#881337", verbose_name="Color de Marca (Hex)")
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPE_CHOICES, default='MARKETING', verbose_name="Tipo de Agencia / Negocio")
    primary_goal = models.CharField(max_length=255, default="Captar clientes y automatizar ventas", verbose_name="Objetivo Principal")
    TIME_FORMAT_CHOICES = [
        ('12h', '12 Horas (ej: 09:00 AM / 09:00 PM)'),
        ('24h', '24 Horas (ej: 09:00 / 21:00)'),
    ]

    enabled_modules = models.JSONField(default=list, blank=True, verbose_name="Módulos Habilitados")
    onboarding_completed = models.BooleanField(default=False, verbose_name="Onboarding Completado")
    time_format = models.CharField(max_length=10, choices=TIME_FORMAT_CHOICES, default='12h', verbose_name="Formato de Hora")
    allow_editing_client_history = models.BooleanField(default=True, verbose_name="Permitir editar el historial de servicios de clientes")

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"

    def __str__(self):
        return self.name

    def is_module_enabled(self, module_name):
        if not self.enabled_modules:
            return True # By default all modules enabled if list is empty
        return module_name in self.enabled_modules

class Branch(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=150, verbose_name="Nombre de Sucursal")
    address = models.CharField(max_length=255, verbose_name="Dirección")
    phone = models.CharField(max_length=50, blank=True, null=True)
    is_main = models.BooleanField(default=False, verbose_name="Sucursal Principal")
    google_maps_url = models.URLField(blank=True, null=True, verbose_name="Ubicación Google Maps / URL")

    def __str__(self):
        return f"{self.business.name} - {self.name}"

class User(AbstractUser):
    ROLE_CHOICES = [
        ('OWNER', 'Propietario / Dueño'),
        ('ADMIN', 'Administrador General'),
        ('PROFESSIONAL', 'Profesional / Especialista'),
        ('RECEPTIONIST', 'Recepción / Caja'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='OWNER', verbose_name="Rol en el Sistema")
    business = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

class StaffMember(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="staff_members")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="staff_members", null=True, blank=True)
    branches = models.ManyToManyField(Branch, blank=True, related_name="staff_members_multi", verbose_name="Sucursales Asignadas")
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_profile")
    first_name = models.CharField(max_length=100, verbose_name="Nombre")
    last_name = models.CharField(max_length=100, verbose_name="Apellido")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    role_title = models.CharField(max_length=100, default="Especialista", verbose_name="Cargo / Especialidad")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Comisión Porcentaje (%)")
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Sueldo Base ($)")
    is_active = models.BooleanField(default=True)
    avatar_color = models.CharField(max_length=20, default="#3b82f6")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def pending_commissions(self):
        from django.db.models import Sum
        total = self.commission_records.filter(is_settled=False).aggregate(total=Sum('amount'))['total']
        return total or 0.00

    @property
    def estimated_total_salary(self):
        return float(self.base_salary or 0) + float(self.pending_commissions or 0)

    def __str__(self):
        return self.full_name

class WorkSchedule(TimeStampedModel):
    DAYS_OF_WEEK = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="schedules")
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField(default="09:00")
    end_time = models.TimeField(default="18:00")
    is_working_day = models.BooleanField(default=True)

    class Meta:
        unique_together = ('staff', 'day_of_week')

    def __str__(self):
        return f"{self.staff.full_name} - {self.get_day_of_week_display()} ({self.start_time} a {self.end_time})"

class PaymentMethodConfig(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payment_methods")
    name = models.CharField(max_length=100, verbose_name="Método de Pago")
    is_enabled = models.BooleanField(default=True)
    instructions = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({'Activo' if self.is_enabled else 'Inactivo'})"
