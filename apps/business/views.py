import uuid
import datetime
import json
import urllib.request
import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.utils.text import slugify
from django.utils import timezone
from apps.business.models import Business, Branch, StaffMember, WorkSchedule, PaymentMethodConfig, User
from apps.core.utils import parse_decimal, parse_int

@ensure_csrf_cookie
def landing_view(request):
    if request.user.is_authenticated or request.GET.get('pwa') == '1' or request.GET.get('mode') == 'pwa':
        return redirect('dashboard')
    from apps.superadmin.models import SubscriptionPlan
    from apps.superadmin.views import _ensure_default_plans
    _ensure_default_plans()
    plans = SubscriptionPlan.objects.filter(is_active=True, show_on_landing=True).order_by('monthly_price')
    return render(request, 'business/landing.html', {'plans': plans})


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
    storage = messages.get_messages(request)
    for _ in storage:
        pass
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('login')

@login_required(login_url='login')
@ensure_csrf_cookie
def onboarding_view(request):
    user = request.user
    business = getattr(user, 'business', None)
    if not business:
        agency_name = f"Agencia {user.first_name or user.username}".strip()
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
@login_required(login_url='login')
@ensure_csrf_cookie
def business_config_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST' and business:
        action = request.POST.get('action')

        if action == 'SAVE_BRANCH':
            branch_id = request.POST.get('branch_id')
            b_name = request.POST.get('branch_name', '').strip()
            b_address = request.POST.get('branch_address', '').strip()
            b_phone = request.POST.get('branch_phone', '').strip()
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
                    messages.success(request, f"¡Sucursal '{b_name}' actualizada correctamente!")
                else:
                    Branch.objects.create(
                        business=business,
                        name=b_name,
                        address=b_address,
                        phone=b_phone,
                        google_maps_url=b_maps_url,
                        is_main=is_main
                    )
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
            return redirect('business_config')

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
        business.time_format = request.POST.get('time_format', getattr(business, 'time_format', '12h'))
        business.allow_editing_client_history = (request.POST.get('allow_editing_client_history') == 'on' or request.POST.get('allow_editing_client_history') == 'true')
        
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

        business.save()
        messages.success(request, f"¡Configuración de {business.name} actualizada correctamente!")
        return redirect('business_config')

    branches = Branch.objects.filter(business=business) if business else []
    payment_methods = PaymentMethodConfig.objects.filter(business=business) if business else []

    # Load subscription and available plans
    from apps.superadmin.models import SubscriptionPlan, BusinessSubscription
    subscription = getattr(business, 'subscription', None) if business else None
    available_plans = SubscriptionPlan.objects.filter(is_active=True)

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

    session_user = str(business.id) if business else "default"
    gw_status = {'online': False, 'status': 'offline'}
    try:
        url = f"http://127.0.0.1:3000/status?user={session_user}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Django-RauDieOS'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            gw_status = {'online': True, 'status': data.get('status', 'disconnected')}
    except Exception:
        gw_status = {'online': False, 'status': 'offline'}

    return render(request, 'business/config_company.html', {
        'business': business,
        'branches': branches,
        'payment_methods': payment_methods,
        'all_modules': all_modules,
        'schedules': schedules,
        'subscription': subscription,
        'available_plans': available_plans,
        'business_types': Business.BUSINESS_TYPE_CHOICES,
        'time_format_choices': getattr(Business, 'TIME_FORMAT_CHOICES', [('12h', '12 Horas'), ('24h', '24 Horas')]),
        'gw_status': gw_status,
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
            user_phone = request.POST.get('user_phone', '').strip()
            if user_first_name:
                request.user.first_name = user_first_name
            if user_last_name:
                request.user.last_name = user_last_name
            if user_phone:
                request.user.phone = user_phone
            request.user.save()
            messages.success(request, "¡Información de tu perfil actualizada correctamente!")
            return redirect('user_profile_config')

    return render(request, 'business/config_user.html', {
        'business': business,
    })

@login_required
def staff_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff_members = StaffMember.objects.filter(business=business).prefetch_related('schedules').order_by('first_name') if business else []
    
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
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    branches = Branch.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        role_title = request.POST.get('role_title', 'Especialista')
        commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        base_salary = parse_decimal(request.POST.get('base_salary'), '0.00')
        branch_id = request.POST.get('branch_id')
        branch_ids = request.POST.getlist('branch_ids')
        branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
        
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
            is_active=True
        )

        if branch_ids:
            selected_branches = Branch.objects.filter(id__in=branch_ids, business=business)
            staff.branches.set(selected_branches)
            if not staff.branch and selected_branches.exists():
                staff.branch = selected_branches.first()
                staff.save()
        elif branch:
            staff.branches.set([branch])
        
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

@login_required
def staff_edit_view(request, staff_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff = get_object_or_404(StaffMember, id=staff_id, business=business)
    branches = Branch.objects.filter(business=business)
    
    if request.method == 'POST':
        staff.first_name = request.POST.get('first_name')
        staff.last_name = request.POST.get('last_name')
        staff.email = request.POST.get('email', '')
        staff.phone = request.POST.get('phone', '')
        staff.role_title = request.POST.get('role_title', 'Especialista')
        staff.commission_rate = parse_decimal(request.POST.get('commission_rate'), '0.00')
        staff.base_salary = parse_decimal(request.POST.get('base_salary'), '0.00')
        branch_id = request.POST.get('branch_id')
        branch_ids = request.POST.getlist('branch_ids')
        staff.branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
        staff.save()

        if branch_ids:
            selected_branches = Branch.objects.filter(id__in=branch_ids, business=business)
            staff.branches.set(selected_branches)
            if not staff.branch and selected_branches.exists():
                staff.branch = selected_branches.first()
                staff.save()
        elif staff.branch:
            staff.branches.set([staff.branch])

        return redirect('staff_list')
        
    return render(request, 'business/staff_form.html', {
        'business': business,
        'staff': staff,
        'branches': branches,
        'title': f'Editar Profesional: {staff.full_name}'
    })

# ==============================================================================
# WHATSAPP GATEWAY API PROXY VIEWS (Node.js microservice integration)
# ==============================================================================

GATEWAY_BASE_URL = "http://127.0.0.1:3000"

def _gw_user(business):
    return str(business.id) if business else "default"

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



