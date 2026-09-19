from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from apps.business.models import Business, StaffMember
from apps.commissions.models import CommissionRecord, PayrollSettlement

def commission_report_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
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

    return render(request, 'commissions/report.html', {
        'business': business,
        'staff_members': staff_members,
        'records': records,
        'total_unsettled': total_unsettled,
        'settlements': settlements,
        'selected_staff_id': selected_staff_id,
    })
