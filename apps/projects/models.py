from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, StaffMember
from apps.crm.models import Client
from apps.invoicing.models import Quote

class ProjectType(TimeStampedModel):
    COLOR_CHOICES = [
        ('rose', 'Vinotinto / Rose'),
        ('blue', 'Azul'),
        ('emerald', 'Verde Esmeralda'),
        ('purple', 'Púrpura'),
        ('pink', 'Rosa Fucsia'),
        ('amber', 'Ámbar / Naranja'),
        ('indigo', 'Índigo'),
        ('slate', 'Gris Pizarra'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="project_types")
    name = models.CharField(max_length=100, verbose_name="Nombre del Tipo")
    code = models.CharField(max_length=50, blank=True, verbose_name="Código")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción / Alcance")
    color = models.CharField(max_length=30, choices=COLOR_CHOICES, default='rose', verbose_name="Color de Etiqueta")
    icon = models.CharField(max_length=50, default='folder-kanban', verbose_name="Ícono Lucide")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        ordering = ['name']
        verbose_name = "Tipo de Proyecto"
        verbose_name_plural = "Tipos de Proyecto"

    def __str__(self):
        return self.name

    @property
    def badge_class(self):
        color_map = {
            'rose': 'bg-rose-50 text-rose-700 border-rose-200',
            'blue': 'bg-blue-50 text-blue-700 border-blue-200',
            'emerald': 'bg-emerald-50 text-emerald-700 border-emerald-200',
            'purple': 'bg-purple-50 text-purple-700 border-purple-200',
            'pink': 'bg-pink-50 text-pink-700 border-pink-200',
            'amber': 'bg-amber-50 text-amber-700 border-amber-200',
            'indigo': 'bg-indigo-50 text-indigo-700 border-indigo-200',
            'slate': 'bg-slate-100 text-slate-700 border-slate-200',
        }
        return color_map.get(self.color, 'bg-slate-100 text-slate-700 border-slate-200')

    @property
    def dot_color(self):
        dot_map = {
            'rose': 'bg-rose-500',
            'blue': 'bg-blue-500',
            'emerald': 'bg-emerald-500',
            'purple': 'bg-purple-500',
            'pink': 'bg-pink-500',
            'amber': 'bg-amber-500',
            'indigo': 'bg-indigo-500',
            'slate': 'bg-slate-500',
        }
        return dot_map.get(self.color, 'bg-slate-500')


class Project(TimeStampedModel):
    PROJECT_TYPE_CHOICES = [
        ('SOCIAL_MEDIA', 'Redes Sociales'),
        ('BRANDING', 'Branding'),
        ('WEB_DEV', 'Desarrollo Web'),
        ('MARKETING_ADS', 'Marketing & Ads'),
        ('AUDIOVISUAL', 'Audiovisual'),
        ('CONSULTING', 'Consultoría'),
        ('OTHER', 'General'),
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
    project_type = models.CharField(max_length=30, choices=PROJECT_TYPE_CHOICES, default='SOCIAL_MEDIA', verbose_name="Tipo de Proyecto (Legacy)")
    custom_type = models.ForeignKey(
        ProjectType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name="Tipo de Proyecto Personalizado"
    )
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
    def display_type(self):
        if self.custom_type:
            return self.custom_type.name
        return self.get_project_type_display()

    @property
    def type_badge_class(self):
        if self.custom_type:
            return self.custom_type.badge_class
        type_color_map = {
            'SOCIAL_MEDIA': 'bg-pink-50 text-pink-700 border-pink-200',
            'BRANDING': 'bg-purple-50 text-purple-700 border-purple-200',
            'WEB_DEV': 'bg-blue-50 text-blue-700 border-blue-200',
            'MARKETING_ADS': 'bg-amber-50 text-amber-700 border-amber-200',
            'AUDIOVISUAL': 'bg-rose-50 text-rose-700 border-rose-200',
            'CONSULTING': 'bg-emerald-50 text-emerald-700 border-emerald-200',
            'OTHER': 'bg-slate-100 text-slate-700 border-slate-200',
        }
        return type_color_map.get(self.project_type, 'bg-slate-100 text-slate-700 border-slate-200')

    @property
    def type_icon(self):
        if self.custom_type and self.custom_type.icon:
            return self.custom_type.icon
        type_icon_map = {
            'SOCIAL_MEDIA': 'share-2',
            'BRANDING': 'palette',
            'WEB_DEV': 'globe',
            'MARKETING_ADS': 'target',
            'AUDIOVISUAL': 'video',
            'CONSULTING': 'briefcase',
            'OTHER': 'folder-kanban',
        }
        return type_icon_map.get(self.project_type, 'folder-kanban')

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

    @property
    def checklist_stats(self):
        total = self.checklists.count()
        completed = self.checklists.filter(is_completed=True).count()
        percent = int((completed / total) * 100) if total > 0 else 0
        return {
            'total': total,
            'completed': completed,
            'percent': percent,
        }


class TaskChecklistItem(TimeStampedModel):
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name="checklists")
    title = models.CharField(max_length=255, verbose_name="Elemento de Checklist")
    is_completed = models.BooleanField(default=False, verbose_name="Completado")
    order = models.PositiveIntegerField(default=0, verbose_name="Orden")

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Elemento de Checklist"
        verbose_name_plural = "Elementos de Checklist"

    def __str__(self):
        status = "✓" if self.is_completed else "○"
        return f"{status} {self.title}"


