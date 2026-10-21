from django.urls import path
from . import views

urlpatterns = [
    # Proyectos
    path('', views.project_list_view, name='project_list'),
    path('nuevo/', views.project_create_view, name='project_create'),
    path('<uuid:project_id>/', views.project_detail_view, name='project_detail'),
    path('<uuid:project_id>/editar/', views.project_edit_view, name='project_edit'),
    path('<uuid:project_id>/eliminar/', views.project_delete_view, name='project_delete'),
    path('<uuid:project_id>/status/', views.project_status_update_view, name='project_status_update'),

    # Tareas de Proyecto
    path('<uuid:project_id>/tareas/nueva/', views.project_task_create_view, name='project_task_create'),
    path('tareas/<uuid:task_id>/status/', views.project_task_status_update_view, name='project_task_status_update'),
    path('tareas/<uuid:task_id>/toggle/', views.project_task_toggle_view, name='project_task_toggle'),
    path('tareas/<uuid:task_id>/eliminar/', views.project_task_delete_view, name='project_task_delete'),

    # Planificador de Contenido en Redes Sociales
    path('contenido/', views.content_planner_view, name='content_planner'),
    path('contenido/nuevo/', views.social_post_create_view, name='social_post_create'),
    path('contenido/<uuid:post_id>/editar/', views.social_post_edit_view, name='social_post_edit'),
    path('contenido/<uuid:post_id>/estado/', views.social_post_status_view, name='social_post_status'),
    path('contenido/<uuid:post_id>/eliminar/', views.social_post_delete_view, name='social_post_delete'),
]
