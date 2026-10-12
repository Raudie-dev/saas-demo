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
    logo_url = models.ImageField(upload_to='business/logos/', blank=True, null=True, verbose_name="Logo de Perfil")
    banner_url = models.ImageField(upload_to='business/banners/', blank=True, null=True, verbose_name="Banner/Portada")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción del Negocio / Bio")
    whatsapp_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de WhatsApp (Opcional)")
    currency = models.CharField(max_length=10, default="$", verbose_name="Símbolo de Moneda")
    branding_color = models.CharField(max_length=20, default="#881337", verbose_name="Color de Marca (Hex)")
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPE_CHOICES, default='MARKETING', verbose_name="Tipo de Agencia / Negocio")
    primary_goal = models.CharField(max_length=255, default="Captar clientes y automatizar ventas", verbose_name="Objetivo Principal")
    appointment_reminder_message = models.TextField(
        default="Hola {client_name}, te recordamos tu cita de *{service}* en *{business}* para el día *{date}* a las *{time}* con *{staff}*. ¡Te esperamos!",
        verbose_name="Plantilla de Recordatorio de Cita (WhatsApp)"
    )
    TIME_FORMAT_CHOICES = [
        ('12h', '12 Horas (ej: 09:00 AM / 09:00 PM)'),
        ('24h', '24 Horas (ej: 09:00 / 21:00)'),
    ]

    enabled_modules = models.JSONField(default=list, blank=True, verbose_name="Módulos Habilitados")
    onboarding_completed = models.BooleanField(default=False, verbose_name="Onboarding Completado")
    time_format = models.CharField(max_length=10, choices=TIME_FORMAT_CHOICES, default='12h', verbose_name="Formato de Hora")
    allow_editing_client_history = models.BooleanField(default=True, verbose_name="Permitir editar el historial de servicios de clientes")
    region = models.ForeignKey('superadmin.Region', on_delete=models.SET_NULL, null=True, blank=True, related_name='businesses', verbose_name="Región")
    is_booking_enabled = models.BooleanField(default=True, verbose_name="Portal de Reservas Público Activo")

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"

    def __str__(self):
        return self.name

    def get_allowed_modules(self):
        sub = getattr(self, 'subscription', None)
        if sub and sub.plan and sub.plan.included_modules:
            return sub.plan.included_modules
        return ['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing']

    def is_module_allowed_by_plan(self, module_name):
        allowed = self.get_allowed_modules()
        return module_name in allowed

    def is_module_enabled(self, module_name):
        if module_name == 'booking' and not getattr(self, 'is_booking_enabled', True):
            return False
        if not self.is_module_allowed_by_plan(module_name):
            return False
        if not self.enabled_modules:
            return True
        return module_name in self.enabled_modules

    def save(self, *args, **kwargs):
        from apps.core.utils_image import process_image_to_webp
        
        # Process logo if it's new or changed
        if self.pk:
            try:
                old_instance = Business.objects.get(pk=self.pk)
                if self.logo_url and hasattr(self.logo_url, 'file') and getattr(old_instance.logo_url, 'name', None) != self.logo_url.name:
                    process_image_to_webp(self.logo_url, max_size=(512, 512))
                
                if self.banner_url and hasattr(self.banner_url, 'file') and getattr(old_instance.banner_url, 'name', None) != self.banner_url.name:
                    process_image_to_webp(self.banner_url, max_size=(1920, 1080))
            except Business.DoesNotExist:
                pass
        else:
            if self.logo_url and hasattr(self.logo_url, 'file'):
                process_image_to_webp(self.logo_url, max_size=(512, 512))
            if self.banner_url and hasattr(self.banner_url, 'file'):
                process_image_to_webp(self.banner_url, max_size=(1920, 1080))

        super().save(*args, **kwargs)

class Branch(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=150, verbose_name="Nombre de Sucursal")
    address = models.CharField(max_length=255, verbose_name="Dirección")
    phone = models.CharField(max_length=50, blank=True, null=True)
    is_main = models.BooleanField(default=False, verbose_name="Sucursal Principal")
    google_maps_url = models.URLField(blank=True, null=True, verbose_name="Ubicación Google Maps / URL")

    def __str__(self):
        return f"{self.business.name} - {self.name}"

class UserProfileRole(TimeStampedModel):
    SCOPE_APPOINTMENTS_CHOICES = [
        ('OWN', 'Solo sus propias citas asignadas'),
        ('ALL', 'Todas las citas de la clínica / sucursal'),
    ]
    SCOPE_COMMISSIONS_CHOICES = [
        ('OWN', 'Solo sus propias comisiones'),
        ('ALL', 'Todas las comisiones del equipo'),
        ('NONE', 'Sin acceso a comisiones'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="role_profiles", verbose_name="Agencia / Clínica")
    name = models.CharField(max_length=100, verbose_name="Nombre del Perfil")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción del Perfil")
    is_system_default = models.BooleanField(default=False, verbose_name="Perfil Base del Sistema")
    allowed_modules = models.JSONField(default=list, blank=True, verbose_name="Módulos Habilitados")
    scope_appointments = models.CharField(max_length=10, choices=SCOPE_APPOINTMENTS_CHOICES, default='ALL', verbose_name="Alcance de Citas")
    scope_commissions = models.CharField(max_length=10, choices=SCOPE_COMMISSIONS_CHOICES, default='NONE', verbose_name="Alcance de Comisiones")
    can_charge_pos = models.BooleanField(default=False, verbose_name="Permitir Cobrar y Operar POS / Caja")
    can_view_financial_reports = models.BooleanField(default=False, verbose_name="Permitir Ver Reportes Financieros")
    can_manage_settings = models.BooleanField(default=False, verbose_name="Permitir Configurar Empresa y Gestionar Usuarios")
    can_manage_clients = models.BooleanField(default=True, verbose_name="Permitir Gestionar Clientes (CRM)")
    can_manage_inventory = models.BooleanField(default=False, verbose_name="Permitir Gestionar Inventario")

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.business.name})"

    def clean_modules_against_subscription(self):
        """Asegura que los módulos permitidos no excedan los contratados en el plan."""
        allowed_in_plan = self.business.get_allowed_modules()
        self.allowed_modules = [m for m in (self.allowed_modules or []) if m in allowed_in_plan]

def ensure_default_profiles(business):
    """Crea los 3 perfiles base estándar para una clínica o negocio si no existen."""
    if not business:
        return
    allowed_plan_modules = business.get_allowed_modules()
    
    # 1. Profesional / Especialista
    prof_modules = [m for m in ['agenda', 'commissions'] if m in allowed_plan_modules]
    UserProfileRole.objects.get_or_create(
        business=business,
        name='Profesional / Especialista',
        defaults={
            'description': 'Acceso exclusivo a sus citas asignadas y sus comisiones personales.',
            'is_system_default': True,
            'allowed_modules': prof_modules,
            'scope_appointments': 'OWN',
            'scope_commissions': 'OWN',
            'can_charge_pos': False,
            'can_view_financial_reports': False,
            'can_manage_settings': False,
            'can_manage_clients': True,
            'can_manage_inventory': False,
        }
    )

    # 2. Recepción & Caja
    recep_modules = [m for m in ['agenda', 'crm', 'pos'] if m in allowed_plan_modules]
    UserProfileRole.objects.get_or_create(
        business=business,
        name='Recepción & Caja',
        defaults={
            'description': 'Control de agenda de la clínica, gestión de clientes y cobro en POS / Caja.',
            'is_system_default': True,
            'allowed_modules': recep_modules,
            'scope_appointments': 'ALL',
            'scope_commissions': 'NONE',
            'can_charge_pos': True,
            'can_view_financial_reports': False,
            'can_manage_settings': False,
            'can_manage_clients': True,
            'can_manage_inventory': False,
        }
    )

    # 3. Administrador de Clínica
    UserProfileRole.objects.get_or_create(
        business=business,
        name='Administrador de Clínica',
        defaults={
            'description': 'Acceso total a todos los módulos y herramientas de configuración del negocio.',
            'is_system_default': True,
            'allowed_modules': list(allowed_plan_modules),
            'scope_appointments': 'ALL',
            'scope_commissions': 'ALL',
            'can_charge_pos': True,
            'can_view_financial_reports': True,
            'can_manage_settings': True,
            'can_manage_clients': True,
            'can_manage_inventory': True,
        }
    )
    return list(UserProfileRole.objects.filter(business=business))

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
    profile_role = models.ForeignKey(UserProfileRole, on_delete=models.SET_NULL, null=True, blank=True, related_name="users", verbose_name="Perfil / Rol de Acceso")
    business = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")

    def __str__(self):
        role_label = self.profile_role.name if self.profile_role else self.get_role_display()
        return f"{self.get_full_name() or self.username} ({role_label})"

    def has_module_access(self, module_code):
        if not self.business:
            return False
        if not self.business.is_module_enabled(module_code):
            return False
        if self.is_superuser or self.role == 'OWNER':
            return True
        if self.profile_role:
            return module_code in (self.profile_role.allowed_modules or [])
        if self.role == 'ADMIN':
            return True
        elif self.role == 'PROFESSIONAL':
            return module_code in ['agenda', 'commissions', 'crm']
        elif self.role == 'RECEPTIONIST':
            return module_code in ['agenda', 'crm', 'pos']
        return False

    def has_perm_flag(self, flag_name):
        if self.is_superuser or self.role == 'OWNER':
            return True
        if self.profile_role:
            return getattr(self.profile_role, flag_name, False)
        if self.role == 'ADMIN':
            return True
        elif self.role == 'PROFESSIONAL':
            if flag_name in ['scope_appointments', 'scope_commissions']:
                return 'OWN'
            return False
        elif self.role == 'RECEPTIONIST':
            if flag_name in ['can_charge_pos', 'can_manage_clients']:
                return True
            return False
        return False

    @property
    def appointment_scope(self):
        if self.is_superuser or (self.role in ['OWNER', 'ADMIN'] and not self.profile_role):
            return 'ALL'
        if self.profile_role:
            return self.profile_role.scope_appointments
        if self.role == 'PROFESSIONAL':
            return 'OWN'
        return 'ALL'

    @property
    def commission_scope(self):
        if self.is_superuser or (self.role in ['OWNER', 'ADMIN'] and not self.profile_role):
            return 'ALL'
        if self.profile_role:
            return self.profile_role.scope_commissions
        if self.role == 'PROFESSIONAL':
            return 'OWN'
        if self.role == 'RECEPTIONIST':
            return 'NONE'
        return 'ALL'

    @property
    def is_restricted_professional(self):
        return self.appointment_scope == 'OWN' or self.role == 'PROFESSIONAL'

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
    profile_picture = models.ImageField(upload_to='staff/profiles/', blank=True, null=True, verbose_name="Foto de Perfil")

    def save(self, *args, **kwargs):
        from apps.core.utils_image import process_image_to_webp
        
        if self.pk:
            try:
                old_instance = StaffMember.objects.get(pk=self.pk)
                if self.profile_picture and hasattr(self.profile_picture, 'file') and getattr(old_instance.profile_picture, 'name', None) != self.profile_picture.name:
                    process_image_to_webp(self.profile_picture, max_size=(512, 512))
            except StaffMember.DoesNotExist:
                pass
        else:
            if self.profile_picture and hasattr(self.profile_picture, 'file'):
                process_image_to_webp(self.profile_picture, max_size=(512, 512))

        super().save(*args, **kwargs)

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
