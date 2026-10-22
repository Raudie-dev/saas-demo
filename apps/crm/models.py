from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business

class Client(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Activo'),
        ('INACTIVE', 'Inactivo (+60 días)'),
        ('VIP', 'Cliente Frecuente / VIP'),
        ('PROSPECT', 'Prospecto'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="clients")
    first_name = models.CharField(max_length=100, verbose_name="Nombre")
    last_name = models.CharField(max_length=100, verbose_name="Apellido")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    phone = models.CharField(max_length=50, verbose_name="Teléfono / WhatsApp")
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="DNI / Número de Identidad")
    address = models.TextField(blank=True, null=True, verbose_name="Dirección")
    birth_date = models.DateField(blank=True, null=True, verbose_name="Fecha de Nacimiento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    notes = models.TextField(blank=True, null=True, verbose_name="Notas y Preferencias")
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Total Gastado")
    last_visit = models.DateTimeField(blank=True, null=True, verbose_name="Última Visita")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['-created_at']

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def real_estate_role(self):
        """Returns a human-readable role summary for real estate agencies."""
        try:
            has_owned = self.owned_properties.exists() if hasattr(self, 'owned_properties') else False
            has_seller_inq = False
            has_buyer_inq = False
            has_sell_to_buy = False
            if hasattr(self, 'property_inquiries'):
                inqs = list(self.property_inquiries.all())
                has_seller_inq = any(i.inquiry_type == 'SELLER' for i in inqs)
                has_buyer_inq = any(i.inquiry_type == 'BUYER' for i in inqs)
                has_sell_to_buy = any(i.inquiry_type == 'SELL_TO_BUY' for i in inqs)
            has_visits = self.appointments.filter(related_property__isnull=False).exists() if hasattr(self, 'appointments') else False
            
            if self.notes:
                if '[VENDER PARA COMPRAR' in self.notes.upper():
                    has_sell_to_buy = True
                elif '[PROPIETARIO' in self.notes:
                    has_seller_inq = True

            if has_sell_to_buy or ((has_owned or has_seller_inq) and (has_buyer_inq or has_visits)):
                return {'badge': 'Vender para Comprar', 'color': 'purple', 'type': 'SELL_TO_BUY'}
            elif has_owned or has_seller_inq:
                return {'badge': 'Propietario', 'color': 'amber', 'type': 'SELLER'}
            elif has_buyer_inq or has_visits:
                return {'badge': 'Comprador', 'color': 'emerald', 'type': 'BUYER'}
        except Exception:
            pass
        return {'badge': 'Cliente', 'color': 'slate', 'type': 'PROSPECT'}

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

class ClientNote(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_notes")
    author = models.CharField(max_length=100, default="Sistema")
    content = models.TextField()

    def __str__(self):
        return f"Nota para {self.client.full_name} por {self.author}"

class ServiceHistoryNote(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="service_notes")
    appointment = models.ForeignKey('agenda.Appointment', on_delete=models.SET_NULL, null=True, blank=True, related_name="service_notes")
    service_name = models.CharField(max_length=200, verbose_name="Servicio / Tratamiento")
    author = models.CharField(max_length=100, default="Staff")
    content = models.TextField(verbose_name="Anotación Técnica / Detalle del Servicio")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Anotación de Servicio"
        verbose_name_plural = "Anotaciones de Servicios"

    def __str__(self):
        return f"Nota de Servicio '{self.service_name}' para {self.client.full_name}"

class Supplier(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="suppliers")
    company_name = models.CharField(max_length=200, verbose_name="Razón Social / Proveedor")
    contact_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Persona de Contacto")
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="RUT / RFC / Tax ID")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=100, default="Insumos Generales")

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return self.company_name
