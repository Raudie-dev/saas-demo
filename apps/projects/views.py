from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import models
from django.core.paginator import Paginator

from apps.business.models import Business, StaffMember
from apps.crm.models import Client
from apps.projects.models import Project, ProjectTask, SocialPost
from apps.core.utils import parse_decimal

# ==========================================
# GESTIÓN DE PROYECTOS Y ENTREGABLES
# ==========================================

@login_required
def project_list_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    status_filter = request.GET.get('status', '').strip()
    type_filter = request.GET.get('type', '').strip()
    search_query = request.GET.get('q', '').strip()

    projects = Project.objects.filter(business=business).select_related('client', 'responsible')

    if status_filter:
        projects = projects.filter(status=status_filter)
    if type_filter:
        projects = projects.filter(project_type=type_filter)
    if search_query:
        projects = projects.filter(
            models.Q(name__icontains=search_query) |
            models.Q(client__first_name__icontains=search_query) |
            models.Q(client__last_name__icontains=search_query)
        )

    projects = projects.order_by('-created_at')

    # Métricas de proyectos
    all_projects = Project.objects.filter(business=business)
    total_projects = all_projects.count()
    active_projects = all_projects.filter(status__in=['PLANNING', 'IN_PROGRESS', 'REVIEW']).count()
    completed_projects = all_projects.filter(status='COMPLETED').count()
    total_budget = sum(p.budget for p in all_projects.filter(status__in=['IN_PROGRESS', 'COMPLETED']))

    paginator = Paginator(projects, 9)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'projects/project_list.html', {
        'business': business,
        'projects': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'total_budget': total_budget,
        'project_types': Project.PROJECT_TYPE_CHOICES,
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
        project_type = request.POST.get('project_type', 'SOCIAL_MEDIA')
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
            project_type=project_type,
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

    return render(request, 'projects/project_form.html', {
        'business': business,
        'project': None,
        'clients': clients,
        'staff_members': staff_members,
        'preselected_client_id': preselected_client_id,
        'project_types': Project.PROJECT_TYPE_CHOICES,
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
    social_posts = project.social_posts.all().order_by('-scheduled_date')[:6]
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    total_task_estimated_hours = sum(t.estimated_hours for t in tasks)
    total_task_logged_hours = sum(t.logged_hours for t in tasks)

    return render(request, 'projects/project_detail.html', {
        'business': business,
        'project': project,
        'tasks': tasks,
        'social_posts': social_posts,
        'staff_members': staff_members,
        'priority_choices': ProjectTask.PRIORITY_CHOICES,
        'total_task_estimated_hours': total_task_estimated_hours,
        'total_task_logged_hours': total_task_logged_hours,
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
        project.project_type = request.POST.get('project_type', project.project_type)
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
        'project_types': Project.PROJECT_TYPE_CHOICES,
        'pricing_types': Project.PRICING_TYPE_CHOICES,
        'status_choices': Project.STATUS_CHOICES,
        'priority_choices': Project.PRIORITY_CHOICES,
        'today': project.start_date or timezone.now().date(),
    })


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
        due_date = request.POST.get('due_date') or None
        estimated_hours = parse_decimal(request.POST.get('estimated_hours'), '0.00')
        assigned_to_id = request.POST.get('assigned_to_id')
        assigned_to = StaffMember.objects.filter(id=assigned_to_id, business=business).first() if assigned_to_id else None

        if title:
            ProjectTask.objects.create(
                project=project,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date,
                assigned_to=assigned_to,
                estimated_hours=estimated_hours,
                status='TODO'
            )
            project.update_progress_auto()

    return redirect('project_detail', project_id=project.id)

    return redirect('project_detail', project_id=project.id)


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
# PLANIFICADOR DE CONTENIDO PARA REDES SOCIALES
# ==========================================

@login_required
def content_planner_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    platform_filter = request.GET.get('platform', '').strip()
    status_filter = request.GET.get('status', '').strip()
    client_filter = request.GET.get('client_id', '').strip()
    search_query = request.GET.get('q', '').strip()

    posts = SocialPost.objects.filter(business=business).select_related('client', 'project', 'assigned_to')

    if platform_filter:
        posts = posts.filter(platform=platform_filter)
    if status_filter:
        posts = posts.filter(status=status_filter)
    if client_filter:
        posts = posts.filter(client_id=client_filter)
    if search_query:
        posts = posts.filter(
            models.Q(title__icontains=search_query) |
            models.Q(caption__icontains=search_query) |
            models.Q(hook__icontains=search_query)
        )

    posts = posts.order_by('-scheduled_date', '-created_at')

    # Métricas
    all_posts = SocialPost.objects.filter(business=business)
    total_posts = all_posts.count()
    in_production = all_posts.filter(status__in=['IDEA', 'SCRIPT', 'DESIGN']).count()
    awaiting_review = all_posts.filter(status='CLIENT_REVIEW').count()
    published_or_scheduled = all_posts.filter(status__in=['SCHEDULED', 'PUBLISHED']).count()

    clients = Client.objects.filter(business=business).order_by('first_name')

    # Agrupación estilo Kanban
    columns = [
        {'code': 'IDEA', 'label': '💡 Ideas', 'posts': [p for p in posts if p.status == 'IDEA']},
        {'code': 'SCRIPT', 'label': '📝 Guion / Copy', 'posts': [p for p in posts if p.status == 'SCRIPT']},
        {'code': 'DESIGN', 'label': '🎨 En Diseño', 'posts': [p for p in posts if p.status == 'DESIGN']},
        {'code': 'CLIENT_REVIEW', 'label': '⏳ En Aprobación', 'posts': [p for p in posts if p.status == 'CLIENT_REVIEW']},
        {'code': 'APPROVED', 'label': '✅ Aprobados', 'posts': [p for p in posts if p.status == 'APPROVED']},
        {'code': 'SCHEDULED', 'label': '⏰ Programados / Listos', 'posts': [p for p in posts if p.status in ['SCHEDULED', 'PUBLISHED']]},
    ]

    return render(request, 'projects/content_planner.html', {
        'business': business,
        'posts': posts,
        'columns': columns,
        'clients': clients,
        'platform_filter': platform_filter,
        'status_filter': status_filter,
        'client_filter': client_filter,
        'search_query': search_query,
        'total_posts': total_posts,
        'in_production': in_production,
        'awaiting_review': awaiting_review,
        'published_or_scheduled': published_or_scheduled,
        'platform_choices': SocialPost.PLATFORM_CHOICES,
        'status_choices': SocialPost.STATUS_CHOICES,
        'format_choices': SocialPost.FORMAT_CHOICES,
    })


@login_required
def social_post_create_view(request):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    projects = Project.objects.filter(business=business).order_by('-created_at')
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        client = Client.objects.filter(id=client_id, business=business).first() if client_id else None

        project_id = request.POST.get('project_id')
        project = Project.objects.filter(id=project_id, business=business).first() if project_id else None

        assigned_to_id = request.POST.get('assigned_to_id')
        assigned_to = StaffMember.objects.filter(id=assigned_to_id, business=business).first() if assigned_to_id else None

        title = request.POST.get('title', '').strip()
        platform = request.POST.get('platform', 'INSTAGRAM')
        post_format = request.POST.get('format', 'REEL')
        pillar = request.POST.get('pillar', 'EDUCATIONAL')
        status = request.POST.get('status', 'IDEA')
        scheduled_date = request.POST.get('scheduled_date') or None
        hook = request.POST.get('hook', '').strip()
        caption = request.POST.get('caption', '').strip()
        hashtags = request.POST.get('hashtags', '').strip()
        media_url = request.POST.get('media_url', '').strip()
        notes = request.POST.get('notes', '').strip()

        post = SocialPost.objects.create(
            business=business,
            client=client,
            project=project,
            assigned_to=assigned_to,
            title=title,
            platform=platform,
            format=post_format,
            pillar=pillar,
            status=status,
            scheduled_date=scheduled_date,
            hook=hook,
            caption=caption,
            hashtags=hashtags,
            media_url=media_url,
            notes=notes
        )

        return redirect('content_planner')

    preselected_client_id = request.GET.get('client_id')
    preselected_project_id = request.GET.get('project_id')

    return render(request, 'projects/social_post_form.html', {
        'business': business,
        'post': None,
        'clients': clients,
        'projects': projects,
        'staff_members': staff_members,
        'preselected_client_id': preselected_client_id,
        'preselected_project_id': preselected_project_id,
        'platform_choices': SocialPost.PLATFORM_CHOICES,
        'format_choices': SocialPost.FORMAT_CHOICES,
        'pillar_choices': SocialPost.PILLAR_CHOICES,
        'status_choices': SocialPost.STATUS_CHOICES,
    })


@login_required
def social_post_edit_view(request, post_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    post = get_object_or_404(SocialPost, id=post_id, business=business)
    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    projects = Project.objects.filter(business=business).order_by('-created_at')
    staff_members = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        post.client = Client.objects.filter(id=client_id, business=business).first() if client_id else None

        project_id = request.POST.get('project_id')
        post.project = Project.objects.filter(id=project_id, business=business).first() if project_id else None

        assigned_to_id = request.POST.get('assigned_to_id')
        post.assigned_to = StaffMember.objects.filter(id=assigned_to_id, business=business).first() if assigned_to_id else None

        post.title = request.POST.get('title', post.title).strip()
        post.platform = request.POST.get('platform', post.platform)
        post.format = request.POST.get('format', post.format)
        post.pillar = request.POST.get('pillar', post.pillar)
        post.status = request.POST.get('status', post.status)
        post.scheduled_date = request.POST.get('scheduled_date') or None
        post.hook = request.POST.get('hook', '').strip()
        post.caption = request.POST.get('caption', '').strip()
        post.hashtags = request.POST.get('hashtags', '').strip()
        post.media_url = request.POST.get('media_url', '').strip()
        post.notes = request.POST.get('notes', '').strip()
        post.save()

        return redirect('content_planner')

    return render(request, 'projects/social_post_form.html', {
        'business': business,
        'post': post,
        'clients': clients,
        'projects': projects,
        'staff_members': staff_members,
        'platform_choices': SocialPost.PLATFORM_CHOICES,
        'format_choices': SocialPost.FORMAT_CHOICES,
        'pillar_choices': SocialPost.PILLAR_CHOICES,
        'status_choices': SocialPost.STATUS_CHOICES,
    })


@login_required
def social_post_status_view(request, post_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    post = get_object_or_404(SocialPost, id=post_id, business=business)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(SocialPost.STATUS_CHOICES):
            post.status = new_status
            post.save(update_fields=['status'])

    return redirect('content_planner')


@login_required
def social_post_delete_view(request, post_id):
    business = getattr(request, 'current_business', None) or request.user.business
    if not business:
        return redirect('onboarding')

    post = get_object_or_404(SocialPost, id=post_id, business=business)
    if request.method == 'POST':
        post.delete()
        return redirect('content_planner')

    return redirect('content_planner')
