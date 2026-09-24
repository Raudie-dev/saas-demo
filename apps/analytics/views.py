import datetime
import csv
from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from apps.business.models import Business, StaffMember
from apps.pos.models import Sale, SaleItem
from apps.invoicing.models import Expense, Invoice, AccountReceivable
from apps.crm.models import Client
from apps.agenda.models import Appointment
from apps.inventory.models import Product

def dashboard_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    
    if not business:
        return render(request, 'analytics/dashboard.html', {'business': None})
        
    today = datetime.date.today()
    
    # Facturación del día (Ventas POS del día de hoy)
    today_sales_qs = Sale.objects.filter(business=business, status='COMPLETED', created_at__date=today)
    today_sales = today_sales_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    today_sales_count = today_sales_qs.count()
    
    # Citas del día y próximas citas
    today_appointments = Appointment.objects.filter(business=business, date=today).select_related('client', 'staff', 'service')
    upcoming_appointments = today_appointments.order_by('start_time')
    
    # Clientes totales y Alertas de Stock
    total_clients = Client.objects.filter(business=business).count()
    low_stock_products = Product.objects.filter(business=business, stock__lte=5)
    
    # Ocupación de Agenda %
    total_staff_count = StaffMember.objects.filter(business=business, is_active=True).count()
    max_daily_capacity = (total_staff_count * 8) if total_staff_count > 0 else 1
    agenda_occupancy_pct = min(100, int((today_appointments.count() / max_daily_capacity) * 100)) if total_staff_count > 0 else 0

    context = {
        'business': business,
        'today_sales': today_sales,
        'today_sales_count': today_sales_count,
        'today_appointments': today_appointments,
        'today_appointments_count': today_appointments.count(),
        'recent_appointments': upcoming_appointments,
        'total_clients': total_clients,
        'low_stock_count': low_stock_products.count(),
        'low_stock_products': low_stock_products,
        'agenda_occupancy_pct': agenda_occupancy_pct,
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

    # Payment Methods breakdown
    pm_qr = completed_sales.filter(payment_method='MERCADOPAGO').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    pm_cash = completed_sales.filter(payment_method='CASH').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    pm_card = completed_sales.filter(payment_method='CARD').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    pm_transfer = completed_sales.filter(payment_method='TRANSFER').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    payment_methods_breakdown = {
        'MERCADOPAGO': pm_qr,
        'CASH': pm_cash,
        'CARD': pm_card,
        'TRANSFER': pm_transfer,
    }

    # Staff Performance
    staff_reports = StaffMember.objects.filter(business=business)
    if staff_id:
        staff_reports = staff_reports.filter(id=staff_id)
    
    staff_reports = staff_reports.annotate(
        total_sales_amount=Sum('sales__total_amount'),
        appointments_completed=Count('appointments')
    )

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

    # Pie Chart 2: Proyección por Profesional (Estimación de Ingresos a Generar)
    staff_proj_qs = upcoming_appointments_qs.values('staff__first_name', 'staff__last_name').annotate(total_est=Sum('total_price'), count=Count('id')).order_by('-total_est')
    staff_proj_labels = [f"{item['staff__first_name'] or ''} {item['staff__last_name'] or ''}".strip() or 'Sin Asignar' for item in staff_proj_qs]
    staff_proj_data = [float(item['total_est'] or 0) for item in staff_proj_qs]

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

    payment_methods_chart_data = [
        float(pm_qr),
        float(pm_cash),
        float(pm_card),
        float(pm_transfer)
    ]

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
        'staff_proj_labels': staff_proj_labels,
        'staff_proj_data': staff_proj_data,
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
    }


def reports_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    data = get_filtered_analytics_data(business, request)
    return render(request, 'analytics/reports.html', data)


def export_analytics_excel(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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

    writer.writerow(['PROYECCIONES FINANCIERAS Y RESERVAS FUTURAS', ''])
    writer.writerow(['Citas Agendadas Próximos 7 Días', data['upcoming_7d_count']])
    writer.writerow(['Ingresos Proyectados (7 Días)', f"{business.currency}{data['upcoming_7d_revenue']:.2f}"])
    writer.writerow(['Citas Agendadas Próximos 30 Días', data['upcoming_30d_count']])
    writer.writerow(['Ingresos Proyectados (30 Días)', f"{business.currency}{data['upcoming_30d_revenue']:.2f}"])
    writer.writerow(['Venta Diaria Promedio (Mes Actual)', f"{business.currency}{data['daily_avg_sales']:.2f}"])
    writer.writerow(['Proyección Cierre de Mes (Run-Rate)', f"{business.currency}{data['projected_monthly_sales']:.2f}"])
    writer.writerow([])
    
    writer.writerow(['DESEMPEÑO Y VENTAS POR COLABORADOR', '', '', ''])
    writer.writerow(['Profesional', 'Rol / Especialidad', 'Citas Atendidas', 'Ventas Generadas'])
    for st in data['staff_reports']:
        amt = st.total_sales_amount or Decimal('0.00')
        writer.writerow([st.full_name, st.role_title, st.appointments_completed, f"{business.currency}{amt:.2f}"])
        
    return response


def export_analytics_pdf(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    data = get_filtered_analytics_data(business, request)
    data['report_title'] = 'Reporte Financiero, Métricas & Proyecciones'
    data['generated_at'] = timezone.now()
    
    recent_sales = Sale.objects.filter(business=business, status='COMPLETED').select_related('client', 'staff')[:15]
    data['recent_sales'] = recent_sales

    return render(request, 'analytics/pdf_report.html', data)

