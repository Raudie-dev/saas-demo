import os
import sys
import django

# Configurar el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.superadmin.models import SuperAdminUser

def print_menu():
    print("\n" + "="*30)
    print("   GESTIÓN DE SUPERUSUARIOS")
    print("="*30)
    print("1. Ver superusuarios")
    print("2. Crear superusuario")
    print("3. Modificar contraseña de superusuario")
    print("4. Eliminar superusuario")
    print("5. Salir")
    print("="*30)

def list_superadmins():
    superadmins = SuperAdminUser.objects.all()
    if not superadmins:
        print("\n[!] No hay superusuarios registrados en la base de datos.")
        return
    print("\n--- Lista de Superusuarios ---")
    for admin in superadmins:
        print(f" - {admin.email} (Usuario: {admin.username})")
    print("------------------------------")

def create_superadmin():
    print("\n--- Crear Superusuario ---")
    email = input("Ingresa el email del nuevo superusuario: ").strip()
    if SuperAdminUser.objects.filter(email=email).exists():
        print(f"[X] Error: El usuario con email '{email}' ya existe.")
        return
        
    username = input("Ingresa el nombre de usuario (ej. admin): ").strip()
    if SuperAdminUser.objects.filter(username=username).exists():
        print(f"[X] Error: El nombre de usuario '{username}' ya está en uso.")
        return
        
    password = input("Ingresa la contraseña: ").strip()
    
    if not email or not username or not password:
        print("[X] Error: El email, nombre de usuario y contraseña son obligatorios.")
        return
        
    try:
        SuperAdminUser.objects.create_superuser(email=email, username=username, password=password)
        print(f"[OK] Superusuario '{username}' ({email}) creado exitosamente.")
    except Exception as e:
        print(f"[X] Error al crear superusuario: {e}")

def modify_superadmin():
    print("\n--- Modificar Contraseña ---")
    email = input("Ingresa el EMAIL del superusuario que deseas modificar: ").strip()
    try:
        admin = SuperAdminUser.objects.get(email=email)
        new_password = input("Ingresa la nueva contraseña: ").strip()
        if not new_password:
            print("[X] Error: La contraseña no puede estar vacía.")
            return
            
        admin.set_password(new_password)
        admin.save()
        print(f"[OK] Contraseña de '{email}' actualizada exitosamente.")
    except SuperAdminUser.DoesNotExist:
        print(f"[X] Error: No se encontró un superusuario con el email '{email}'.")

def delete_superadmin():
    print("\n--- Eliminar Superusuario ---")
    email = input("Ingresa el EMAIL del superusuario que deseas eliminar: ").strip()
    try:
        admin = SuperAdminUser.objects.get(email=email)
        confirm = input(f"¿Estás seguro de que deseas eliminar a '{email}' de forma permanente? (s/n): ").strip().lower()
        if confirm == 's':
            admin.delete()
            print(f"[OK] Superusuario '{email}' eliminado correctamente.")
        else:
            print("[!] Operación cancelada.")
    except SuperAdminUser.DoesNotExist:
        print(f"[X] Error: No se encontró un superusuario con el email '{email}'.")

def main():
    while True:
        print_menu()
        choice = input("Elige una opción (1-5): ").strip()
        
        if choice == '1':
            list_superadmins()
        elif choice == '2':
            create_superadmin()
        elif choice == '3':
            modify_superadmin()
        elif choice == '4':
            delete_superadmin()
        elif choice == '5':
            print("Saliendo del administrador... ¡Hasta luego!")
            sys.exit(0)
        else:
            print("[X] Opción inválida. Por favor ingresa un número del 1 al 5.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSaliendo del administrador... ¡Hasta luego!")
        sys.exit(0)
