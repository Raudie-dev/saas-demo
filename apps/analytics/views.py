import datetime
import csv
from decimal import Decimal
from collections import defaultdict
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from apps.business.models import Business, StaffMember
from apps.pos.models import Sale, SaleItem
from apps.invoicing.models import Expense, Invoice, AccountReceivable, PaymentPlan, PaymentInstallment
from apps.projects.models import Project, ProjectTask
from apps.crm.models import Client
from apps.agenda.models import Appointment
from apps.inventory.models import Product

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.business.models import Business, StaffMember

@login_required
def dashboard_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
        
    today = datetime.date.today()
    user = request.user
    is_professional = getattr(user, 'is_restricted_professional', False)

    # Vista Especializada para Profesionales (Solo sus citas, comisiones y métricas personales)
    if is_professional:
        user_staff = getattr(user, 'staff_profile', None)
        if user_staff:
            today_appointments = Appointment.objects.filter(business=business, staff=user_staff, date=today).select_related('client', 'service')
            upcoming_appointments = today_appointments.order_by('start_time')
            pending_commissions = user_staff.pending_commissions
            base_salary = user_staff.base_salary
            estimated_total = user_staff.estimated_total_salary
            month_appointments_count = Appointment.objects.filter(
                business=business, staff=user_staff, status='COMPLETED', date__year=today.year, date__month=today.month
            ).count()
        else:
            today_appointments = Appointment.objects.none()
            upcoming_appointments = []
            pending_commissions = Decimal('0.00')
            base_salary = Decimal('0.00')
            estimated_total = Decimal('0.00')
            month_appointments_count = 0

        context = {
            'business': business,
            'is_professional_dashboard': True,
            'user_staff': user_staff,
            'today_appointments': today_appointments,
            'today_appointments_count': today_appointments.count(),
            'recent_appointments': upcoming_appointments,
            'pending_commissions': pending_commissions,
            'base_salary': base_salary,
            'estimated_total': estimated_total,
            'month_appointments_count': month_appointments_count,
        }
        return render(request, 'analytics/dashboard.html', context)
    
    # Vista General / Administrativa
    today_sales_qs = Sale.objects.filter(business=business, status='COMPLETED', created_at__date=today)
    today_sales = today_sales_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    today_sales_count = today_sales_qs.count()
    
    # Citas del día y próximas citas
    today_appointments = Appointment.objects.filter(business=business, date=today).select_related('client', 'staff', 'service')
    upcoming_appointments = today_appointments.order_by('start_time')
    
    # Clientes totales y Alertas de Stock
    total_clients = Client.objects.filter(business=business).count()
    low_stock_products = Product.objects.filter(business=business, stock__lte=5) if business.is_module_enabled('inventory') else Product.objects.none()
    
    # Proyectos activos si el módulo está habilitado
    active_projects = []
    active_projects_count = 0
    pending_tasks_count = 0
    completed_projects_count = 0
    if business.is_module_enabled('projects'):
        try:
            from apps.projects.models import Project, ProjectTask
            active_projects_qs = Project.objects.filter(business=business).exclude(status__in=['COMPLETED', 'CANCELLED'])
            active_projects_count = active_projects_qs.count()
            active_projects = list(active_projects_qs.select_related('client', 'responsible').order_by('-updated_at')[:5])
            pending_tasks_count = ProjectTask.objects.filter(project__business=business).exclude(status='DONE').count()
            completed_projects_count = Project.objects.filter(business=business, status='COMPLETED').count()
        except Exception:
            pass

    # Gráfico semanal de Ingresos y Citas (Últimos 7 días)
    chart_days = []
    sales_values = []
    app_values = []
    week_sales_total = Decimal('0.00')
    day_abbrs = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        d_sales = Sale.objects.filter(business=business, status='COMPLETED', created_at__date=d).aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        d_apps = Appointment.objects.filter(business=business, date=d).count()
        week_sales_total += d_sales
        sales_values.append(float(d_sales))
        app_values.append(d_apps)
        chart_days.append({
            'day': day_abbrs[d.weekday()],
            'date': d.strftime('%d/%m'),
            'sales': float(d_sales),
            'appointments': d_apps,
        })
    
    max_sales = max(sales_values) if sales_values and max(sales_values) > 0 else 1.0
    max_apps = max(app_values) if app_values and max(app_values) > 0 else 1.0
    for item in chart_days:
        item['sales_pct'] = max(12, int((item['sales'] / max_sales) * 85)) if item['sales'] > 0 else 12
        item['apps_pct'] = max(15, int((item['appointments'] / max_apps) * 95)) if item['appointments'] > 0 else 15

    # Actividad / Transacciones Recientes (combinando citas y ventas)
    recent_transactions = []
    for a in Appointment.objects.filter(business=business).select_related('client', 'service', 'staff').order_by('-date', '-start_time')[:5]:
        recent_transactions.append({
            'type': 'appointment',
            'title': a.client.full_name if a.client else 'Cliente General',
            'subtitle': f"{a.service.name if a.service else 'Cita'} • {a.staff.full_name if a.staff else 'Staff'}",
            'status': a.status,
            'status_label': a.get_status_display() or 'Confirmada',
            'status_color': 'emerald' if a.status == 'COMPLETED' else ('blue' if a.status in ['CONFIRMED', 'PENDING'] else 'rose'),
            'amount': a.total_price or Decimal('0.00'),
            'date': a.date,
            'time': a.start_time.strftime('%H:%M') if a.start_time else '',
            'icon': 'calendar',
            'icon_bg': 'bg-rose-50 text-rose-900 border-rose-200',
        })
    for s in Sale.objects.filter(business=business).select_related('client').order_by('-created_at')[:5]:
        recent_transactions.append({
            'type': 'sale',
            'title': s.client.full_name if s.client else 'Venta Mostrador POS',
            'subtitle': f"Recibo #{s.id} • {s.get_payment_method_display() if hasattr(s, 'get_payment_method_display') else 'Caja'}",
            'status': s.status,
            'status_label': 'Completada' if s.status == 'COMPLETED' else s.status,
            'status_color': 'emerald' if s.status == 'COMPLETED' else 'amber',
            'amount': s.total_amount or Decimal('0.00'),
            'date': s.created_at.date() if s.created_at else today,
            'time': s.created_at.strftime('%H:%M') if s.created_at else '',
            'icon': 'shopping-bag',
            'icon_bg': 'bg-emerald-50 text-emerald-800 border-emerald-200',
        })
    recent_transactions.sort(key=lambda x: (x['date'], x['time']), reverse=True)
    recent_transactions = recent_transactions[:6]

    # Donut Performance Data
    month_start = today.replace(day=1)
    month_appointments_total = Appointment.objects.filter(business=business, date__gte=month_start).count()
    month_sales_total = Sale.objects.filter(business=business, created_at__date__gte=month_start).count()
    total_perf = month_appointments_total + month_sales_total + (active_projects_count if business.is_module_enabled('projects') else total_clients)
    if total_perf == 0:
        total_perf = 1
    donut_citas_pct = int((month_appointments_total / total_perf) * 100) if month_appointments_total > 0 else 35
    donut_sales_pct = int((month_sales_total / total_perf) * 100) if month_sales_total > 0 else 40
    donut_other_pct = max(10, 100 - (donut_citas_pct + donut_sales_pct))
    total_perf_count = month_appointments_total + month_sales_total + active_projects_count

    # Propiedades activas si es inmobiliaria
    active_properties = []
    active_properties_count = 0
    if False:
        try:
            from apps.properties.models import Property
            active_props_qs = Property.objects.filter(business=business, status='AVAILABLE')
            active_properties_count = active_props_qs.count()
            active_properties = list(active_props_qs.order_by('-is_featured', '-created_at')[:5])
        except Exception:
            pass

    # Ocupación de Agenda %
    total_staff_count = StaffMember.objects.filter(business=business, is_active=True).count()
    max_daily_capacity = (total_staff_count * 8) if total_staff_count > 0 else 1
    agenda_occupancy_pct = min(100, int((today_appointments.count() / max_daily_capacity) * 100)) if total_staff_count > 0 else 0

    context = {
        'business': business,
        'is_professional_dashboard': False,
        'today_sales': today_sales,
        'today_sales_count': today_sales_count,
        'week_sales_total': week_sales_total,
        'today_appointments': today_appointments,
        'today_appointments_count': today_appointments.count(),
        'recent_appointments': upcoming_appointments,
        'total_clients': total_clients,
        'low_stock_count': low_stock_products.count(),
        'low_stock_products': low_stock_products,
        'active_projects': active_projects,
        'active_projects_count': active_projects_count,
        'pending_tasks_count': pending_tasks_count,
        'completed_projects_count': completed_projects_count,
        'active_properties': active_properties,
        'active_properties_count': active_properties_count,
        'agenda_occupancy_pct': agenda_occupancy_pct,
        'chart_days': chart_days,
        'recent_transactions': recent_transactions,
        'donut_citas_pct': donut_citas_pct,
        'donut_sales_pct': donut_sales_pct,
        'donut_other_pct': donut_other_pct,
        'total_perf_count': total_perf_count,
    }
    return render(request, 'analytics/dashboard.html', context)

import calendar

def get_filtered_analytics_data(business, request):
    preset = request.GET.get('preset', 'this_month')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    staff_id = request.GET.get('staff_id')
    status_filter = request.GET.get('status', 'ALL')

    today = datetime.date.today()
    start_date = None
    end_date = None

    if preset == 'today':
        start_date = today
        end_date = today
    elif preset == 'this_week':
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = today
    elif preset == 'this_month':
        start_date = today.replace(day=1)
        end_date = today
    elif preset == 'this_year':
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif preset == 'custom' and start_date_str and end_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today.replace(day=1)
            end_date = today
    else:
        preset = 'this_month'
        start_date = today.replace(day=1)
        end_date = today

    # Base Sales Query
    sales_qs = Sale.objects.filter(business=business)
    if start_date and end_date:
        sales_qs = sales_qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
    if staff_id:
        sales_qs = sales_qs.filter(staff_id=staff_id)
    if status_filter != 'ALL':
        sales_qs = sales_qs.filter(status=status_filter)

    completed_sales = sales_qs.filter(status='COMPLETED')
    total_sales = completed_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    sales_count = completed_sales.count()
    avg_ticket = (total_sales / sales_count) if sales_count > 0 else Decimal('0.00')

    # Base Expenses Query
    expenses_qs = Expense.objects.filter(business=business)
    if start_date and end_date:
        expenses_qs = expenses_qs.filter(issue_date__gte=start_date, issue_date__lte=end_date)
    total_expenses = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    net_profit = total_sales - total_expenses

    # Invoicing breakdown for period
    invoices_qs = Invoice.objects.filter(business=business)
    if start_date and end_date:
        invoices_qs = invoices_qs.filter(issue_date__gte=start_date, issue_date__lte=end_date)
    
    invoices_paid = invoices_qs.filter(status='PAID').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    invoices_issued = invoices_qs.filter(status__in=['ISSUED', 'PARTIAL']).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    invoices_overdue = invoices_qs.filter(status='OVERDUE').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    accounts_receivable = AccountReceivable.objects.filter(business=business, status='PENDING').aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
    accounts_payable = Expense.objects.filter(business=business, status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Integración con el Módulo de Cobranzas / Cuotas (PaymentInstallment & PaymentPlan)
    installments_all = PaymentInstallment.objects.filter(business=business)
    
    # Cuotas cobradas en el período filtrado
    installments_paid_qs = installments_all.filter(status='PAID')
    if start_date and end_date:
        installments_paid_qs = installments_paid_qs.filter(paid_date__gte=start_date, paid_date__lte=end_date)
    installments_collected_period = installments_paid_qs.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
    installments_paid_count = installments_paid_qs.count()

    # Cuentas por cobrar en Cuotas (Pendientes o Parciales activas)
    installments_pending_qs = installments_all.exclude(status__in=['PAID', 'CANCELLED'])
    installments_receivable = sum((i.balance for i in installments_pending_qs), Decimal('0.00'))
    installments_pending_count = installments_pending_qs.count()

    # Si hay cuotas activas, enriquecer las cuentas por cobrar totales
    if installments_receivable > Decimal('0.00'):
        accounts_receivable = accounts_receivable + installments_receivable

    # Cuotas Vencidas / En Mora
    installments_overdue_qs = installments_all.filter(status__in=['PENDING', 'PARTIAL'], due_date__lt=today)
    installments_overdue_amount = sum((i.balance for i in installments_overdue_qs), Decimal('0.00'))
    installments_overdue_count = installments_overdue_qs.count()

    # Próximas cuotas a vencer (Próximos 7 y 30 días)
    installments_7d_qs = installments_all.filter(status__in=['PENDING', 'PARTIAL'], due_date__gte=today, due_date__lte=today + datetime.timedelta(days=7))
    installments_7d_amount = sum((i.balance for i in installments_7d_qs), Decimal('0.00'))
    installments_7d_count = installments_7d_qs.count()

    installments_upcoming_30d_qs = installments_all.filter(
        status__in=['PENDING', 'PARTIAL'],
        due_date__gte=today,
        due_date__lte=today + datetime.timedelta(days=30)
    ).select_related('client', 'project', 'plan').order_by('due_date')
    installments_upcoming_30d_amount = sum((i.balance for i in installments_upcoming_30d_qs), Decimal('0.00'))
    installments_upcoming_30d_count = installments_upcoming_30d_qs.count()

    # Planes de cobro activos
    payment_plans_active = PaymentPlan.objects.filter(business=business, status='ACTIVE').select_related('client', 'project').prefetch_related('installments')
    payment_plans_active_count = payment_plans_active.count()
    payment_plans_total_amount = payment_plans_active.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    payment_plans_collected = sum((p.amount_paid for p in payment_plans_active), Decimal('0.00'))
    payment_plans_pending = sum((p.balance_pending for p in payment_plans_active), Decimal('0.00'))

    upcoming_installments_list = list(installments_upcoming_30d_qs[:10])

    # Integración con el Módulo de Proyectos
    projects_all = Project.objects.filter(business=business)
    active_projects_qs = projects_all.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).select_related('client', 'responsible')
    active_projects_count = active_projects_qs.count()
    active_projects_budget = active_projects_qs.aggregate(total=Sum('budget'))['total'] or Decimal('0.00')
    completed_projects_count = projects_all.filter(status='COMPLETED').count()

    # Cobrado en proyectos vs saldo pendiente
    project_installments = installments_all.filter(project__isnull=False)
    project_installments_collected = project_installments.filter(status='PAID').aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
    project_installments_pending = sum((i.balance for i in project_installments.exclude(status__in=['PAID', 'CANCELLED'])), Decimal('0.00'))

    # Top Proyectos por Presupuesto
    top_projects = list(projects_all.order_by('-budget')[:5])
    top_projects_labels = [p.name for p in top_projects]
    top_projects_data = [float(p.budget) for p in top_projects]

    # Dynamic Payment Methods breakdown based on real sales and SalePayment records
    pm_totals = defaultdict(Decimal)
    completed_sales_with_payments = completed_sales.prefetch_related('payments')
    for s in completed_sales_with_payments:
        pm_list = list(s.payments.all())
        if pm_list:
            for p in pm_list:
                pm_name = (p.payment_method or '').strip() or 'Otros'
                pm_totals[pm_name] += (p.amount or Decimal('0.00'))
        else:
            pm_name = (s.payment_method or '').strip() or 'Efectivo'
            pm_totals[pm_name] += (s.total_amount or Decimal('0.00'))

    pm_cash = Decimal('0.00')
    pm_card = Decimal('0.00')
    pm_qr = Decimal('0.00')
    pm_transfer = Decimal('0.00')
    for name, val in pm_totals.items():
        name_l = name.lower()
        if 'efectivo' in name_l or 'cash' in name_l:
            pm_cash += val
        elif 'tarjeta' in name_l or 'card' in name_l or 'débito' in name_l or 'crédito' in name_l:
            pm_card += val
        elif 'mercado' in name_l or 'qr' in name_l:
            pm_qr += val
        elif 'transfer' in name_l:
            pm_transfer += val

    payment_methods_breakdown = {
        'MERCADOPAGO': pm_qr,
        'CASH': pm_cash,
        'CARD': pm_card,
        'TRANSFER': pm_transfer,
    }

    sorted_pm = sorted(pm_totals.items(), key=lambda x: x[1], reverse=True)
    pm_labels = [k for k, v in sorted_pm if v > 0]
    pm_values = [float(v) for k, v in sorted_pm if v > 0]
    total_pm_amount = sum(pm_values)

    palette = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4', '#84cc16', '#64748b']

    payment_methods_summary = []
    for idx, (label, val) in enumerate([(k, v) for k, v in sorted_pm if v > 0]):
        pct = round((float(val) / total_pm_amount * 100), 1) if total_pm_amount > 0 else 0
        payment_methods_summary.append({
            'name': label,
            'amount': val,
            'percentage': pct,
            'percentage_css': f"{pct:.1f}",
            'color': palette[idx % len(palette)],
        })

    payment_methods_chart_data = pm_values
    payment_methods_chart_labels = pm_labels
    payment_methods_chart_colors = [palette[i % len(palette)] for i in range(len(pm_labels))]

    # Staff Performance
    staff_reports = StaffMember.objects.filter(business=business, is_active=True)
    if staff_id:
        staff_reports = staff_reports.filter(id=staff_id)
    
    staff_reports = list(staff_reports.annotate(
        total_sales_amount=Sum('sales__total_amount'),
        appointments_completed=Count('appointments')
    ))

    for st in staff_reports:
        st.managed_projects_count = st.managed_projects.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).count()
        st.managed_projects_budget = st.managed_projects.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).aggregate(total=Sum('budget'))['total'] or Decimal('0.00')

    # CRM Client Counts
    clients_active = Client.objects.filter(business=business, status='ACTIVE').count()
    clients_vip = Client.objects.filter(business=business, status='VIP').count()
    clients_inactive = Client.objects.filter(business=business, status='INACTIVE').count()

    # FINANCIAL PROJECTIONS (Dinámicas por Filtro Seleccionado)
    # Citas agendadas dentro del rango filtrado (o fechas futuras asociadas al período)
    upcoming_appointments_qs = Appointment.objects.filter(
        business=business,
        status__in=['CONFIRMED', 'PENDING']
    )
    if start_date and end_date:
        upcoming_appointments_qs = upcoming_appointments_qs.filter(date__gte=start_date, date__lte=end_date)
    if staff_id:
        upcoming_appointments_qs = upcoming_appointments_qs.filter(staff_id=staff_id)

    upcoming_appointments_revenue = upcoming_appointments_qs.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    upcoming_appointments_count = upcoming_appointments_qs.count()

    # Cálculo de Run-Rate y Proyección según el período de días filtrado
    period_days = max(1, (end_date - start_date).days + 1) if (start_date and end_date) else 30
    daily_avg_sales = (total_sales / Decimal(str(period_days))) if total_sales > 0 else Decimal('0.00')
    projected_period_sales = daily_avg_sales * Decimal(str(period_days))

    # Pie Chart 1: Proyección por Servicio/Producto (Estimación de Ingresos según Citas Filtradas)
    services_proj_qs = upcoming_appointments_qs.values('service__name').annotate(total_est=Sum('total_price'), count=Count('id')).order_by('-total_est')
    service_proj_labels = [item['service__name'] or 'Servicio General' for item in services_proj_qs]
    service_proj_data = [float(item['total_est'] or 0) for item in services_proj_qs]
    service_proj_total = sum(service_proj_data)

    # Pie Chart 2: Proyección por Profesional (Estimación de Ingresos a Generar, Citas + Proyectos)
    staff_proj_qs = upcoming_appointments_qs.values('staff__first_name', 'staff__last_name').annotate(total_est=Sum('total_price'), count=Count('id')).order_by('-total_est')
    staff_proj_dict = defaultdict(float)
    for item in staff_proj_qs:
        name = f"{item['staff__first_name'] or ''} {item['staff__last_name'] or ''}".strip() or 'Sin Asignar'
        staff_proj_dict[name] += float(item['total_est'] or 0)
    for p in active_projects_qs:
        if p.responsible and p.budget > 0:
            r_name = p.responsible.full_name
            staff_proj_dict[r_name] += float(p.budget)
    staff_proj_labels = list(staff_proj_dict.keys())
    staff_proj_data = list(staff_proj_dict.values())
    staff_proj_total = sum(staff_proj_data)

    # Pie/Donut Chart 3: Proyección por Cartera de Proyectos Activos (Presupuestos Contratados)
    project_proj_labels = []
    project_proj_data = []
    for p in active_projects_qs:
        project_proj_labels.append(p.name)
        project_proj_data.append(float(p.budget or 0))
    project_proj_total = sum(project_proj_data)

    # Pie/Donut Chart 4: Proyección por Cuotas / Cobros Planificados
    installment_proj_labels = []
    installment_proj_data = []
    for inst in installments_upcoming_30d_qs:
        lbl = f"Cuota #{inst.installment_number} - {inst.concept}"
        if inst.client:
            lbl += f" ({inst.client.full_name})"
        installment_proj_labels.append(lbl)
        installment_proj_data.append(float(inst.balance))
    if not installment_proj_data and installments_pending_qs.exists():
        for inst in installments_pending_qs[:6]:
            lbl = f"Cuota #{inst.installment_number} - {inst.concept}"
            if inst.client:
                lbl += f" ({inst.client.full_name})"
            installment_proj_labels.append(lbl)
            installment_proj_data.append(float(inst.balance))
    installment_proj_total = sum(installment_proj_data)

    # SECCIÓN MÁS VENDIDOS POR RANGO DE FECHAS (Productos, Servicios y Profesionales)
    completed_sales_ids = completed_sales.values_list('id', flat=True)
    
    # 1. Top Servicios más vendidos en el rango de fechas
    top_services = list(SaleItem.objects.filter(
        sale_id__in=completed_sales_ids,
        item_type='SERVICE',
        service__isnull=False
    ).values('service__name').annotate(
        total_revenue=Sum('total_price'),
        total_qty=Sum('quantity')
    ).order_by('-total_revenue')[:5])

    top_services_labels = [item['service__name'] for item in top_services]
    top_services_data = [float(item['total_revenue'] or 0) for item in top_services]

    # 2. Top Productos más vendidos en el rango de fechas
    top_products = list(SaleItem.objects.filter(
        sale_id__in=completed_sales_ids,
        item_type='PRODUCT',
        product__isnull=False
    ).values('product__name').annotate(
        total_revenue=Sum('total_price'),
        total_qty=Sum('quantity')
    ).order_by('-total_revenue')[:5])

    top_products_labels = [item['product__name'] for item in top_products]
    top_products_data = [float(item['total_revenue'] or 0) for item in top_products]

    # 3. Top Profesionales que más venden en el rango de fechas
    top_staff = list(completed_sales.values(
        'staff__first_name', 
        'staff__last_name', 
        'staff__role_title'
    ).annotate(
        total_revenue=Sum('total_amount'),
        total_sales_count=Count('id')
    ).order_by('-total_revenue')[:5])

    top_staff_labels = [f"{item['staff__first_name'] or ''} {item['staff__last_name'] or ''}".strip() or 'Sin Asignar' for item in top_staff]
    top_staff_data = [float(item['total_revenue'] or 0) for item in top_staff]

    # Calculate Monthly Sales & Expenses for Current Year (Jan to Dec) for Financial Charts
    current_year = today.year
    monthly_sales_data = []
    monthly_expenses_data = []
    
    for month in range(1, 13):
        m_sales = Sale.objects.filter(
            business=business, 
            status='COMPLETED', 
            created_at__year=current_year, 
            created_at__month=month
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        monthly_sales_data.append(float(m_sales))

        m_exp = Expense.objects.filter(
            business=business, 
            created_at__year=current_year, 
            created_at__month=month
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        monthly_expenses_data.append(float(m_exp))

    all_staff = StaffMember.objects.filter(business=business, is_active=True)

    return {
        'business': business,
        'preset': preset,
        'start_date': start_date,
        'end_date': end_date,
        'staff_id': staff_id,
        'status_filter': status_filter,
        'total_sales': total_sales,
        'sales_count': sales_count,
        'avg_ticket': avg_ticket,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'invoices_paid': invoices_paid,
        'invoices_issued': invoices_issued,
        'invoices_overdue': invoices_overdue,
        'accounts_receivable': accounts_receivable,
        'accounts_payable': accounts_payable,
        'payment_methods_breakdown': payment_methods_breakdown,
        'payment_methods_chart_data': payment_methods_chart_data,
        'payment_methods_chart_labels': payment_methods_chart_labels,
        'payment_methods_chart_colors': payment_methods_chart_colors,
        'payment_methods_summary': payment_methods_summary,
        'total_pm_amount': total_pm_amount,
        'monthly_sales_data': monthly_sales_data,
        'monthly_expenses_data': monthly_expenses_data,
        'staff_reports': staff_reports,
        'all_staff': all_staff,
        'clients_active': clients_active,
        'clients_vip': clients_vip,
        'clients_inactive': clients_inactive,
        # Dynamic Projections by Filter
        'upcoming_appointments_revenue': upcoming_appointments_revenue,
        'upcoming_appointments_count': upcoming_appointments_count,
        'period_days': period_days,
        'daily_avg_sales': daily_avg_sales,
        'projected_period_sales': projected_period_sales,
        # Pie Chart Projections Data
        'service_proj_labels': service_proj_labels,
        'service_proj_data': service_proj_data,
        'service_proj_total': service_proj_total,
        'staff_proj_labels': staff_proj_labels,
        'staff_proj_data': staff_proj_data,
        'staff_proj_total': staff_proj_total,
        'project_proj_labels': project_proj_labels,
        'project_proj_data': project_proj_data,
        'project_proj_total': project_proj_total,
        'installment_proj_labels': installment_proj_labels,
        'installment_proj_data': installment_proj_data,
        'installment_proj_total': installment_proj_total,
        # Top Performers per Date Range
        'top_services': top_services,
        'top_products': top_products,
        'top_staff': top_staff,
        # Pie Chart Top Performers Datasets
        'top_services_labels': top_services_labels,
        'top_services_data': top_services_data,
        'top_products_labels': top_products_labels,
        'top_products_data': top_products_data,
        'top_staff_labels': top_staff_labels,
        'top_staff_data': top_staff_data,
        # Cuotas & Cobranzas
        'installments_collected_period': installments_collected_period,
        'installments_paid_count': installments_paid_count,
        'installments_receivable': installments_receivable,
        'installments_pending_count': installments_pending_count,
        'installments_overdue_amount': installments_overdue_amount,
        'installments_overdue_count': installments_overdue_count,
        'installments_upcoming_30d_amount': installments_upcoming_30d_amount,
        'installments_upcoming_30d_count': installments_upcoming_30d_count,
        'installments_7d_amount': installments_7d_amount,
        'installments_7d_count': installments_7d_count,
        'upcoming_installments_list': upcoming_installments_list,
        'payment_plans_active_count': payment_plans_active_count,
        'payment_plans_total_amount': payment_plans_total_amount,
        'payment_plans_collected': payment_plans_collected,
        'payment_plans_pending': payment_plans_pending,
        'payment_plans_active': payment_plans_active,
        # Proyectos
        'active_projects_count': active_projects_count,
        'active_projects_budget': active_projects_budget,
        'completed_projects_count': completed_projects_count,
        'project_installments_collected': project_installments_collected,
        'project_installments_pending': project_installments_pending,
        'top_projects': top_projects,
        'top_projects_labels': top_projects_labels,
        'top_projects_data': top_projects_data,
        'total_projected_7d': (upcoming_appointments_revenue + installments_7d_amount),
        'total_projected_30d': (upcoming_appointments_revenue + installments_upcoming_30d_amount),
    }


@login_required
def reports_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    if not request.user.has_perm_flag('can_view_financial_reports'):
        messages.error(request, "No tienes permiso para consultar reportes financieros globales.")
        return redirect('dashboard')
    data = get_filtered_analytics_data(business, request)
    return render(request, 'analytics/reports.html', data)


@login_required
def export_analytics_excel(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    if not request.user.has_perm_flag('can_view_financial_reports'):
        messages.error(request, "No tienes permiso para exportar reportes financieros.")
        return redirect('dashboard')
    data = get_filtered_analytics_data(business, request)
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"reporte_financiero_{data['start_date']}_a_{data['end_date']}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['REPORTE FINANCIERO Y ANALÍTICA DE VENTAS', business.name if business else ''])
    writer.writerow(['Período', f"{data['start_date']} al {data['end_date']}"])
    writer.writerow(['Generado el', timezone.now().strftime('%d/%m/%Y %H:%M hs')])
    writer.writerow([])
    
    writer.writerow(['RESUMEN DE INDICADORES FINANCIEROS (KPIs)', ''])
    writer.writerow(['Ventas Totales Completadas', f"{business.currency}{data['total_sales']:.2f}"])
    writer.writerow(['Transacciones Totales', data['sales_count']])
    writer.writerow(['Ticket Promedio', f"{business.currency}{data['avg_ticket']:.2f}"])
    writer.writerow(['Gastos Operativos', f"{business.currency}{data['total_expenses']:.2f}"])
    writer.writerow(['Utilidad Neta', f"{business.currency}{data['net_profit']:.2f}"])
    writer.writerow(['Facturado Pendiente de Cobro', f"{business.currency}{data['invoices_issued']:.2f}"])
    writer.writerow(['Cuentas por Cobrar Total', f"{business.currency}{data['accounts_receivable']:.2f}"])
    writer.writerow([])

    if business.is_module_enabled('invoicing'):
        writer.writerow(['CARTERA DE COBRANZAS Y CUOTAS PLANIFICADAS', ''])
        writer.writerow(['Cobrado en Cuotas (Período)', f"{business.currency}{data['installments_collected_period']:.2f}"])
        writer.writerow(['Cuotas Cobradas (Cant.)', data['installments_paid_count']])
        writer.writerow(['Cuotas Pendientes / Por Cobrar', f"{business.currency}{data['installments_receivable']:.2f}"])
        writer.writerow(['Cuotas Vencidas / En Mora', f"{business.currency}{data['installments_overdue_amount']:.2f}"])
        writer.writerow(['Próximos Vencimientos (30 Días)', f"{business.currency}{data['installments_upcoming_30d_amount']:.2f}"])
        writer.writerow([])

    if business.is_module_enabled('projects'):
        writer.writerow(['CARTERA FINANCIERA DE PROYECTOS', ''])
        writer.writerow(['Presupuesto Total Proyectos Activos', f"{business.currency}{data['active_projects_budget']:.2f}"])
        writer.writerow(['Proyectos en Curso (Cant.)', data['active_projects_count']])
        writer.writerow(['Total Cobrado por Hitos de Proyectos', f"{business.currency}{data['project_installments_collected']:.2f}"])
        writer.writerow(['Saldo Pendiente en Proyectos', f"{business.currency}{data['project_installments_pending']:.2f}"])
        writer.writerow([])

    writer.writerow(['PROYECCIONES FINANCIERAS Y RESERVAS FUTURAS', ''])
    writer.writerow(['Citas Agendadas Próximo Período', data.get('upcoming_appointments_count', 0)])
    writer.writerow(['Ingresos Proyectados por Citas', f"{business.currency}{data.get('upcoming_appointments_revenue', Decimal('0.00')):.2f}"])
    writer.writerow(['Cuotas Proyectadas (30 Días)', f"{business.currency}{data.get('installments_upcoming_30d_amount', Decimal('0.00')):.2f}"])
    writer.writerow(['Total Flujo Proyectado (30 Días)', f"{business.currency}{data.get('total_projected_30d', Decimal('0.00')):.2f}"])
    writer.writerow(['Venta Diaria Promedio', f"{business.currency}{data['daily_avg_sales']:.2f}"])
    writer.writerow(['Proyección Run-Rate Período', f"{business.currency}{data['projected_period_sales']:.2f}"])
    writer.writerow([])
    
    writer.writerow(['DESEMPEÑO Y VENTAS POR COLABORADOR', '', '', ''])
    writer.writerow(['Profesional', 'Rol / Especialidad', 'Citas Atendidas', 'Ventas Generadas'])
    for st in data['staff_reports']:
        amt = st.total_sales_amount or Decimal('0.00')
        writer.writerow([st.full_name, st.role_title, st.appointments_completed, f"{business.currency}{amt:.2f}"])
        
    return response


@login_required
def export_analytics_pdf(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    if not request.user.has_perm_flag('can_view_financial_reports'):
        messages.error(request, "No tienes permiso para exportar reportes financieros.")
        return redirect('dashboard')
    data = get_filtered_analytics_data(business, request)
    data['report_title'] = 'Reporte Financiero, Métricas & Proyecciones'
    data['generated_at'] = timezone.now()
    
    recent_sales = Sale.objects.filter(business=business, status='COMPLETED').select_related('client', 'staff')[:15]
    data['recent_sales'] = recent_sales

    return render(request, 'analytics/pdf_report.html', data)

