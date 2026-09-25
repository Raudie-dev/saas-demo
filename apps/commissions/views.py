import csv
from django.http import HttpResponse
from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from apps.business.models import Business, StaffMember
from apps.commissions.models import CommissionRecord, PayrollSettlement

@login_required
def commission_report_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    staff_members = StaffMember.objects.filter(business=business) if business else []
    
    selected_staff_id = request.GET.get('staff_id', '')
    records = CommissionRecord.objects.filter(business=business).select_related('staff')
    
    if selected_staff_id:
        records = records.filter(staff_id=selected_staff_id)
        
    total_unsettled = records.filter(is_settled=False).aggregate(total=Sum('amount'))['total'] or 0
    settlements = PayrollSettlement.objects.filter(business=business).order_by('-settled_at')
    
    if request.method == 'POST':
        staff_id = request.POST.get('staff_id')
        staff = get_object_or_404(StaffMember, id=staff_id, business=business)
        
        unsettled_staff_records = CommissionRecord.objects.filter(business=business, staff=staff, is_settled=False)
        total_comm = unsettled_staff_records.aggregate(total=Sum('amount'))['total'] or 0
        
        if total_comm > 0:
            settlement = PayrollSettlement.objects.create(
                business=business,
                staff=staff,
                period_start=datetime.date.today() - datetime.timedelta(days=30),
                period_end=datetime.date.today(),
                total_commission=total_comm,
                notes="Liquidación de comisiones realizada desde BusinessOS"
            )
            unsettled_staff_records.update(is_settled=True, settlement=settlement)
            
        return redirect('commission_report')

    from django.core.paginator import Paginator
    rec_paginator = Paginator(records, 10)
    records_page_obj = rec_paginator.get_page(request.GET.get('page', 1))

    set_paginator = Paginator(settlements, 10)
    settlements_page_obj = set_paginator.get_page(request.GET.get('set_page', 1))

    return render(request, 'commissions/report.html', {
        'business': business,
        'staff_members': staff_members,
        'records': records_page_obj,
        'page_obj': records_page_obj,
        'records_page_obj': records_page_obj,
        'total_unsettled': total_unsettled,
        'settlements': settlements_page_obj,
        'settlements_page_obj': settlements_page_obj,
        'selected_staff_id': selected_staff_id,
    })

@login_required
def export_commissions_excel(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    selected_staff_id = request.GET.get('staff_id', '')
    records = CommissionRecord.objects.filter(business=business).select_related('staff')
    if selected_staff_id:
        records = records.filter(staff_id=selected_staff_id)
        
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="comisiones_reporte.csv"'
    
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Profesional', 'Concepto / Servicio', 'Monto Venta', 'Comisión %', 'Comisión $', 'Estado', 'Fecha'])
    
    for r in records:
        writer.writerow([
            r.staff.user.get_full_name() if r.staff and r.staff.user else (r.staff.display_name if r.staff else 'Desconocido'),
            r.notes or 'Comisión por venta/servicio',
            f"${r.sale_amount:,.2f}" if hasattr(r, 'sale_amount') and r.sale_amount else "$0.00",
            f"{r.commission_rate}%" if hasattr(r, 'commission_rate') and r.commission_rate else "-",
            f"${r.amount:,.2f}",
            'LIQUIDADO' if r.is_settled else 'PENDIENTE',
            r.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(r, 'created_at') and r.created_at else ''
        ])
        
    return response

@login_required
def export_commissions_pdf(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')
    selected_staff_id = request.GET.get('staff_id', '')
    records = CommissionRecord.objects.filter(business=business).select_related('staff')
    if selected_staff_id:
        records = records.filter(staff_id=selected_staff_id)
        
    rows = []
    total_amt = Decimal('0.00')
    for r in records:
        total_amt += r.amount
        staff_name = r.staff.user.get_full_name() if r.staff and r.staff.user else (r.staff.display_name if r.staff else 'Desconocido')
        rows.append({
            'col1': staff_name,
            'col2': r.notes or 'Comisión de servicio',
            'col3': f"${r.amount:,.2f}",
            'col4': 'Liquidado' if r.is_settled else 'Pendiente',
            'col5': r.created_at.strftime('%Y-%m-%d') if hasattr(r, 'created_at') and r.created_at else '-'
        })
        
    return render(request, 'analytics/pdf_report.html', {
        'title': 'Reporte de Comisiones de Equipo',
        'subtitle': f'Comisiones y Liquidaciones - {business.name if business else ""}',
        'business': business,
        'headers': ['Profesional', 'Concepto', 'Comisión ($)', 'Estado', 'Fecha'],
        'rows': rows,
        'summary': f'Total Comisiones Registradas: ${total_amt:,.2f}'
    })

