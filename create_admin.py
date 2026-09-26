import os
import sys
import django

# Configurar entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.urls' if os.getenv('DJANGO_SETTINGS_MODULE') else 'config.settings')
django.setup()

from apps.business.models import User, Business

def create_admin_user(username, email, password, role='ADMIN', business_name=None):
    """
    Crea o actualiza un usuario administrador en el sistema.
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
            'is_staff': True,
            'is_superuser': True if role in ('ADMIN', 'OWNER') else False,
            'business': business,
        }
    )

    user.set_password(password)
    user.is_staff = True
    user.role = role
    if role in ('ADMIN', 'OWNER'):
        user.is_superuser = True
    if business:
        user.business = business
    user.save()

    status = "creado" if created else "actualizado"
    print(f"✅ Usuario '{username}' {status} exitosamente con rol '{role}'.")
    return user

if __name__ == '__main__':
    print("--- Creador de Usuario Administrador ---")
    
    # Valores por defecto o argumentos CLI
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
