import datetime
from decimal import Decimal
from django.shortcuts import render
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

def reports_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    
    total_sales = Sale.objects.filter(business=business, status='COMPLETED').aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_expenses = Expense.objects.filter(business=business).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    net_profit = total_sales - total_expenses
    
    clients_active = Client.objects.filter(business=business, status='ACTIVE').count()
    clients_vip = Client.objects.filter(business=business, status='VIP').count()
    clients_inactive = Client.objects.filter(business=business, status='INACTIVE').count()
    
    staff_reports = StaffMember.objects.filter(business=business).annotate(
        total_sales_amount=Sum('sales__total_amount'),
        appointments_completed=Count('appointments')
    )

    return render(request, 'analytics/reports.html', {
        'business': business,
        'total_sales': total_sales,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'clients_active': clients_active,
        'clients_vip': clients_vip,
        'clients_inactive': clients_inactive,
        'staff_reports': staff_reports,
    })
