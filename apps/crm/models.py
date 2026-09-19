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
    tax_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="RUT / RFC / NIF")
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

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

class ClientNote(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_notes")
    author = models.CharField(max_length=100, default="Sistema")
    content = models.TextField()

    def __str__(self):
        return f"Nota para {self.client.full_name} por {self.author}"

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
