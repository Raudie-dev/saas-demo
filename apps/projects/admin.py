from django.contrib import admin
from .models import Project, ProjectTask, SocialPost

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'client', 'project_type', 'status', 'progress_percent', 'due_date')
    list_filter = ('project_type', 'status', 'business')
    search_fields = ('name', 'description')

@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'assigned_to', 'status', 'priority', 'due_date')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'description')

@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'business', 'client', 'platform', 'format', 'status', 'scheduled_date')
    list_filter = ('platform', 'format', 'status', 'business')
    search_fields = ('title', 'caption', 'hook')
