import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.core.models import TimeStampedModel

class Business(TimeStampedModel):
    BUSINESS_TYPE_CHOICES = [
        ('HEALTH_CLINIC', 'Clínica, Consultorio & Odontología'),
        ('AESTHETICS_SPA', 'Estética, Dermatología & Spa'),
        ('BARBER_SALON', 'Barbería, Salón & Peluquería'),
        ('KINESIOLOGY', 'Kinesiología & Fisioterapia'),
        ('RETAIL_COMMERCE', 'Comercio, Retail & Venta Directa'),
        ('SERVICES_OTHER', 'Servicios Profesionales & Otros'),
        ('HEALTH_BEAUTY', 'Salud, Estética & Spa'),
        ('RETAIL_OTHER', 'Comercio & Retail'),
        ('MARKETING', 'Servicios Digitales'),
        ('CONSULTING', 'Consultoría'),
        ('REAL_ESTATE', 'Inmobiliaria (Deshabilitado)'),
        ('TRAVEL', 'Viajes (Deshabilitado)'),
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
    pending_booking_expiry_hours = models.PositiveIntegerField(default=24, verbose_name="Horas de Espera para Confirmar Reserva Pendiente")
    default_deposit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=30.00, verbose_name="Porcentaje de Seña / Anticipo General (%)")

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"

    def __str__(self):
        return self.name

    BUSINESS_TYPE_MODULES = {
        'HEALTH_CLINIC': ['agenda', 'booking', 'crm', 'invoicing', 'pos', 'commissions'],
        'AESTHETICS_SPA': ['agenda', 'booking', 'crm', 'pos', 'inventory', 'commissions', 'marketing', 'invoicing'],
        'BARBER_SALON': ['agenda', 'booking', 'pos', 'commissions', 'inventory', 'crm'],
        'KINESIOLOGY': ['agenda', 'booking', 'crm', 'invoicing', 'commissions'],
        'RETAIL_COMMERCE': ['pos', 'inventory', 'invoicing', 'crm', 'commissions'],
        'SERVICES_OTHER': ['crm', 'agenda', 'booking', 'invoicing', 'ai_engine'],
        'HEALTH_BEAUTY': ['agenda', 'booking', 'pos', 'inventory', 'commissions', 'crm', 'marketing', 'invoicing'],
        'RETAIL_OTHER': ['pos', 'inventory', 'invoicing', 'crm', 'commissions', 'agenda', 'booking'],
        'MARKETING': ['crm', 'invoicing', 'ai_engine', 'marketing', 'booking', 'agenda', 'commissions'],
        'CONSULTING': ['crm', 'agenda', 'booking', 'invoicing', 'commissions', 'ai_engine'],
        'REAL_ESTATE': ['crm', 'invoicing', 'commissions', 'booking', 'agenda'],
        'TRAVEL': ['crm', 'agenda', 'booking', 'invoicing', 'commissions', 'pos'],
    }

    @property
    def is_real_estate(self):
        return False

    @property
    def is_marketing_agency(self):
        return self.business_type == 'MARKETING'

    @property
    def is_health_beauty(self):
        return self.business_type == 'HEALTH_BEAUTY'

    @property
    def is_consulting(self):
        return self.business_type == 'CONSULTING'

    @property
    def is_travel(self):
        return False

    @property
    def is_retail(self):
        return self.business_type == 'RETAIL_OTHER'

    @property
    def business_entity_label(self):
        labels = {
            'MARKETING': 'la Agencia',
            'REAL_ESTATE': 'la Inmobiliaria',
            'HEALTH_BEAUTY': 'la Clínica / Spa',
            'CONSULTING': 'la Consultora',
            'TRAVEL': 'la Agencia de Viajes',
            'RETAIL_OTHER': 'la Empresa',
        }
        return labels.get(self.business_type, 'la Empresa')

    @property
    def client_label_singular(self):
        if self.is_health_beauty:
            return 'Paciente'
        if self.is_travel:
            return 'Pasajero / Cliente'
        return 'Cliente'

    @property
    def client_label_plural(self):
        if self.is_health_beauty:
            return 'Pacientes'
        if self.is_travel:
            return 'Pasajeros & Clientes'
        return 'Clientes'

    def is_module_allowed_by_business_type(self, module_name):
        """Valida si un módulo es compatible con el tipo de negocio."""
        allowed_for_type = self.BUSINESS_TYPE_MODULES.get(self.business_type)
        if allowed_for_type is not None:
            return module_name in allowed_for_type
        return True

    def get_allowed_modules(self):
        """Retorna los módulos permitidos según el plan de suscripción y filtrados estrictamente por tipo de negocio."""
        sub = getattr(self, 'subscription', None)
        if sub and sub.plan and sub.plan.included_modules:
            modules = list(sub.plan.included_modules)
            modules = [m for m in modules if m not in ('properties', 'projects', 'travel')]
            return [m for m in modules if self.is_module_allowed_by_business_type(m)]
        
        # Fallback sin suscripción o plan abierto
        default_modules = self.BUSINESS_TYPE_MODULES.get(
            self.business_type,
            ['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing']
        )
        return list(default_modules)

    def is_module_allowed_by_plan(self, module_name):
        if not self.is_module_allowed_by_business_type(module_name):
            return False
        allowed = self.get_allowed_modules()
        return module_name in allowed

    def is_module_enabled(self, module_name):
        # 1. Filtro estricto por tipo de negocio
        if not self.is_module_allowed_by_business_type(module_name):
            return False
        # 2. Si el portal de reservas está desactivado globalmente para el negocio
        if module_name == 'booking' and not getattr(self, 'is_booking_enabled', True):
            return False
        # 3. Validación por plan de suscripción
        if not self.is_module_allowed_by_plan(module_name):
            return False
        # 4. Habilitación específica por el negocio
        if module_name == 'properties':
            if self.is_real_estate:
                return True
            return False
        if module_name == 'projects':
            if self.is_marketing_agency or self.is_consulting:
                return True
            return False
        if module_name == 'travel':
            if self.is_travel:
                return True
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
                if self.logo_url and getattr(old_instance.logo_url, 'name', None) != self.logo_url.name:
                    try:
                        if hasattr(self.logo_url, 'file'):
                            process_image_to_webp(self.logo_url, max_size=(512, 512))
                    except (FileNotFoundError, OSError, Exception) as e:
                        print(f"Skipping logo webp conversion: {e}")
                
                if self.banner_url and getattr(old_instance.banner_url, 'name', None) != self.banner_url.name:
                    try:
                        if hasattr(self.banner_url, 'file'):
                            process_image_to_webp(self.banner_url, max_size=(1920, 1080))
                    except (FileNotFoundError, OSError, Exception) as e:
                        print(f"Skipping banner webp conversion: {e}")
            except Business.DoesNotExist:
                pass
        else:
            if self.logo_url:
                try:
                    if hasattr(self.logo_url, 'file'):
                        process_image_to_webp(self.logo_url, max_size=(512, 512))
                except (FileNotFoundError, OSError, Exception) as e:
                    print(f"Skipping logo webp conversion: {e}")
            if self.banner_url:
                try:
                    if hasattr(self.banner_url, 'file'):
                        process_image_to_webp(self.banner_url, max_size=(1920, 1080))
                except (FileNotFoundError, OSError, Exception) as e:
                    print(f"Skipping banner webp conversion: {e}")

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
    """Crea los 3 perfiles base estándar para un negocio únicamente si no tiene ningún perfil configurado."""
    if not business:
        return []
    
    allowed_plan_modules = business.get_allowed_modules()

    # Si la empresa ya tiene perfiles creados (o el usuario los borró intencionalmente), no recrear automáticamente
    if UserProfileRole.objects.filter(business=business).exists():
        # Sincronizar el perfil Administrador del sistema para que contenga todos los módulos permitidos actuales
        admin_role = UserProfileRole.objects.filter(business=business, name='Administrador', is_system_default=True).first()
        if admin_role:
            updated_mods = list(admin_role.allowed_modules or [])
            changed = False
            for mod in allowed_plan_modules:
                if mod not in updated_mods:
                    updated_mods.append(mod)
                    changed = True
            if changed:
                admin_role.allowed_modules = updated_mods
                admin_role.save(update_fields=['allowed_modules'])
        return list(UserProfileRole.objects.filter(business=business))
    
    role1_name = 'Profesional'
    role1_desc = 'Acceso a sus citas o proyectos asignados y sus comisiones personales.'
    role1_mods = [m for m in ['agenda', 'projects', 'properties', 'travel', 'commissions', 'crm'] if m in allowed_plan_modules]
    
    role2_name = 'Recepción'
    role2_desc = 'Control de agenda, gestión de clientes y cobro en POS / Caja.'
    role2_mods = [m for m in ['agenda', 'crm', 'pos', 'booking', 'invoicing', 'travel'] if m in allowed_plan_modules]
    
    role3_name = 'Administrador'
    role3_desc = 'Acceso total a reportes, facturación, usuarios y configuración del negocio.'

    # 1. Perfil Operativo / Profesional
    UserProfileRole.objects.create(
        business=business,
        name=role1_name,
        description=role1_desc,
        is_system_default=True,
        allowed_modules=role1_mods,
        scope_appointments='OWN',
        scope_commissions='OWN',
        can_charge_pos=False,
        can_view_financial_reports=False,
        can_manage_settings=False,
        can_manage_clients=True,
        can_manage_inventory=False,
    )

    # 2. Perfil Atención / Recepción
    UserProfileRole.objects.create(
        business=business,
        name=role2_name,
        description=role2_desc,
        is_system_default=True,
        allowed_modules=role2_mods,
        scope_appointments='ALL',
        scope_commissions='NONE',
        can_charge_pos=True if 'pos' in allowed_plan_modules else False,
        can_view_financial_reports=False,
        can_manage_settings=False,
        can_manage_clients=True,
        can_manage_inventory=False,
    )

    # 3. Perfil Administrador
    UserProfileRole.objects.create(
        business=business,
        name=role3_name,
        description=role3_desc,
        is_system_default=True,
        allowed_modules=list(allowed_plan_modules),
        scope_appointments='ALL',
        scope_commissions='ALL',
        can_charge_pos=True if 'pos' in allowed_plan_modules else False,
        can_view_financial_reports=True,
        can_manage_settings=True,
        can_manage_clients=True,
        can_manage_inventory=True,
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
            return module_code in ['agenda', 'commissions', 'crm', 'projects', 'properties', 'travel']
        elif self.role == 'RECEPTIONIST':
            return module_code in ['agenda', 'crm', 'pos', 'booking', 'travel']
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
                if self.profile_picture and getattr(old_instance.profile_picture, 'name', None) != self.profile_picture.name:
                    try:
                        if hasattr(self.profile_picture, 'file'):
                            process_image_to_webp(self.profile_picture, max_size=(512, 512))
                    except (FileNotFoundError, OSError, Exception) as e:
                        print(f"Skipping staff profile webp conversion: {e}")
            except StaffMember.DoesNotExist:
                pass
        else:
            if self.profile_picture:
                try:
                    if hasattr(self.profile_picture, 'file'):
                        process_image_to_webp(self.profile_picture, max_size=(512, 512))
                except (FileNotFoundError, OSError, Exception) as e:
                    print(f"Skipping staff profile webp conversion: {e}")

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
