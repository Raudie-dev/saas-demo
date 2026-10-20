from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, StaffMember
from apps.crm.models import Client
from apps.invoicing.models import Quote

class Project(TimeStampedModel):
    PROJECT_TYPE_CHOICES = [
        ('SOCIAL_MEDIA', 'Gestión de Redes Sociales'),
        ('BRANDING', 'Diseño de Marca & Identidad'),
        ('WEB_DEV', 'Desarrollo Web / E-Commerce'),
        ('MARKETING_ADS', 'Campañas Publicitarias & Ads'),
        ('AUDIOVISUAL', 'Producción Audiovisual & Foto'),
        ('CONSULTING', 'Consultoría & Estrategia'),
        ('OTHER', 'Servicio General / Otro'),
    ]

    STATUS_CHOICES = [
        ('PLANNING', 'En Planificación'),
        ('IN_PROGRESS', 'En Progreso'),
        ('REVIEW', 'En Revisión / Entrega'),
        ('COMPLETED', 'Completado'),
        ('ON_HOLD', 'En Pausa'),
        ('CANCELLED', 'Cancelado'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Baja'),
        ('MEDIUM', 'Media'),
        ('HIGH', 'Alta'),
        ('URGENT', 'Urgente'),
    ]

    PRICING_TYPE_CHOICES = [
        ('FIXED', 'Precio Fijo / Por Proyecto'),
        ('HOURLY', 'Por Horas de Trabajo'),
        ('PERFORMANCE', 'Por Desempeño / Resultados'),
        ('HYBRID', 'Mixto (Horas, Fijo y Desempeño)'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects", verbose_name="Cliente")
    quote = models.ForeignKey(Quote, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects", verbose_name="Cotización Origen")
    responsible = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_projects", verbose_name="Responsable")

    name = models.CharField(max_length=200, verbose_name="Nombre del Proyecto")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción / Alcance")
    project_type = models.CharField(max_length=30, choices=PROJECT_TYPE_CHOICES, default='SOCIAL_MEDIA', verbose_name="Tipo de Proyecto")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNING', verbose_name="Estado")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM', verbose_name="Prioridad")
    pricing_type = models.CharField(max_length=20, choices=PRICING_TYPE_CHOICES, default='FIXED', verbose_name="Modalidad")

    start_date = models.DateField(null=True, blank=True, verbose_name="Fecha de Inicio")
    due_date = models.DateField(null=True, blank=True, verbose_name="Fecha Límite / Entrega")
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Presupuesto Asignado")
    progress_percent = models.PositiveIntegerField(default=0, verbose_name="Avance (%)")
    
    # Horas y desempeño
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="Horas Estimadas")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Tarifa por Hora")

    drive_url = models.URLField(blank=True, null=True, verbose_name="Enlace Google Drive / Assets")
    figma_url = models.URLField(blank=True, null=True, verbose_name="Enlace Figma / Tablero")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"

    def __str__(self):
        client_name = self.client.full_name if self.client else "Interno"
        return f"{self.name} ({client_name})"

    @property
    def completed_tasks_count(self):
        return self.tasks.filter(status='DONE').count()

    @property
    def total_tasks_count(self):
        return self.tasks.count()

    def update_progress_auto(self):
        """Calcula el progreso en base a tareas completadas si existen."""
        total = self.total_tasks_count
        if total > 0:
            completed = self.completed_tasks_count
            self.progress_percent = int((completed / total) * 100)
            self.save(update_fields=['progress_percent'])


class ProjectTask(TimeStampedModel):
    STATUS_CHOICES = [
        ('TODO', 'Por Hacer'),
        ('IN_PROGRESS', 'En Progreso'),
        ('REVIEW', 'En Revisión'),
        ('DONE', 'Completada'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Baja'),
        ('MEDIUM', 'Media'),
        ('HIGH', 'Alta'),
        ('URGENT', 'Urgente'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    assigned_to = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="project_tasks", verbose_name="Asignado a")
    title = models.CharField(max_length=200, verbose_name="Título del Entregable / Tarea")
    description = models.TextField(blank=True, null=True, verbose_name="Detalle de la tarea")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TODO', verbose_name="Estado")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM', verbose_name="Prioridad")
    due_date = models.DateField(null=True, blank=True, verbose_name="Fecha Límite")
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name="Horas Estimadas")
    logged_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name="Horas Reales Trabajadas")

    class Meta:
        ordering = ['status', 'due_date', '-created_at']
        verbose_name = "Tarea / Entregable"
        verbose_name_plural = "Tareas / Entregables"

    def __str__(self):
        return f"{self.title} - {self.project.name}"


class SocialPost(TimeStampedModel):
    PLATFORM_CHOICES = [
        ('INSTAGRAM', 'Instagram'),
        ('TIKTOK', 'TikTok'),
        ('FACEBOOK', 'Facebook'),
        ('YOUTUBE', 'YouTube / Shorts'),
        ('LINKEDIN', 'LinkedIn'),
        ('TWITTER', 'X (Twitter)'),
        ('THREADS', 'Threads'),
        ('OTHER', 'Otra Plataforma'),
    ]

    FORMAT_CHOICES = [
        ('REEL', 'Reel / Video Vertical'),
        ('CAROUSEL', 'Carrusel Informativo'),
        ('STATIC', 'Post Estático / Imagen'),
        ('STORY', 'Historia / Story'),
        ('LONG_VIDEO', 'Video Largo / YouTube'),
        ('ARTICLE', 'Artículo / Texto'),
    ]

    PILLAR_CHOICES = [
        ('EDUCATIONAL', 'Educativo & Valor'),
        ('ENTERTAINMENT', 'Entretenimiento & Tendencias'),
        ('INSPIRATIONAL', 'Inspiración & Storytelling'),
        ('PROMOTIONAL', 'Venta Directa & Promoción'),
        ('BEHIND_SCENES', 'Detrás de Escena & Proceso'),
        ('COMMUNITY', 'Comunidad & Testimonios'),
    ]

    STATUS_CHOICES = [
        ('IDEA', '💡 Idea en Borrador'),
        ('SCRIPT', '📝 Guion / Copy Listo'),
        ('DESIGN', '🎨 En Diseño / Edición'),
        ('CLIENT_REVIEW', '⏳ Esperando Aprobación'),
        ('APPROVED', '✅ Aprobado'),
        ('SCHEDULED', '⏰ Programado'),
        ('PUBLISHED', '🚀 Publicado'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="social_posts")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="social_posts", verbose_name="Cliente / Cuenta")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="social_posts", verbose_name="Proyecto Relacionado")
    assigned_to = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_posts", verbose_name="Creador / Editor")

    title = models.CharField(max_length=200, verbose_name="Título / Idea del Post")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='INSTAGRAM', verbose_name="Red Social")
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='REEL', verbose_name="Formato")
    pillar = models.CharField(max_length=20, choices=PILLAR_CHOICES, default='EDUCATIONAL', verbose_name="Pilar de Contenido")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDEA', verbose_name="Estado de Producción")

    scheduled_date = models.DateTimeField(null=True, blank=True, verbose_name="Fecha y Hora Programada")
    hook = models.CharField(max_length=255, blank=True, null=True, verbose_name="Gancho / Hook inicial")
    caption = models.TextField(blank=True, null=True, verbose_name="Copy / Guión Completo")
    hashtags = models.CharField(max_length=300, blank=True, null=True, verbose_name="Hashtags")
    media_url = models.URLField(blank=True, null=True, verbose_name="Enlace Asset (Drive / Canva / Video)")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas de Producción / Feedback")

    class Meta:
        ordering = ['-scheduled_date', '-created_at']
        verbose_name = "Planificación de Contenido"
        verbose_name_plural = "Planificaciones de Contenido"

    def __str__(self):
        client_name = self.client.full_name if self.client else self.business.name
        return f"[{self.get_platform_display()}] {self.title} ({client_name})"
