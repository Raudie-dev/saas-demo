import datetime
import csv
from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from apps.business.models import Business, StaffMember
from apps.pos.models import Sale
from apps.invoicing.models import Expense, Invoice, AccountReceivable
from apps.crm.models import Client
from apps.agenda.models import Appointment
from apps.inventory.models import Product

def dashboard_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    
    if not business:
        return render(request, 'analytics/dashboard.html', {'business': None})
        
    # KPI Financial Metrics
    completed_sales = Sale.objects.filter(business=business, status='COMPLETED')
    total_sales = completed_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_expenses = Expense.objects.filter(business=business).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    net_profit = total_sales - total_expenses
    
    accounts_receivable = AccountReceivable.objects.filter(business=business, status='PENDING').aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
    accounts_payable = Expense.objects.filter(business=business, status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    sales_count = completed_sales.count()
    avg_ticket = (total_sales / sales_count) if sales_count > 0 else Decimal('0.00')
    
    # Operational KPIs
    today = datetime.date.today()
    today_appointments = Appointment.objects.filter(business=business, date=today)
    total_clients = Client.objects.filter(business=business).count()
    low_stock_products = Product.objects.filter(business=business, stock__lte=5)
    
    # Calculate Agenda Occupancy %
    total_staff_count = StaffMember.objects.filter(business=business, is_active=True).count()
    max_daily_capacity = (total_staff_count * 8) if total_staff_count > 0 else 1
    agenda_occupancy_pct = min(100, int((today_appointments.count() / max_daily_capacity) * 100)) if total_staff_count > 0 else 0

    # Calculate REAL Monthly Sales & Expenses for Current Year (Jan to Dec)
    current_year = today.year
    monthly_sales_data = []
    monthly_expenses_data = []
    
    for month in range(1, 13):
        # Monthly sales
        m_sales = Sale.objects.filter(
            business=business, 
            status='COMPLETED', 
            created_at__year=current_year, 
            created_at__month=month
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        monthly_sales_data.append(float(m_sales))

        # Monthly expenses
        m_exp = Expense.objects.filter(
            business=business, 
            created_at__year=current_year, 
            created_at__month=month
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        monthly_expenses_data.append(float(m_exp))

    # Calculate REAL Payment Methods Distribution
    pm_qr = completed_sales.filter(payment_method='MERCADOPAGO').count()
    pm_cash = completed_sales.filter(payment_method='CASH').count()
    pm_card = completed_sales.filter(payment_method='CARD').count()
    pm_transfer = completed_sales.filter(payment_method='TRANSFER').count()
    
    payment_methods_data = [pm_qr, pm_cash, pm_card, pm_transfer]

    # Recent Sales and Appointments
    recent_sales = Sale.objects.filter(business=business).select_related('client', 'staff')[:5]
    recent_appointments = Appointment.objects.filter(business=business).select_related('client', 'staff', 'service')[:6]
    
    # Staff performance
    staff_performance = StaffMember.objects.filter(business=business).annotate(
        sales_total=Sum('sales__total_amount'),
        appointments_count=Count('appointments')
    )

    context = {
        'business': business,
        'total_sales': total_sales,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'accounts_receivable': accounts_receivable,
        'accounts_payable': accounts_payable,
        'avg_ticket': avg_ticket,
        'today_appointments_count': today_appointments.count(),
        'total_clients': total_clients,
        'low_stock_count': low_stock_products.count(),
        'low_stock_products': low_stock_products,
        'recent_sales': recent_sales,
        'recent_appointments': recent_appointments,
        'staff_performance': staff_performance,
        'agenda_occupancy_pct': agenda_occupancy_pct,
        'monthly_sales_data': monthly_sales_data,
        'monthly_expenses_data': monthly_expenses_data,
        'payment_methods_data': payment_methods_data,
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

    # FINANCIAL PROJECTIONS (Proyecciones de Ventas y Reservas)
    # 1. Confirmed upcoming appointments revenue pipeline
    upcoming_7d_appointments = Appointment.objects.filter(
        business=business,
        date__gte=today,
        date__lte=today + datetime.timedelta(days=7),
        status__in=['CONFIRMED', 'PENDING']
    )
    upcoming_7d_revenue = upcoming_7d_appointments.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    upcoming_7d_count = upcoming_7d_appointments.count()

    upcoming_30d_appointments = Appointment.objects.filter(
        business=business,
        date__gte=today,
        date__lte=today + datetime.timedelta(days=30),
        status__in=['CONFIRMED', 'PENDING']
    )
    upcoming_30d_revenue = upcoming_30d_appointments.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    upcoming_30d_count = upcoming_30d_appointments.count()

    # 2. Run-rate projection for current month
    first_day_of_month = today.replace(day=1)
    mtd_sales = Sale.objects.filter(
        business=business,
        status='COMPLETED',
        created_at__date__gte=first_day_of_month,
        created_at__date__lte=today
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    days_passed = max(1, today.day)
    num_days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_avg_sales = mtd_sales / Decimal(str(days_passed))
    projected_monthly_sales = daily_avg_sales * Decimal(str(num_days_in_month))

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
        'staff_reports': staff_reports,
        'all_staff': all_staff,
        'clients_active': clients_active,
        'clients_vip': clients_vip,
        'clients_inactive': clients_inactive,
        # Projections
        'upcoming_7d_revenue': upcoming_7d_revenue,
        'upcoming_7d_count': upcoming_7d_count,
        'upcoming_30d_revenue': upcoming_30d_revenue,
        'upcoming_30d_count': upcoming_30d_count,
        'mtd_sales': mtd_sales,
        'daily_avg_sales': daily_avg_sales,
        'projected_monthly_sales': projected_monthly_sales,
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

