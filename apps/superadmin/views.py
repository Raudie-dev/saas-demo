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
from apps.superadmin.models import SubscriptionPlan, BusinessSubscription, SystemAuditLog

from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import authenticate, login, logout

def is_super_admin(user):
    # Check if user is staff/superuser or has OWNER/ADMIN role
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role in ['OWNER', 'ADMIN'])

@ensure_csrf_cookie
def superadmin_login_view(request):
    if request.user.is_authenticated and is_super_admin(request.user):
        return redirect('superadmin_dashboard')

    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user_obj = User.objects.filter(email__iexact=username_or_email).first() or User.objects.filter(username__iexact=username_or_email).first()
        
        if user_obj:
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None and is_super_admin(user):
                login(request, user)
                SystemAuditLog.objects.create(
                    actor_email=user.email or user.username,
                    action="SUPERADMIN_LOGIN",
                    details="Inicio de sesión exitoso en el Panel SuperAdmin"
                )
                messages.success(request, f"¡Bienvenido al Panel SuperAdmin, {user.first_name or user.username}!")
                return redirect('superadmin_dashboard')

        messages.error(request, "Acceso denegado. Credenciales de SuperAdmin incorrectas o permisos insuficientes.")

    return render(request, 'superadmin/login.html')

def superadmin_logout_view(request):
    logout(request)
    messages.info(request, "Sesión de SuperAdmin cerrada correctamente.")
    return redirect('superadmin_login')

@login_required(login_url='superadmin_login')
@user_passes_test(is_super_admin, login_url='superadmin_login')
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

@login_required(login_url='superadmin_login')
@user_passes_test(is_super_admin, login_url='superadmin_login')
@ensure_csrf_cookie
def subscriptions_list_view(request):
    _ensure_default_plans()
    _sync_business_subscriptions()

    status_filter = request.GET.get('status', 'ALL')
    query = request.GET.get('q', '').strip()

    subscriptions = BusinessSubscription.objects.select_related('business', 'plan').all()

    if status_filter != 'ALL':
        subscriptions = subscriptions.filter(status=status_filter)

    if query:
        subscriptions = subscriptions.filter(business__name__icontains=query)

    plans = SubscriptionPlan.objects.filter(is_active=True)
    all_businesses = Business.objects.all().order_by('name')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CREATE_CUSTOM':
            biz_id = request.POST.get('business_id')
            sub_id = request.POST.get('subscription_id')
            status = request.POST.get('status', 'TRIAL')
            plan_id = request.POST.get('plan_id')
            duration_type = request.POST.get('duration_type', 'DAYS')
            custom_days = request.POST.get('custom_days')
            expiration_date_str = request.POST.get('expiration_date')
            notes = request.POST.get('notes', '').strip()

            sub = None
            if sub_id:
                sub = get_object_or_404(BusinessSubscription, id=sub_id)
            elif biz_id:
                biz = get_object_or_404(Business, id=biz_id)
                sub = getattr(biz, 'subscription', None)
                if not sub:
                    sub = BusinessSubscription.objects.create(
                        business=biz,
                        start_date=timezone.now().date(),
                        expiration_date=timezone.now().date() + datetime.timedelta(days=14)
                    )

            if not sub:
                messages.error(request, "Debe seleccionar una agencia o suscripción válida.")
                return redirect('superadmin_subscriptions')

            sub.status = status
            if plan_id:
                sub.plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            else:
                sub.plan = None

            if duration_type == 'DATE' and expiration_date_str:
                try:
                    sub.expiration_date = datetime.datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif duration_type == 'DAYS' and custom_days:
                days_int = int(custom_days)
                sub.expiration_date = timezone.now().date() + datetime.timedelta(days=days_int)

            if notes:
                sub.notes = notes

            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="GESTION_LICENCIA",
                details=f"Licencia configurada para {sub.business.name} (Estado: {sub.get_status_display()}, Vence: {sub.expiration_date})"
            )
            messages.success(request, f"¡Licencia configurada exitosamente para {sub.business.name}!")
            return redirect('superadmin_subscriptions')

        elif action == 'REGENERATE_TOKEN':
            sub_id = request.POST.get('subscription_id')
            sub = get_object_or_404(BusinessSubscription, id=sub_id)
            sub.license_key = uuid.uuid4()
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="REGENERAR_TOKEN",
                details=f"Token de licencia regenerado para {sub.business.name}"
            )
            messages.success(request, f"¡Nuevo Token de Licencia generado para {sub.business.name}!")
            return redirect('superadmin_subscriptions')

        sub_id = request.POST.get('subscription_id')
        sub = get_object_or_404(BusinessSubscription, id=sub_id)

        if action == 'ACTIVATE':
            sub.status = 'ACTIVE'
            plan_id = request.POST.get('plan_id')
            if plan_id:
                sub.plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            # Extend 30 days from now
            sub.expiration_date = timezone.now().date() + datetime.timedelta(days=30)
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="ACTIVACION_LICENCIA",
                details=f"Licencia activada para {sub.business.name} (Plan: {sub.plan.name if sub.plan else 'Estándar'})"
            )
            messages.success(request, f"¡Licencia activada exitosamente para {sub.business.name}!")

        elif action == 'EXTEND_TRIAL':
            days = int(request.POST.get('days', 15))
            sub.status = 'TRIAL'
            current_exp = sub.expiration_date if sub.expiration_date and sub.expiration_date > timezone.now().date() else timezone.now().date()
            sub.expiration_date = current_exp + datetime.timedelta(days=days)
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="EXTENSION_PRUEBA",
                details=f"Prueba extendida por {days} días para {sub.business.name}"
            )
            messages.success(request, f"Período de prueba extendido por {days} días para {sub.business.name}.")

        elif action == 'SUSPEND':
            sub.status = 'SUSPENDED'
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="SUSPENSION_CUENTA",
                details=f"Cuenta suspendida para {sub.business.name}"
            )
            messages.warning(request, f"La cuenta de {sub.business.name} ha sido suspendida.")

        elif action == 'CHANGE_PLAN':
            plan_id = request.POST.get('plan_id')
            new_plan = get_object_or_404(SubscriptionPlan, id=plan_id)
            sub.plan = new_plan
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="CAMBIO_PLAN",
                details=f"Plan de {sub.business.name} actualizado a {new_plan.name}"
            )
            messages.success(request, f"Plan de {sub.business.name} actualizado a {new_plan.name}.")

        return redirect('superadmin_subscriptions')

    from django.core.paginator import Paginator
    paginator = Paginator(subscriptions.order_by('-updated_at'), 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/subscriptions.html', {
        'subscriptions': page_obj,
        'page_obj': page_obj,
        'plans': plans,
        'all_businesses': all_businesses,
        'status_filter': status_filter,
        'query': query,
    })

@login_required(login_url='superadmin_login')
@user_passes_test(is_super_admin, login_url='superadmin_login')
@ensure_csrf_cookie
def businesses_list_view(request):
    _ensure_default_plans()
    _sync_business_subscriptions()

    plans = SubscriptionPlan.objects.filter(is_active=True)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'CREATE_CUSTOM':
            biz_id = request.POST.get('business_id')
            sub_id = request.POST.get('subscription_id')
            status = request.POST.get('status', 'TRIAL')
            plan_id = request.POST.get('plan_id')
            duration_type = request.POST.get('duration_type', 'DAYS')
            custom_days = request.POST.get('custom_days')
            expiration_date_str = request.POST.get('expiration_date')
            notes = request.POST.get('notes', '').strip()

            sub = None
            if sub_id:
                sub = BusinessSubscription.objects.filter(id=sub_id).first()
            if not sub and biz_id:
                biz = get_object_or_404(Business, id=biz_id)
                sub = getattr(biz, 'subscription', None)
                if not sub:
                    sub = BusinessSubscription.objects.create(
                        business=biz,
                        start_date=timezone.now().date(),
                        expiration_date=timezone.now().date() + datetime.timedelta(days=14)
                    )

            if sub:
                sub.status = status
                if plan_id:
                    sub.plan = SubscriptionPlan.objects.filter(id=plan_id).first()
                else:
                    sub.plan = None

                if duration_type == 'DATE' and expiration_date_str:
                    try:
                        sub.expiration_date = datetime.datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                elif duration_type == 'DAYS' and custom_days:
                    days_int = int(custom_days)
                    sub.expiration_date = timezone.now().date() + datetime.timedelta(days=days_int)

                if notes:
                    sub.notes = notes

                sub.save()

                SystemAuditLog.objects.create(
                    actor_email=request.user.email or request.user.username,
                    action="GESTION_LICENCIA",
                    details=f"Licencia actualizada para {sub.business.name} (Estado: {sub.get_status_display()}, Vence: {sub.expiration_date})"
                )
                messages.success(request, f"¡Licencia actualizada exitosamente para {sub.business.name}!")
                return redirect('superadmin_businesses')

        elif action == 'REGENERATE_TOKEN':
            sub_id = request.POST.get('subscription_id')
            sub = get_object_or_404(BusinessSubscription, id=sub_id)
            sub.license_key = uuid.uuid4()
            sub.save()

            SystemAuditLog.objects.create(
                actor_email=request.user.email or request.user.username,
                action="REGENERAR_TOKEN",
                details=f"Token de licencia regenerado para {sub.business.name}"
            )
            messages.success(request, f"¡Nuevo Token de Licencia generado para {sub.business.name}!")
            return redirect('superadmin_businesses')

    query = request.GET.get('q', '').strip()
    businesses = Business.objects.prefetch_related('subscription', 'branches', 'users').all()

    if query:
        businesses = businesses.filter(name__icontains=query)

    from django.core.paginator import Paginator
    paginator = Paginator(businesses.order_by('-created_at'), 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'superadmin/businesses.html', {
        'businesses': page_obj,
        'page_obj': page_obj,
        'query': query,
        'plans': plans,
    })

@login_required(login_url='superadmin_login')
@user_passes_test(is_super_admin, login_url='superadmin_login')
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
                SubscriptionPlan.objects.create(
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

    return render(request, 'superadmin/plans.html', {
        'plans': plans,
        'all_modules': all_modules
    })

# Helpers
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
