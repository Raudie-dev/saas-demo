from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business
from apps.crm.models import Client, Supplier
from apps.pos.models import Sale

class Invoice(TimeStampedModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('ISSUED', 'Emitida / Pendiente'),
        ('PAID', 'Pagada'),
        ('PARTIAL', 'Pago Parcial'),
        ('CANCELLED', 'Anulada'),
        ('OVERDUE', 'Vencida'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="invoices")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invoices")
    sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice")
    invoice_number = models.CharField(max_length=50, verbose_name="Número de Factura")
    issue_date = models.DateField(verbose_name="Fecha Emisión")
    due_date = models.DateField(verbose_name="Fecha Vencimiento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"Factura #{self.invoice_number} - {self.client.full_name} (${self.total_amount})"

class InvoiceItem(TimeStampedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.description} x{self.quantity} (${self.total_price})"

class Quote(TimeStampedModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('SENT', 'Enviada al Cliente'),
        ('ACCEPTED', 'Aceptada'),
        ('REJECTED', 'Rechazada'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="quotes")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="quotes")
    quote_number = models.CharField(max_length=50, verbose_name="Número de Presupuesto")
    date = models.DateField()
    valid_until = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SENT')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Presupuesto #{self.quote_number} - {self.client.full_name} (${self.total_amount})"

class QuoteItem(TimeStampedModel):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

class ExpenseCategory(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="expense_categories")
    name = models.CharField(max_length=100, verbose_name="Nombre de Categoria de Gasto")

    def __str__(self):
        return self.name

class Expense(TimeStampedModel):
    STATUS_CHOICES = [
        ('PAID', 'Pagado'),
        ('PENDING', 'Pendiente de Pago'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    concept = models.CharField(max_length=200, verbose_name="Concepto del Gasto")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Monto")
    issue_date = models.DateField(verbose_name="Fecha de Comprobante")
    due_date = models.DateField(blank=True, null=True, verbose_name="Vencimiento")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PAID')
    receipt_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nº Comprobante / Factura")
    is_recurring = models.BooleanField(default=False, verbose_name="Gasto Recurrente Mensual")

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"Gasto: {self.concept} - ${self.amount} ({self.get_status_display()})"

class AccountReceivable(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="accounts_receivable")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="accounts_receivable")
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    due_date = models.DateField()
    status = models.CharField(max_length=20, default='PENDING')

    @property
    def balance(self):
        return self.amount_due - self.amount_paid

    def __str__(self):
        return f"Cuenta por Cobrar: {self.client.full_name} - Pendiente: ${self.balance}"

class CreditNote(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="credit_notes")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="credit_notes")
    note_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()

    def __str__(self):
        return f"Nota de Crédito #{self.note_number} para Factura #{self.invoice.invoice_number}"

class PaymentReceipt(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payment_receipts")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="payment_receipts")
    receipt_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    date = models.DateField()

    def __str__(self):
        return f"Recibo de Pago #{self.receipt_number} - ${self.amount}"

