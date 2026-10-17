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
    staff_members = models.ManyToManyField(StaffMember, blank=True, related_name="services", verbose_name="Profesionales Habilitados")
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
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    related_property = models.ForeignKey('properties.Property', on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments", verbose_name="Inmueble / Propiedad")
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

    @property
    def services_summary(self):
        items = list(self.appointment_services.select_related('service').all())
        if items:
            parts = []
            for item in items:
                if item.quantity > 1:
                    parts.append(f"{item.service.name} (x{item.quantity})")
                else:
                    parts.append(item.service.name)
            return ", ".join(parts)
        if self.service:
            return self.service.name
        return "Sin servicio"

    @property
    def total_duration_minutes(self):
        items = list(self.appointment_services.all())
        if items:
            return sum(item.duration_minutes * item.quantity for item in items)
        if self.service:
            return self.service.duration_minutes
        return 0

    @property
    def primary_service(self):
        if self.service:
            return self.service
        first_item = self.appointment_services.first()
        return first_item.service if first_item else None

    @property
    def confirmation_deadline(self):
        hours = getattr(self.business, 'pending_booking_expiry_hours', 24)
        if not hours or hours <= 0 or not self.created_at:
            return None
        return self.created_at + datetime.timedelta(hours=hours)

    @property
    def is_pending_expired(self):
        if self.status != 'PENDING':
            return False
        deadline = self.confirmation_deadline
        if not deadline:
            return False
        from django.utils import timezone
        return timezone.now() >= deadline

    @property
    def pending_time_remaining_display(self):
        if self.status != 'PENDING':
            return ""
        deadline = self.confirmation_deadline
        if not deadline:
            return "Sin límite de tiempo"
        from django.utils import timezone
        remaining = deadline - timezone.now()
        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            return "Tiempo agotado"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m restantes"
        return f"{minutes} min restantes"

class AppointmentService(TimeStampedModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="appointment_services")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="appointment_items")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    duration_minutes = models.IntegerField(default=0, verbose_name="Duración (minutos)")

    class Meta:
        verbose_name = "Servicio de Cita"
        verbose_name_plural = "Servicios de Citas"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.service.name} ({self.appointment})"

class ScheduleBlock(TimeStampedModel):
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="blocks")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=200, default="Bloqueo Personal / Almuerzo")

    def __str__(self):
        return f"Bloqueo {self.staff.full_name} el {self.date} ({self.start_time} - {self.end_time})"
