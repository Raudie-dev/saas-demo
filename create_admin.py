import os
import sys
import django

# Configurar entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.urls' if os.getenv('DJANGO_SETTINGS_MODULE') else 'config.settings')
django.setup()

from apps.business.models import User, Business
from apps.superadmin.models import SuperAdminUser

def create_superadmin_user(email, username, password, first_name="Super", last_name="Admin"):
    """
    Crea o actualiza un SuperAdminUser en la tabla independiente del SuperAdmin.
    """
    admin_user, created = SuperAdminUser.objects.get_or_create(
        email=email,
        defaults={
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        }
    )
    admin_user.username = username
    admin_user.set_password(password)
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.is_active = True
    admin_user.save()

    status = "creado" if created else "actualizado"
    print(f"✅ SuperAdminUser '{email}' {status} exitosamente.")
    return admin_user

def create_admin_user(username, email, password, role='ADMIN', business_name=None):
    """
    Crea o actualiza un usuario de negocio en el sistema.
    """
    business = None
    if business_name:
        business, _ = Business.objects.get_or_create(
            name=business_name,
            defaults={
                'slug': business_name.lower().replace(' ', '-'),
                'email': email,
                'phone': '+000000000',
            }
        )

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'role': role,
            'is_staff': False,
            'is_superuser': False,
            'business': business,
        }
    )

    user.set_password(password)
    user.role = role
    if business:
        user.business = business
    user.save()

    status = "creado" if created else "actualizado"
    print(f"✅ Usuario de negocio '{username}' {status} exitosamente con rol '{role}'.")
    return user

if __name__ == '__main__':
    print("--- Creador de Usuarios ---")
    tipo = input("¿Deseas crear [1] SuperAdmin independiente o [2] Usuario de negocio? [1]: ").strip() or "1"
    
    if tipo == "1":
        u_email = input("Email SuperAdmin [admin@example.com]: ").strip() or "admin@example.com"
        u_username = input("Username SuperAdmin [superadmin]: ").strip() or "superadmin"
        u_password = input("Password [admin12345]: ").strip() or "admin12345"
        create_superadmin_user(u_email, u_username, u_password)
    else:
        u_username = input("Username [admin]: ").strip() or "admin"
        u_email = input("Email [admin@example.com]: ").strip() or "admin@example.com"
        u_password = input("Password [admin12345]: ").strip() or "admin12345"
        u_role = input("Rol (OWNER/ADMIN/PROFESSIONAL/RECEPTIONIST) [ADMIN]: ").strip().upper() or "ADMIN"
        u_business = input("Nombre del Negocio (Opcional): ").strip() or None
        create_admin_user(
            username=u_username,
            email=u_email,
            password=u_password,
            role=u_role,
            business_name=u_business
        )
