from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business
from apps.crm.models import Client

class Coupon(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="coupons")
    code = models.CharField(max_length=50, verbose_name="Código del Cupón")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Descuento (%)")
    valid_until = models.DateField(verbose_name="Válido Hasta")
    max_uses = models.IntegerField(default=50, verbose_name="Usos Máximos")
    uses_count = models.IntegerField(default=0, verbose_name="Usos Actuales")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cupón Promocional"
        verbose_name_plural = "Cupones Promocionales"

    def __str__(self):
        return f"Cupón: {self.code} ({self.discount_percentage}% OFF)"

class GiftCard(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="giftcards")
    code = models.CharField(max_length=50, unique=True, verbose_name="Código Gift Card")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="giftcards")
    initial_balance = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Saldo Inicial")
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Saldo Actual")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Gift Card / Tarjeta de Regalo"
        verbose_name_plural = "Gift Cards"

    def __str__(self):
        return f"GiftCard #{self.code} - Saldo: ${self.current_balance}"

class LoyaltyProgram(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="loyalty_programs")
    name = models.CharField(max_length=150, verbose_name="Nombre del Programa (Ej: Cliente VIP, Puntos Belleza)")
    points_per_currency = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, verbose_name="Puntos por cada $ gastado")
    minimum_points_to_redeem = models.IntegerField(default=100, verbose_name="Puntos Mínimos para Canjear")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Programa de Fidelización: {self.name}"

class LoyaltyCard(TimeStampedModel):
    program = models.ForeignKey(LoyaltyProgram, on_delete=models.CASCADE, related_name="cards")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="loyalty_cards")
    points = models.IntegerField(default=0, verbose_name="Puntos Acumulados")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Fidelización: {self.client.full_name} ({self.points} pts)"

class EmailCampaign(TimeStampedModel):
    AUDIENCE_CHOICES = [
        ('ALL', 'Todos los Clientes'),
        ('VIP', 'Clientes VIP / Frecuentes'),
        ('INACTIVE', 'Clientes Inactivos'),
        ('CUSTOM', 'Personalizado')
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('SENT', 'Enviado')
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="email_campaigns")
    name = models.CharField(max_length=150, verbose_name="Nombre de la Campaña")
    subject = models.CharField(max_length=255, verbose_name="Asunto del Email")
    body = models.TextField(verbose_name="Contenido del Correo")
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='ALL', verbose_name="Audiencia Objetivo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Estado")
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Campaña: {self.name} ({self.get_status_display()})"
