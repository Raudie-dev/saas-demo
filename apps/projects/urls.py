from django.urls import path
from . import views

urlpatterns = [
    # Proyectos
    path('', views.project_list_view, name='project_list'),
    path('nuevo/', views.project_create_view, name='project_create'),
    path('tipos/', views.project_types_view, name='project_types'),
    path('tipos/nuevo/', views.project_type_create_view, name='project_type_create'),
    path('tipos/<uuid:type_id>/editar/', views.project_type_edit_view, name='project_type_edit'),
    path('tipos/<uuid:type_id>/eliminar/', views.project_type_delete_view, name='project_type_delete'),
    path('<uuid:project_id>/', views.project_detail_view, name='project_detail'),
    path('<uuid:project_id>/editar/', views.project_edit_view, name='project_edit'),
    path('<uuid:project_id>/eliminar/', views.project_delete_view, name='project_delete'),
    path('<uuid:project_id>/status/', views.project_status_update_view, name='project_status_update'),
    path('<uuid:project_id>/quick-update/', views.project_quick_update_view, name='project_quick_update'),

    # Tareas de Proyecto
    path('<uuid:project_id>/tareas/nueva/', views.project_task_create_view, name='project_task_create'),
    path('tareas/<uuid:task_id>/', views.project_task_detail_api, name='project_task_detail'),
    path('tareas/<uuid:task_id>/editar/', views.project_task_edit_view, name='project_task_edit'),
    path('tareas/<uuid:task_id>/status/', views.project_task_status_update_view, name='project_task_status_update'),
    path('tareas/<uuid:task_id>/toggle/', views.project_task_toggle_view, name='project_task_toggle'),
    path('tareas/<uuid:task_id>/eliminar/', views.project_task_delete_view, name='project_task_delete'),
]
