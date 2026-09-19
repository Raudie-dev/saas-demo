import datetime
from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, Branch, StaffMember
from apps.crm.models import Client

class ServiceCategory(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="service_categories")
    name = models.CharField(max_length=100, verbose_name="Nombre de Categoría")
    color = models.CharField(max_length=20, default="#6366f1")

    class Meta:
        verbose_name = "Categoría de Servicio"
        verbose_name_plural = "Categorías de Servicios"

    def __str__(self):
        return self.name

class Service(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="services")
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="services")
    name = models.CharField(max_length=150, verbose_name="Nombre del Servicio")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    duration_minutes = models.IntegerField(default=45, verbose_name="Duración (minutos)")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio del Servicio")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Comisión (%) (Opcional)")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"

    def __str__(self):
        return f"{self.name} - {self.business.currency}{self.price} ({self.duration_minutes} min)"

class Appointment(TimeStampedModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente'),
        ('CONFIRMED', 'Confirmada'),
        ('COMPLETED', 'Realizada / Finalizada'),
        ('CANCELLED', 'Cancelada'),
        ('NO_SHOW', 'Inasistencia / No se presentó'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="appointments")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="appointments")
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="appointments")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="appointments")
    date = models.DateField(verbose_name="Fecha de Cita")
    start_time = models.TimeField(verbose_name="Hora Inicio")
    end_time = models.TimeField(verbose_name="Hora Fin")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMED')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Seña / Pago Parcial")
    notes = models.TextField(blank=True, null=True)
    whatsapp_sent = models.BooleanField(default=False, verbose_name="Recordatorio WhatsApp Enviado")

    class Meta:
        verbose_name = "Cita / Reserva"
        verbose_name_plural = "Citas / Reservas"
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"Cita: {self.client.full_name} con {self.staff.full_name} ({self.date} {self.start_time})"

class ScheduleBlock(TimeStampedModel):
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="blocks")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=200, default="Bloqueo Personal / Almuerzo")

    def __str__(self):
        return f"Bloqueo {self.staff.full_name} el {self.date} ({self.start_time} - {self.end_time})"
