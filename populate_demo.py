import os
import sys
import django
from decimal import Decimal
from datetime import timedelta, date, time
from django.utils import timezone

# Configurar entorno de Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.business.models import Business, Branch, User, StaffMember
from apps.agenda.models import ServiceCategory, Service, Appointment
from apps.inventory.models import ProductCategory, Product
from apps.crm.models import Client
from apps.pos.models import CashRegister, Sale, SaleItem, SalePayment

def create_demo_data():
    print("Iniciando creación de datos de prueba (Demo)...")
    
    # 1. Crear o recuperar el Negocio
    business, created = Business.objects.get_or_create(
        slug="spa-beauty-demo",
        defaults={
            "name": "Spa & Beauty Lounge",
            "email": "contacto@spabeauty.com",
            "phone": "+5491122334455",
            "address": "Av. Principal 123, Ciudad",
            "currency": "$",
            "branding_color": "#be185d", # Rosa oscuro para un Spa
            "business_type": "HEALTH_BEAUTY",
            "onboarding_completed": True,
            "enabled_modules": ['crm', 'agenda', 'pos', 'inventory', 'commissions', 'invoicing', 'marketing']
        }
    )
    if not created:
        print("Negocio 'Spa & Beauty Lounge' ya existe, actualizando...")
        business.name = "Spa & Beauty Lounge"
        business.branding_color = "#be185d"
        business.business_type = "HEALTH_BEAUTY"
        business.onboarding_completed = True
        business.save()
    
    # 2. Sucursal
    branch, _ = Branch.objects.get_or_create(
        business=business,
        name="Sede Central",
        defaults={"is_main": True, "address": "Av. Principal 123, Ciudad"}
    )
    
    # 3. Usuario Admin
    admin_user, _ = User.objects.get_or_create(
        username="demo_admin",
        defaults={
            "email": "demo@example.com",
            "role": "OWNER",
            "business": business,
            "first_name": "Laura",
            "last_name": "Gerente"
        }
    )
    admin_user.set_password("demo1234")
    admin_user.business = business
    admin_user.save()
    print("Usuario admin creado: demo_admin / demo1234")

    # 4. Staff
    staff1, _ = StaffMember.objects.get_or_create(
        business=business,
        first_name="Sofía",
        last_name="Martínez",
        defaults={
            "role_title": "Especialista Facial",
            "commission_rate": 15.00,
            "base_salary": 50000.00,
            "avatar_color": "#ec4899",
            "branch": branch
        }
    )
    staff2, _ = StaffMember.objects.get_or_create(
        business=business,
        first_name="Diego",
        last_name="López",
        defaults={
            "role_title": "Masajista Terapéutico",
            "commission_rate": 20.00,
            "base_salary": 45000.00,
            "avatar_color": "#8b5cf6",
            "branch": branch
        }
    )

    # 5. Categorías y Servicios
    cat_facial, _ = ServiceCategory.objects.get_or_create(business=business, name="Tratamientos Faciales")
    cat_masajes, _ = ServiceCategory.objects.get_or_create(business=business, name="Masajes y Relax")

    srv_facial, _ = Service.objects.get_or_create(
        business=business,
        name="Limpieza Facial Profunda",
        defaults={
            "category": cat_facial,
            "duration_minutes": 60,
            "price": 3500.00
        }
    )
    srv_masaje, _ = Service.objects.get_or_create(
        business=business,
        name="Masaje Descontracturante",
        defaults={
            "category": cat_masajes,
            "duration_minutes": 45,
            "price": 4200.00
        }
    )

    # 6. Inventario (Productos)
    cat_prod, _ = ProductCategory.objects.get_or_create(business=business, name="Cuidado Personal")
    prod_crema, _ = Product.objects.get_or_create(
        business=business,
        name="Crema Hidratante Ácido Hialurónico",
        defaults={
            "sku": "CH-AH-01",
            "category": cat_prod,
            "cost_price": 1200.00,
            "sale_price": 2800.00,
            "stock": 15,
            "min_stock": 5
        }
    )
    prod_aceite, _ = Product.objects.get_or_create(
        business=business,
        name="Aceite Esencial Lavanda",
        defaults={
            "sku": "AE-LAV-02",
            "category": cat_prod,
            "cost_price": 800.00,
            "sale_price": 1900.00,
            "stock": 8,
            "min_stock": 10
        }
    )

    # 7. Clientes
    client1, _ = Client.objects.get_or_create(business=business, first_name="María", last_name="González", defaults={"email": "maria@test.com", "phone": "1122334455"})
    client2, _ = Client.objects.get_or_create(business=business, first_name="Carlos", last_name="Rodríguez", defaults={"email": "carlos@test.com", "phone": "5544332211"})

    # 8. Citas (Agenda)
    today = timezone.now().date()
    Appointment.objects.get_or_create(
        business=business,
        client=client1,
        service=srv_facial,
        staff=staff1,
        branch=branch,
        date=today,
        start_time=time(10, 0),
        defaults={
            "end_time": time(11, 0),
            "status": "CONFIRMED",
            "total_price": srv_facial.price
        }
    )
    Appointment.objects.get_or_create(
        business=business,
        client=client2,
        service=srv_masaje,
        staff=staff2,
        branch=branch,
        date=today,
        start_time=time(14, 0),
        defaults={
            "end_time": time(14, 45),
            "status": "PENDING",
            "total_price": srv_masaje.price
        }
    )

    # 9. Ventas y Caja
    register, reg_created = CashRegister.objects.get_or_create(
        business=business,
        branch=branch,
        opened_by=admin_user,
        closed_at__isnull=True,
        defaults={
            "initial_amount": 5000.00,
            "status": "OPEN",
        }
    )

    sale1, s1_created = Sale.objects.get_or_create(
        business=business,
        branch=branch,
        cash_register=register,
        client=client1,
        staff=staff1,
        total_amount=srv_facial.price,
        defaults={"status": "COMPLETED"}
    )
    if s1_created:
        SaleItem.objects.create(sale=sale1, item_type='SERVICE', service=srv_facial, quantity=1, unit_price=srv_facial.price, total_price=srv_facial.price)
        SalePayment.objects.create(sale=sale1, payment_method="Efectivo", amount=srv_facial.price)

    sale2, s2_created = Sale.objects.get_or_create(
        business=business,
        branch=branch,
        cash_register=register,
        client=client2,
        total_amount=prod_crema.sale_price,
        defaults={"status": "COMPLETED"}
    )
    if s2_created:
        SaleItem.objects.create(sale=sale2, item_type='PRODUCT', product=prod_crema, quantity=1, unit_price=prod_crema.sale_price, total_price=prod_crema.sale_price)
        SalePayment.objects.create(sale=sale2, payment_method="Tarjeta", amount=prod_crema.sale_price)
    
    print("✅ Base de datos poblada exitosamente con datos de Spa & Beauty Lounge!")
    print("👉 Puedes ingresar con el usuario: demo_admin y contraseña: demo1234")

if __name__ == '__main__':
    create_demo_data()
