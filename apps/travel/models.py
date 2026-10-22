import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel
from apps.business.models import Business, StaffMember
from apps.crm.models import Client

class TravelPackage(TimeStampedModel):
    TRAVEL_TYPE_CHOICES = [
        ('PACKAGE', 'Paquete Completo (Vuelo + Hotel + Traslados)'),
        ('TOUR', 'Tour / Excursión Guiada'),
        ('HOTEL_RESORT', 'Alojamiento / Resort All-Inclusive'),
        ('CRUISE', 'Crucero'),
        ('FLIGHT_HOTEL', 'Vuelo + Hotel'),
        ('CUSTOM', 'Viaje a Medida / Personalizado'),
    ]

    STATUS_CHOICES = [
        ('AVAILABLE', 'Disponible'),
        ('LAST_SLOTS', 'Últimos Cupos'),
        ('SOLD_OUT', 'Agotado'),
        ('PAUSED', 'En Pausa'),
        ('DRAFT', 'Borrador'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'USD (Dólares)'),
        ('$', '$ (Moneda Local)'),
        ('EUR', 'EUR (Euros)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='travel_packages', verbose_name="Agencia de Viajes")
    code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Código de Paquete (ej: TOUR-2026-001)")
    title = models.CharField(max_length=200, verbose_name="Nombre del Paquete / Destino")
    destination = models.CharField(max_length=200, verbose_name="Destino Principal (Ciudad / País / Región)")
    travel_type = models.CharField(max_length=30, choices=TRAVEL_TYPE_CHOICES, default='PACKAGE', verbose_name="Tipo de Viaje")
    
    duration_days = models.PositiveIntegerField(default=5, verbose_name="Días")
    duration_nights = models.PositiveIntegerField(default=4, verbose_name="Noches")
    
    price_per_person = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Precio Base por Persona")
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='USD', verbose_name="Moneda")
    
    available_slots = models.PositiveIntegerField(default=10, verbose_name="Cupos Disponibles")
    start_date = models.DateField(blank=True, null=True, verbose_name="Fecha de Salida / Inicio Temporada")
    end_date = models.DateField(blank=True, null=True, verbose_name="Fecha de Regreso / Fin Temporada")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', verbose_name="Estado de Disponibilidad")
    
    hotel_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Hotel / Alojamiento Previsto")
    airline = models.CharField(max_length=100, blank=True, null=True, verbose_name="Aerolínea de Referencia")
    
    includes = models.TextField(blank=True, null=True, verbose_name="Servicios Incluidos (Vuelos, Traslados, Desayunos...)")
    excludes = models.TextField(blank=True, null=True, verbose_name="No Incluye (Propinas, Gastos personales...)")
    itinerary = models.TextField(blank=True, null=True, verbose_name="Itinerario Detallado (Día por Día)")
    notes = models.TextField(blank=True, null=True, verbose_name="Requisitos & Notas de Visado / Vacunación")
    
    image = models.ImageField(upload_to='travel/packages/', blank=True, null=True, verbose_name="Foto de Portada del Destino")
    is_featured = models.BooleanField(default=False, verbose_name="Destacado en Cartelera")
    is_active = models.BooleanField(default=True, verbose_name="Activo en Sistema")

    class Meta:
        verbose_name = "Paquete de Viaje"
        verbose_name_plural = "Paquetes de Viaje"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.destination}"

    @property
    def duration_display(self):
        return f"{self.duration_days}D / {self.duration_nights}N"

    @property
    def bookings_count(self):
        return self.bookings.count()

    def save(self, *args, **kwargs):
        # Generate default code if missing
        if not self.code and self.business_id:
            count = TravelPackage.objects.filter(business=self.business).count() + 1
            self.code = f"VIAJE-{timezone.now().year}-{count:03d}"
        super().save(*args, **kwargs)


class TravelBooking(TimeStampedModel):
    STATUS_CHOICES = [
        ('QUOTE', 'Cotización Pendiente'),
        ('PENDING', 'Pendiente de Confirmación'),
        ('CONFIRMED', 'Reserva Confirmada'),
        ('PARTIAL_PAID', 'Señada / Pago Parcial'),
        ('PAID', 'Totalmente Pagada'),
        ('TRAVELING', 'Pasajeros en Viaje'),
        ('COMPLETED', 'Viaje Finalizado'),
        ('CANCELLED', 'Cancelada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='travel_bookings', verbose_name="Agencia")
    booking_number = models.CharField(max_length=50, unique=True, verbose_name="Localizador / N° de Expediente")
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='travel_bookings', verbose_name="Pasajero Principal / Titular")
    package = models.ForeignKey(TravelPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings', verbose_name="Paquete Turístico")
    agent = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True, related_name='travel_bookings', verbose_name="Asesor de Viajes")
    
    departure_date = models.DateField(verbose_name="Fecha de Salida")
    return_date = models.DateField(blank=True, null=True, verbose_name="Fecha de Regreso")
    
    num_adults = models.PositiveIntegerField(default=1, verbose_name="Adultos")
    num_children = models.PositiveIntegerField(default=0, verbose_name="Menores / Niños")
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Precio Total del Viaje")
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Monto Pagado / Seña")
    currency = models.CharField(max_length=10, default='USD', verbose_name="Moneda")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMED', verbose_name="Estado de la Reserva")
    
    pnr_locator = models.CharField(max_length=50, blank=True, null=True, verbose_name="Código PNR / Localizador Aerolínea u Hotel")
    airline_flight_details = models.CharField(max_length=200, blank=True, null=True, verbose_name="Detalles de Vuelos / Horarios")
    hotel_confirmation = models.CharField(max_length=200, blank=True, null=True, verbose_name="Confirmación Hotelera / Voucher")
    
    passengers_info = models.TextField(blank=True, null=True, verbose_name="Datos de los Pasajeros (Nombres, Pasaportes, DNI)")
    special_requests = models.TextField(blank=True, null=True, verbose_name="Requerimientos Especiales (Asientos, Dietas, Cunas)")
    notes = models.TextField(blank=True, null=True, verbose_name="Observaciones Internas")

    class Meta:
        verbose_name = "Reserva de Viaje"
        verbose_name_plural = "Reservas de Viajes"
        ordering = ['-departure_date', '-created_at']

    def __str__(self):
        return f"Expediente #{self.booking_number} - {self.client.full_name}"

    @property
    def balance_due(self):
        return max(Decimal('0.00'), self.total_amount - self.deposit_amount)

    @property
    def total_passengers(self):
        return self.num_adults + self.num_children
