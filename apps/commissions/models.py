from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, StaffMember
from apps.agenda.models import Appointment
from apps.pos.models import Sale

class PayrollSettlement(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payroll_settlements")
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="payroll_settlements")
    period_start = models.DateField()
    period_end = models.DateField()
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    settled_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Liquidación {self.staff.full_name}: ${self.total_commission} ({self.period_start} a {self.period_end})"

class CommissionRecord(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="commission_records")
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="commission_records")
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto de Comisión")
    concept = models.CharField(max_length=200, verbose_name="Concepto")
    date = models.DateField(auto_now_add=True)
    is_settled = models.BooleanField(default=False)
    settlement = models.ForeignKey(PayrollSettlement, on_delete=models.SET_NULL, null=True, blank=True, related_name="records")

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Comisión {self.staff.full_name}: ${self.amount} - {self.concept}"
