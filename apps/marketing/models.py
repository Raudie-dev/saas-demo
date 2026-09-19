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
