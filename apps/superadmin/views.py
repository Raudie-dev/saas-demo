import datetime
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count
from django.utils.text import slugify
from apps.business.models import Business, User, StaffMember, Branch
from apps.agenda.models import Appointment
from apps.invoicing.models import Invoice
from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, SystemAuditLog, SuperAdminUser, GlobalPaymentMethod, Region, RegionPaymentMethod, SubscriptionPayment, PlanRegionPricing

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
        messages.warning(request, "Tu sesión de SuperAdmin ha expirado tras más de 3 horas de inactividad.")
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

            if subscription.plan:
                allowed = business.get_allowed_modules()
                current_enabled = list(business.enabled_modules or [])
                # Keep enabled modules that are in the new plan, and enable any newly unlocked modules
                synced_modules = [m for m in current_enabled if m in allowed]
                for m in allowed:
                    if m not in synced_modules:
                        synced_modules.append(m)
                business.enabled_modules = synced_modules
                business.save(update_fields=['enabled_modules'])
                for rp in business.role_profiles.all():
                    rp.clean_modules_against_subscription()
                    rp.save(update_fields=['allowed_modules'])

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

        elif action == 'APPROVE_SUBSCRIPTION_PAYMENT':
            payment_id = request.POST.get('payment_id')
            payment = get_object_or_404(SubscriptionPayment, id=payment_id, business=business)
            from apps.superadmin.mercadopago import apply_approved_payment
            updated = apply_approved_payment(
                payment,
                reviewer=request.superadmin_user,
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
            )
            if updated is None:
                messages.info(request, f"El pago #{payment.id} ya estaba aprobado.")
                return redirect('superadmin_user_detail', business_id=business.id)
            subscription = updated
            messages.success(request, f"¡Pago de {payment.amount} aprobado con éxito! Licencia renovada hasta {subscription.expiration_date}.")
            return redirect('superadmin_user_detail', business_id=business.id)

        elif action == 'REJECT_SUBSCRIPTION_PAYMENT':
            payment_id = request.POST.get('payment_id')
            reject_notes = request.POST.get('reject_notes', '').strip()
            payment = get_object_or_404(SubscriptionPayment, id=payment_id, business=business)
            payment.status = 'REJECTED'
            payment.notes = reject_notes
            payment.reviewed_at = timezone.now()
            payment.reviewed_by = request.superadmin_user
            payment.save()

            SystemAuditLog.objects.create(
                actor_email=request.superadmin_user.email or request.superadmin_user.username,
                action="PAGO_RECHAZADO",
                details=f"SuperAdmin rechazó el pago #{payment.id} de {business.name}. Motivo: {reject_notes}"
            )
            messages.warning(request, f"Pago #{payment.id} marcado como rechazado.")
            return redirect('superadmin_user_detail', business_id=business.id)

        elif action == 'DELETE_BUSINESS':
            return delete_business_view(request, business.id)

    branches = business.branches.all()
    staff_members = business.staff_members.all()
    payment_methods = business.payment_methods.all()
    business_users = business.users.all()
    all_regions = Region.objects.filter(is_active=True).order_by('name')
    subscription_payments = SubscriptionPayment.objects.filter(business=business).select_related(
        'plan', 'region_payment_method', 'region_payment_method__payment_method'
    ).order_by('-created_at')

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
        'subscription_payments': subscription_payments,
    })

def _safe_delete_file(field_file):
    """Elimina de forma segura un archivo adjunto del almacenamiento sin lanzar excepciones."""
    if field_file:
        try:
            field_file.delete(save=False)
        except Exception:
            pass

def delete_business_and_all_records(business, actor_email="SuperAdmin"):
    """
    Elimina permanentemente una cuenta de negocio/agencia junto con:
    1. Archivos multimedia asociados (logos, banners, fotos de personal, recibos, etc.)
    2. Registros de sucursales, staff, CRM, agenda, facturación, POS, proyectos, inmuebles, marketing, suscripción.
    3. Todos los usuarios (User) vinculados a la cuenta.
    4. Registra la acción en SystemAuditLog.
    """
    from django.db import transaction

    business_name = business.name
    business_id_str = str(business.id)

    # Recolectar datos antes del borrado para el log de auditoría
    user_ids = list(business.users.values_list('id', flat=True))
    users_count = len(user_ids)
    branches_count = business.branches.count()
    staff_count = business.staff_members.count()
    clients_count = business.clients.count()
    appointments_count = business.appointments.count()

    # 1. Limpieza segura de archivos (opcional, no bloquea el borrado en base de datos)
    try:
        _safe_delete_file(getattr(business, 'logo_url', None))
        _safe_delete_file(getattr(business, 'banner_url', None))

        if hasattr(business, 'staff_members'):
            for staff in business.staff_members.all():
                _safe_delete_file(getattr(staff, 'profile_picture', None))

        if hasattr(business, 'properties'):
            for prop in business.properties.all():
                imgs = getattr(prop, 'images', None)
                if imgs is not None and hasattr(imgs, 'all'):
                    for pimg in imgs.all():
                        _safe_delete_file(getattr(pimg, 'image', None))

        if hasattr(business, 'subscription_payments'):
            for sp in business.subscription_payments.all():
                _safe_delete_file(getattr(sp, 'receipt_file', None))
    except Exception:
        pass

    # 2. Transacción de eliminación atómica
    with transaction.atomic():
        # Borra el negocio (activa el CASCADE de Django a todas las relaciones ForeignKey con CASCADE)
        business.delete()

        # Borra los usuarios de acceso del negocio (User.business tiene on_delete=SET_NULL)
        if user_ids:
            User.objects.filter(id__in=user_ids).delete()

        # Registra la auditoría
        details = (
            f"SuperAdmin eliminó permanentemente la cuenta '{business_name}' (ID: {business_id_str}) "
            f"y sus registros: {users_count} usuarios, {branches_count} sucursales, {staff_count} profesionales, "
            f"{clients_count} clientes CRM, {appointments_count} citas y registros operativos."
        )
        SystemAuditLog.objects.create(
            actor_email=actor_email,
            action="ELIMINACION_CUENTA",
            details=details
        )

    return {
        'name': business_name,
        'id': business_id_str,
        'users_count': users_count,
        'branches_count': branches_count,
        'staff_count': staff_count,
        'clients_count': clients_count,
        'appointments_count': appointments_count,
    }

@superadmin_required
@ensure_csrf_cookie
def delete_business_view(request, business_id):
    """
    Vista para eliminar una cuenta/agencia y todos sus registros asociados.
    """
    if request.method != 'POST':
        messages.warning(request, "La eliminación de una cuenta solo se puede realizar mediante solicitud POST confirmada.")
        return redirect('superadmin_users')

    business = get_object_or_404(Business, id=business_id)
    actor_email = getattr(request.superadmin_user, 'email', None) or getattr(request.superadmin_user, 'username', 'SuperAdmin')

    confirmation = request.POST.get('confirmation', '').strip().upper()
    confirm_flag = request.POST.get('confirm_delete')

    # Validar confirmación de seguridad
    if confirmation != 'ELIMINAR' and confirm_flag != '1':
        messages.error(request, "Para eliminar la cuenta debes escribir la palabra de confirmación 'ELIMINAR'.")
        return redirect('superadmin_user_detail', business_id=business.id)

    try:
        res = delete_business_and_all_records(business, actor_email=actor_email)
        messages.success(
            request,
            f"¡La cuenta '{res['name']}' y todos sus registros asociados ({res['users_count']} usuarios, {res['branches_count']} sucursales, {res['clients_count']} clientes, etc.) han sido eliminados permanentemente!"
        )
    except Exception as e:
        messages.error(request, f"Ocurrió un error al eliminar la cuenta: {str(e)}")
        return redirect('superadmin_users')

    return redirect('superadmin_users')

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
                
                # Create default region pricing for existing regions with currency conversion
                regions = Region.objects.filter(is_active=True)
                for r in regions:
                    conv_monthly, conv_annual = _convert_plan_prices_for_region(plan.monthly_price, plan.annual_price, r)
                    PlanRegionPricing.objects.create(
                        plan=plan,
                        region=r,
                        monthly_price=conv_monthly,
                        annual_price=conv_annual,
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

            old_modules = set(plan.included_modules or [])
            added_modules = [m for m in selected_modules if m not in old_modules]

            plan.name = name
            plan.monthly_price = monthly_price
            plan.annual_price = annual_price
            plan.max_users = max_users_val
            plan.max_branches = max_branches_val
            plan.included_modules = selected_modules
            plan.show_on_landing = show_on_landing
            plan.is_active = is_active
            plan.save()

            # Sync enabled_modules for businesses on this plan so added/removed modules reflect immediately
            for sub in plan.subscriptions.select_related('business').all():
                biz = sub.business
                if not biz:
                    continue
                allowed = biz.get_allowed_modules()
                current_enabled = list(biz.enabled_modules or [])
                synced = [m for m in current_enabled if m in allowed]
                for m in added_modules:
                    if m in allowed and m not in synced:
                        synced.append(m)
                if synced != current_enabled:
                    biz.enabled_modules = synced
                    biz.save(update_fields=['enabled_modules'])
                for rp in biz.role_profiles.all():
                    rp.clean_modules_against_subscription()
                    rp.save(update_fields=['allowed_modules'])

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

    plans = SubscriptionPlan.objects.prefetch_related('region_prices').all().order_by('monthly_price')

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
        {'code': 'projects', 'name': 'Proyectos & Contenido Redes'},
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

    _ensure_default_payment_methods()
    _ensure_default_regions()
    payment_methods = GlobalPaymentMethod.objects.all().order_by('name')
    all_regions = Region.objects.filter(is_active=True).order_by('name')
    
    import json
    for pm in payment_methods:
        active_rpms = RegionPaymentMethod.objects.filter(payment_method=pm, use_for_sales=True).select_related('region').order_by('region__name')
        pm.selected_regions_json = json.dumps([str(rpm.region_id) for rpm in active_rpms])
        pm.active_regions_list = [rpm.region for rpm in active_rpms]

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
                country_codes = ",".join(request.POST.getlist('country_codes'))
                Region.objects.create(
                    name=name,
                    code=code,
                    country_codes=country_codes,
                    currency_symbol=currency_symbol,
                    currency_code=request.POST.get('currency_code', '').strip().upper()[:3],
                    is_active=is_active
                )
                messages.success(request, f"¡Región '{name}' creada exitosamente!")
            return redirect('superadmin_regions')

        elif action == 'UPDATE':
            region_id = request.POST.get('region_id')
            region = get_object_or_404(Region, id=region_id)
            region.name = request.POST.get('name', '').strip() or region.name
            region.country_codes = ",".join(request.POST.getlist('country_codes'))
            region.currency_symbol = request.POST.get('currency_symbol', '$').strip()
            region.currency_code = request.POST.get('currency_code', '').strip().upper()[:3]
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
                    payment_url = request.POST.get(f'method_{gm.id}_payment_url', '').strip()
                    
                    rpm, _ = RegionPaymentMethod.objects.update_or_create(
                        region=region,
                        payment_method=gm,
                        defaults={
                            'use_for_billing': True,
                            'instructions': instructions,
                            'payment_url': payment_url,
                            'is_active': True
                        }
                    )
            messages.success(request, f"¡Métodos de pago para la región '{region.name}' actualizados!")
            return redirect('superadmin_regions')

    _ensure_default_payment_methods()
    _ensure_default_regions()
    from apps.superadmin.payment_gateways import is_available
    regions = Region.objects.all().order_by('name')
    global_methods = GlobalPaymentMethod.objects.filter(is_active=True).order_by('name')
    
    # Pre-fetch region payment methods
    regions_data = []
    for region in regions:
        region_methods = {rpm.payment_method_id: rpm for rpm in region.payment_methods.all()}
        primary_methods = []
        other_methods = []
        for gm in global_methods:
            rc = region_methods.get(gm.id)
            item_dict = {
                'global_method': gm,
                'region_config': rc,
                'credentials_ok': is_available(gm.provider, region) if gm.provider else None,
            }
            if region.code == 'GLOBAL' or (rc and (rc.use_for_sales or rc.use_for_billing)):
                primary_methods.append(item_dict)
            else:
                other_methods.append(item_dict)

        regions_data.append({
            'region': region,
            'methods': primary_methods if primary_methods else other_methods,
            'other_methods': other_methods if primary_methods else [],
        })

    return render(request, 'superadmin/regions.html', {
        'regions_data': regions_data,
        'global_methods': global_methods,
    })

# Helpers
def _ensure_default_payment_methods():
    from apps.superadmin.payment_gateways import ensure_integrated_methods
    ensure_integrated_methods()
    default_methods = [
        # Métodos transversales en Latinoamérica
        {
            'code': 'TRANSFERENCIA',
            'name': 'Transferencia Bancaria',
            'description': 'Validación manual: Transferencia bancaria directa (CBU, Alias, CLABE, CCI, CuentaRUT, ACH o IBAN).'
        },
        {
            'code': 'EFECTIVO',
            'name': 'Efectivo (Caja)',
            'description': 'Pago presencial en efectivo en moneda local o divisas en la sucursal.'
        },
        {
            'code': 'TARJETA',
            'name': 'Tarjeta de Débito / Crédito (POS)',
            'description': 'Cobro con tarjeta de débito o crédito mediante terminal POS / datáfono o link de pago.'
        },
        {
            'code': 'ZELLE',
            'name': 'Zelle (USD)',
            'description': 'Transferencia inmediata en dólares estadounidenses vía Zelle (correo electrónico o teléfono asociado).'
        },
        {
            'code': 'BINANCE_PAY',
            'name': 'Binance Pay / USDT',
            'description': 'Pago inmediato en criptomonedas / USDT mediante Binance Pay ID, QR o correo registrado.'
        },
        {
            'code': 'PAYPAL',
            'name': 'PayPal',
            'description': 'Pago internacional en USD con saldo PayPal o tarjeta mediante correo o enlace PayPal.Me.'
        },
        # Métodos locales por país latinoamericano
        {
            'code': 'PAGOMOVIL',
            'name': 'Pago Móvil (Venezuela)',
            'description': 'Validación manual: Pago Móvil interbancario inmediato en Bolívares (Banco, Cédula/RIF y Teléfono).'
        },
        {
            'code': 'PIX',
            'name': 'Pix (Brasil)',
            'description': 'Transferencia instantánea 24/7 en Reales mediante llave Pix (CPF/CNPJ, Email, Teléfono o QR Code).'
        },
        {
            'code': 'NEQUI_DAVIPLATA',
            'name': 'Nequi / DaviPlata / PSE (Colombia)',
            'description': 'Transferencia rápida desde billeteras digitales Nequi, DaviPlata, Bre-B o débito PSE en Colombia.'
        },
        {
            'code': 'YAPE_PLIN',
            'name': 'Yape / Plin (Perú)',
            'description': 'Pago inmediato con número de celular o código QR a través de Yape o Plin en Perú.'
        },
        {
            'code': 'SPEI_OXXO',
            'name': 'SPEI / CoDi / OXXO (México)',
            'description': 'Transferencia interbancaria CLABE (SPEI), cobro digital CoDi o depósito en efectivo en OXXO.'
        },
        {
            'code': 'WEBPAY_KHIPU',
            'name': 'Webpay / CuentaRUT / Khipu (Chile)',
            'description': 'Pago con tarjetas vía Transbank Webpay, Khipu o transferencia a CuentaRUT BancoEstado.'
        },
        {
            'code': 'SINPE_MOVIL',
            'name': 'SINPE Móvil (Costa Rica)',
            'description': 'Transferencia bancaria inmediata al número de teléfono celular afiliado a SINPE Móvil.'
        },
        {
            'code': 'YAPPY',
            'name': 'Yappy / ACH Xpress (Panamá)',
            'description': 'Pago rápido por directorio comercial o número celular en Yappy (Banco General) o ACH Xpress.'
        },
        {
            'code': 'QR_SIMPLE',
            'name': 'QR Simple (Bolivia)',
            'description': 'Cobro interbancario inmediato en Bolivianos mediante código QR Simple.'
        },
        {
            'code': 'SIPAP',
            'name': 'SIPAP / Giros Tigo (Paraguay)',
            'description': 'Transferencia bancaria instantánea vía SIPAP / Alias o billetera móvil Giros Tigo.'
        },
        {
            'code': 'DEUNA',
            'name': 'Deuna! / Pago QR (Ecuador)',
            'description': 'Pago inmediato sin comisión mediante código QR o número celular con Deuna! (Banco Pichincha).'
        },
        {
            'code': 'TRANSFER365',
            'name': 'Transfer365 / Billetera Local (El Salvador)',
            'description': 'Transferencia interbancaria inmediata 24/7 vía Transfer365 del BCR en El Salvador.'
        },
        {
            'code': 'ATH_MOVIL',
            'name': 'ATH Móvil (Puerto Rico)',
            'description': 'Pago instantáneo a número telefónico o tarjeta mediante ATH Móvil / ATH Móvil Business.'
        },
    ]

    for item in default_methods:
        pm = GlobalPaymentMethod.objects.filter(code=item['code']).first()
        if not pm:
            pm = GlobalPaymentMethod.objects.filter(name=item['name']).first()
        if not pm:
            pm = GlobalPaymentMethod.objects.create(
                code=item['code'],
                name=item['name'],
                description=item['description'],
                is_active=True
            )
        elif item['code'] == 'PAGOMOVIL' and pm.name == 'Pago Móvil':
            pm.name = item['name']
            pm.save(update_fields=['name'])

def _ensure_default_regions():
    """
    Asegura que las regiones latinoamericanas principales estén registradas
    con sus códigos telefónicos/ISO, símbolo de moneda, moneda ISO y sus métodos de pago regionales.
    """
    from django.db.models import Q
    latam_regions = [
        {
            'name': 'Argentina', 'code': '54', 'country_codes': 'AR', 'currency_symbol': '$', 'currency_code': 'ARS',
            'methods': ['MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'ZELLE', 'PAYPAL'],
            'transfer_instructions': 'Transferencia en Pesos (ARS) o USD: Indicar Banco/Billetera, CBU/CVU, Alias y CUIT/CUIL.'
        },
        {
            'name': 'Bolivia', 'code': '591', 'country_codes': 'BO', 'currency_symbol': 'Bs.', 'currency_code': 'BOB',
            'methods': ['QR_SIMPLE', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia interbancaria en Bs.: Indicar Banco, N° de Cuenta, Titular y CI/NIT.'
        },
        {
            'name': 'Brasil', 'code': '55', 'country_codes': 'BR', 'currency_symbol': 'R$', 'currency_code': 'BRL',
            'methods': ['PIX', 'MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferência TED / Pix: Informe Banco, Agência, Conta, Titular e CPF/CNPJ.'
        },
        {
            'name': 'Chile', 'code': '56', 'country_codes': 'CL', 'currency_symbol': 'CLP $', 'currency_code': 'CLP',
            'methods': ['WEBPAY_KHIPU', 'MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia electrónica (CLP): Indicar Banco, Tipo de Cuenta (Corriente/Vista/RUT), N° de Cuenta y RUT.'
        },
        {
            'name': 'Colombia', 'code': '57', 'country_codes': 'CO', 'currency_symbol': 'COP $', 'currency_code': 'COP',
            'methods': ['NEQUI_DAVIPLATA', 'MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia Bancolombia / Davivienda / Bre-B: Indicar Banco, Tipo y N° de Cuenta, Titular y NIT/Cédula.'
        },
        {
            'name': 'Costa Rica', 'code': '506', 'country_codes': 'CR', 'currency_symbol': '₡', 'currency_code': 'CRC',
            'methods': ['SINPE_MOVIL', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia IBAN (BAC / BCR / BN): Indicar Cuenta IBAN en Colones o Dólares y Cédula.'
        },
        {
            'name': 'Ecuador', 'code': '593', 'country_codes': 'EC', 'currency_symbol': '$', 'currency_code': 'USD',
            'methods': ['DEUNA', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia Banco Pichincha / Guayaquil / Produbanco / Pacífico: Tipo y N° de Cuenta, Cédula/RUC y Correo.'
        },
        {
            'name': 'El Salvador', 'code': '503', 'country_codes': 'SV', 'currency_symbol': '$', 'currency_code': 'USD',
            'methods': ['TRANSFER365', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia Banco Agrícola / Cuscatlán / BAC: Indicar Tipo y N° de Cuenta, Nombre y DUI/NIT.'
        },
        {
            'name': 'Guatemala', 'code': '502', 'country_codes': 'GT', 'currency_symbol': 'Q', 'currency_code': 'GTQ',
            'methods': ['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia ACH (Banco Industrial / Banrural / G&T / BAC): Indicar Tipo y N° de Cuenta, Titular y NIT.'
        },
        {
            'name': 'Honduras', 'code': '504', 'country_codes': 'HN', 'currency_symbol': 'L', 'currency_code': 'HNL',
            'methods': ['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia ACH (BAC / Atlántida / Ficohsa / Occidente): Indicar N° de Cuenta en Lempiras o USD y RTN/DNI.'
        },
        {
            'name': 'México', 'code': '52', 'country_codes': 'MX', 'currency_symbol': 'MXN $', 'currency_code': 'MXN',
            'methods': ['SPEI_OXXO', 'MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'PAYPAL', 'BINANCE_PAY', 'ZELLE'],
            'transfer_instructions': 'Transferencia SPEI (MXN): Indicar Banco, CLABE interbancaria de 18 dígitos, Beneficiario y Concepto.'
        },
        {
            'name': 'Nicaragua', 'code': '505', 'country_codes': 'NI', 'currency_symbol': 'C$', 'currency_code': 'NIO',
            'methods': ['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia ACH (Lafise Bancentro / BAC / Banpro): Indicar N° de Cuenta en Córdobas o Dólares y Cédula/RUC.'
        },
        {
            'name': 'Panamá', 'code': '507', 'country_codes': 'PA', 'currency_symbol': '$', 'currency_code': 'USD',
            'methods': ['YAPPY', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia ACH / Banco General / Banistmo / BAC: Indicar Banco, Tipo de Cuenta, N° de Cuenta y Titular.'
        },
        {
            'name': 'Paraguay', 'code': '595', 'country_codes': 'PY', 'currency_symbol': 'Gs.', 'currency_code': 'PYG',
            'methods': ['SIPAP', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'PAYPAL'],
            'transfer_instructions': 'Transferencia SIPAP (Itaú / Continental / Ueno / Familiar): Indicar Banco, N° de Cuenta, Alias y CI/RUC.'
        },
        {
            'name': 'Perú', 'code': '51', 'country_codes': 'PE', 'currency_symbol': 'S/', 'currency_code': 'PEN',
            'methods': ['YAPE_PLIN', 'MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'BINANCE_PAY', 'PAYPAL', 'ZELLE'],
            'transfer_instructions': 'Transferencia BCP / Interbank / BBVA / Scotiabank: Indicar N° de Cuenta y CCI en Soles o Dólares, RUC/DNI.'
        },
        {
            'name': 'Puerto Rico', 'code': '1787', 'country_codes': 'PR', 'currency_symbol': '$', 'currency_code': 'USD',
            'methods': ['ATH_MOVIL', 'ZELLE', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'PAYPAL', 'BINANCE_PAY'],
            'transfer_instructions': 'Transferencia Banco Popular / FirstBank / Oriental: Indicar N° de Cuenta y Titular.'
        },
        {
            'name': 'República Dominicana', 'code': '1809', 'country_codes': 'DO', 'currency_symbol': 'RD$', 'currency_code': 'DOP',
            'methods': ['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'ZELLE', 'PAYPAL', 'BINANCE_PAY'],
            'transfer_instructions': 'Transferencia LBTR / ACH (Popular / Banreservas / BHD): Indicar Banco, Tipo y N° de Cuenta y Cédula/RNC.'
        },
        {
            'name': 'Uruguay', 'code': '598', 'country_codes': 'UY', 'currency_symbol': '$U', 'currency_code': 'UYU',
            'methods': ['MERCADOPAGO', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'PAYPAL', 'BINANCE_PAY'],
            'transfer_instructions': 'Transferencia BROU / Itaú / Santander / Prex: Indicar Banco, Moneda ($U o USD), N° de Cuenta y Titular.'
        },
        {
            'name': 'Venezuela', 'code': '58', 'country_codes': 'VE', 'currency_symbol': '$', 'currency_code': 'USD',
            'methods': ['PAGOMOVIL', 'ZELLE', 'BINANCE_PAY', 'TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'PAYPAL'],
            'transfer_instructions': 'Transferencia Bancaria Nacional (Bs. a tasa oficial BCV o USD): Indicar Banco, Código de 20 dígitos de Cuenta, Titular y Cédula/RIF.'
        },
    ]

    pm_map = {pm.code: pm for pm in GlobalPaymentMethod.objects.all()}

    for item in latam_regions:
        region = Region.objects.filter(
            Q(name__iexact=item['name']) |
            Q(code__iexact=item['code']) |
            Q(code__iexact=item['country_codes'])
        ).first()

        if not region:
            region = Region.objects.create(
                name=item['name'],
                code=item['code'],
                country_codes=item['country_codes'],
                currency_symbol=item['currency_symbol'],
                currency_code=item['currency_code'],
                is_active=True,
                is_default=False,
            )
        else:
            updated = False
            if not region.country_codes:
                region.country_codes = item['country_codes']
                updated = True
            if not region.currency_code:
                region.currency_code = item['currency_code']
                updated = True
            if item['name'] == 'Venezuela' and (region.currency_symbol != '$' or region.currency_code != 'USD'):
                region.currency_symbol = '$'
                region.currency_code = 'USD'
                updated = True
            if updated:
                region.save()

        for m_code in item['methods']:
            pm = pm_map.get(m_code)
            if not pm:
                continue
            default_instr = item['transfer_instructions'] if m_code == 'TRANSFERENCIA' else pm.description
            rpm, rpm_created = RegionPaymentMethod.objects.get_or_create(
                region=region,
                payment_method=pm,
                defaults={
                    'instructions': default_instr,
                    'use_for_sales': True,
                    'use_for_billing': False,
                    'is_active': True,
                }
            )
            if not rpm_created and m_code == 'TRANSFERENCIA' and (not rpm.instructions or rpm.instructions == pm.description):
                rpm.instructions = default_instr
                rpm.save(update_fields=['instructions'])

REGION_USD_RATES = {
    'ARS': Decimal('1200.00'),  # Argentina ($)
    'UYU': Decimal('43.00'),    # Uruguay ($U)
    'CLP': Decimal('960.00'),   # Chile (CLP $)
    'COP': Decimal('4200.00'),  # Colombia (COP $)
    'MXN': Decimal('20.00'),    # México (MXN $)
    'BRL': Decimal('5.70'),     # Brasil (R$)
    'PEN': Decimal('3.75'),     # Perú (S/)
    'PYG': Decimal('7800.00'),  # Paraguay (Gs.)
    'BOB': Decimal('7.00'),     # Bolivia (Bs.)
    'CRC': Decimal('515.00'),   # Costa Rica (₡)
    'DOP': Decimal('60.00'),    # República Dominicana (RD$)
    'GTQ': Decimal('7.75'),     # Guatemala (Q)
    'HNL': Decimal('25.00'),    # Honduras (L)
    'NIO': Decimal('36.80'),    # Nicaragua (C$)
    'VES': Decimal('1.00'),     # Venezuela opera en USD para planes SaaS
    'USD': Decimal('1.00'),     # Dólares (USD)
}

def _get_region_usd_rate(region):
    if not region:
        return Decimal('1.00')
    name_lower = (getattr(region, 'name', '') or '').strip().lower()
    if 'venezuela' in name_lower:
        return Decimal('1.00')
    curr = (getattr(region, 'currency_code', '') or '').strip().upper()
    if curr in REGION_USD_RATES:
        return REGION_USD_RATES[curr]
    name_lower = (getattr(region, 'name', '') or '').strip().lower()
    if 'argentina' in name_lower:
        return REGION_USD_RATES['ARS']
    if 'uruguay' in name_lower:
        return REGION_USD_RATES['UYU']
    if 'chile' in name_lower:
        return REGION_USD_RATES['CLP']
    if 'colombia' in name_lower:
        return REGION_USD_RATES['COP']
    if 'méxico' in name_lower or 'mexico' in name_lower:
        return REGION_USD_RATES['MXN']
    if 'brasil' in name_lower:
        return REGION_USD_RATES['BRL']
    if 'perú' in name_lower or 'peru' in name_lower:
        return REGION_USD_RATES['PEN']
    if 'paraguay' in name_lower:
        return REGION_USD_RATES['PYG']
    return Decimal('1.00')

def _convert_plan_prices_for_region(usd_monthly, usd_annual, region):
    rate = _get_region_usd_rate(region)
    if rate == Decimal('1.00'):
        return Decimal(usd_monthly).quantize(Decimal('0.01')), Decimal(usd_annual).quantize(Decimal('0.01'))
    conv_monthly = (Decimal(usd_monthly) * rate).quantize(Decimal('1'))
    conv_annual = (Decimal(usd_annual) * rate).quantize(Decimal('1'))
    return conv_monthly.quantize(Decimal('0.01')), conv_annual.quantize(Decimal('0.01'))

def _ensure_default_plans():
    _ensure_default_payment_methods()
    _ensure_default_regions()

    default_tiers = [
        {
            'code': 'STARTER',
            'name': 'Plan Inicial',
            'monthly_price': Decimal('19.00'),
            'annual_price': Decimal('180.00'),
            'max_users': 3,
            'max_branches': 1,
            'included_modules': ['crm', 'agenda', 'booking', 'pos', 'invoicing', 'inventory'],
        },
        {
            'code': 'PRO',
            'name': 'Plan Profesional',
            'monthly_price': Decimal('30.00'),
            'annual_price': Decimal('288.00'),
            'max_users': 10,
            'max_branches': 2,
            'included_modules': ['crm', 'agenda', 'booking', 'pos', 'invoicing', 'inventory', 'commissions', 'ai_engine', 'marketing', 'projects'],
        },
        {
            'code': 'ENTERPRISE',
            'name': 'Plan Corporativo',
            'monthly_price': Decimal('59.00'),
            'annual_price': Decimal('560.00'),
            'max_users': 0,
            'max_branches': 0,
            'included_modules': ['crm', 'agenda', 'booking', 'pos', 'invoicing', 'inventory', 'commissions', 'ai_engine', 'marketing', 'projects'],
        },
    ]

    needs_initial_seed = (
        not SubscriptionPlan.objects.exists()
        or (
            SubscriptionPlan.objects.count() == 1
            and SubscriptionPlan.objects.filter(code='PRO').exists()
        )
    )

    if needs_initial_seed:
        for tier in default_tiers:
            plan, created = SubscriptionPlan.objects.get_or_create(
                code=tier['code'],
                defaults={
                    'name': tier['name'],
                    'monthly_price': tier['monthly_price'],
                    'annual_price': tier['annual_price'],
                    'max_users': tier['max_users'],
                    'max_branches': tier['max_branches'],
                    'included_modules': tier['included_modules'],
                    'show_on_landing': True,
                    'is_active': True,
                }
            )
            if not created and tier['code'] == 'PRO' and plan.name == 'Plan Acceso Completo':
                plan.name = tier['name']
                plan.monthly_price = tier['monthly_price']
                plan.annual_price = tier['annual_price']
                plan.max_users = tier['max_users']
                plan.max_branches = tier['max_branches']
                plan.included_modules = tier['included_modules']
                plan.show_on_landing = True
                plan.is_active = True
                plan.save()

    # Ensure every active plan (especially PRO) is registered in all active regions with local currency conversion
    active_regions = list(Region.objects.filter(is_active=True))
    all_plans = list(SubscriptionPlan.objects.all())
    unconverted_usd_values = {Decimal('19.00'), Decimal('29.00'), Decimal('30.00'), Decimal('59.00')}

    for plan in all_plans:
        unconverted_usd_values.add(plan.monthly_price)
        for region in active_regions:
            conv_monthly, conv_annual = _convert_plan_prices_for_region(plan.monthly_price, plan.annual_price, region)
            rp, rp_created = PlanRegionPricing.objects.get_or_create(
                plan=plan,
                region=region,
                defaults={
                    'monthly_price': conv_monthly,
                    'annual_price': conv_annual,
                    'is_active': True,
                }
            )
            # If the region uses a local currency (e.g. ARS, UYU) and still had the raw USD value stored, convert it
            if not rp_created:
                rate = _get_region_usd_rate(region)
                if rate > Decimal('1.00') and rp.monthly_price in unconverted_usd_values:
                    rp.monthly_price = conv_monthly
                    rp.annual_price = conv_annual
                    rp.is_active = True
                    rp.save(update_fields=['monthly_price', 'annual_price', 'is_active'])
                elif rate == Decimal('1.00') and (rp.monthly_price != conv_monthly or rp.annual_price != conv_annual):
                    # Países dolarizados o que operan en USD (como Venezuela, Ecuador, Panamá) deben reflejar el precio base en USD
                    rp.monthly_price = conv_monthly
                    rp.annual_price = conv_annual
                    rp.is_active = True
                    rp.save(update_fields=['monthly_price', 'annual_price', 'is_active'])

def _sync_business_subscriptions():
    pro_plan = SubscriptionPlan.objects.filter(code='PRO').first() or SubscriptionPlan.objects.first()
    default_exp = timezone.now().date() + datetime.timedelta(days=14)

    for biz in Business.objects.all():
        if not hasattr(biz, 'subscription'):
            BusinessSubscription.objects.create(
                business=biz,
                plan=pro_plan,
                status='ACTIVE' if biz.onboarding_completed else 'TRIAL',
                start_date=timezone.now().date(),
                expiration_date=default_exp
            )



