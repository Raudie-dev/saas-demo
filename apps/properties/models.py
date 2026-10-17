import urllib.parse
from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business

class Property(TimeStampedModel):
    PROPERTY_TYPE_CHOICES = [
        ('APARTMENT', 'Departamento / Piso'),
        ('HOUSE', 'Casa'),
        ('PH', 'PH'),
        ('COMMERCIAL', 'Local Comercial / Oficina'),
        ('LAND', 'Terreno / Lote'),
        ('WAREHOUSE', 'Galpón / Depósito'),
        ('CHALET', 'Quinta / Chalet'),
        ('OTHER', 'Otro Inmueble'),
    ]

    OPERATION_TYPE_CHOICES = [
        ('SALE', 'Venta'),
        ('RENT', 'Alquiler'),
        ('TEMPORARY_RENT', 'Alquiler Temporario'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'USD (Dólares)'),
        ('$', '$ (Moneda Local)'),
        ('EUR', 'EUR (Euros)'),
    ]

    STATUS_CHOICES = [
        ('AVAILABLE', 'Disponible'),
        ('RESERVED', 'Reservada'),
        ('SOLD_RENTED', 'Vendida / Alquilada'),
        ('PAUSED', 'Pausada'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='properties', verbose_name="Inmobiliaria / Negocio")
    title = models.CharField(max_length=200, verbose_name="Título del Inmueble")
    reference_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="Código de Referencia / Ref")
    
    property_type = models.CharField(max_length=30, choices=PROPERTY_TYPE_CHOICES, default='APARTMENT', verbose_name="Tipo de Inmueble")
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPE_CHOICES, default='SALE', verbose_name="Tipo de Operación")
    
    price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Precio")
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='USD', verbose_name="Moneda")
    expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True, verbose_name="Expensas (opcional)")
    
    address = models.CharField(max_length=255, verbose_name="Dirección / Calle y Altura")
    zone = models.CharField(max_length=150, verbose_name="Barrio / Zona / Ciudad")
    description = models.TextField(verbose_name="Descripción detallada de la propiedad")
    
    # Specs
    bedrooms = models.PositiveIntegerField(default=1, verbose_name="Dormitorios")
    bathrooms = models.PositiveIntegerField(default=1, verbose_name="Baños")
    total_surface = models.DecimalField(max_digits=8, decimal_places=2, default=0, blank=True, null=True, verbose_name="Superficie Total (m²)")
    covered_surface = models.DecimalField(max_digits=8, decimal_places=2, default=0, blank=True, null=True, verbose_name="Superficie Cubierta (m²)")
    garages = models.PositiveIntegerField(default=0, verbose_name="Cocheras")
    
    # Exactly 3 photos as requested
    photo_1 = models.ImageField(upload_to='properties/', blank=True, null=True, verbose_name="Foto 1 (Principal)")
    photo_2 = models.ImageField(upload_to='properties/', blank=True, null=True, verbose_name="Foto 2")
    photo_3 = models.ImageField(upload_to='properties/', blank=True, null=True, verbose_name="Foto 3")
    
    # External portal link
    portal_url = models.URLField(blank=True, null=True, verbose_name="Link de la Publicación (Portal Inmobiliario)")
    portal_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre del Portal (opcional)")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', verbose_name="Estado")
    is_featured = models.BooleanField(default=False, verbose_name="Propiedad Destacada")

    # Internal Real Estate Control (Agente Asignado & Cliente Propietario/Vendedor)
    agent = models.ForeignKey(
        'business.StaffMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_properties',
        verbose_name="Agente / Asesor Inmobiliario Asignado"
    )
    owner_client = models.ForeignKey(
        'crm.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_properties',
        verbose_name="Cliente Propietario / Vendedor"
    )

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"
        ordering = ['-is_featured', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_operation_type_display()} - {self.currency} {self.price})"

    @property
    def formatted_price(self):
        try:
            val = int(self.price) if self.price % 1 == 0 else self.price
            formatted = f"{val:,.0f}".replace(",", ".")
            return f"{self.currency} {formatted}"
        except Exception:
            return f"{self.currency} {self.price}"

    @property
    def formatted_expenses(self):
        if not self.expenses or self.expenses <= 0:
            return None
        try:
            val = int(self.expenses) if self.expenses % 1 == 0 else self.expenses
            formatted = f"{val:,.0f}".replace(",", ".")
            return f"{self.currency} {formatted}"
        except Exception:
            return f"{self.currency} {self.expenses}"

    @property
    def photos_list(self):
        photos = []
        if self.photo_1:
            photos.append({'url': self.photo_1.url, 'index': 1, 'is_main': True})
        if self.photo_2:
            photos.append({'url': self.photo_2.url, 'index': 2, 'is_main': False})
        if self.photo_3:
            photos.append({'url': self.photo_3.url, 'index': 3, 'is_main': False})
        return photos

    @property
    def photos_count(self):
        return len(self.photos_list)

    @property
    def main_photo_url(self):
        if self.photo_1:
            return self.photo_1.url
        if self.photo_2:
            return self.photo_2.url
        if self.photo_3:
            return self.photo_3.url
        return None

    @property
    def portal_display_name(self):
        if self.portal_name:
            return self.portal_name
        if not self.portal_url:
            return "Ver Publicación"
        try:
            domain = urllib.parse.urlparse(self.portal_url).netloc.lower()
            if 'zonaprop' in domain:
                return 'Zonaprop'
            elif 'argenprop' in domain:
                return 'Argenprop'
            elif 'mercadolibre' in domain:
                return 'Mercado Libre'
            elif 'properati' in domain:
                return 'Properati'
            elif 'inmuebles24' in domain:
                return 'Inmuebles24'
            elif 'fotocasa' in domain:
                return 'Fotocasa'
            elif 'idealista' in domain:
                return 'Idealista'
            return domain.replace('www.', '')
        except Exception:
            return "Ver en Portal"

    def save(self, *args, **kwargs):
        from apps.core.utils_image import process_image_to_webp
        # Optimize photos to WebP format if uploaded
        for photo_field_name in ['photo_1', 'photo_2', 'photo_3']:
            field = getattr(self, photo_field_name)
            if field and hasattr(field, 'file') and not str(field.name).lower().endswith('.webp'):
                process_image_to_webp(field, max_size=(1600, 1200))
        super().save(*args, **kwargs)


class PropertyInquiry(TimeStampedModel):
    INQUIRY_TYPE_CHOICES = [
        ('SELLER', 'Propietario (Quiere Vender / Alquilar / Tasar)'),
        ('BUYER', 'Interesado en Comprar / Alquilar'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Contacto'),
        ('CONTACTED', 'En Seguimiento / Contactado'),
        ('VISITING', 'Visita Coordinada'),
        ('NEGOTIATING', 'En Negociación / Reserva'),
        ('CLOSED', 'Operación Concretada'),
        ('CANCELLED', 'Desestimado / Cancelado'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='property_inquiries', verbose_name="Inmobiliaria / Negocio")
    client = models.ForeignKey('crm.Client', on_delete=models.CASCADE, related_name='property_inquiries', verbose_name="Cliente / Interesado")
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name='inquiries', verbose_name="Inmueble de Interés")
    
    inquiry_type = models.CharField(max_length=20, choices=INQUIRY_TYPE_CHOICES, default='SELLER', verbose_name="Tipo de Solicitud")
    operation_type = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tipo de Operación")
    property_type = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tipo de Inmueble")
    address_zone = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ubicación / Barrio / Zona")
    rooms = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ambientes / Dormitorios")
    estimated_price = models.CharField(max_length=100, blank=True, null=True, verbose_name="Precio Estimado / Presupuesto")
    notes = models.TextField(blank=True, null=True, verbose_name="Comentarios / Requerimientos")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="Estado de Gestión")
    agent = models.ForeignKey('business.StaffMember', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_inquiries', verbose_name="Asesor Inmobiliario Asignado")

    class Meta:
        verbose_name = "Consulta / Solicitud Inmobiliaria"
        verbose_name_plural = "Consultas y Solicitudes Inmobiliarias"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_inquiry_type_display()} - {self.client.full_name} ({self.operation_type or 'General'})"
