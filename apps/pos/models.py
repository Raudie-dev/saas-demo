from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, Branch, User, StaffMember
from apps.crm.models import Client
from apps.agenda.models import Appointment, Service
from apps.inventory.models import Product

class CashRegister(TimeStampedModel):
    STATUS_CHOICES = [
        ('OPEN', 'Abierta'),
        ('CLOSED', 'Cerrada'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="cash_registers")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_registers")
    opened_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="opened_registers")
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_registers")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    initial_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Monto de Apertura")
    final_amount_cash = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Monto Final en Efectivo")
    final_amount_system = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Monto Esperado por Sistema")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Caja #{self.id} ({self.get_status_display()}) - {self.opened_at.strftime('%Y-%m-%d %H:%M')}"

class CashMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ('INCOME', 'Ingreso Extra de Caja'),
        ('EXPENSE', 'Egreso / Retiro de Caja'),
    ]

    cash_register = models.ForeignKey(CashRegister, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    concept = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.movement_type}: ${self.amount} - {self.concept}"

class Sale(TimeStampedModel):
    STATUS_CHOICES = [
        ('COMPLETED', 'Completada'),
        ('REFUNDED', 'Devuelta / Anulada'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="sales")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    cash_register = models.ForeignKey(CashRegister, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    staff = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale")
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tip_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Propina")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED')
    payment_method = models.CharField(max_length=50, default="Efectivo")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Venta #{str(self.id)[:8]} - Total: {self.business.currency}{self.total_amount}"

class SaleItem(TimeStampedModel):
    ITEM_TYPE_CHOICES = [
        ('SERVICE', 'Servicio'),
        ('PRODUCT', 'Producto'),
    ]

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def item_name(self):
        if self.item_type == 'SERVICE' and self.service:
            return self.service.name
        elif self.item_type == 'PRODUCT' and self.product:
            return self.product.name
        return "Ítem Varios"

    def __str__(self):
        return f"{self.item_name} x{self.quantity} = ${self.total_price}"
