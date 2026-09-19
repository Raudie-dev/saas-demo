import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.text import slugify
from apps.business.models import Business, Branch, StaffMember, WorkSchedule, PaymentMethodConfig, User
from apps.core.utils import parse_decimal, parse_int

def landing_view(request):
    return render(request, 'business/landing.html')

def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'business') and request.user.business and not request.user.business.onboarding_completed:
            return redirect('onboarding')
        return redirect('dashboard')

    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # Allow logging in with email or username
        user_obj = User.objects.filter(email__iexact=username_or_email).first() or User.objects.filter(username__iexact=username_or_email).first()
        
        if user_obj:
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"¡Bienvenido de nuevo, {user.first_name or user.username}!")
                if user.business and not user.business.onboarding_completed:
                    return redirect('onboarding')
                return redirect('dashboard')

        messages.error(request, "Usuario/Email o contraseña incorrectos. Por favor, verifica tus datos.")

    return render(request, 'business/login.html')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', 'OWNER')

        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            messages.error(request, "Ya existe un usuario registrado con este correo electrónico.")
            return render(request, 'business/register.html', {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
            })

        # Create User
        username = email
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role
        )

        # Create provisional Business for onboarding setup
        agency_default_name = f"Agencia {first_name}".strip() if first_name else "Mi Nueva Agencia"
        raw_slug = slugify(agency_default_name) or "agencia"
        unique_slug = f"{raw_slug}-{uuid.uuid4().hex[:4]}"

        business = Business.objects.create(
            name=agency_default_name,
            slug=unique_slug,
            email=email,
            phone=phone,
            currency="$",
            branding_color="#881337",
            business_type='MARKETING',
            primary_goal='Captar clientes y automatizar ventas',
            enabled_modules=['crm', 'agenda', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing'],
            onboarding_completed=False
        )

        # Create main branch
        Branch.objects.create(
            business=business,
            name="Sede Central",
            address="Dirección por configurar",
            phone=phone,
            is_main=True
        )

        # Create staff profile for owner
        StaffMember.objects.create(
            business=business,
            user=user,
            first_name=first_name or "Administrador",
            last_name=last_name or "Principal",
            email=email,
            phone=phone,
            role_title="Director / Administrador",
            commission_rate=Decimal("0.00"),
            is_active=True
        )

        user.business = business
        user.save()

        # Log user in & redirect to onboarding wizard
        login(request, user)
        messages.success(request, "¡Cuenta creada exitosamente! Vamos a configurar tu agencia paso a paso.")
        return redirect('onboarding')

    return render(request, 'business/register.html')

def logout_view(request):
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('login')

@login_required(login_url='login')
def onboarding_view(request):
    user = request.user
    business = getattr(user, 'business', None) or Business.objects.first()

    if not business:
        # Create a emergency business if none linked
        business = Business.objects.create(
            name=f"Agencia de {user.first_name or user.username}",
            slug=f"agencia-{user.username}-{uuid.uuid4().hex[:4]}",
            email=user.email or "contacto@agencia.com",
            phone=user.phone or "+1 555-0000",
            onboarding_completed=False
        )
        user.business = business
        user.save()

    if request.method == 'POST':
        agency_name = request.POST.get('agency_name', '').strip()
        business_type = request.POST.get('business_type', 'MARKETING')
        primary_goal = request.POST.get('primary_goal', '').strip()
        selected_modules = request.POST.getlist('enabled_modules')
        currency = request.POST.get('currency', '$')
        branding_color = request.POST.get('branding_color', '#881337')
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()

        if agency_name:
            business.name = agency_name
            raw_slug = slugify(agency_name)
            if not Business.objects.filter(slug=raw_slug).exclude(id=business.id).exists():
                business.slug = raw_slug
            else:
                business.slug = f"{raw_slug}-{uuid.uuid4().hex[:4]}"

        business.business_type = business_type
        business.primary_goal = primary_goal or "Gestionar y hacer crecer la agencia"
        business.enabled_modules = selected_modules if selected_modules else ['crm', 'agenda', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing']
        business.currency = currency
        business.branding_color = branding_color
        if phone:
            business.phone = phone
        if address:
            business.address = address
        business.onboarding_completed = True
        business.save()

        # Ensure main branch is updated
        main_branch = Branch.objects.filter(business=business, is_main=True).first()
        if main_branch:
            main_branch.address = address or "Sede Principal"
            main_branch.phone = phone or business.phone
            main_branch.save()
        else:
            Branch.objects.create(
                business=business,
                name="Sede Principal",
                address=address or "Dirección Principal",
                phone=phone or business.phone,
                is_main=True
            )

        messages.success(request, f"¡Configuración de {business.name} guardada con éxito! Tu panel ya está personalizado para tu tipo de negocio.")
        return redirect('dashboard')

    # Available business profiles & recommended modules
    agency_profiles = [
        {
            'code': 'MARKETING',
            'title': 'Agencia Digital & Marketing',
            'icon': 'sparkles',
            'desc': 'Especializada en captación de leads, servicios recurrentes, campañas, facturación y automatización con IA.',
            'modules': ['crm', 'invoicing', 'marketing', 'ai_engine', 'commissions', 'agenda']
        },
        {
            'code': 'REAL_ESTATE',
            'title': 'Agencia Inmobiliaria / Bienes Raíces',
            'icon': 'home',
            'desc': 'Gestión de clientes interesados, agenda de visitas, contratos, comisión de agentes e inventario de propiedades.',
            'modules': ['crm', 'agenda', 'commissions', 'invoicing', 'ai_engine']
        },
        {
            'code': 'TRAVEL',
            'title': 'Agencia de Viajes & Turismo',
            'icon': 'plane',
            'desc': 'Reservas de paquetes, agenda de itinerarios, venta POS, facturación y comisión de asesores de viaje.',
            'modules': ['crm', 'booking', 'agenda', 'pos', 'invoicing', 'commissions']
        },
        {
            'code': 'CONSULTING',
            'title': 'Agencia de Consultoría & Servicios',
            'icon': 'briefcase',
            'desc': 'Agenda de reuniones, reservas en línea, propuestas, seguimiento de clientes y facturación rápida.',
            'modules': ['crm', 'agenda', 'booking', 'invoicing', 'ai_engine']
        },
        {
            'code': 'HEALTH_BEAUTY',
            'title': 'Salud, Estética & Spa',
            'icon': 'heart-pulse',
            'desc': 'Citas de pacientes/clientes, portal de reservas 24/7, productos en stock, comisiones y caja registradora POS.',
            'modules': ['agenda', 'booking', 'pos', 'inventory', 'commissions', 'crm']
        },
        {
            'code': 'RETAIL_OTHER',
            'title': 'Comercio, Retail & Servicios Generales',
            'icon': 'shopping-bag',
            'desc': 'Punto de venta directo, control de inventario de productos, facturación, clientes y reportes financieros.',
            'modules': ['pos', 'inventory', 'invoicing', 'crm', 'commissions', 'analytics']
        }
    ]

    all_modules = [
        {'code': 'crm', 'name': 'CRM & Clientes', 'icon': 'users', 'desc': 'Seguimiento de prospectos, clientes VIP e historial completo'},
        {'code': 'agenda', 'name': 'Agenda & Citas', 'icon': 'calendar', 'desc': 'Programación de citas y control de horarios de colaboradores'},
        {'code': 'booking', 'name': 'Reservas Públicas 24/7', 'icon': 'globe', 'desc': 'Portal web para que tus clientes agenden solos'},
        {'code': 'invoicing', 'name': 'Facturación & Gastos', 'icon': 'file-text', 'desc': 'Emisión de comprobantes, cuentas por cobrar y control de gastos'},
        {'code': 'pos', 'name': 'Ventas POS & Caja', 'icon': 'shopping-bag', 'desc': 'Cobros rápidos en mostrador y apertura/cierre de caja'},
        {'code': 'inventory', 'name': 'Inventario & Stock', 'icon': 'package', 'desc': 'Control de productos, servicios y alertas de stock bajo'},
        {'code': 'commissions', 'name': 'Comisiones de Equipo', 'icon': 'dollar-sign', 'desc': 'Cálculo automático de comisiones para tu equipo'},
        {'code': 'ai_engine', 'name': 'IA & Automatización', 'icon': 'sparkles', 'desc': 'Asistente IA para generar copies, presupuestos y resúmenes'},
        {'code': 'marketing', 'name': 'Marketing & Promociones', 'icon': 'tag', 'desc': 'Campañas de email, descuentos y fidelización de clientes'},
    ]

    return render(request, 'business/onboarding.html', {
        'business': business,
        'agency_profiles': agency_profiles,
        'all_modules': all_modules,
    })

@login_required(login_url='login')
def business_config_view(request):
    business = getattr(request, 'current_business', None)
    if not business and hasattr(request.user, 'business') and request.user.business:
        business = request.user.business

    if not business:
        business = Business.objects.first()

    if request.method == 'POST' and business:
        agency_name = request.POST.get('name', '').strip()
        if agency_name:
            business.name = agency_name

        business.tax_id = request.POST.get('tax_id', business.tax_id).strip()
        business.email = request.POST.get('email', business.email).strip()
        business.phone = request.POST.get('phone', business.phone).strip()
        business.address = request.POST.get('address', business.address).strip()
        business.currency = request.POST.get('currency', business.currency).strip()
        business.branding_color = request.POST.get('branding_color', business.branding_color).strip()
        business.business_type = request.POST.get('business_type', business.business_type)
        business.primary_goal = request.POST.get('primary_goal', business.primary_goal).strip()
        
        selected_modules = request.POST.getlist('enabled_modules')
        if selected_modules:
            business.enabled_modules = selected_modules

        slug_input = request.POST.get('slug', '').strip()
        if slug_input and slug_input != business.slug:
            new_slug = slugify(slug_input)
            if not Business.objects.filter(slug=new_slug).exclude(id=business.id).exists():
                business.slug = new_slug
            else:
                messages.warning(request, "El slug ingresado ya está en uso. Se mantuvo el anterior.")

        # Update User Profile info if provided
        user_first_name = request.POST.get('user_first_name', '').strip()
        user_last_name = request.POST.get('user_last_name', '').strip()
        user_phone = request.POST.get('user_phone', '').strip()
        if user_first_name:
            request.user.first_name = user_first_name
        if user_last_name:
            request.user.last_name = user_last_name
        if user_phone:
            request.user.phone = user_phone
        request.user.save()

        business.save()
        messages.success(request, f"¡Configuración de {business.name} actualizada correctamente!")
        return redirect('business_config')

    branches = Branch.objects.filter(business=business) if business else []
    payment_methods = PaymentMethodConfig.objects.filter(business=business) if business else []

    all_modules = [
        {'code': 'crm', 'name': 'CRM & Clientes', 'icon': 'users'},
        {'code': 'agenda', 'name': 'Agenda & Citas', 'icon': 'calendar'},
        {'code': 'booking', 'name': 'Portal Reservas 24/7', 'icon': 'globe'},
        {'code': 'invoicing', 'name': 'Facturación & Gastos', 'icon': 'file-text'},
        {'code': 'pos', 'name': 'Ventas POS & Caja', 'icon': 'shopping-bag'},
        {'code': 'inventory', 'name': 'Inventario & Stock', 'icon': 'package'},
        {'code': 'commissions', 'name': 'Comisiones de Equipo', 'icon': 'dollar-sign'},
        {'code': 'ai_engine', 'name': 'IA & Automatización', 'icon': 'sparkles'},
        {'code': 'marketing', 'name': 'Marketing & Promociones', 'icon': 'tag'},
    ]

    return render(request, 'business/config.html', {
        'business': business,
        'branches': branches,
        'payment_methods': payment_methods,
        'all_modules': all_modules,
        'business_types': Business.BUSINESS_TYPE_CHOICES,
    })

def staff_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    staff_members = StaffMember.objects.filter(business=business).prefetch_related('schedules') if business else []
    
    return render(request, 'business/staff_list.html', {
        'business': business,
        'staff_members': staff_members,
    })

def staff_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    branches = Branch.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        role_title = request.POST.get('role_title', 'Especialista')
        commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        branch_id = request.POST.get('branch_id')
        branch = Branch.objects.filter(id=branch_id).first() if branch_id else None
        
        staff = StaffMember.objects.create(
            business=business,
            branch=branch,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            role_title=role_title,
            commission_rate=commission_rate,
            is_active=True
        )
        
        # Create default work schedule Mon-Sat
        for day in range(0, 6):
            WorkSchedule.objects.create(
                staff=staff,
                day_of_week=day,
                start_time="09:00",
                end_time="19:00",
                is_working_day=True
            )
            
        return redirect('staff_list')
        
    return render(request, 'business/staff_form.html', {
        'business': business,
        'staff': None,
        'branches': branches,
        'title': 'Registrar Nuevo Profesional / Empleado'
    })

def staff_edit_view(request, staff_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    staff = get_object_or_404(StaffMember, id=staff_id, business=business)
    branches = Branch.objects.filter(business=business)
    
    if request.method == 'POST':
        staff.first_name = request.POST.get('first_name')
        staff.last_name = request.POST.get('last_name')
        staff.email = request.POST.get('email', '')
        staff.phone = request.POST.get('phone', '')
        staff.role_title = request.POST.get('role_title', 'Especialista')
        staff.commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        branch_id = request.POST.get('branch_id')
        staff.branch = Branch.objects.filter(id=branch_id).first() if branch_id else None
        staff.save()
        return redirect('staff_list')
        
    return render(request, 'business/staff_form.html', {
        'business': business,
        'staff': staff,
        'branches': branches,
        'title': f'Editar Profesional: {staff.full_name}'
    })

