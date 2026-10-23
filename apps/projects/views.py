from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.core.paginator import Paginator

from apps.business.models import Business, StaffMember
from apps.crm.models import Client
from apps.projects.models import Project, ProjectType, ProjectTask
from apps.core.utils import parse_decimal

DEFAULT_PROJECT_TYPES = [
    {
        'name': 'Gestión de Redes Sociales',
        'code': 'SOCIAL_MEDIA',
        'color': 'pink',
        'icon': 'share-2',
        'description': 'Estrategia, parrillas de contenido, reels y community management.'
    },
    {
        'name': 'Diseño de Marca & Identidad',
        'code': 'BRANDING',
        'color': 'purple',
        'icon': 'palette',
        'description': 'Logotipos, manuales de marca, tipografía y diseño gráfico corporativo.'
    },
    {
        'name': 'Desarrollo Web / E-Commerce',
        'code': 'WEB_DEV',
        'color': 'blue',
        'icon': 'globe',
        'description': 'Sitios web corporativos, tiendas online, landing pages y plataformas.'
    },
    {
        'name': 'Campañas Publicitarias & Ads',
        'code': 'MARKETING_ADS',
        'color': 'amber',
        'icon': 'target',
        'description': 'Pauta digital en Meta Ads, Google Ads y generación de leads.'
    },
    {
        'name': 'Producción Audiovisual & Foto',
        'code': 'AUDIOVISUAL',
        'color': 'rose',
        'icon': 'video',
        'description': 'Grabación de video, sesiones de fotos de producto y post-producción.'
    },
    {
        'name': 'Consultoría & Estrategia',
        'code': 'CONSULTING',
        'color': 'emerald',
        'icon': 'briefcase',
        'description': 'Asesoría de negocio, auditorías digitales y optimización de embudos.'
    },
    {
        'name': 'Servicio General / Otro',
        'code': 'OTHER',
        'color': 'slate',
        'icon': 'folder-kanban',
        'description': 'Proyectos a medida, desarrollos especiales u otros entregables.'
    },
]

def ensure_default_project_types(business):
    if not business:
        return
    if not ProjectType.objects.filter(business=business).exists():
        for item in DEFAULT_PROJECT_TYPES:
            ProjectType.objects.create(
                business=business,
                name=item['name'],
                code=item['code'],
                color=item['color'],
                icon=item['icon'],
                description=item['description'],
                is_active=True
            )
    # Vincular proyectos existentes que no tengan custom_type
    projects_without_type = Project.objects.filter(business=business, custom_type__isnull=True)
    if projects_without_type.exists():
        types_by_code = {t.code: t for t in ProjectType.objects.filter(business=business)}
        for p in projects_without_type:
            if p.project_type in types_by_code:
                p.custom_type = types_by_code[p.project_type]
                p.save(update_fields=['custom_type'])

# ==========================================
# GESTIÓN DE PROYECTOS Y ENTREGABLES
# ==========================================

@login_required
def project_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    ensure_default_project_types(business)

    status_filter = request.GET.get('status', '').strip()
    type_filter = request.GET.get('type', '').strip()
    search_query = request.GET.get('q', '').strip()
    view_mode = request.GET.get('view', 'kanban').strip()

    projects_qs = Project.objects.filter(business=business).select_related('client', 'responsible', 'custom_type').prefetch_related('tasks')

    if type_filter:
        projects_qs = projects_qs.filter(
            models.Q(custom_type_id=type_filter) | models.Q(project_type=type_filter)
        )
    if search_query:
        projects_qs = projects_qs.filter(
            models.Q(name__icontains=search_query) |
            models.Q(client__first_name__icontains=search_query) |
            models.Q(client__last_name__icontains=search_query) |
            models.Q(description__icontains=search_query)
        )

    # Lista completa para el tablero Kanban
    kanban_projects = list(projects_qs.order_by('-priority', '-created_at'))

    # Métricas generales de proyectos
    all_projects = Project.objects.filter(business=business)
    total_projects = all_projects.count()
    active_projects = all_projects.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).count()
    completed_projects = all_projects.filter(status='COMPLETED').count()
    total_budget = sum(p.budget for p in all_projects.filter(status__in=['IN_PROGRESS', 'COMPLETED']))

    # Definición de Columnas Kanban Trello para Proyectos
    columns = [
        {
            'code': 'PLANNING',
            'label': 'En Planificación',
            'icon': 'clipboard-list',
            'header_bg': 'bg-slate-100/90 text-slate-800 border-slate-200',
            'badge_bg': 'bg-slate-200/80 text-slate-700',
            'dot_color': 'bg-slate-500',
            'projects': [p for p in kanban_projects if p.status == 'PLANNING'],
        },
        {
            'code': 'IN_PROGRESS',
            'label': 'En Progreso',
            'icon': 'play',
            'header_bg': 'bg-blue-50/90 text-blue-900 border-blue-200',
            'badge_bg': 'bg-blue-100 text-blue-800',
            'dot_color': 'bg-blue-600',
            'projects': [p for p in kanban_projects if p.status == 'IN_PROGRESS'],
        },
        {
            'code': 'REVIEW',
            'label': 'En Revisión / Entrega',
            'icon': 'eye',
            'header_bg': 'bg-purple-50/90 text-purple-900 border-purple-200',
            'badge_bg': 'bg-purple-100 text-purple-800',
            'dot_color': 'bg-purple-600',
            'projects': [p for p in kanban_projects if p.status == 'REVIEW'],
        },
        {
            'code': 'ON_HOLD',
            'label': 'En Pausa',
            'icon': 'pause',
            'header_bg': 'bg-amber-50/90 text-amber-900 border-amber-200',
            'badge_bg': 'bg-amber-100 text-amber-800',
            'dot_color': 'bg-amber-600',
            'projects': [p for p in kanban_projects if p.status == 'ON_HOLD'],
        },
        {
            'code': 'COMPLETED',
            'label': 'Completados',
            'icon': 'check-circle-2',
            'header_bg': 'bg-emerald-50/90 text-emerald-900 border-emerald-200',
            'badge_bg': 'bg-emerald-100 text-emerald-800',
            'dot_color': 'bg-emerald-600',
            'projects': [p for p in kanban_projects if p.status == 'COMPLETED'],
        },
    ]

    for col in columns:
        col['count'] = len(col['projects'])
        col['total_budget'] = sum(p.budget for p in col['projects'])

    # Vista lista / cuadrícula
    grid_projects = projects_qs
    if status_filter:
        grid_projects = grid_projects.filter(status=status_filter)
    grid_projects = grid_projects.order_by('-created_at')

    paginator = Paginator(grid_projects, 9)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'projects/project_list.html', {
        'business': business,
        'projects': page_obj,
        'page_obj': page_obj,
        'columns': columns,
        'view_mode': view_mode,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'total_budget': total_budget,
        'project_types': ProjectType.objects.filter(business=business, is_active=True).order_by('name'),
        'status_choices': Project.STATUS_CHOICES,
    })


@login_required
def project_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None

        responsible_id = request.POST.get('responsible_id')
        responsible = StaffMember.objects.filter(id=responsible_id, business=business).first() if responsible_id else None

        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        custom_type_id = request.POST.get('custom_type_id') or request.POST.get('project_type')
        custom_type = ProjectType.objects.filter(id=custom_type_id, business=business).first() if custom_type_id else None
        project_type_code = custom_type.code if custom_type and custom_type.code else (request.POST.get('project_type') or 'OTHER')

        pricing_type = request.POST.get('pricing_type', 'FIXED')
        status = request.POST.get('status', 'PLANNING')
        priority = request.POST.get('priority', 'MEDIUM')
        start_date = request.POST.get('start_date') or timezone.now().date()
        due_date = request.POST.get('due_date') or None
        budget = parse_decimal(request.POST.get('budget'), '0.00')
        estimated_hours = parse_decimal(request.POST.get('estimated_hours'), '0.00')
        hourly_rate = parse_decimal(request.POST.get('hourly_rate'), '0.00')
        drive_url = request.POST.get('drive_url', '').strip()
        figma_url = request.POST.get('figma_url', '').strip()

        project = Project.objects.create(
            business=business,
            client=client,
            responsible=responsible,
            name=name,
            description=description,
            project_type=project_type_code,
            custom_type=custom_type,
            pricing_type=pricing_type,
            status=status,
            priority=priority,
            start_date=start_date,
            due_date=due_date,
            budget=budget,
            estimated_hours=estimated_hours,
            hourly_rate=hourly_rate,
            drive_url=drive_url,
            figma_url=figma_url,
            progress_percent=0
        )

        return redirect('project_detail', project_id=project.id)

    preselected_client_id = request.GET.get('client_id')
    preselected_status = request.GET.get('status')

    return render(request, 'projects/project_form.html', {
        'business': business,
        'project': None,
        'clients': clients,
        'staff_members': staff_members,
        'preselected_client_id': preselected_client_id,
        'preselected_status': preselected_status,
        'project_types': ProjectType.objects.filter(business=business, is_active=True).order_by('name'),
        'pricing_types': Project.PRICING_TYPE_CHOICES,
        'status_choices': Project.STATUS_CHOICES,
        'priority_choices': Project.PRIORITY_CHOICES,
        'today': timezone.now().date(),
    })


@login_required
def project_detail_view(request, project_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    project = get_object_or_404(
        Project.objects.select_related('client', 'responsible', 'quote'),
        id=project_id,
        business=business
    )
    tasks = project.tasks.select_related('assigned_to').all()
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    total_task_estimated_hours = sum(t.estimated_hours for t in tasks)
    total_task_logged_hours = sum(t.logged_hours for t in tasks)

    # Columnas Kanban Trello para Tareas del Proyecto
    task_columns = [
        {
            'code': 'TODO',
            'label': 'Por Hacer',
            'icon': 'circle',
            'header_bg': 'bg-slate-100/90 text-slate-800 border-slate-200',
            'badge_bg': 'bg-slate-200/80 text-slate-700',
            'dot_color': 'bg-slate-400',
            'tasks': [t for t in tasks if t.status == 'TODO'],
        },
        {
            'code': 'IN_PROGRESS',
            'label': 'En Progreso',
            'icon': 'play',
            'header_bg': 'bg-blue-50/90 text-blue-900 border-blue-200',
            'badge_bg': 'bg-blue-100 text-blue-800',
            'dot_color': 'bg-blue-600',
            'tasks': [t for t in tasks if t.status == 'IN_PROGRESS'],
        },
        {
            'code': 'REVIEW',
            'label': 'En Revisión',
            'icon': 'eye',
            'header_bg': 'bg-purple-50/90 text-purple-900 border-purple-200',
            'badge_bg': 'bg-purple-100 text-purple-800',
            'dot_color': 'bg-purple-600',
            'tasks': [t for t in tasks if t.status == 'REVIEW'],
        },
        {
            'code': 'DONE',
            'label': 'Completadas',
            'icon': 'check-circle-2',
            'header_bg': 'bg-emerald-50/90 text-emerald-900 border-emerald-200',
            'badge_bg': 'bg-emerald-100 text-emerald-800',
            'dot_color': 'bg-emerald-600',
            'tasks': [t for t in tasks if t.status == 'DONE'],
        },
    ]

    for col in task_columns:
        col['count'] = len(col['tasks'])
        col['total_hours'] = sum(t.estimated_hours for t in col['tasks'])

    return render(request, 'projects/project_detail.html', {
        'business': business,
        'project': project,
        'tasks': tasks,
        'task_columns': task_columns,
        'staff_members': staff_members,
        'priority_choices': ProjectTask.PRIORITY_CHOICES,
        'task_status_choices': ProjectTask.STATUS_CHOICES,
        'total_task_estimated_hours': total_task_estimated_hours,
        'total_task_logged_hours': total_task_logged_hours,
        'today': timezone.now().date(),
    })


@login_required
def project_edit_view(request, project_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    project = get_object_or_404(Project, id=project_id, business=business)
    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        project.client = Client.objects.filter(id=client_id, business=business).first() if client_id else None

        responsible_id = request.POST.get('responsible_id')
        project.responsible = StaffMember.objects.filter(id=responsible_id, business=business).first() if responsible_id else None

        project.name = request.POST.get('name', project.name).strip()
        project.description = request.POST.get('description', '').strip()

        custom_type_id = request.POST.get('custom_type_id') or request.POST.get('project_type')
        if custom_type_id:
            custom_type = ProjectType.objects.filter(id=custom_type_id, business=business).first()
            if custom_type:
                project.custom_type = custom_type
                if custom_type.code:
                    project.project_type = custom_type.code
            else:
                project.project_type = custom_type_id

        project.pricing_type = request.POST.get('pricing_type', project.pricing_type)
        project.status = request.POST.get('status', project.status)
        project.priority = request.POST.get('priority', project.priority)
        project.start_date = request.POST.get('start_date') or project.start_date
        project.due_date = request.POST.get('due_date') or None
        project.budget = parse_decimal(request.POST.get('budget'), '0.00')
        project.estimated_hours = parse_decimal(request.POST.get('estimated_hours'), '0.00')
        project.hourly_rate = parse_decimal(request.POST.get('hourly_rate'), '0.00')

        progress_val = request.POST.get('progress_percent')
        if progress_val is not None:
            try:
                project.progress_percent = min(100, max(0, int(progress_val)))
            except ValueError:
                pass

        project.drive_url = request.POST.get('drive_url', '').strip()
        project.figma_url = request.POST.get('figma_url', '').strip()
        project.save()

        return redirect('project_detail', project_id=project.id)

    return render(request, 'projects/project_form.html', {
        'business': business,
        'project': project,
        'clients': clients,
        'staff_members': staff_members,
        'project_types': ProjectType.objects.filter(business=business, is_active=True).order_by('name'),
        'pricing_types': Project.PRICING_TYPE_CHOICES,
        'status_choices': Project.STATUS_CHOICES,
        'priority_choices': Project.PRIORITY_CHOICES,
        'today': project.start_date or timezone.now().date(),
    })


@login_required
def project_status_update_view(request, project_id):
    """Actualiza el estado de un proyecto vía AJAX (drag and drop del Kanban)"""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=403)

    project = get_object_or_404(Project, id=project_id, business=business)

    if request.method == 'POST':
        import json
        new_status = None
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                new_status = body.get('status')
            except Exception:
                pass
        if not new_status:
            new_status = request.POST.get('status')

        valid_statuses = [code for code, _ in Project.STATUS_CHOICES]
        if new_status in valid_statuses:
            project.status = new_status
            project.save(update_fields=['status'])
            return JsonResponse({
                'success': True,
                'project_id': str(project.id),
                'new_status': project.status,
                'status_display': project.get_status_display()
            })

        return JsonResponse({'success': False, 'error': f'Estado no válido: {new_status}'}, status=400)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def project_quick_update_view(request, project_id):
    """Actualiza recursos (enlaces Drive/Figma) y descripción/delimitaciones del proyecto."""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=403)

    project = get_object_or_404(Project, id=project_id, business=business)

    if request.method == 'POST':
        import json
        is_json = request.content_type == 'application/json'
        data = {}
        if is_json:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        else:
            data = request.POST

        drive_url = data.get('drive_url', '').strip()
        figma_url = data.get('figma_url', '').strip()
        description = data.get('description', '').strip()

        project.drive_url = drive_url
        project.figma_url = figma_url
        project.description = description
        project.save(update_fields=['drive_url', 'figma_url', 'description'])

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or is_json:
            return JsonResponse({
                'success': True,
                'message': 'Recursos y delimitaciones actualizados correctamente',
                'drive_url': project.drive_url,
                'figma_url': project.figma_url,
                'description': project.description,
            })

        messages.success(request, 'Información del proyecto actualizada correctamente.')
        return redirect('project_detail', project_id=project.id)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def project_delete_view(request, project_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    project = get_object_or_404(Project, id=project_id, business=business)
    if request.method == 'POST':
        project.delete()
        return redirect('project_list')

    return redirect('project_detail', project_id=project.id)


@login_required
def project_task_create_view(request, project_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    project = get_object_or_404(Project, id=project_id, business=business)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        priority = request.POST.get('priority', 'MEDIUM')
        status = request.POST.get('status', 'TODO')
        valid_statuses = [code for code, _ in ProjectTask.STATUS_CHOICES]
        if status not in valid_statuses:
            status = 'TODO'

        due_date = request.POST.get('due_date') or None
        estimated_hours = parse_decimal(request.POST.get('estimated_hours'), '0.00')
        assigned_to_id = request.POST.get('assigned_to_id')
        assigned_to = StaffMember.objects.filter(id=assigned_to_id, business=business).first() if assigned_to_id else None

        if title:
            task = ProjectTask.objects.create(
                project=project,
                title=title,
                description=description,
                priority=priority,
                status=status,
                due_date=due_date,
                assigned_to=assigned_to,
                estimated_hours=estimated_hours,
            )
            project.update_progress_auto()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'success': True,
                    'task': {
                        'id': str(task.id),
                        'title': task.title,
                        'status': task.status,
                        'status_display': task.get_status_display(),
                        'priority': task.priority,
                        'priority_display': task.get_priority_display(),
                        'estimated_hours': float(task.estimated_hours),
                        'assigned_to': task.assigned_to.first_name if task.assigned_to else None,
                        'due_date': task.due_date.strftime('%d/%m/%Y') if task.due_date else None,
                    },
                    'progress_percent': project.progress_percent,
                    'completed_tasks': project.completed_tasks_count,
                    'total_tasks': project.total_tasks_count
                })

    return redirect('project_detail', project_id=project.id)


@login_required
def project_task_detail_api(request, task_id):
    """Retorna los datos completos de una tarea o procesa su edición/actualización"""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=403)

    task = get_object_or_404(ProjectTask, id=task_id, project__business=business)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'task': {
                'id': str(task.id),
                'project_id': str(task.project.id),
                'project_name': task.project.name,
                'title': task.title,
                'description': task.description or '',
                'status': task.status,
                'status_display': task.get_status_display(),
                'priority': task.priority,
                'priority_display': task.get_priority_display(),
                'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
                'due_date_display': task.due_date.strftime('%d/%m/%Y') if task.due_date else '',
                'estimated_hours': float(task.estimated_hours),
                'logged_hours': float(task.logged_hours),
                'assigned_to_id': str(task.assigned_to.id) if task.assigned_to else '',
                'assigned_to_name': task.assigned_to.first_name if task.assigned_to else 'Sin asignar',
                'created_at': task.created_at.strftime('%d/%m/%Y %H:%M') if hasattr(task, 'created_at') and task.created_at else '',
            }
        })

    if request.method == 'POST':
        import json
        data = request.POST
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = request.POST

        title = str(data.get('title', '')).strip()
        description = str(data.get('description', '')).strip()
        priority = data.get('priority', task.priority)
        status = data.get('status', task.status)
        valid_statuses = [code for code, _ in ProjectTask.STATUS_CHOICES]
        valid_priorities = [code for code, _ in ProjectTask.PRIORITY_CHOICES]

        if title:
            task.title = title
        task.description = description

        if status in valid_statuses:
            task.status = status
        if priority in valid_priorities:
            task.priority = priority

        due_date = data.get('due_date')
        task.due_date = due_date if due_date else None

        if 'estimated_hours' in data:
            task.estimated_hours = parse_decimal(data.get('estimated_hours'), '0.00')

        if 'logged_hours' in data:
            task.logged_hours = parse_decimal(data.get('logged_hours'), '0.00')

        assigned_to_id = data.get('assigned_to_id')
        if assigned_to_id:
            task.assigned_to = StaffMember.objects.filter(id=assigned_to_id, business=business).first()
        else:
            task.assigned_to = None

        task.save()
        task.project.update_progress_auto()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json' or request.content_type == 'application/json':
            return JsonResponse({
                'success': True,
                'message': 'Tarea actualizada correctamente',
                'task': {
                    'id': str(task.id),
                    'title': task.title,
                    'description': task.description or '',
                    'status': task.status,
                    'status_display': task.get_status_display(),
                    'priority': task.priority,
                    'priority_display': task.get_priority_display(),
                    'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
                    'due_date_display': task.due_date.strftime('%d/%m/%Y') if task.due_date else '',
                    'estimated_hours': float(task.estimated_hours),
                    'logged_hours': float(task.logged_hours),
                    'assigned_to_id': str(task.assigned_to.id) if task.assigned_to else '',
                    'assigned_to_name': task.assigned_to.first_name if task.assigned_to else 'Sin asignar',
                },
                'progress_percent': task.project.progress_percent,
                'completed_tasks': task.project.completed_tasks_count,
                'total_tasks': task.project.total_tasks_count
            })

        messages.success(request, f"Tarea '{task.title}' actualizada correctamente.")
        return redirect('project_detail', project_id=task.project.id)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def project_task_edit_view(request, task_id):
    return project_task_detail_api(request, task_id)


@login_required
def project_task_status_update_view(request, task_id):
    """Actualiza el estado de una tarea vía AJAX (drag and drop del Kanban de tareas)"""
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=403)

    task = get_object_or_404(ProjectTask, id=task_id, project__business=business)

    if request.method == 'POST':
        import json
        new_status = None
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                new_status = body.get('status')
            except Exception:
                pass
        if not new_status:
            new_status = request.POST.get('status')

        valid_statuses = [code for code, _ in ProjectTask.STATUS_CHOICES]
        if new_status in valid_statuses:
            task.status = new_status
            task.save(update_fields=['status'])
            task.project.update_progress_auto()
            return JsonResponse({
                'success': True,
                'task_id': str(task.id),
                'new_status': task.status,
                'status_display': task.get_status_display(),
                'progress_percent': task.project.progress_percent,
                'completed_tasks': task.project.completed_tasks_count,
                'total_tasks': task.project.total_tasks_count
            })

        return JsonResponse({'success': False, 'error': f'Estado no válido: {new_status}'}, status=400)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def project_task_toggle_view(request, task_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return JsonResponse({'success': False}, status=403)

    task = get_object_or_404(ProjectTask, id=task_id, project__business=business)
    if task.status == 'DONE':
        task.status = 'TODO'
    else:
        task.status = 'DONE'
    task.save(update_fields=['status'])

    task.project.update_progress_auto()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'success': True,
            'new_status': task.status,
            'progress_percent': task.project.progress_percent,
            'completed_tasks': task.project.completed_tasks_count,
            'total_tasks': task.project.total_tasks_count
        })

    return redirect('project_detail', project_id=task.project.id)


@login_required
def project_task_delete_view(request, task_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    task = get_object_or_404(ProjectTask, id=task_id, project__business=business)
    project_id = task.project.id
    if request.method == 'POST':
        task.delete()
        project = Project.objects.filter(id=project_id).first()
        if project:
            project.update_progress_auto()

    return redirect('project_detail', project_id=project_id)


# ==========================================
# GESTIÓN DE TIPOS DE PROYECTO
# ==========================================

@login_required
def project_types_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    ensure_default_project_types(business)

    types = ProjectType.objects.filter(business=business).annotate(
        projects_count=models.Count('projects')
    ).order_by('-is_active', 'name')

    total_types = types.count()
    active_types = types.filter(is_active=True).count()
    total_linked_projects = Project.objects.filter(business=business, custom_type__isnull=False).count()

    return render(request, 'projects/project_types.html', {
        'business': business,
        'types': types,
        'total_types': total_types,
        'active_types': active_types,
        'total_linked_projects': total_linked_projects,
        'color_choices': ProjectType.COLOR_CHOICES,
    })


@login_required
def project_type_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        color = request.POST.get('color', 'rose').strip()
        icon = request.POST.get('icon', 'folder-kanban').strip()

        if name:
            pt = ProjectType.objects.create(
                business=business,
                name=name,
                description=description,
                color=color,
                icon=icon or 'folder-kanban',
                is_active=True
            )
            messages.success(request, f"Tipo de proyecto '{name}' creado exitosamente.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'success': True,
                    'id': str(pt.id),
                    'name': pt.name,
                    'color': pt.color,
                    'badge_class': pt.badge_class,
                })
        else:
            messages.error(request, "El nombre del tipo de proyecto es obligatorio.")

    next_url = request.POST.get('next') or request.GET.get('next') or 'project_types'
    return redirect(next_url)


@login_required
def project_type_edit_view(request, type_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    pt = get_object_or_404(ProjectType, id=type_id, business=business)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        color = request.POST.get('color', pt.color).strip()
        icon = request.POST.get('icon', pt.icon).strip()
        is_active = request.POST.get('is_active') in ['true', '1', 'on'] or 'is_active' in request.POST

        if name:
            pt.name = name
            pt.description = description
            pt.color = color
            pt.icon = icon or 'folder-kanban'
            pt.is_active = is_active
            pt.save()
            messages.success(request, f"Tipo de proyecto '{name}' actualizado.")
        else:
            messages.error(request, "El nombre es obligatorio.")

    return redirect('project_types')


@login_required
def project_type_delete_view(request, type_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    pt = get_object_or_404(ProjectType, id=type_id, business=business)

    if request.method == 'POST':
        name = pt.name
        pt.delete()
        messages.success(request, f"Tipo de proyecto '{name}' eliminado.")

    return redirect('project_types')

