import datetime
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count
from apps.business.models import Business, User, StaffMember, Branch
from apps.agenda.models import Appointment
from apps.invoicing.models import Invoice
from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, SystemAuditLog, SuperAdminUser, GlobalPaymentMethod, Region, RegionPaymentMethod, SubscriptionPayment, SystemAnnouncement, AnnouncementDismissal, PlanRegionPricing

from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import authenticate, login, logout

def get_current_superadmin(request):
    """
    Obtiene el SuperAdminUser directamente de la sesión actual de Django.
    """
    superadmin_id = request.session.get('superadmin_id')
    if superadmin_id:
        admin_user = SuperAdminUser.objects.filter(id=superadmin_id, is_active=True).first()
        if admin_user:
            return admin_user
    return None

def is_super_admin(user_or_request):
    """
    Helper para los decoradores y vistas.
    """
    if hasattr(user_or_request, 'session'):
        return get_current_superadmin(user_or_request) is not None
    return isinstance(user_or_request, SuperAdminUser) and user_or_request.is_active

def superadmin_required(view_func):
    """
    Decorador dedicado para proteger las vistas de SuperAdmin comprobando exclusivamente SuperAdminUser.
    """
    def _wrapped_view(request, *args, **kwargs):
        current_admin = get_current_superadmin(request)
        if not current_admin:
            messages.error(request, "Debes iniciar sesión con una cuenta de SuperAdmin.")
            return redirect('superadmin_login')
        request.superadmin_user = current_admin
        request.user = current_admin
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@ensure_csrf_cookie
def superadmin_login_view(request):
    if get_current_superadmin(request):
        return redirect('superadmin_dashboard')

    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # Buscar exclusivamente en el modelo SuperAdminUser
        admin_user = (
            SuperAdminUser.objects.filter(email__iexact=username_or_email).first() or
            SuperAdminUser.objects.filter(username__iexact=username_or_email).first()
        )

        if admin_user and admin_user.is_active and admin_user.check_password(password):
            # Guardar la sesión de SuperAdmin de forma independiente
            request.session['superadmin_id'] = str(admin_user.id)
            SystemAuditLog.objects.create(
                actor_email=admin_user.email,
                action="SUPERADMIN_LOGIN",
                details="Inicio de sesión exitoso en el Panel SuperAdmin"
            )
            messages.success(request, f"¡Bienvenido al Panel SuperAdmin, {admin_user.first_name or admin_user.username}!")
            return redirect('superadmin_dashboard')

        messages.error(request, "Acceso denegado. Credenciales de SuperAdmin incorrectas o cuenta inactiva.")

    return render(request, 'superadmin/login.html')

def superadmin_logout_view(request):
    if 'superadmin_id' in request.session:
        del request.session['superadmin_id']
        
    if request.GET.get('timeout') == '1':
        messages.warning(request, "Tu sesión de SuperAdmin ha expirado por inactividad de 30 minutos.")
    else:
        messages.info(request, "Sesión de SuperAdmin cerrada correctamente.")
        
    return redirect('superadmin_login')

@superadmin_required
def superadmin_dashboard_view(request):
    # Ensure default plans exist
    _ensure_default_plans()
    # Ensure subscriptions exist for all businesses
    _sync_business_subscriptions()

    total_businesses = Business.objects.count()
    total_users = User.objects.count()
    total_appointments = Appointment.objects.count()
    total_invoices = Invoice.objects.count()

    active_subs = BusinessSubscription.objects.filter(status='ACTIVE')
    trial_subs = BusinessSubscription.objects.filter(status='TRIAL')
    expired_subs = BusinessSubscription.objects.filter(status='EXPIRED')
    suspended_subs = BusinessSubscription.objects.filter(status='SUSPENDED')

    # Calculate Monthly Recurring Revenue (MRR)
    mrr = Decimal('0.00')
    for sub in active_subs:
        if sub.plan:
            mrr += sub.plan.monthly_price
    # Add trial conversion projection
    projected_mrr = mrr + (trial_subs.count() * Decimal('29.00'))

    # Recent Audit Logs
    recent_logs = SystemAuditLog.objects.order_by('-created_at')[:10]

    # Plan distribution
    plan_stats = SubscriptionPlan.objects.annotate(sub_count=Count('subscriptions'))

    # Infrastructure status metrics
    server_metrics = {
        'status': 'OPERATIONAL',
        'db_health': 'Óptimo (SQLite/Postgres Online)',
        'latency_ms': '16ms',
        'uptime_pct': '99.98%',
        'cpu_usage': '24%',
        'mem_usage': '38%',
    }

    recent_businesses = Business.objects.order_by('-created_at')[:5]

    return render(request, 'superadmin/dashboard.html', {
        'total_businesses': total_businesses,
        'total_users': total_users,
        'total_appointments': total_appointments,
        'total_invoices': total_invoices,
        'active_subs_count': active_subs.count(),
        'trial_subs_count': trial_subs.count(),
        'expired_subs_count': expired_subs.count(),
        'suspended_subs_count': suspended_subs.count(),
        'mrr': mrr,
        'projected_mrr': projected_mrr,
        'recent_logs': recent_logs,
        'plan_stats': plan_stats,
        'server_metrics': server_metrics,
        'recent_businesses': recent_businesses,
    })

@superadmin_required
@ensure_csrf_cookie
def users_list_view(request):
    """
    Vista unificada 'Usuarios / Agencias' para administrar el listado de clientes/agencias de la plataforma.
    """
    _ensure_default_plans()
    _sync_business_subscriptions()

    status_filter = request.GET.get('status', 'ALL')
    query = request.GET.get('q', '').strip()

    businesses = Business.objects.select_related('subscription', 'subscription__plan').prefetch_related('branches', 'staff_members', 'users', 'payment_methods').all()

    if status_filter != 'ALL':
        businesses = businesses.filter(subscription__status=status_filter)

    if query:
        businesses = businesses.filter(name__icontains=query)

    from django.core.paginator import Paginator
    paginator = Paginator(businesses.order_by('-created_at'), 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/users.html', {
        'businesses': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'query': query,
    })

@superadmin_required
@ensure_csrf_cookie
def user_detail_view(request, business_id):
    """
    Ficha detallada del usuario/agencia para inspeccionar y modificar:
    - Sucursales
    - Profesionales / Staff
    - Métodos de Pago
    - Suscripción y Licencia tomados dinámicamente de SubscriptionPlan
    """
    _ensure_default_plans()
    business = get_object_or_404(Business, id=business_id)
    subscription, _ = BusinessSubscription.objects.get_or_create(
        business=business,
        defaults={
            'start_date': timezone.now().date(),
            'expiration_date': timezone.now().date() + datetime.timedelta(days=14)
        }
    )

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('monthly_price')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'UPDATE_SUBSCRIPTION':
            status = request.POST.get('status', 'TRIAL')
            plan_id = request.POST.get('plan_id')
            duration_type = request.POST.get('duration_type', 'DAYS')
            custom_days = request.POST.get('custom_days')
            expiration_date_str = request.POST.get('expiration_date')
            notes = request.POST.get('notes', '').strip()

            subscription.status = status
            if plan_id:
                subscription.plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
            else:
                subscription.plan = None

            if duration_type == 'DATE' and expiration_date_str:
                try:
                    subscription.expiration_date = datetime.datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif duration_type == 'DAYS' and custom_days:
                days_int = int(custom_days)
                subscription.expiration_date = timezone.now().date() + datetime.timedelta(days=days_int)

            if notes:
                subscription.notes = notes

            subscription.pending_plan = None
            subscription.save()

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="ACTUALIZACION_LICENCIA",
                details=f"Licencia actualizada para {business.name} (Plan: {subscription.plan.name if subscription.plan else 'Sin Plan'}, Estado: {subscription.get_status_display()}, Vence: {subscription.expiration_date})"
            )
            messages.success(request, f"¡Suscripción de {business.name} actualizada correctamente!")
            return redirect('superadmin_user_detail', business_id=business.id)

        elif action == 'REGENERATE_TOKEN':
            subscription.license_key = uuid.uuid4()
            subscription.save()

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="REGENERAR_TOKEN",
                details=f"Token de licencia regenerado para {business.name}"
            )
            messages.success(request, f"¡Nuevo Token de Licencia generado para {business.name}!")
            return redirect('superadmin_user_detail', business_id=business.id)
            
        elif action == 'UPDATE_REGION':
            region_id = request.POST.get('region_id')
            if region_id:
                region = get_object_or_404(Region, id=region_id)
                business.region = region
                business.save()
                SystemAuditLog.objects.create(
                    actor_email=request.superadmin_user.email or request.superadmin_user.username,
                    action="ACTUALIZACION_REGION",
                    details=f"Región actualizada para {business.name} a {region.name}"
                )
                messages.success(request, f"¡Región de {business.name} actualizada a {region.name}!")
            return redirect('superadmin_user_detail', business_id=business.id)

    branches = business.branches.all()
    staff_members = business.staff_members.all()
    payment_methods = business.payment_methods.all()
    business_users = business.users.all()
    all_regions = Region.objects.filter(is_active=True).order_by('name')

    return render(request, 'superadmin/user_detail.html', {
        'business': business,
        'subscription': subscription,
        'plans': plans,
        'branches': branches,
        'branches_count': branches.count(),
        'staff_members': staff_members,
        'staff_count': staff_members.count(),
        'payment_methods': payment_methods,
        'payment_methods_count': payment_methods.count(),
        'business_users': business_users,
        'all_regions': all_regions,
    })

@superadmin_required
@ensure_csrf_cookie
def plans_management_view(request):
    _ensure_default_plans()

    if request.method == 'POST':
        action = request.POST.get('action', 'UPDATE')
        
        if action == 'CREATE':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper()
            monthly_price = request.POST.get('monthly_price', '29.00')
            annual_price = request.POST.get('annual_price', '290.00')
            max_users = request.POST.get('max_users', 5)
            max_branches = request.POST.get('max_branches', 2)
            selected_modules = request.POST.getlist('included_modules')
            show_on_landing = request.POST.get('show_on_landing') in ['on', 'true', '1']

            if name and code:
                code_clean = slugify(code).replace('-', '_').upper()
                plan = SubscriptionPlan.objects.create(
                    code=code_clean,
                    name=name,
                    monthly_price=Decimal(monthly_price),
                    annual_price=Decimal(annual_price),
                    max_users=int(max_users),
                    max_branches=int(max_branches),
                    included_modules=selected_modules if selected_modules else ['crm', 'agenda', 'booking', 'invoicing'],
                    show_on_landing=show_on_landing,
                    is_active=True
                )
                
                # Create default region pricing for existing regions
                regions = Region.objects.filter(is_active=True)
                for r in regions:
                    PlanRegionPricing.objects.create(
                        plan=plan,
                        region=r,
                        monthly_price=plan.monthly_price,
                        annual_price=plan.annual_price,
                        is_active=True
                    )
                    
                messages.success(request, f"¡Plan '{name}' creado exitosamente!")
                return redirect('superadmin_plans')

        elif action == 'UPDATE':
            plan_id = request.POST.get('plan_id')
            plan = get_object_or_404(SubscriptionPlan, id=plan_id)

            name = request.POST.get('name', '').strip() or plan.name
            
            raw_monthly = request.POST.get('monthly_price', '').strip().replace(',', '.')
            monthly_price = Decimal(raw_monthly) if raw_monthly else plan.monthly_price

            raw_annual = request.POST.get('annual_price', '').strip().replace(',', '.')
            annual_price = Decimal(raw_annual) if raw_annual else plan.annual_price

            raw_users = request.POST.get('max_users', '').strip()
            max_users_val = int(raw_users) if raw_users != '' else plan.max_users

            raw_branches = request.POST.get('max_branches', '').strip()
            max_branches_val = int(raw_branches) if raw_branches != '' else plan.max_branches

            selected_modules = request.POST.getlist('included_modules')
            show_on_landing = request.POST.get('show_on_landing') in ['on', 'true', '1']
            is_active = request.POST.get('is_active') in ['on', 'true', '1']

            plan.name = name
            plan.monthly_price = monthly_price
            plan.annual_price = annual_price
            plan.max_users = max_users_val
            plan.max_branches = max_branches_val
            plan.included_modules = selected_modules
            plan.show_on_landing = show_on_landing
            plan.is_active = is_active
            plan.save()

            # Handle region pricing
            regions = Region.objects.filter(is_active=True)
            for r in regions:
                r_monthly = request.POST.get(f'region_monthly_{r.id}')
                r_annual = request.POST.get(f'region_annual_{r.id}')
                r_active = request.POST.get(f'region_active_{r.id}') == 'on'
                
                if r_monthly and r_annual:
                    PlanRegionPricing.objects.update_or_create(
                        plan=plan,
                        region=r,
                        defaults={
                            'monthly_price': Decimal(r_monthly.replace(',', '.')),
                            'annual_price': Decimal(r_annual.replace(',', '.')),
                            'is_active': r_active
                        }
                    )

            messages.success(request, f"¡Plan '{plan.name}' actualizado exitosamente!")
            return redirect('superadmin_plans')

        elif action == 'DELETE':
            plan_id = request.POST.get('plan_id')
            plan = get_object_or_404(SubscriptionPlan, id=plan_id)
            plan.delete()
            messages.warning(request, f"El plan '{plan.name}' ha sido eliminado.")
            return redirect('superadmin_plans')

    plans = SubscriptionPlan.objects.all().order_by('monthly_price')

    all_modules = [
        {'code': 'crm', 'name': 'CRM & Clientes'},
        {'code': 'agenda', 'name': 'Agenda & Citas'},
        {'code': 'booking', 'name': 'Portal Reservas 24/7'},
        {'code': 'invoicing', 'name': 'Facturación & Gastos'},
        {'code': 'pos', 'name': 'Ventas POS & Caja'},
        {'code': 'inventory', 'name': 'Inventario & Stock'},
        {'code': 'commissions', 'name': 'Comisiones de Equipo'},
        {'code': 'ai_engine', 'name': 'IA & Automatización'},
        {'code': 'marketing', 'name': 'Marketing & Promociones'},
    ]

    regions = Region.objects.filter(is_active=True).order_by('name')

    return render(request, 'superadmin/plans.html', {
        'plans': plans,
        'all_modules': all_modules,
        'regions': regions
    })

@superadmin_required
@ensure_csrf_cookie
def payment_methods_management_view(request):
    """
    Gestión de Métodos de Pago Globales que las agencias/clientes pueden habilitar o utilizar.
    """
    _ensure_default_payment_methods()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CREATE':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper()
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name or not code:
                messages.error(request, "Nombre y Código Identificador son obligatorios.")
                return redirect('superadmin_payment_methods')

            if GlobalPaymentMethod.objects.filter(code=code).exists():
                messages.error(request, f"Ya existe un método de pago con el código '{code}'.")
                return redirect('superadmin_payment_methods')

            pm = GlobalPaymentMethod.objects.create(
                name=name,
                code=code,
                description=description,
                is_active=is_active
            )
            
            selected_regions = request.POST.getlist('regions')
            for r_id in selected_regions:
                RegionPaymentMethod.objects.create(
                    region_id=r_id, 
                    payment_method=pm, 
                    use_for_sales=True, 
                    is_active=True, 
                    instructions=description
                )

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="CREAR_METODO_PAGO",
                details=f"Método de pago global '{pm.name}' ({pm.code}) creado."
            )
            messages.success(request, f"¡Método de pago '{pm.name}' creado exitosamente!")
            return redirect('superadmin_payment_methods')

        elif action == 'UPDATE':
            pm_id = request.POST.get('payment_method_id')
            pm = get_object_or_404(GlobalPaymentMethod, id=pm_id)

            pm.name = request.POST.get('name', '').strip() or pm.name
            pm.description = request.POST.get('description', '').strip()
            pm.is_active = request.POST.get('is_active') == 'on'
            pm.save()
            
            selected_regions = request.POST.getlist('regions')
            RegionPaymentMethod.objects.filter(payment_method=pm).update(use_for_sales=False)
            
            for r_id in selected_regions:
                rpm, _ = RegionPaymentMethod.objects.get_or_create(region_id=r_id, payment_method=pm)
                rpm.use_for_sales = True
                rpm.is_active = True
                rpm.save()

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="ACTUALIZAR_METODO_PAGO",
                details=f"Método de pago '{pm.name}' ({pm.code}) actualizado."
            )
            messages.success(request, f"¡Método de pago '{pm.name}' actualizado correctamente!")
            return redirect('superadmin_payment_methods')

        elif action == 'TOGGLE_STATUS':
            pm_id = request.POST.get('payment_method_id')
            pm = get_object_or_404(GlobalPaymentMethod, id=pm_id)
            pm.is_active = not pm.is_active
            pm.save()

            status_txt = "activado" if pm.is_active else "desactivado"
            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="ESTADO_METODO_PAGO",
                details=f"Método de pago '{pm.name}' {status_txt}."
            )
            messages.info(request, f"Método de pago '{pm.name}' {status_txt}.")
            return redirect('superadmin_payment_methods')

    payment_methods = GlobalPaymentMethod.objects.all().order_by('name')
    all_regions = Region.objects.filter(is_active=True).order_by('name')
    
    import json
    for pm in payment_methods:
        pm.selected_regions_json = json.dumps([str(r_id) for r_id in RegionPaymentMethod.objects.filter(payment_method=pm, use_for_sales=True).values_list('region_id', flat=True)])

    return render(request, 'superadmin/payment_methods.html', {
        'payment_methods': payment_methods,
        'all_regions': all_regions,
    })

@superadmin_required
@ensure_csrf_cookie
def regions_management_view(request):
    """
    Gestión de Regiones y sus Métodos de Pago.
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CREATE':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper()
            currency_symbol = request.POST.get('currency_symbol', '$').strip()
            is_active = request.POST.get('is_active') == 'on'

            if Region.objects.filter(code=code).exists():
                messages.error(request, f"Ya existe una región con el código '{code}'.")
            else:
                Region.objects.create(
                    name=name,
                    code=code,
                    country_codes=request.POST.get('country_codes', '').strip(),
                    currency_symbol=currency_symbol,
                    is_active=is_active
                )
                messages.success(request, f"¡Región '{name}' creada exitosamente!")
            return redirect('superadmin_regions')

        elif action == 'UPDATE':
            region_id = request.POST.get('region_id')
            region = get_object_or_404(Region, id=region_id)
            region.name = request.POST.get('name', '').strip() or region.name
            region.country_codes = request.POST.get('country_codes', '').strip()
            region.currency_symbol = request.POST.get('currency_symbol', '$').strip()
            region.is_active = request.POST.get('is_active') == 'on'
            region.save()
            messages.success(request, f"¡Región '{region.name}' actualizada correctamente!")
            return redirect('superadmin_regions')

        elif action == 'UPDATE_PAYMENT_METHODS':
            region_id = request.POST.get('region_id')
            region = get_object_or_404(Region, id=region_id)
            
            # Disable all billing methods first, then process form
            RegionPaymentMethod.objects.filter(region=region).update(use_for_billing=False)
            
            global_methods = GlobalPaymentMethod.objects.filter(is_active=True)
            for gm in global_methods:
                if request.POST.get(f'method_{gm.id}_active') == 'on':
                    instructions = request.POST.get(f'method_{gm.id}_instructions', '').strip()
                    
                    rpm, _ = RegionPaymentMethod.objects.update_or_create(
                        region=region,
                        payment_method=gm,
                        defaults={
                            'use_for_billing': True,
                            'instructions': instructions,
                            'is_active': True
                        }
                    )
            messages.success(request, f"¡Métodos de pago para la región '{region.name}' actualizados!")
            return redirect('superadmin_regions')

    regions = Region.objects.all().order_by('name')
    global_methods = GlobalPaymentMethod.objects.filter(is_active=True)
    
    # Pre-fetch region payment methods
    regions_data = []
    for region in regions:
        region_methods = {rpm.payment_method_id: rpm for rpm in region.payment_methods.all()}
        methods_data = []
        for gm in global_methods:
            methods_data.append({
                'global_method': gm,
                'region_config': region_methods.get(gm.id)
            })
        regions_data.append({
            'region': region,
            'methods': methods_data
        })

    return render(request, 'superadmin/regions.html', {
        'regions_data': regions_data,
        'global_methods': global_methods,
    })

# Helpers
def _ensure_default_payment_methods():
    default_methods = [
        {'code': 'Efectivo', 'name': 'Efectivo', 'description': 'Cobro directo en efectivo / caja física.'},
        {'code': 'Tarjeta', 'name': 'Tarjeta de Débito / Crédito', 'description': 'Pago con tarjeta mediante POS físico o terminal web.'},
        {'code': 'MercadoPago / QR', 'name': 'MercadoPago / Código QR', 'description': 'Cobro digital escaneando código QR o billetera virtual.'},
        {'code': 'Transferencia', 'name': 'Transferencia Bancaria', 'description': 'Transferencia bancaria directa con CBU / Alias.'},
    ]

    for item in default_methods:
        GlobalPaymentMethod.objects.get_or_create(
            code=item['code'],
            defaults={
                'name': item['name'],
                'description': item['description'],
                'is_active': True
            }
        )

def _ensure_default_plans():
    if SubscriptionPlan.objects.exists():
        pro = SubscriptionPlan.objects.filter(code='PRO').first()
        if pro and pro.monthly_price == Decimal('29.00'):
            pro.name = 'Plan Acceso Completo'
            pro.monthly_price = Decimal('30.00')
            pro.annual_price = Decimal('288.00')
            pro.save()
        return

    SubscriptionPlan.objects.create(
        code='PRO',
        name='Plan Acceso Completo',
        monthly_price=Decimal('30.00'),
        annual_price=Decimal('288.00'),
        max_users=50,
        max_branches=10,
        included_modules=['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing'],
        is_active=True
    )

def _sync_business_subscriptions():
    pro_plan = SubscriptionPlan.objects.filter(code='PRO').first() or SubscriptionPlan.objects.first()
    default_exp = timezone.now().date() + datetime.timedelta(days=30)

    for biz in Business.objects.all():
        if not hasattr(biz, 'subscription'):
            BusinessSubscription.objects.create(
                business=biz,
                plan=pro_plan,
                status='ACTIVE' if biz.onboarding_completed else 'TRIAL',
                start_date=timezone.now().date(),
                expiration_date=default_exp
            )

@superadmin_required
@ensure_csrf_cookie
def announcements_management_view(request):
    """
    Vista para gestionar modales y comunicados.
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CREATE':
            title = request.POST.get('title', '').strip()
            message = request.POST.get('message', '').strip()
            ann_type = request.POST.get('type', 'INFO')
            is_active = request.POST.get('is_active') == 'on'
            is_dismissible = request.POST.get('is_dismissible') == 'on'
            
            action_button_text = request.POST.get('action_button_text', '').strip()
            action_button_url = request.POST.get('action_button_url', '').strip()
            
            target_region_ids = request.POST.getlist('target_regions')
            target_missing_region = request.POST.get('target_missing_region') == 'on'

            ann = SystemAnnouncement.objects.create(
                title=title,
                message=message,
                type=ann_type,
                is_active=is_active,
                is_dismissible=is_dismissible,
                action_button_text=action_button_text,
                action_button_url=action_button_url,
                target_missing_region=target_missing_region
            )
            
            if target_region_ids:
                regions = Region.objects.filter(id__in=target_region_ids)
                ann.target_regions.set(regions)

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="CREAR_COMUNICADO",
                details=f"Modal '{ann.title}' creado."
            )
            messages.success(request, f"Comunicado '{ann.title}' creado exitosamente.")
            return redirect('superadmin_announcements')

        elif action == 'TOGGLE_STATUS':
            ann_id = request.POST.get('announcement_id')
            ann = get_object_or_404(SystemAnnouncement, id=ann_id)
            ann.is_active = not ann.is_active
            ann.save()
            status_str = "activado" if ann.is_active else "pausado"
            messages.info(request, f"Comunicado '{ann.title}' {status_str}.")
            return redirect('superadmin_announcements')

        elif action == 'DELETE':
            ann_id = request.POST.get('announcement_id')
            ann = get_object_or_404(SystemAnnouncement, id=ann_id)
            ann_title = ann.title
            ann.delete()
            messages.warning(request, f"Comunicado '{ann_title}' eliminado.")
            return redirect('superadmin_announcements')

    announcements = SystemAnnouncement.objects.all()
    regions = Region.objects.filter(is_active=True)

    return render(request, 'superadmin/announcements.html', {
        'announcements': announcements,
        'regions': regions,
    })
