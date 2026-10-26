import os
import uuid
import datetime
import json
import urllib.request
import urllib.parse
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.text import slugify
from django.utils import timezone
from apps.business.models import Business, Branch, StaffMember, WorkSchedule, PaymentMethodConfig, User, UserProfileRole, WhatsAppMessageTemplate, ensure_default_profiles
from django.db.models import Count
from apps.core.utils import parse_decimal, parse_int, format_phone_with_prefix, split_phone_number

@ensure_csrf_cookie
def landing_view(request):
    if request.user.is_authenticated or request.GET.get('pwa') == '1' or request.GET.get('mode') == 'pwa':
        return redirect('dashboard')
    from apps.superadmin.models import SubscriptionPlan, Region, PlanRegionPricing
    from apps.superadmin.views import _ensure_default_plans
    _ensure_default_plans()

    regions = Region.objects.filter(is_active=True).order_by('name')
    selected_region_id = request.GET.get('region')
    
    current_region = None
    if selected_region_id:
        current_region = regions.filter(id=selected_region_id).first()
        
    if not current_region:
        country_code = request.META.get('HTTP_CF_IPCOUNTRY') or request.META.get('HTTP_X_APPENGINE_COUNTRY') or request.META.get('HTTP_X_COUNTRY_CODE')
        if country_code:
            # First try matching by code exactly
            current_region = regions.filter(code__iexact=country_code).first()
            if not current_region:
                # Try matching in country_codes field (comma separated)
                for r in regions:
                    if r.country_codes:
                        codes = [c.strip().upper() for c in r.country_codes.split(',')]
                        if country_code.upper() in codes:
                            current_region = r
                            break

    if not current_region:
        current_region = regions.filter(is_default=True).first() or regions.first()

    base_plans = SubscriptionPlan.objects.filter(is_active=True, show_on_landing=True)
    
    # Enrich plans with regional pricing
    plans = []
    for plan in base_plans:
        # Defaults
        display_monthly = plan.monthly_price
        display_annual = plan.annual_price
        currency = "$"

        if current_region:
            currency = current_region.currency_symbol
            rp = PlanRegionPricing.objects.filter(plan=plan, region=current_region).first()
            if rp:
                if not rp.is_active:
                    continue  # Plan is not active in this region
                display_monthly = rp.monthly_price
                display_annual = rp.annual_price
            
        setattr(plan, 'display_monthly', display_monthly)
        setattr(plan, 'display_annual', display_annual)
        setattr(plan, 'currency', currency)
        plans.append(plan)

    plans.sort(key=lambda x: x.display_monthly)

    return render(request, 'business/landing.html', {
        'plans': plans,
        'regions': regions,
        'current_region': current_region
    })


@ensure_csrf_cookie
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

@ensure_csrf_cookie
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        phone_prefix = request.POST.get('phone_prefix', '+54').strip()
        phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
        phone = format_phone_with_prefix(phone_prefix, phone_number)
        role = request.POST.get('role', 'OWNER')

        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            messages.error(request, "Ya existe un usuario registrado con este correo electrónico.")
            return render(request, 'business/register.html', {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone_prefix': phone_prefix,
                'phone_number': phone_number,
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
    storage = messages.get_messages(request)
    for _ in storage:
        pass
    logout(request)
    
    if request.GET.get('timeout') == '1':
        messages.warning(request, "Tu sesión ha expirado tras más de 3 horas de inactividad.")
    else:
        messages.info(request, "Has cerrado sesión correctamente.")
        
    return redirect('login')

@login_required(login_url='login')
@ensure_csrf_cookie
def onboarding_view(request):
    user = request.user
    business = getattr(user, 'business', None)
    if not business:
        business_name = f"Negocio {user.first_name or user.username}".strip()
        business = Business.objects.create(
            name=f"Negocio de {user.first_name or user.username}",
            slug=f"negocio-{user.username}-{uuid.uuid4().hex[:4]}",
            email=user.email or "contacto@negocio.com",
            phone=user.phone or "+1 555-0000",
            onboarding_completed=False
        )
        user.business = business
        user.save()

    if request.method == 'POST':
        agency_name = (request.POST.get('business_name') or request.POST.get('agency_name') or '').strip()
        business_type = request.POST.get('business_type', 'MARKETING')
        primary_goal = request.POST.get('primary_goal', '').strip()
        selected_modules = request.POST.getlist('enabled_modules')
        currency = request.POST.get('currency', '$')
        branding_color = request.POST.get('branding_color', '#881337')
        
        phone_prefix = request.POST.get('phone_prefix', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        if phone_number:
            phone = format_phone_with_prefix(phone_prefix, phone_number)
        else:
            phone = ''
        
        address = request.POST.get('address', '').strip()

        if agency_name:
            business.name = agency_name
            raw_slug = slugify(agency_name)
            if not Business.objects.filter(slug=raw_slug).exclude(id=business.id).exists():
                business.slug = raw_slug
            else:
                business.slug = f"{raw_slug}-{uuid.uuid4().hex[:4]}"

        allowed_modules = business.get_allowed_modules()
        if selected_modules:
            selected_modules = [m for m in selected_modules if m in allowed_modules]
        else:
            selected_modules = allowed_modules

        business.business_type = business_type
        
        region_id = request.POST.get('region_id')
        if region_id:
            from apps.superadmin.models import Region
            region = Region.objects.filter(id=region_id).first()
            if region:
                business.region = region

        business.primary_goal = primary_goal or "Gestionar y hacer crecer el negocio"
        if 'ai_engine' in selected_modules and 'whatsapp' not in selected_modules:
            selected_modules.append('whatsapp')
        business.enabled_modules = selected_modules
        business.currency = currency
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
    business_profiles = [
        {
            'code': 'HEALTH_CLINIC',
            'title': 'Clínicas, Consultorios & Odontología',
            'icon': 'stethoscope',
            'desc': 'Gestión de pacientes, turnos médicos, historias clínicas, facturación y recordatorios por WhatsApp.',
            'modules': ['agenda', 'booking', 'crm', 'invoicing', 'pos', 'commissions']
        },
        {
            'code': 'AESTHETICS_SPA',
            'title': 'Estética, Dermatología & Spas',
            'icon': 'sparkles',
            'desc': 'Tratamientos faciales/corporales, agenda multi-especialista, fichas con notas, stock y fidelización.',
            'modules': ['agenda', 'booking', 'crm', 'pos', 'inventory', 'commissions', 'marketing']
        },
        {
            'code': 'BARBER_SALON',
            'title': 'Barberías, Salones & Peluquerías',
            'icon': 'scissors',
            'desc': 'Turnos rápidos por sillón o estilista, caja mostrador POS, comisiones del equipo y venta de productos.',
            'modules': ['agenda', 'booking', 'pos', 'commissions', 'inventory', 'crm']
        },
        {
            'code': 'KINESIOLOGY',
            'title': 'Kinesiología & Fisioterapia',
            'icon': 'activity',
            'desc': 'Sesiones periódicas, evolución clínica, asignación de boxes o gabinetes y cobro en mostrador.',
            'modules': ['agenda', 'booking', 'crm', 'invoicing', 'commissions']
        },
        {
            'code': 'RETAIL_COMMERCE',
            'title': 'Comercio, Retail & Venta Directa',
            'icon': 'shopping-bag',
            'desc': 'Terminal de cobro POS, apertura y arqueo de caja, inventario con alertas de stock y comprobantes fiscales.',
            'modules': ['pos', 'inventory', 'invoicing', 'crm', 'commissions']
        },
        {
            'code': 'SERVICES_OTHER',
            'title': 'Servicios Profesionales & Otros',
            'icon': 'briefcase',
            'desc': 'Agenda interactiva, portal de reservas online 24/7, seguimiento de clientes, presupuestos y cobros.',
            'modules': ['crm', 'agenda', 'booking', 'invoicing', 'ai_engine']
        }
    ]
    agency_profiles = business_profiles

    # Obtain default plan modules allowed
    allowed_codes = business.get_allowed_modules() if business else ['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing']
    if hasattr(business, 'subscription') and business.subscription and business.subscription.plan:
        allowed_codes = business.get_allowed_modules()

    raw_modules = [
        {'code': 'crm', 'name': 'CRM & Clientes', 'icon': 'users', 'desc': 'Seguimiento de prospectos, clientes VIP e historial completo'},
        {'code': 'agenda', 'name': 'Agenda & Citas', 'icon': 'calendar', 'desc': 'Programación de citas y control de horarios de colaboradores'},
        {'code': 'booking', 'name': 'Reservas Públicas 24/7', 'icon': 'globe', 'desc': 'Portal web para que tus clientes agenden solos'},
        {'code': 'travel', 'name': 'Paquetes & Reservas de Viajes', 'icon': 'plane', 'desc': 'Vuelos, paquetes turísticos, expedientes de pasajeros y vouchers'},
        {'code': 'properties', 'name': 'Inmuebles & Propiedades', 'icon': 'building-2', 'desc': 'Catálogo de propiedades, ventas y alquileres inmobiliarios'},
        {'code': 'projects', 'name': 'Proyectos', 'icon': 'folder-kanban', 'desc': 'Gestión de proyectos, tareas por fases y entregables'},
        {'code': 'invoicing', 'name': 'Facturación & Gastos', 'icon': 'file-text', 'desc': 'Emisión de comprobantes, cuentas por cobrar y control de gastos'},
        {'code': 'pos', 'name': 'Ventas POS & Caja', 'icon': 'shopping-bag', 'desc': 'Cobros rápidos en mostrador y apertura/cierre de caja'},
        {'code': 'inventory', 'name': 'Inventario & Stock', 'icon': 'package', 'desc': 'Control de productos, servicios y alertas de stock bajo'},
        {'code': 'commissions', 'name': 'Comisiones de Equipo', 'icon': 'dollar-sign', 'desc': 'Cálculo automático de comisiones para tu equipo'},
        {'code': 'whatsapp', 'name': 'WhatsApp & Mensajería', 'icon': 'message-square', 'desc': 'Conexión QR, recordatorios de citas y plantillas de mensajes'},
        {'code': 'ai_engine', 'name': 'IA & Automatización', 'icon': 'sparkles', 'desc': 'Asistente IA para generar copies, presupuestos y resúmenes'},
        {'code': 'marketing', 'name': 'Marketing & Promociones', 'icon': 'tag', 'desc': 'Campañas de email, descuentos y fidelización de clientes'},
    ]

    all_modules = [m for m in raw_modules if m['code'] in allowed_codes]
    
    from apps.superadmin.models import Region
    all_regions = Region.objects.filter(is_active=True).exclude(code='GLOBAL').order_by('name')

    biz_prefix, biz_num = split_phone_number(business.phone if business else '')

    return render(request, 'business/onboarding.html', {
        'business': business,
        'business_phone_prefix': biz_prefix,
        'business_phone_number': biz_num,
        'agency_profiles': agency_profiles,
        'all_modules': all_modules,
        'all_regions': all_regions,
    })

@login_required(login_url='login')
@ensure_csrf_cookie
@login_required
@login_required(login_url='login')
def switch_branch_view(request):
    if request.method == 'POST':
        branch_id = request.POST.get('branch_id')
        business = getattr(request, 'current_business', None) or request.user.business
        if branch_id and business:
            branch = Branch.objects.filter(id=branch_id, business=business).first()
            if branch:
                request.session['active_branch_id'] = str(branch.id)
                messages.success(request, f"¡Sucursal activa cambiada a: {branch.name}!")
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer or 'dashboard')

@login_required(login_url='login')
@ensure_csrf_cookie
def business_config_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permisos para acceder a la configuración de la empresa.")
        return redirect('dashboard')

    if request.method == 'POST' and business:
        action = request.POST.get('action')

        if action == 'SAVE_BRANCH':
            branch_id = request.POST.get('branch_id')
            b_name = request.POST.get('branch_name', '').strip()
            b_address = request.POST.get('branch_address', '').strip()
            b_prefix = request.POST.get('branch_phone_prefix', '').strip()
            b_phone_raw = request.POST.get('branch_phone', '').strip()
            b_phone = format_phone_with_prefix(b_prefix, b_phone_raw) if b_phone_raw else ''
            b_maps_url = request.POST.get('google_maps_url', '').strip()
            is_main = request.POST.get('is_main') in ['on', 'true', '1']

            if b_name and b_address:
                if is_main:
                    Branch.objects.filter(business=business).update(is_main=False)

                if branch_id:
                    br = get_object_or_404(Branch, id=branch_id, business=business)
                    br.name = b_name
                    br.address = b_address
                    br.phone = b_phone
                    br.google_maps_url = b_maps_url
                    br.is_main = is_main
                    br.save()
                    if br.is_main or Branch.objects.filter(business=business).count() == 1:
                        business.address = b_address
                        business.save(update_fields=['address'])
                    messages.success(request, f"¡Sucursal '{b_name}' actualizada correctamente!")
                else:
                    br = Branch.objects.create(
                        business=business,
                        name=b_name,
                        address=b_address,
                        phone=b_phone,
                        google_maps_url=b_maps_url,
                        is_main=is_main
                    )
                    if br.is_main or Branch.objects.filter(business=business).count() == 1:
                        business.address = b_address
                        business.save(update_fields=['address'])
                    messages.success(request, f"¡Sucursal '{b_name}' creada exitosamente!")
            else:
                messages.error(request, "El nombre y dirección de la sucursal son obligatorios.")
            return redirect('business_config')

        elif action == 'DELETE_BRANCH':
            branch_id = request.POST.get('branch_id')
            if Branch.objects.filter(business=business).count() > 1:
                br = Branch.objects.filter(id=branch_id, business=business).first()
                if br:
                    name_del = br.name
                    br.delete()
                    messages.warning(request, f"Sucursal '{name_del}' eliminada.")
            else:
                messages.error(request, "No puedes eliminar la única sucursal de tu negocio.")
        elif action == 'SAVE_PAYMENT_METHODS':
            enabled_pm_ids = request.POST.getlist('enabled_payment_methods')
            # Actualizar todos los métodos de pago de la empresa
            PaymentMethodConfig.objects.filter(business=business).update(is_enabled=False)
            if enabled_pm_ids:
                PaymentMethodConfig.objects.filter(business=business, id__in=enabled_pm_ids).update(is_enabled=True)
            messages.success(request, "¡Métodos de pago preferidos guardados con éxito!")
            return redirect('business_config')

        agency_name = request.POST.get('name', '').strip()
        if agency_name:
            business.name = agency_name

        business.tax_id = request.POST.get('tax_id', business.tax_id).strip()
        business.email = request.POST.get('email', business.email).strip()
        
        phone_prefix = request.POST.get('phone_prefix', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        if phone_number:
            business.phone = format_phone_with_prefix(phone_prefix, phone_number)
        elif request.POST.get('phone'):
            business.phone = request.POST.get('phone').strip()
        import base64
        from django.core.files.base import ContentFile

        # Handle cropped logo (Base64) or direct file upload
        cropped_logo_b64 = request.POST.get('cropped_logo_base64')
        if cropped_logo_b64 and ';base64,' in cropped_logo_b64:
            try:
                format_meta, imgstr = cropped_logo_b64.split(';base64,')
                ext = format_meta.split('/')[-1] if '/' in format_meta else 'png'
                data = base64.b64decode(imgstr)
                file_name = f"{business.slug}_logo_cropped.{ext}"
                business.logo_url = ContentFile(data, name=file_name)
            except Exception as e:
                print(f"Error decoding cropped logo: {e}")
        elif 'logo_url' in request.FILES:
            business.logo_url = request.FILES['logo_url']

        # Handle cropped banner (Base64) or direct file upload
        cropped_banner_b64 = request.POST.get('cropped_banner_base64')
        if cropped_banner_b64 and ';base64,' in cropped_banner_b64:
            try:
                format_meta, imgstr = cropped_banner_b64.split(';base64,')
                ext = format_meta.split('/')[-1] if '/' in format_meta else 'png'
                data = base64.b64decode(imgstr)
                file_name = f"{business.slug}_banner_cropped.{ext}"
                business.banner_url = ContentFile(data, name=file_name)
            except Exception as e:
                print(f"Error decoding cropped banner: {e}")
        elif 'banner_url' in request.FILES:
            business.banner_url = request.FILES['banner_url']

        business.description = request.POST.get('description', business.description or '').strip() or None
        business.whatsapp_number = request.POST.get('whatsapp_number', business.whatsapp_number or '').strip() or None
            
        business.address = request.POST.get('address', business.address or '').strip()
        business.currency = request.POST.get('currency', business.currency).strip()
        business.business_type = request.POST.get('business_type', business.business_type)
        business.primary_goal = request.POST.get('primary_goal', business.primary_goal).strip()
        if 'allow_editing_client_history' in request.POST:
            business.allow_editing_client_history = (request.POST.get('allow_editing_client_history') == 'on' or request.POST.get('allow_editing_client_history') == 'true')
        
        # Guardar mensaje de recordatorio de cita y mensaje por defecto a cliente
        if 'appointment_reminder_message' in request.POST:
            business.appointment_reminder_message = request.POST.get('appointment_reminder_message').strip()
        if 'client_default_message' in request.POST:
            business.client_default_message = request.POST.get('client_default_message').strip()
        
        if request.POST.get('submitted_modules_section') == '1' or 'enabled_modules' in request.POST:
            selected_modules = request.POST.getlist('enabled_modules')
            if 'ai_engine' in selected_modules and 'whatsapp' not in selected_modules:
                selected_modules.append('whatsapp')
            allowed_modules = business.get_allowed_modules()
            business.enabled_modules = [m for m in selected_modules if m in allowed_modules and business.is_module_allowed_by_business_type(m)]

        slug_input = request.POST.get('slug', '').strip()
        if slug_input and slug_input != business.slug:
            new_slug = slugify(slug_input)
            if not Business.objects.filter(slug=new_slug).exclude(id=business.id).exists():
                business.slug = new_slug
            else:
                messages.warning(request, "El slug ingresado ya está en uso. Se mantuvo el anterior.")
                
        region_id = request.POST.get('region_id')
        if region_id:
            from apps.superadmin.models import Region
            region = Region.objects.filter(id=region_id).first()
            if region:
                business.region = region

        # Save agency working hours schedule
        primary_staff = StaffMember.objects.filter(business=business).first()
        if primary_staff:
            for day in range(7):
                is_working = request.POST.get(f'schedule_active_{day}') == 'on'
                start_time = request.POST.get(f'schedule_start_{day}', '09:00')
                end_time = request.POST.get(f'schedule_end_{day}', '19:00')
                WorkSchedule.objects.update_or_create(
                    staff=primary_staff,
                    day_of_week=day,
                    defaults={
                        'start_time': start_time,
                        'end_time': end_time,
                        'is_working_day': is_working
                    }
                )

        # Update Subscription Plan if selected
        selected_plan_id = request.POST.get('selected_plan_id')
        if selected_plan_id:
            from apps.superadmin.models import SubscriptionPlan, BusinessSubscription
            new_plan = SubscriptionPlan.objects.filter(id=selected_plan_id).first()
            if new_plan:
                sub, _ = BusinessSubscription.objects.get_or_create(
                    business=business,
                    defaults={'status': 'ACTIVE', 'expiration_date': timezone.now().date() + datetime.timedelta(days=30)}
                )
                sub.plan = new_plan
                sub.save()
                business.sync_modules_with_plan()

        business.save()

        # Sincronizar la dirección principal con la Sucursal Principal (para que el Portal refleje el cambio)
        if business.address:
            main_branch = (
                Branch.objects.filter(business=business, is_main=True).first()
                or Branch.objects.filter(business=business).first()
            )
            if main_branch and main_branch.address != business.address:
                main_branch.address = business.address
                main_branch.save(update_fields=['address'])

        messages.success(request, f"¡Configuración de {business.name} actualizada correctamente!")
        if request.POST.get('submitted_modules_section') == '1':
            return redirect(f"{request.path}?tab=modules#modules")
        return redirect('business_config')

    branches = Branch.objects.filter(business=business) if business else []
    payment_methods = PaymentMethodConfig.objects.filter(business=business) if business else []

    # Cargar Métodos de Pago de la Región para Ventas POS
    from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, RegionPaymentMethod, Region
    
    # Sincronizar automáticamente los métodos de la región en la empresa si no existen
    if business and business.region:
        region_methods = RegionPaymentMethod.objects.filter(region=business.region, is_active=True, use_for_sales=True)
        if region_methods.exists():
            for rm in region_methods:
                PaymentMethodConfig.objects.get_or_create(
                    business=business,
                    name=rm.payment_method.name,
                    defaults={
                        'is_enabled': True,
                        'instructions': rm.instructions or rm.payment_method.description or ''
                    }
                )
        payment_methods = PaymentMethodConfig.objects.filter(business=business)
    else:
        payment_methods = []

    subscription = getattr(business, 'subscription', None) if business else None
    available_plans = SubscriptionPlan.objects.filter(is_active=True)
    all_regions = Region.objects.filter(is_active=True).exclude(code='GLOBAL').order_by('name')

    # Load working hours schedule
    primary_staff = StaffMember.objects.filter(business=business).first() if business else None
    schedules = []
    days_label = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    if primary_staff:
        existing_schedules = {s.day_of_week: s for s in WorkSchedule.objects.filter(staff=primary_staff)}
        for day_code in range(7):
            sched = existing_schedules.get(day_code)
            default_start = "09:00"
            default_end = "14:00" if day_code == 5 else "19:00"
            default_active = (day_code < 6)

            start_val = default_start
            end_val = default_end
            is_active = default_active

            if sched:
                is_active = sched.is_working_day
                start_val = sched.start_time.strftime('%H:%M') if hasattr(sched.start_time, 'strftime') else str(sched.start_time)[:5]
                end_val = sched.end_time.strftime('%H:%M') if hasattr(sched.end_time, 'strftime') else str(sched.end_time)[:5]

            def to_12h(t_str):
                try:
                    parts = t_str.split(':')
                    h, m = int(parts[0]), int(parts[1])
                    ampm = 'PM' if h >= 12 else 'AM'
                    h12 = h % 12 or 12
                    return f"{h12:02d}:{m:02d} {ampm}"
                except Exception:
                    return t_str

            schedules.append({
                'day_code': day_code,
                'day_name': days_label[day_code],
                'is_working_day': is_active,
                'start_time': start_val,
                'end_time': end_val,
                'start_12h': to_12h(start_val),
                'end_12h': to_12h(end_val),
            })

    allowed_modules = business.get_allowed_modules() if business else []
    all_modules_catalog = [
        {'code': 'crm', 'name': 'CRM & Clientes', 'icon': 'users'},
        {'code': 'agenda', 'name': 'Agenda & Citas', 'icon': 'calendar'},
        {'code': 'booking', 'name': 'Portal Reservas 24/7', 'icon': 'globe'},
        {'code': 'invoicing', 'name': 'Facturación & Gastos', 'icon': 'file-text'},
        {'code': 'pos', 'name': 'Ventas POS & Caja', 'icon': 'shopping-bag'},
        {'code': 'inventory', 'name': 'Inventario & Stock', 'icon': 'package'},
        {'code': 'commissions', 'name': 'Comisiones de Equipo', 'icon': 'dollar-sign'},
        {'code': 'whatsapp', 'name': 'WhatsApp & Mensajería', 'icon': 'message-square'},
        {'code': 'ai_engine', 'name': 'IA & Automatización', 'icon': 'sparkles'},
        {'code': 'marketing', 'name': 'Marketing & Promociones', 'icon': 'tag'},
        {'code': 'projects', 'name': 'Proyectos', 'icon': 'folder-kanban'},
        {'code': 'travel', 'name': 'Paquetes & Reservas de Viajes', 'icon': 'plane'},
        {'code': 'properties', 'name': 'Cartera de Inmuebles & Propiedades', 'icon': 'building-2'},
    ]
    # Filtrar estrictamente según la matriz del tipo de negocio
    all_modules = [
        {
            'code': m['code'],
            'name': m['name'],
            'icon': m['icon'],
            'is_allowed': m['code'] in allowed_modules
        }
        for m in all_modules_catalog
        if (not business or business.is_module_allowed_by_business_type(m['code']))
    ]

    session_user = str(business.id) if business else "default"
    gw_status = {'online': False, 'status': 'offline'}
    try:
        url = f"{GATEWAY_BASE_URL}/status?user={session_user}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            gw_status = {'online': True, 'status': data.get('status', 'disconnected')}
    except Exception:
        gw_status = {'online': False, 'status': 'offline'}

    biz_prefix, biz_num = split_phone_number(business.phone if business else '')

    return render(request, 'business/config_company.html', {
        'business': business,
        'business_phone_prefix': biz_prefix,
        'business_phone_number': biz_num,
        'branches': branches,
        'payment_methods': payment_methods,
        'all_modules': all_modules,
        'schedules': schedules,
        'subscription': subscription,
        'available_plans': available_plans,
        'business_types': Business.BUSINESS_TYPE_CHOICES,
        'time_format_choices': getattr(Business, 'TIME_FORMAT_CHOICES', [('12h', '12 Horas'), ('24h', '24 Horas')]),
        'gw_status': gw_status,
        'all_regions': all_regions,
    })

@login_required(login_url='login')
@ensure_csrf_cookie
def user_profile_config_view(request):
    business = getattr(request, 'current_business', None) or request.user.business

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CHANGE_PASSWORD':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not request.user.check_password(old_password):
                messages.error(request, "La contraseña actual no es correcta.")
            elif new_password != confirm_password:
                messages.error(request, "Las nuevas contraseñas no coinciden.")
            elif len(new_password) < 6:
                messages.error(request, "La nueva contraseña debe tener al menos 6 caracteres.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, "¡Tu contraseña se ha actualizado correctamente!")
            return redirect('user_profile_config')

        elif action == 'UPDATE_PROFILE':
            user_first_name = request.POST.get('user_first_name', '').strip()
            user_last_name = request.POST.get('user_last_name', '').strip()
            user_phone_prefix = request.POST.get('user_phone_prefix', '').strip()
            user_phone_number = request.POST.get('user_phone_number', '').strip() or request.POST.get('user_phone', '').strip()
            if user_first_name:
                request.user.first_name = user_first_name
            if user_last_name:
                request.user.last_name = user_last_name
            if user_phone_number:
                request.user.phone = format_phone_with_prefix(user_phone_prefix, user_phone_number)
            request.user.save()
            messages.success(request, "¡Información de tu perfil actualizada correctamente!")
            return redirect('user_profile_config')

        elif action == 'REQUEST_PLAN_CHANGE':
            if not request.user.has_perm_flag('can_manage_settings'):
                messages.error(request, "No tienes permiso para solicitar cambios de plan de la empresa.")
                return redirect('user_profile_config')

            plan_id = request.POST.get('plan_id')
            from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, SystemAuditLog
            target_plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
            if target_plan and business:
                sub, _ = BusinessSubscription.objects.get_or_create(
                    business=business,
                    defaults={'status': 'TRIAL', 'start_date': timezone.now().date(), 'expiration_date': timezone.now().date() + datetime.timedelta(days=14)}
                )
                sub.pending_plan = target_plan
                sub.save()

                SystemAuditLog.objects.create(
                    actor_email=request.user.email or request.user.username,
                    action="SOLICITUD_CAMBIO_PLAN",
                    details=f"La agencia '{business.name}' solicitó cambiar al plan '{target_plan.name}'."
                )
                messages.success(request, f"¡Solicitud enviada! Has solicitado el cambio al plan '{target_plan.name}'. Un administrador revisará y aprobará tu cambio de plan a la brevedad.")
            else:
                messages.error(request, "No se pudo procesar la solicitud de cambio de plan.")
            return redirect('user_profile_config')

        elif action == 'REPORT_PAYMENT':
            if not request.user.has_perm_flag('can_manage_settings'):
                messages.error(request, "No tienes permiso para reportar pagos de suscripción de la empresa.")
                return redirect('user_profile_config')

            from apps.superadmin.models import RegionPaymentMethod, SubscriptionPayment, SubscriptionPlan, SystemAuditLog
            amount = request.POST.get('amount')
            reference = request.POST.get('reference', '').strip()
            rpm_id = request.POST.get('region_payment_method_id')
            plan_id = request.POST.get('plan_id')
            billing_cycle = request.POST.get('billing_cycle', 'MONTHLY')
            receipt_file = request.FILES.get('receipt_file')
            notes = request.POST.get('notes', '').strip()
            
            rpm = RegionPaymentMethod.objects.filter(id=rpm_id).first()
            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            
            if business and amount and rpm:
                SubscriptionPayment.objects.create(
                    business=business,
                    plan=plan,
                    region_payment_method=rpm,
                    billing_cycle=billing_cycle,
                    amount=amount,
                    reference=reference,
                    receipt_file=receipt_file,
                    notes=notes
                )
                SystemAuditLog.objects.create(
                    actor_email=request.user.email or request.user.username,
                    action="PAGO_REPORTADO",
                    details=f"La agencia '{business.name}' informó un pago de {amount} mediante {rpm.payment_method.name} ({billing_cycle})."
                )
                messages.success(request, "¡Tu pago ha sido informado con éxito! Un administrador lo revisará pronto para actualizar tu suscripción.")
            else:
                messages.error(request, "Error al informar el pago. Verifica los datos.")
            return redirect('subscription_billing')

    from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, RegionPaymentMethod, PlanRegionPricing
    subscription = getattr(business, 'subscription', None) if business else None
    base_plans = SubscriptionPlan.objects.filter(is_active=True)
    
    available_plans = []
    for plan in base_plans:
        display_monthly = plan.monthly_price
        display_annual = plan.annual_price
        currency = "$"

        if business and business.region:
            currency = business.region.currency_symbol
            rp = PlanRegionPricing.objects.filter(plan=plan, region=business.region).first()
            if rp:
                if not rp.is_active:
                    continue
                display_monthly = rp.monthly_price
                display_annual = rp.annual_price
        
        setattr(plan, 'display_monthly', display_monthly)
        setattr(plan, 'display_annual', display_annual)
        setattr(plan, 'currency', currency)
        available_plans.append(plan)

    available_plans.sort(key=lambda x: x.display_monthly)
    
    billing_methods = []
    if business and business.region:
        billing_methods = RegionPaymentMethod.objects.filter(region=business.region, is_active=True, use_for_billing=True)

    default_prefix, _ = split_phone_number(business.phone if business else '')
    user_prefix, user_num = split_phone_number(request.user.phone, default_prefix=default_prefix)

    return render(request, 'business/config_user.html', {
        'business': business,
        'subscription': subscription,
        'available_plans': available_plans,
        'billing_methods': billing_methods,
        'default_phone_prefix': default_prefix,
        'user_phone_prefix': user_prefix,
        'user_phone_number': user_num,
    })

@login_required(login_url='login')
@ensure_csrf_cookie
def subscription_billing_view(request):
    """
    Vista dedicada para la gestión y pago de suscripción adaptada a los
    métodos de pago e importes de la región asignada a la empresa.
    """
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para acceder a la facturación y suscripción del negocio.")
        return redirect('business_config')

    from apps.superadmin.models import (
        SubscriptionPlan, BusinessSubscription, RegionPaymentMethod, 
        PlanRegionPricing, Region, SubscriptionPayment, SystemAuditLog
    )
    from apps.superadmin.views import _ensure_default_plans
    _ensure_default_plans()

    current_region = business.region
    if not current_region:
        current_region = Region.objects.filter(is_default=True).first() or Region.objects.first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'UPDATE_REGION':
            region_id = request.POST.get('region_id')
            if region_id:
                new_region = Region.objects.filter(id=region_id, is_active=True).first()
                if new_region:
                    business.region = new_region
                    business.save()
                    SystemAuditLog.objects.create(
                        actor_email=request.user.email or request.user.username,
                        action="CAMBIO_REGION_EMPRESA",
                        details=f"La agencia '{business.name}' actualizó su región de facturación a '{new_region.name}'."
                    )
                    messages.success(request, f"¡Región actualizada a {new_region.name}! Ahora se muestran los métodos y moneda correspondientes ({new_region.currency_symbol}).")
            return redirect('subscription_billing')

        elif action == 'REQUEST_PLAN_CHANGE':
            plan_id = request.POST.get('plan_id')
            target_plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
            if target_plan:
                sub, _ = BusinessSubscription.objects.get_or_create(
                    business=business,
                    defaults={'status': 'TRIAL', 'start_date': timezone.now().date(), 'expiration_date': timezone.now().date() + datetime.timedelta(days=14)}
                )
                sub.pending_plan = target_plan
                sub.save()

                SystemAuditLog.objects.create(
                    actor_email=request.user.email or request.user.username,
                    action="SOLICITUD_CAMBIO_PLAN",
                    details=f"La agencia '{business.name}' solicitó cambiar al plan '{target_plan.name}'."
                )
                messages.success(request, f"¡Solicitud enviada! Has solicitado el plan '{target_plan.name}'. Un administrador la revisará a la brevedad.")
            return redirect('subscription_billing')

        elif action == 'REPORT_PAYMENT':
            from apps.superadmin.regional_payment_registry import get_payment_method_by_code
            amount = request.POST.get('amount')
            reference = request.POST.get('reference', '').strip()
            rpm_id = request.POST.get('region_payment_method_id')
            plan_id = request.POST.get('plan_id')
            billing_cycle = request.POST.get('billing_cycle', 'MONTHLY')
            receipt_file = request.FILES.get('receipt_file')
            user_notes = request.POST.get('notes', '').strip()

            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            selected_method = get_payment_method_by_code(rpm_id, current_region)

            rpm = None
            try:
                rpm = RegionPaymentMethod.objects.filter(id=rpm_id).first()
            except Exception:
                rpm = None

            if not rpm and selected_method:
                rpm = RegionPaymentMethod.objects.filter(
                    region=current_region,
                    payment_method__code=selected_method.code
                ).first()

            method_name = selected_method.name if selected_method else (rpm.payment_method.name if rpm else "Transferencia / Alias")
            payment_notes = f"Método: {method_name}"
            if user_notes:
                payment_notes = f"{payment_notes}\n{user_notes}"

            if amount and (selected_method or rpm):
                payment = SubscriptionPayment.objects.create(
                    business=business,
                    plan=plan,
                    region_payment_method=rpm,
                    billing_cycle=billing_cycle,
                    amount=amount,
                    reference=reference,
                    receipt_file=receipt_file,
                    status='PENDING',
                    notes=payment_notes
                )
                SystemAuditLog.objects.create(
                    actor_email=request.user.email or request.user.username,
                    action="PAGO_REPORTADO",
                    details=f"La agencia '{business.name}' informó un pago de {amount} mediante {method_name} ({billing_cycle}). Estado: Pendiente de revisión."
                )
                curr_sym = current_region.currency_symbol if current_region else "$"
                messages.success(
                    request,
                    f"¡Pago de {curr_sym}{amount} ({method_name}) informado con éxito! "
                    "Ha quedado en estado PENDIENTE. Un administrador verificará tu comprobante y confirmará el pago para activar o extender tu suscripción."
                )
            else:
                messages.error(request, "Por favor completa el método de pago y el importe para informar el pago.")
            return redirect('subscription_billing')

        elif action == 'PAY_GATEWAY':
            from apps.superadmin import payment_gateways as gateways
            from apps.superadmin.regional_payment_registry import get_payment_method_by_code
            plan_id = request.POST.get('plan_id')
            billing_cycle = 'ANNUAL' if request.POST.get('billing_cycle') == 'ANNUAL' else 'MONTHLY'
            plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
            if not plan:
                messages.error(request, "Selecciona un plan válido para pagar.")
                return redirect('subscription_billing')

            target_code = request.POST.get('region_payment_method_id') or 'MERCADOPAGO'
            code_method = get_payment_method_by_code(target_code, business.region)
            provider = code_method.provider if code_method else target_code

            rpm = None
            try:
                rpm = RegionPaymentMethod.objects.filter(id=target_code).select_related('payment_method').first()
                if rpm and rpm.payment_method.provider:
                    provider = rpm.payment_method.provider
            except Exception:
                rpm = None

            if not rpm and provider:
                rpm = RegionPaymentMethod.objects.filter(
                    region=business.region,
                    payment_method__provider=provider
                ).select_related('payment_method').first()

            if not provider or not gateways.is_available(provider, business.region):
                messages.error(request, "Este método de pago no está disponible en tu región.")
                return redirect('subscription_billing')

            amount = plan.annual_price if billing_cycle == 'ANNUAL' else plan.monthly_price
            rp = PlanRegionPricing.objects.filter(plan=plan, region=business.region, is_active=True).first()
            if rp:
                amount = rp.annual_price if billing_cycle == 'ANNUAL' else rp.monthly_price

            try:
                redirect_url = gateways.start(
                    provider, request=request, business=business, plan=plan,
                    billing_cycle=billing_cycle, amount=amount, rpm=rpm,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Error iniciando pasarela %s", provider)
                messages.error(request, f"No se pudo iniciar el pago con {code_method.name if code_method else provider}. Intenta nuevamente.")
                return redirect('subscription_billing')

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="PAGO_PASARELA_INICIADO",
                details=f"La agencia '{business.name}' inició un pago de {amount} ({billing_cycle}) vía {code_method.name if code_method else provider}.",
            )
            return redirect(redirect_url)

        elif action == 'CANCEL_RECURRING':
            from apps.superadmin import mercadopago as mp
            sub = BusinessSubscription.objects.filter(business=business).first()
            if sub and sub.has_active_recurring:
                try:
                    if sub.gateway_provider == 'MERCADOPAGO_SUBSCRIPTION':
                        mp.cancel_subscription(sub)
                    SystemAuditLog.objects.create(
                        actor_email=request.user.email or request.user.username,
                        action="DEBITO_AUTOMATICO_CANCELADO",
                        details=f"La agencia '{business.name}' canceló su débito automático ({sub.gateway_subscription_id}).",
                    )
                    messages.success(request, "Débito automático cancelado. Tu licencia sigue vigente hasta su fecha de vencimiento.")
                except mp.MercadoPagoError:
                    messages.error(request, "No se pudo cancelar el débito automático. Intenta nuevamente.")
            return redirect('subscription_billing')

    subscription, _ = BusinessSubscription.objects.get_or_create(
        business=business,
        defaults={
            'status': 'TRIAL',
            'start_date': timezone.now().date(),
            'expiration_date': timezone.now().date() + datetime.timedelta(days=14)
        }
    )

    current_region = business.region
    if not current_region:
        current_region = Region.objects.filter(is_default=True).first() or Region.objects.first()

    all_regions = Region.objects.filter(is_active=True).exclude(code='GLOBAL').order_by('name')

    base_plans = SubscriptionPlan.objects.filter(is_active=True)
    available_plans = []
    currency_symbol = current_region.currency_symbol if current_region else "$"

    current_plan_display_monthly = subscription.plan.monthly_price if subscription.plan else Decimal('0.00')
    for plan in base_plans:
        display_monthly = plan.monthly_price
        display_annual = plan.annual_price

        if current_region:
            rp = PlanRegionPricing.objects.filter(plan=plan, region=current_region).first()
            if rp:
                if not rp.is_active:
                    continue
                display_monthly = rp.monthly_price
                display_annual = rp.annual_price

        if subscription.plan and plan.id == subscription.plan.id:
            current_plan_display_monthly = display_monthly

        setattr(plan, 'display_monthly', display_monthly)
        setattr(plan, 'display_annual', display_annual)
        setattr(plan, 'currency', currency_symbol)

        try:
            full_year = display_monthly * 12
            if full_year > display_annual and full_year > 0:
                savings_pct = int(round((1 - (display_annual / full_year)) * 100))
            else:
                savings_pct = 0
        except Exception:
            savings_pct = 0
        setattr(plan, 'savings_pct', savings_pct)

        available_plans.append(plan)

    available_plans.sort(key=lambda x: x.display_monthly)

    from apps.superadmin.regional_payment_registry import normalize_region_key
    from apps.superadmin.bcv_service import get_bcv_info

    is_venezuela = (normalize_region_key(current_region) == 'VE')
    bcv_info = None

    if is_venezuela:
        try:
            from decimal import ROUND_HALF_UP
            bcv_info = get_bcv_info()
            rate = bcv_info['rate']
            for plan in available_plans:
                bs_m = (plan.display_monthly * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                bs_a = (plan.display_annual * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                setattr(plan, 'bs_monthly', bs_m)
                setattr(plan, 'bs_annual', bs_a)
                setattr(plan, 'bs_monthly_formatted', f"{bs_m:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                setattr(plan, 'bs_annual_formatted', f"{bs_a:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("No se pudo obtener la tasa BCV: %s", e)

    # Auto-sincronizar pagos pendientes de Mercado Pago
    try:
        from apps.superadmin import mercadopago as mp
        mp.sync_pending_payments_for_business(business)
    except Exception:
        pass

    payment_history = SubscriptionPayment.objects.filter(business=business).select_related(
        'plan', 'region_payment_method', 'region_payment_method__payment_method'
    ).order_by('-created_at')[:20]

    current_users_count = business.users.count()
    current_branches_count = business.branches.count()

    from apps.superadmin.regional_payment_registry import get_regional_payment_methods
    from apps.superadmin.payment_gateways import is_available, get_provider

    # Los métodos de cobro de suscripción se obtienen del registro centralizado por código según la región
    regional_code_methods = get_regional_payment_methods(current_region)
    gateway_methods, manual_methods = [], []
    for rm in regional_code_methods:
        if rm.type == 'GATEWAY':
            provider = rm.provider or 'MERCADOPAGO'
            if is_available(provider, current_region):
                rm.gateway = get_provider(provider) or rm.gateway
                gateway_methods.append(rm)
        else:
            manual_methods.append(rm)

    return render(request, 'business/subscription_billing.html', {
        'business': business,
        'subscription': subscription,
        'current_region': current_region,
        'all_regions': all_regions,
        'currency_symbol': currency_symbol,
        'available_plans': available_plans,
        'current_plan_display_monthly': current_plan_display_monthly,
        'billing_methods': manual_methods,
        'gateway_methods': gateway_methods,
        'payment_history': payment_history,
        'current_users_count': current_users_count,
        'current_branches_count': current_branches_count,
        'is_venezuela': is_venezuela,
        'bcv_info': bcv_info,
    })


@login_required(login_url='login')
def mercadopago_return_view(request):
    """Retorno del usuario desde Mercado Pago. Verifica el estado contra la API de MP."""
    from apps.superadmin import mercadopago as mp
    business = getattr(request, 'current_business', None) or request.user.business
    region = getattr(business, 'region', None)

    # Retorno de suscripción (débito automático)
    preapproval_id = request.GET.get('preapproval_id')
    if request.GET.get('type') == 'subscription' or preapproval_id:
        status = None
        if preapproval_id:
            try:
                sub = mp.sync_preapproval(preapproval_id, region)
                if sub and sub.business_id == getattr(business, 'id', None):
                    status = sub.recurring_status
            except mp.MercadoPagoError:
                pass
        if status == 'authorized':
            messages.success(request, "¡Débito automático activado! La licencia se renovará con cada cobro aprobado.")
        elif status == 'cancelled':
            messages.error(request, "La suscripción con débito automático no se completó.")
        else:
            messages.info(request, "Estamos esperando la confirmación de Mercado Pago. Tu licencia se actualizará automáticamente.")
        return redirect('subscription_billing')

    # Retorno de Checkout Pro (pago único)
    mp_payment_id = request.GET.get('payment_id') or request.GET.get('collection_id')
    status = request.GET.get('status') or request.GET.get('collection_status')
    if mp_payment_id and mp_payment_id != 'null':
        try:
            payment = mp.sync_payment_from_mp(mp_payment_id, region)
            if payment and payment.business_id == getattr(business, 'id', None):
                status = payment.mp_status or status
        except mp.MercadoPagoError:
            pass

    if status == 'approved':
        messages.success(request, "¡Pago aprobado por Mercado Pago! Tu suscripción fue renovada automáticamente.")
    elif status in ('pending', 'in_process'):
        messages.info(request, "Tu pago está pendiente de acreditación en Mercado Pago. Se activará automáticamente al confirmarse.")
    else:
        messages.error(request, "El pago no se completó en Mercado Pago. Puedes intentarlo nuevamente.")
    return redirect('subscription_billing')


@csrf_exempt
@require_POST
def mercadopago_webhook_view(request):
    """
    Webhook de notificaciones de Mercado Pago. Siempre consulta el recurso en la API
    (fuente de verdad), por lo que no se confía en el contenido de la notificación.
    `?region=XX` indica qué credenciales usar.
    """
    from django.http import HttpResponse
    from apps.superadmin import mercadopago as mp

    region = request.GET.get('region') or None
    topic = request.GET.get('type') or request.GET.get('topic')
    resource_id = request.GET.get('data.id') or request.GET.get('id')
    try:
        body = json.loads(request.body or b'{}')
        topic = body.get('type') or body.get('topic') or topic
        resource_id = (body.get('data') or {}).get('id') or resource_id
    except (ValueError, AttributeError):
        pass

    if not resource_id:
        return HttpResponse(status=200)
    try:
        if topic == 'payment':
            mp.sync_payment_from_mp(resource_id, region)
        elif topic in ('subscription_preapproval', 'preapproval'):
            mp.sync_preapproval(resource_id, region)
        elif topic in ('subscription_authorized_payment', 'authorized_payment'):
            mp.sync_authorized_payment(resource_id, region)
    except mp.MercadoPagoError:
        return HttpResponse(status=500)  # MP reintentará
    return HttpResponse(status=200)


@login_required(login_url='login')
def subscription_receipt_view(request, payment_id):
    """Comprobante oficial de suscripción para el cliente / agencia."""
    from apps.superadmin.models import SubscriptionPayment
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    payment = get_object_or_404(
        SubscriptionPayment.objects.select_related(
            'business', 'business__region', 'business__subscription',
            'plan', 'region_payment_method', 'region_payment_method__payment_method',
            'reviewed_by'
        ),
        id=payment_id
    )

    # Validar que pertenezca a la empresa del usuario logueado o que sea superadmin
    if not business or payment.business_id != business.id:
        from apps.superadmin.views import get_current_superadmin
        if not get_current_superadmin(request):
            messages.error(request, "No tienes permiso para ver este comprobante.")
            return redirect('subscription_billing')

    return render(request, 'superadmin/subscription_receipt.html', {
        'payment': payment,
        'business': payment.business,
        'is_superadmin': False,
    })

@login_required
def staff_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff_members = StaffMember.objects.filter(business=business).prefetch_related('schedules', 'services').order_by('first_name') if business else []
    
    from django.core.paginator import Paginator
    paginator = Paginator(staff_members, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'business/staff_list.html', {
        'business': business,
        'staff_members': page_obj,
        'page_obj': page_obj,
    })

@login_required
def staff_create_view(request):
    from apps.agenda.models import Service
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    branches = Branch.objects.filter(business=business) if business else []
    services = Service.objects.filter(business=business, is_active=True).select_related('category').order_by('name') if business else []
    
    default_prefix, _ = split_phone_number(business.phone if business else '')

    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email', '')
        phone_prefix = request.POST.get('phone_prefix', default_prefix).strip()
        phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
        phone = format_phone_with_prefix(phone_prefix, phone_number, default_prefix=default_prefix)
        role_title = request.POST.get('role_title', 'Especialista')
        commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        base_salary = parse_decimal(request.POST.get('base_salary'), '0.00')
        branch_id = request.POST.get('branch_id')
        branch_ids = request.POST.getlist('branch_ids')
        service_ids = request.POST.getlist('service_ids')
        branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
        
        is_active_val = request.POST.get('is_active', '1') == '1'
        staff = StaffMember.objects.create(
            business=business,
            branch=branch,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            role_title=role_title,
            commission_rate=commission_rate,
            base_salary=base_salary,
            is_active=is_active_val
        )
        if 'profile_picture' in request.FILES:
            staff.profile_picture = request.FILES['profile_picture']
            staff.save()

        if branch_ids:
            selected_branches = Branch.objects.filter(id__in=branch_ids, business=business)
            staff.branches.set(selected_branches)
            if not staff.branch and selected_branches.exists():
                staff.branch = selected_branches.first()
                staff.save()
        elif branch:
            staff.branches.set([branch])

        if service_ids:
            selected_services = Service.objects.filter(id__in=service_ids, business=business)
            staff.services.set(selected_services)
        
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
        'services': services,
        'default_phone_prefix': default_prefix,
        'staff_phone_prefix': default_prefix,
        'staff_phone_number': '',
        'title': 'Registrar Nuevo Profesional / Empleado'
    })

@login_required
def staff_edit_view(request, staff_id):
    from apps.agenda.models import Service
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff = get_object_or_404(StaffMember, id=staff_id, business=business)
    branches = Branch.objects.filter(business=business)
    services = Service.objects.filter(business=business, is_active=True).select_related('category').order_by('name')
    default_prefix, _ = split_phone_number(business.phone if business else '')

    if request.method == 'POST':
        staff.first_name = request.POST.get('first_name')
        staff.last_name = request.POST.get('last_name')
        staff.email = request.POST.get('email', '')
        phone_prefix = request.POST.get('phone_prefix', default_prefix).strip()
        phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
        staff.phone = format_phone_with_prefix(phone_prefix, phone_number, default_prefix=default_prefix)
        staff.role_title = request.POST.get('role_title', 'Especialista')
        staff.commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        staff.base_salary = parse_decimal(request.POST.get('base_salary'), '0.00')
        branch_id = request.POST.get('branch_id')
        branch_ids = request.POST.getlist('branch_ids')
        service_ids = request.POST.getlist('service_ids')
        staff.branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
        
        staff.is_active = (request.POST.get('is_active') == '1')

        if 'profile_picture' in request.FILES:
            staff.profile_picture = request.FILES['profile_picture']
            
        staff.save()

        if branch_ids:
            selected_branches = Branch.objects.filter(id__in=branch_ids, business=business)
            staff.branches.set(selected_branches)
            if not staff.branch and selected_branches.exists():
                staff.branch = selected_branches.first()
                staff.save()
        elif staff.branch:
            staff.branches.set([staff.branch])

        selected_services = Service.objects.filter(id__in=service_ids, business=business)
        staff.services.set(selected_services)

        return redirect('staff_list')
        
    staff_prefix, staff_num = split_phone_number(staff.phone, default_prefix=default_prefix)

    return render(request, 'business/staff_form.html', {
        'business': business,
        'staff': staff,
        'branches': branches,
        'services': services,
        'default_phone_prefix': default_prefix,
        'staff_phone_prefix': staff_prefix,
        'staff_phone_number': staff_num,
        'title': f'Editar Profesional: {staff.full_name}'
    })

@login_required
def staff_delete_view(request, staff_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para gestionar el equipo.")
        return redirect('dashboard')

    staff = get_object_or_404(StaffMember, id=staff_id, business=business)

    if request.method == 'POST':
        staff_name = staff.full_name
        if staff.user and staff.user.role == 'OWNER':
            messages.error(request, "No se puede eliminar el perfil asignado al propietario de la empresa.")
            return redirect('staff_list')

        force_delete = request.POST.get('force_delete') == '1'
        has_history = staff.appointments.exists() or staff.sales.exists() or staff.payroll_settlements.exists()

        if force_delete or not has_history:
            if staff.user:
                staff.user.staff_profile = None
                staff.user.save()
            staff.delete()
            messages.success(request, f"Profesional '{staff_name}' eliminado completamente del sistema.")
        else:
            staff.is_active = False
            if staff.user:
                staff.user = None
            staff.save()
            messages.success(request, f"Profesional '{staff_name}' desactivado. Ya no aparecerá en selectores, agenda ni turnos.")

    return redirect('staff_list')

# ==============================================================================
# WHATSAPP GATEWAY API PROXY VIEWS (Node.js microservice integration)
# ==============================================================================

GATEWAY_BASE_URL = getattr(settings, 'WHATSAPP_GATEWAY_URL', None) or os.environ.get('WHATSAPP_GATEWAY_URL', 'http://127.0.0.1:3000').rstrip('/')

def _gw_user(business):
    return str(business.id) if business else "default"

@login_required(login_url='login')
@ensure_csrf_cookie
def whatsapp_config_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if not business.is_module_enabled('whatsapp'):
        messages.error(request, "El módulo de WhatsApp no está contratado en tu plan o está deshabilitado.")
        return redirect('dashboard')

    if not request.user.has_module_access('whatsapp'):
        messages.error(request, "No tienes permisos asignados para acceder al módulo de WhatsApp.")
        return redirect('dashboard')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permisos para acceder a la configuración de WhatsApp.")
        return redirect('dashboard')

    # Sembrar plantillas por defecto si el negocio aún no tiene ninguna
    if not business.whatsapp_templates.exists():
        WhatsAppMessageTemplate.objects.create(
            business=business,
            title="Recordatorio de Cita Estándar",
            category="APPOINTMENT",
            content=business.appointment_reminder_message or "Hola {client_name}, te recordamos tu cita de *{service}* en *{business}* para el día *{date}* a las *{time}* con *{staff}*. ¡Te esperamos!",
            is_default=True
        )
        WhatsAppMessageTemplate.objects.create(
            business=business,
            title="Confirmación de Turno",
            category="APPOINTMENT",
            content="Hola {client_name}, tu cita en *{business}* para *{service}* el {date} a las {time} hs ha sido confirmada con éxito. ¡Te esperamos!",
            is_default=False
        )
        WhatsAppMessageTemplate.objects.create(
            business=business,
            title="Mensaje de Saludo a Cliente",
            category="CLIENT",
            content=business.client_default_message or "Hola {client_name}, te escribimos desde *{business}*. ¿En qué te podemos ayudar hoy?",
            is_default=True
        )
        WhatsAppMessageTemplate.objects.create(
            business=business,
            title="Seguimiento / Fidelización",
            category="CLIENT",
            content="Hola {client_name}, queríamos agradecerte por tu confianza en *{business}*. ¿Cómo fue tu experiencia con nuestro servicio?",
            is_default=False
        )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_template':
            title = request.POST.get('title', '').strip()
            category = request.POST.get('category', 'APPOINTMENT')
            content = request.POST.get('content', '').strip()
            is_default = request.POST.get('is_default') in ['on', '1', 'true', True]

            if title and content:
                if is_default:
                    WhatsAppMessageTemplate.objects.filter(business=business, category=category).update(is_default=False)
                WhatsAppMessageTemplate.objects.create(
                    business=business,
                    title=title,
                    category=category,
                    content=content,
                    is_default=is_default
                )
                messages.success(request, f"¡Plantilla '{title}' creada con éxito!")
            else:
                messages.error(request, "El título y el contenido son obligatorios.")
            return redirect('whatsapp_config')

        elif action == 'edit_template':
            template_id = request.POST.get('template_id')
            tmpl = get_object_or_404(WhatsAppMessageTemplate, id=template_id, business=business)
            title = request.POST.get('title', '').strip()
            category = request.POST.get('category', tmpl.category)
            content = request.POST.get('content', '').strip()
            is_default = request.POST.get('is_default') in ['on', '1', 'true', True]

            if title and content:
                if is_default:
                    WhatsAppMessageTemplate.objects.filter(business=business, category=category).exclude(id=tmpl.id).update(is_default=False)
                tmpl.title = title
                tmpl.category = category
                tmpl.content = content
                tmpl.is_default = is_default
                tmpl.save()
                messages.success(request, f"¡Plantilla '{title}' actualizada!")
            return redirect('whatsapp_config')

        elif action == 'delete_template':
            template_id = request.POST.get('template_id')
            tmpl = get_object_or_404(WhatsAppMessageTemplate, id=template_id, business=business)
            title = tmpl.title
            tmpl.delete()
            messages.success(request, f"Plantilla '{title}' eliminada.")
            return redirect('whatsapp_config')

        elif action == 'set_default_template':
            template_id = request.POST.get('template_id')
            tmpl = get_object_or_404(WhatsAppMessageTemplate, id=template_id, business=business)
            WhatsAppMessageTemplate.objects.filter(business=business, category=tmpl.category).update(is_default=False)
            tmpl.is_default = True
            tmpl.save()
            messages.success(request, f"'{tmpl.title}' establecida como plantilla por defecto.")
            return redirect('whatsapp_config')

    templates = business.whatsapp_templates.all().order_by('category', '-is_default', 'title')

    session_user = str(business.id) if business else "default"
    gw_status = {'online': False, 'status': 'offline'}
    try:
        url = f"{GATEWAY_BASE_URL}/status?user={session_user}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            gw_status = {'online': True, 'status': data.get('status', 'disconnected')}
    except Exception:
        gw_status = {'online': False, 'status': 'offline'}

    return render(request, 'business/whatsapp_config.html', {
        'business': business,
        'gw_status': gw_status,
        'templates': templates,
    })


@login_required
@ensure_csrf_cookie
def whatsapp_gateway_status_api(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'online': False, 'status': 'offline', 'error': 'Negocio no encontrado'})
    session_user = _gw_user(business)
    try:
        url = f"{GATEWAY_BASE_URL}/status?user={session_user}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return JsonResponse({'online': True, 'status': data.get('status', 'disconnected')})
    except Exception as e:
        return JsonResponse({'online': False, 'status': 'offline', 'error': str(e)})

@login_required
@ensure_csrf_cookie
def whatsapp_gateway_qr_api(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'online': False, 'qr': None, 'status': 'offline', 'error': 'Negocio no encontrado'})
    session_user = _gw_user(business)
    try:
        url = f"{GATEWAY_BASE_URL}/qr?user={session_user}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return JsonResponse({'online': True, 'qr': data.get('qr'), 'status': data.get('status', 'disconnected')})
    except Exception as e:
        return JsonResponse({'online': False, 'qr': None, 'status': 'offline', 'error': str(e)})

@login_required
@ensure_csrf_cookie
def whatsapp_gateway_generate_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'Negocio no encontrado'}, status=400)
    
    session_user = _gw_user(business)
    try:
        url = f"{GATEWAY_BASE_URL}/generate?user={session_user}"
        req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json', 'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return JsonResponse({'success': True, 'qr': data.get('qr'), 'status': 'initializing'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f"Microservicio no responde en {GATEWAY_BASE_URL}. Inicia el gateway ejecutando 'npm start' dentro de la carpeta whatsapp-gateway."})

@login_required
@ensure_csrf_cookie
def whatsapp_gateway_unlink_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'Negocio no encontrado'}, status=400)
    if not business.is_module_enabled('whatsapp'):
        return JsonResponse({'success': False, 'error': 'El módulo de WhatsApp no está habilitado para esta empresa.'}, status=403)
    session_user = _gw_user(business)
    try:
        url = f"{GATEWAY_BASE_URL}/unlink?user={session_user}"
        req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json', 'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return JsonResponse({'success': True, 'status': 'unlinked'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@ensure_csrf_cookie
def whatsapp_gateway_send_reminder_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'Negocio no encontrado'}, status=400)
    if not business.is_module_enabled('whatsapp'):
        return JsonResponse({'success': False, 'error': 'El módulo de WhatsApp no está habilitado para esta empresa.'}, status=403)
    session_user = _gw_user(business)

    phone = request.POST.get('phone', '').strip()
    message = request.POST.get('message', '').strip()

    if not phone or not message:
        return JsonResponse({'success': False, 'error': 'Faltan parámetros requeridos (phone, message)'}, status=400)

    clean_phone = ''.join(filter(str.isdigit, phone))
    
    # Check if gateway is active and connected
    try:
        status_url = f"{GATEWAY_BASE_URL}/status?user={session_user}"
        st_req = urllib.request.Request(status_url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(st_req, timeout=2) as st_resp:
            st_data = json.loads(st_resp.read().decode('utf-8'))
            if st_data.get('status') == 'connected':
                send_url = f"{GATEWAY_BASE_URL}/send?user={session_user}"
                payload = json.dumps({'number': clean_phone, 'message': message}).encode('utf-8')
                send_req = urllib.request.Request(send_url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Django-RauDieOS'})
                with urllib.request.urlopen(send_req, timeout=6) as send_resp:
                    send_data = json.loads(send_resp.read().decode('utf-8'))
                    if send_data.get('ok'):
                        return JsonResponse({'success': True, 'sent_direct': True, 'message': 'Mensaje enviado directamente por WhatsApp Gateway'})
    except Exception as e:
        pass

    fallback_url = f"https://api.whatsapp.com/send?phone={urllib.parse.quote(clean_phone)}&text={urllib.parse.quote(message)}"
    return JsonResponse({'success': True, 'sent_direct': False, 'fallback_url': fallback_url})


def manifest_view(request):
    from django.conf import settings
    from django.http import HttpResponse
    manifest_path = settings.BASE_DIR / 'static' / 'manifest.json'
    if manifest_path.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/manifest+json')
    return HttpResponse('{}', content_type='application/manifest+json')

def service_worker_view(request):
    from django.conf import settings
    from django.http import HttpResponse
    sw_path = settings.BASE_DIR / 'static' / 'sw.js'
    if sw_path.exists():
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    return HttpResponse('console.log("No sw found");', content_type='application/javascript')

def offline_view(request):
    return render(request, 'offline.html')


@login_required(login_url='login')
def booking_portal_config_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'TOGGLE_BOOKING':
            # Support both direct checkbox and toggle state
            is_enabled = request.POST.get('is_booking_enabled') in ['on', 'true', '1']
            business.is_booking_enabled = is_enabled
            business.save()
            status_text = "activado" if is_enabled else "pausado"
            messages.success(request, f"¡El portal de reservas online ha sido {status_text} exitosamente!")
            return redirect('booking_portal_config')

        elif action == 'UPDATE_SLUG':
            slug_input = request.POST.get('slug', '').strip()
            if slug_input:
                new_slug = slugify(slug_input)
                if not Business.objects.filter(slug=new_slug).exclude(id=business.id).exists():
                    business.slug = new_slug
                    business.save()
                    messages.success(request, f"¡Enlace de reservas actualizado! Ahora es: /reservas/{new_slug}/")
                else:
                    messages.error(request, f"El enlace '{new_slug}' ya se encuentra ocupado por otro negocio. Prueba con otro.")
            return redirect('booking_portal_config')

        elif action == 'UPDATE_PENDING_EXPIRY':
            raw_hours = request.POST.get('pending_booking_expiry_hours', '24').strip()
            try:
                hours_val = max(1, min(720, int(raw_hours)))
            except (ValueError, TypeError):
                hours_val = 24
            business.pending_booking_expiry_hours = hours_val
            business.save(update_fields=['pending_booking_expiry_hours'])
            messages.success(
                request,
                f"¡Tiempo de espera de reservas pendientes actualizado a {hours_val} hora(s)! "
                f"Las reservas no confirmadas en ese plazo se liberarán automáticamente."
            )
            return redirect('booking_portal_config')

        elif action == 'UPDATE_DEFAULT_DEPOSIT':
            raw_pct = (request.POST.get('default_deposit_percentage') or '0').replace(',', '.').strip()
            apply_all = request.POST.get('apply_to_all_services') == '1'
            try:
                pct_val = max(Decimal('0.00'), min(Decimal('100.00'), Decimal(raw_pct))).quantize(Decimal('0.01'))
            except Exception:
                pct_val = Decimal('30.00')
            business.default_deposit_percentage = pct_val
            business.save(update_fields=['default_deposit_percentage'])
            if apply_all:
                from apps.agenda.models import Service
                Service.objects.filter(business=business).update(deposit_percentage=pct_val)
                messages.success(request, f"¡Porcentaje de seña/anticipo general actualizado a {pct_val}% y aplicado a todos los servicios!")
            else:
                messages.success(request, f"¡Porcentaje de seña/anticipo general actualizado a {pct_val}%!")
            return redirect('booking_portal_config')

        elif action == 'UPDATE_DETAILS':
            import base64
            from django.core.files.base import ContentFile

            # Handle cropped logo (Base64) or direct file upload
            cropped_logo_b64 = request.POST.get('cropped_logo_base64')
            if cropped_logo_b64 and ';base64,' in cropped_logo_b64:
                try:
                    format_meta, imgstr = cropped_logo_b64.split(';base64,')
                    ext = format_meta.split('/')[-1] if '/' in format_meta else 'png'
                    data = base64.b64decode(imgstr)
                    file_name = f"{business.slug}_logo_cropped.{ext}"
                    business.logo_url = ContentFile(data, name=file_name)
                except Exception as e:
                    print(f"Error decoding cropped logo: {e}")
            elif 'logo_url' in request.FILES:
                business.logo_url = request.FILES['logo_url']

            # Handle cropped banner (Base64) or direct file upload
            cropped_banner_b64 = request.POST.get('cropped_banner_base64')
            if cropped_banner_b64 and ';base64,' in cropped_banner_b64:
                try:
                    format_meta, imgstr = cropped_banner_b64.split(';base64,')
                    ext = format_meta.split('/')[-1] if '/' in format_meta else 'png'
                    data = base64.b64decode(imgstr)
                    file_name = f"{business.slug}_banner_cropped.{ext}"
                    business.banner_url = ContentFile(data, name=file_name)
                except Exception as e:
                    print(f"Error decoding cropped banner: {e}")
            elif 'banner_url' in request.FILES:
                business.banner_url = request.FILES['banner_url']

            wa_pfx = request.POST.get('whatsapp_prefix', '').strip()
            wa_num = request.POST.get('whatsapp_number', '').strip()
            if wa_num:
                business.whatsapp_number = format_phone_with_prefix(wa_pfx, wa_num)
            else:
                business.whatsapp_number = None

            if 'description' in request.POST:
                business.description = request.POST.get('description', '').strip() or None

            if 'pending_booking_expiry_hours' in request.POST:
                try:
                    business.pending_booking_expiry_hours = max(1, min(720, int(request.POST.get('pending_booking_expiry_hours', 24))))
                except (ValueError, TypeError):
                    pass

            if 'address' in request.POST:
                new_addr = request.POST.get('address', '').strip()
                business.address = new_addr
                if new_addr:
                    main_branch = (
                        Branch.objects.filter(business=business, is_main=True).first()
                        or Branch.objects.filter(business=business).first()
                    )
                    if main_branch and main_branch.address != new_addr:
                        main_branch.address = new_addr
                        main_branch.save(update_fields=['address'])

            business.save()
            messages.success(request, "¡Detalles y personalización del perfil público actualizados!")
            return redirect('booking_portal_config')

    full_booking_url = request.build_absolute_uri(f"/reservas/{business.slug}/")
    default_prefix, _ = split_phone_number(business.phone if business else '')
    wa_prefix, wa_number = split_phone_number(business.whatsapp_number or '', default_prefix=default_prefix)

    return render(request, 'business/booking_portal_config.html', {
        'business': business,
        'full_booking_url': full_booking_url,
        'default_phone_prefix': default_prefix,
        'wa_prefix': wa_prefix,
        'wa_number': wa_number,
    })


@login_required(login_url='login')
def booking_portal_toggle_api(request):
    """Endpoint AJAX rápido para activar o desactivar con 1 solo clic"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return JsonResponse({'error': 'Negocio no encontrado'}, status=400)
    
    business.is_booking_enabled = not business.is_booking_enabled
    business.save()
    
    status_label = "Activo" if business.is_booking_enabled else "Pausado"
    return JsonResponse({
        'success': True,
        'is_booking_enabled': business.is_booking_enabled,
        'status_label': status_label,
        'message': f"Portal de reservas {status_label.lower()} correctamente."
    })


# ==============================================================================
# GESTIÓN DE USUARIOS Y PERFILES CONFIGURABLES (RBAC)
# ==============================================================================

ALL_SYSTEM_MODULES = [
    {'code': 'agenda', 'name': 'Agenda & Citas', 'icon': 'calendar', 'desc': 'Calendario interactivo, turnos y citas de clientes.'},
    {'code': 'crm', 'name': 'CRM & Clientes', 'icon': 'users', 'desc': 'Fichas de clientes, historial de visitas y datos de contacto.'},
    {'code': 'travel', 'name': 'Paquetes & Reservas de Viajes', 'icon': 'plane', 'desc': 'Gestión de paquetes turísticos, pasajes, expedientes y vouchers.'},
    {'code': 'properties', 'name': 'Cartera de Inmuebles & Propiedades', 'icon': 'building-2', 'desc': 'Gestión de catálogo inmobiliario, inmuebles y portales.'},
    {'code': 'projects', 'name': 'Proyectos', 'icon': 'folder-kanban', 'desc': 'Seguimiento de proyectos, entregables y tareas.'},
    {'code': 'pos', 'name': 'Ventas POS & Caja', 'icon': 'shopping-bag', 'desc': 'Cobro rápido, apertura/cierre de caja y emisión de comprobantes.'},
    {'code': 'invoicing', 'name': 'Facturación & Gastos', 'icon': 'file-text', 'desc': 'Gestión de comprobantes, egresos y cuentas.'},
    {'code': 'inventory', 'name': 'Inventario & Stock', 'icon': 'package', 'desc': 'Control de productos, existencias y alertas de stock.'},
    {'code': 'commissions', 'name': 'Comisiones de Equipo', 'icon': 'dollar-sign', 'desc': 'Cálculo de comisiones por servicios y liquidaciones.'},
    {'code': 'marketing', 'name': 'Marketing & Promociones', 'icon': 'tag', 'desc': 'Campañas, promociones y fidelización.'},
    {'code': 'booking', 'name': 'Portal de Reservas Online', 'icon': 'globe', 'desc': 'Enlace público 24/7 para que los clientes reserven.'},
    {'code': 'whatsapp', 'name': 'WhatsApp & Mensajería', 'icon': 'message-square', 'desc': 'Conexión QR, recordatorios de citas y plantillas de mensajes.'},
    {'code': 'ai_engine', 'name': 'IA & Automatización', 'icon': 'sparkles', 'desc': 'Herramientas de inteligencia artificial.'},
]

def get_system_modules_for_business(business):
    """
    Retorna la lista de módulos del sistema adaptada al tipo de negocio específico
    (ej: etiquetas de Pacientes para Salud, Pasajeros para Viajes, etc.)
    """
    modules = []
    for mod in ALL_SYSTEM_MODULES:
        item = dict(mod)
        if business:
            if mod['code'] == 'crm':
                if business.is_health_beauty:
                    item['name'] = 'CRM & Pacientes'
                    item['desc'] = 'Fichas de pacientes, historial clínico y datos de contacto.'
                elif business.is_travel:
                    item['name'] = 'CRM & Pasajeros'
                    item['desc'] = 'Fichas de pasajeros, pasaportes y datos de contacto.'
                elif business.is_real_estate:
                    item['name'] = 'CRM & Clientes Inmobiliarios'
                    item['desc'] = 'Fichas de clientes propietarios, compradores y búsquedas activas.'
            elif mod['code'] == 'commissions':
                if business.is_real_estate:
                    item['desc'] = 'Cálculo de comisiones por operaciones de venta y alquiler.'
                elif business.is_travel:
                    item['desc'] = 'Comisiones por venta de paquetes turísticos y pasajes.'
        modules.append(item)
    return modules

@login_required(login_url='login')
def user_list_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para administrar usuarios ni perfiles.")
        return redirect('dashboard')

    ensure_default_profiles(business)

    users = User.objects.filter(business=business).select_related('profile_role', 'staff_profile').order_by('first_name', 'username')
    roles = UserProfileRole.objects.filter(business=business).annotate(users_count=Count('users')).order_by('name')

    subscription = getattr(business, 'subscription', None)
    plan = subscription.plan if subscription else None
    max_users = plan.max_users if plan else 5
    current_users_count = users.count()
    can_create_user = current_users_count < max_users

    active_tab = request.GET.get('tab', 'users')

    return render(request, 'business/user_list.html', {
        'business': business,
        'users': users,
        'roles': roles,
        'current_users_count': current_users_count,
        'max_users': max_users,
        'can_create_user': can_create_user,
        'plan': plan,
        'active_tab': active_tab,
    })


@login_required(login_url='login')
def user_create_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para crear usuarios.")
        return redirect('dashboard')

    ensure_default_profiles(business)

    subscription = getattr(business, 'subscription', None)
    plan = subscription.plan if subscription else None
    max_users = plan.max_users if plan else 5
    current_users_count = User.objects.filter(business=business).count()

    if current_users_count >= max_users:
        messages.error(
            request,
            f"Has alcanzado el límite máximo de {max_users} usuarios incluido en tu plan actual. "
            "Para agregar más usuarios al equipo, actualiza tu plan de suscripción."
        )
        return redirect('user_list')

    roles = UserProfileRole.objects.filter(business=business).order_by('name')
    available_staff = StaffMember.objects.filter(business=business, is_active=True, user__isnull=True).order_by('first_name')

    default_prefix, _ = split_phone_number(business.phone if business else '')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone_prefix = request.POST.get('phone_prefix', default_prefix).strip()
        phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
        phone = format_phone_with_prefix(phone_prefix, phone_number, default_prefix=default_prefix)
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        profile_role_id = request.POST.get('profile_role_id')
        staff_member_id = request.POST.get('staff_member_id')
        create_staff_profile = request.POST.get('create_staff_profile') == '1'

        if not email or not password:
            messages.error(request, "El correo electrónico y la contraseña son obligatorios.")
        elif password != password_confirm:
            messages.error(request, "Las contraseñas no coinciden.")
        elif len(password) < 6:
            messages.error(request, "La contraseña debe tener al menos 6 caracteres.")
        elif User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            messages.error(request, "Ya existe un usuario registrado con este correo electrónico.")
        else:
            profile_role = UserProfileRole.objects.filter(id=profile_role_id, business=business).first() if profile_role_id else None

            # Legacy role determination
            legacy_role = 'ADMIN'
            if profile_role:
                if profile_role.scope_appointments == 'OWN':
                    legacy_role = 'PROFESSIONAL'
                elif profile_role.can_charge_pos and not profile_role.can_view_financial_reports:
                    legacy_role = 'RECEPTIONIST'
                elif profile_role.can_manage_settings:
                    legacy_role = 'ADMIN'

            new_user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                business=business,
                role=legacy_role,
                profile_role=profile_role
            )

            # Link with StaffMember if selected or requested
            if staff_member_id:
                staff = StaffMember.objects.filter(id=staff_member_id, business=business).first()
                if staff:
                    staff.user = new_user
                    staff.save()
            elif create_staff_profile or legacy_role == 'PROFESSIONAL':
                StaffMember.objects.create(
                    business=business,
                    user=new_user,
                    first_name=first_name or "Profesional",
                    last_name=last_name or "",
                    email=email,
                    phone=phone,
                    role_title=profile_role.name if profile_role else "Especialista",
                    commission_rate=Decimal("0.00"),
                    is_active=True
                )

            messages.success(request, f"¡Usuario {new_user.get_full_name() or new_user.email} creado exitosamente!")
            return redirect('user_list')

    return render(request, 'business/user_form.html', {
        'business': business,
        'roles': roles,
        'available_staff': available_staff,
        'edit_user': None,
        'default_phone_prefix': default_prefix,
        'user_phone_prefix': default_prefix,
        'user_phone_number': '',
        'title': 'Crear Nuevo Usuario',
    })


@login_required(login_url='login')
def user_edit_view(request, user_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para editar usuarios.")
        return redirect('dashboard')

    user_obj = get_object_or_404(User, id=user_id, business=business)
    roles = UserProfileRole.objects.filter(business=business).order_by('name')
    from django.db.models import Q
    available_staff = StaffMember.objects.filter(business=business, is_active=True).filter(
        Q(user__isnull=True) | Q(user=user_obj)
    ).order_by('first_name')

    is_editing_self = (request.user.id == user_obj.id)
    is_owner = (user_obj.role == 'OWNER')

    default_prefix, _ = split_phone_number(business.phone if business else '')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_prefix = request.POST.get('phone_prefix', default_prefix).strip()
        phone_number = request.POST.get('phone_number', '').strip() or request.POST.get('phone', '').strip()
        user_obj.phone = format_phone_with_prefix(phone_prefix, phone_number, default_prefix=default_prefix)
        new_password = request.POST.get('new_password', '').strip()
        profile_role_id = request.POST.get('profile_role_id')
        staff_member_id = request.POST.get('staff_member_id')
        is_active_val = request.POST.get('is_active') == '1'

        user_obj.first_name = first_name
        user_obj.last_name = last_name

        if not is_owner and not is_editing_self:
            user_obj.is_active = is_active_val
            if profile_role_id:
                profile_role = UserProfileRole.objects.filter(id=profile_role_id, business=business).first()
                user_obj.profile_role = profile_role
                if profile_role:
                    if profile_role.scope_appointments == 'OWN':
                        user_obj.role = 'PROFESSIONAL'
                    elif profile_role.can_charge_pos and not profile_role.can_view_financial_reports:
                        user_obj.role = 'RECEPTIONIST'
                    elif profile_role.can_manage_settings:
                        user_obj.role = 'ADMIN'
            else:
                user_obj.profile_role = None

        if new_password:
            if len(new_password) < 6:
                messages.error(request, "La nueva contraseña debe tener al menos 6 caracteres.")
                return redirect('user_edit', user_id=user_id)
            user_obj.set_password(new_password)
            if is_editing_self:
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user_obj)

        user_obj.save()

        # Update StaffMember link
        current_staff = getattr(user_obj, 'staff_profile', None)
        if staff_member_id:
            new_staff = StaffMember.objects.filter(id=staff_member_id, business=business).first()
            if new_staff and new_staff != current_staff:
                if current_staff:
                    current_staff.user = None
                    current_staff.save()
                new_staff.user = user_obj
                new_staff.save()
        elif staff_member_id == '' and current_staff:
            current_staff.user = None
            current_staff.save()

        messages.success(request, f"¡Usuario {user_obj.email} actualizado correctamente!")
        return redirect('user_list')

    user_prefix, user_num = split_phone_number(user_obj.phone, default_prefix=default_prefix)

    return render(request, 'business/user_form.html', {
        'business': business,
        'roles': roles,
        'available_staff': available_staff,
        'edit_user': user_obj,
        'is_editing_self': is_editing_self,
        'is_owner': is_owner,
        'default_phone_prefix': default_prefix,
        'user_phone_prefix': user_prefix,
        'user_phone_number': user_num,
        'title': f'Editar Usuario: {user_obj.get_full_name() or user_obj.username}',
    })


@login_required(login_url='login')
def user_delete_view(request, user_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para eliminar usuarios.")
        return redirect('dashboard')

    user_obj = get_object_or_404(User, id=user_id, business=business)

    if user_obj.id == request.user.id:
        messages.error(request, "No puedes eliminar tu propia cuenta de usuario en uso.")
        return redirect('user_list')

    if user_obj.role == 'OWNER':
        messages.error(request, "No se puede eliminar la cuenta principal del propietario de la empresa.")
        return redirect('user_list')

    if request.method == 'POST':
        # Handle linked staff profile if any
        staff = getattr(user_obj, 'staff_profile', None)
        if staff:
            has_history = staff.appointments.exists() or staff.sales.exists() or staff.payroll_settlements.exists()
            delete_completely = (request.POST.get('delete_staff_completely') == '1') or not has_history
            if delete_completely:
                staff.delete()
            else:
                staff.is_active = False
                staff.user = None
                staff.save()

        user_email = user_obj.email
        user_obj.delete()
        messages.success(request, f"Usuario '{user_email}' eliminado correctamente.")

    return redirect('user_list')


@login_required(login_url='login')
def role_list_view(request):
    return redirect('/business/usuarios/?tab=roles')


@login_required(login_url='login')
def role_create_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para crear perfiles de acceso.")
        return redirect('dashboard')

    allowed_plan_modules = business.get_allowed_modules()
    catalog = get_system_modules_for_business(business)
    available_modules = [m for m in catalog if m['code'] in allowed_plan_modules]

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        selected_modules = request.POST.getlist('allowed_modules')
        scope_appointments = request.POST.get('scope_appointments', 'ALL')
        scope_commissions = request.POST.get('scope_commissions', 'NONE')
        can_charge_pos = request.POST.get('can_charge_pos') in ['1', 'true', 'on', True]
        can_view_financial_reports = request.POST.get('can_view_financial_reports') in ['1', 'true', 'on', True]
        can_manage_settings = request.POST.get('can_manage_settings') in ['1', 'true', 'on', True]
        can_manage_clients = request.POST.get('can_manage_clients') in ['1', 'true', 'on', True]
        can_manage_inventory = request.POST.get('can_manage_inventory') in ['1', 'true', 'on', True]

        if not name:
            messages.error(request, "El nombre del perfil es obligatorio.")
        else:
            if 'ai_engine' in selected_modules and 'whatsapp' not in selected_modules and 'whatsapp' in allowed_plan_modules:
                selected_modules.append('whatsapp')
            # Filter strictly against subscription modules
            filtered_modules = [m for m in selected_modules if m in allowed_plan_modules]

            role = UserProfileRole.objects.create(
                business=business,
                name=name,
                description=description,
                is_system_default=False,
                allowed_modules=filtered_modules,
                scope_appointments=scope_appointments,
                scope_commissions=scope_commissions,
                can_charge_pos=can_charge_pos,
                can_view_financial_reports=can_view_financial_reports,
                can_manage_settings=can_manage_settings,
                can_manage_clients=can_manage_clients,
                can_manage_inventory=can_manage_inventory,
            )
            messages.success(request, f"Perfil '{role.name}' creado exitosamente.")
            return redirect('/business/usuarios/?tab=roles')

    return render(request, 'business/role_form.html', {
        'business': business,
        'role': None,
        'available_modules': available_modules,
        'title': 'Crear Perfil de Acceso',
    })


@login_required(login_url='login')
def role_edit_view(request, role_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para editar perfiles.")
        return redirect('dashboard')

    role_obj = get_object_or_404(UserProfileRole, id=role_id, business=business)
    allowed_plan_modules = business.get_allowed_modules()
    catalog = get_system_modules_for_business(business)
    available_modules = [m for m in catalog if m['code'] in allowed_plan_modules]

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        selected_modules = request.POST.getlist('allowed_modules')
        scope_appointments = request.POST.get('scope_appointments', 'ALL')
        scope_commissions = request.POST.get('scope_commissions', 'NONE')
        can_charge_pos = request.POST.get('can_charge_pos') in ['1', 'true', 'on', True]
        can_view_financial_reports = request.POST.get('can_view_financial_reports') in ['1', 'true', 'on', True]
        can_manage_settings = request.POST.get('can_manage_settings') in ['1', 'true', 'on', True]
        can_manage_clients = request.POST.get('can_manage_clients') in ['1', 'true', 'on', True]
        can_manage_inventory = request.POST.get('can_manage_inventory') in ['1', 'true', 'on', True]

        if not name:
            messages.error(request, "El nombre del perfil es obligatorio.")
        else:
            if 'ai_engine' in selected_modules and 'whatsapp' not in selected_modules and 'whatsapp' in allowed_plan_modules:
                selected_modules.append('whatsapp')
            role_obj.name = name
            role_obj.description = description
            role_obj.allowed_modules = [m for m in selected_modules if m in allowed_plan_modules]
            role_obj.scope_appointments = scope_appointments
            role_obj.scope_commissions = scope_commissions
            role_obj.can_charge_pos = can_charge_pos
            role_obj.can_view_financial_reports = can_view_financial_reports
            role_obj.can_manage_settings = can_manage_settings
            role_obj.can_manage_clients = can_manage_clients
            role_obj.can_manage_inventory = can_manage_inventory
            role_obj.save()

            messages.success(request, f"Perfil '{role_obj.name}' actualizado correctamente.")
            return redirect('/business/usuarios/?tab=roles')

    return render(request, 'business/role_form.html', {
        'business': business,
        'role': role_obj,
        'available_modules': available_modules,
        'title': f'Editar Perfil: {role_obj.name}',
    })


@login_required(login_url='login')
def role_delete_view(request, role_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if not request.user.has_perm_flag('can_manage_settings'):
        messages.error(request, "No tienes permiso para eliminar perfiles.")
        return redirect('dashboard')

    role_obj = get_object_or_404(UserProfileRole, id=role_id, business=business)

    if role_obj.users.exists():
        messages.error(
            request,
            f"No se puede eliminar el perfil '{role_obj.name}' porque actualmente tiene {role_obj.users.count()} usuarios asignados. "
            "Reasigna estos usuarios a otro perfil antes de eliminarlo."
        )
        return redirect('/business/usuarios/?tab=roles')

    if request.method == 'POST':
        role_name = role_obj.name
        role_obj.delete()
        messages.success(request, f"Perfil '{role_name}' eliminado correctamente.")

    return redirect('/business/usuarios/?tab=roles')


def privacy_view(request):
    return render(request, 'business/legal.html', {
        'active_tab': 'privacy',
        'page_title': 'Política de Privacidad'
    })

def terms_view(request):
    return render(request, 'business/legal.html', {
        'active_tab': 'terms',
        'page_title': 'Términos y Condiciones de Uso'
    })

def security_view(request):
    return render(request, 'business/legal.html', {
        'active_tab': 'security',
        'page_title': 'Seguridad y Protección de Datos'
    })
