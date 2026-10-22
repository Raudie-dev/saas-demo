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

from apps.business.models import Business, Branch, User, StaffMember, WorkSchedule
from apps.agenda.models import ServiceCategory, Service, Appointment
from apps.inventory.models import ProductCategory, Product
from apps.crm.models import Client, ClientNote
from apps.pos.models import CashRegister, Sale, SaleItem, SalePayment
from apps.invoicing.models import Invoice, InvoiceItem
from apps.commissions.models import CommissionRecord
from apps.marketing.models import LoyaltyProgram, LoyaltyCard, Coupon

def populate_showcase():
    print("🚀 Creando datos de demostración realistas para capturas...")

    # 1. Negocio Modelo
    business, created = Business.objects.get_or_create(
        slug="raudie-clinica-integral",
        defaults={
            "name": "Clínica & Estudio Integral RauDie",
            "email": "contacto@raudie-integral.com",
            "phone": "+54 9 11 4820-9100",
            "address": "Av. Santa Fe 3240, Palermo, CABA",
            "currency": "$",
            "branding_color": "#6B0D16", # Burgundy Oficial
            "business_type": "HEALTH_BEAUTY",
            "onboarding_completed": True,
            "enabled_modules": ['crm', 'agenda', 'pos', 'inventory', 'commissions', 'invoicing', 'marketing', 'analytics']
        }
    )
    business.name = "Clínica & Estudio Integral RauDie"
    business.branding_color = "#6B0D16"
    business.business_type = "HEALTH_BEAUTY"
    business.enabled_modules = ['crm', 'agenda', 'pos', 'inventory', 'commissions', 'invoicing', 'marketing', 'analytics']
    business.onboarding_completed = True
    business.save()

    # 2. Sucursales
    branch_palermo, _ = Branch.objects.get_or_create(
        business=business,
        name="Sede Central Palermo",
        defaults={"is_main": True, "address": "Av. Santa Fe 3240, Palermo, CABA"}
    )
    branch_belgrano, _ = Branch.objects.get_or_create(
        business=business,
        name="Sede Belgrano",
        defaults={"is_main": False, "address": "Av. Cabildo 1820, Belgrano, CABA"}
    )

    # 3. Usuario Administrador Principal
    user, _ = User.objects.get_or_create(
        username="demo_showcase",
        defaults={
            "email": "demo@raudie.com",
            "role": "OWNER",
            "first_name": "Valeria",
            "last_name": "Navarro",
            "business": business
        }
    )
    user.set_password("Raudie2026!")
    user.business = business
    user.role = "OWNER"
    user.first_name = "Valeria"
    user.last_name = "Navarro"
    user.save()

    # 4. Especialistas y Staff (4 perfiles con roles y comisiones)
    staff_data = [
        {"first": "Claudia", "last": "Santos", "role": "Dra. Odontología & Estética", "comm": 40.0, "salary": 450000, "color": "#6B0D16", "branch": branch_palermo},
        {"first": "Roberto", "last": "Paz", "role": "Lic. Kinesiología & Fisioterapia", "comm": 35.0, "salary": 380000, "color": "#0F0F10", "branch": branch_palermo},
        {"first": "Sofía", "last": "Martínez", "role": "Cosmetología & Dermatología", "comm": 30.0, "salary": 320000, "color": "#941423", "branch": branch_palermo},
        {"first": "Mateo", "last": "Ferrero", "role": "Estilismo & Barbería Master", "comm": 45.0, "salary": 350000, "color": "#323234", "branch": branch_belgrano},
    ]
    staff_objs = []
    for s in staff_data:
        st, _ = StaffMember.objects.get_or_create(
            business=business,
            first_name=s["first"],
            last_name=s["last"],
            defaults={
                "role_title": s["role"],
                "commission_rate": Decimal(str(s["comm"])),
                "base_salary": Decimal(str(s["salary"])),
                "avatar_color": s["color"],
                "branch": s["branch"],
                "is_active": True
            }
        )
        staff_objs.append(st)

    # 5. Categorías y Servicios Reales
    cat_med, _ = ServiceCategory.objects.get_or_create(business=business, name="Medicina & Odontología")
    cat_kine, _ = ServiceCategory.objects.get_or_create(business=business, name="Kinesiología & Rehabilitación")
    cat_cosm, _ = ServiceCategory.objects.get_or_create(business=business, name="Estética Facial & Corporal")
    cat_estilo, _ = ServiceCategory.objects.get_or_create(business=business, name="Estilismo & Cuidado Capilar")

    srv_dental, _ = Service.objects.get_or_create(business=business, name="Limpieza Dental Ultrasonido & Blanqueamiento", defaults={"category": cat_med, "duration_minutes": 60, "price": Decimal("24000.00")})
    srv_botox, _ = Service.objects.get_or_create(business=business, name="Aplicación Ácido Hialurónico / Armonización", defaults={"category": cat_med, "duration_minutes": 45, "price": Decimal("55000.00")})
    srv_kine, _ = Service.objects.get_or_create(business=business, name="Sesión Kinesiología Postural & Descarga", defaults={"category": cat_kine, "duration_minutes": 50, "price": Decimal("18500.00")})
    srv_facial, _ = Service.objects.get_or_create(business=business, name="Limpieza Facial Profunda con Punta de Diamante", defaults={"category": cat_cosm, "duration_minutes": 60, "price": Decimal("19000.00")})
    srv_peeling, _ = Service.objects.get_or_create(business=business, name="Peeling Químico Renovador & Hidratación", defaults={"category": cat_cosm, "duration_minutes": 45, "price": Decimal("22000.00")})
    srv_corte, _ = Service.objects.get_or_create(business=business, name="Corte de Autor & Diseño de Barba", defaults={"category": cat_estilo, "duration_minutes": 45, "price": Decimal("12500.00")})

    # 6. Clientes con perfiles reales
    clients_data = [
        {"first": "Martina", "last": "Gómez", "email": "martina.gomez@gmail.com", "phone": "+54 9 11 5421-9988"},
        {"first": "Carlos", "last": "Ramos", "email": "carlos.ramos@hotmail.com", "phone": "+54 9 11 6332-1100"},
        {"first": "Laura", "last": "Torres", "email": "laura.torres@gmail.com", "phone": "+54 9 11 4120-7744"},
        {"first": "Javier", "last": "Méndez", "email": "javier.mendez@empresa.com", "phone": "+54 9 11 5566-3322"},
        {"first": "Camila", "last": "Navarro", "email": "camila.navarro@outlook.com", "phone": "+54 9 11 8899-4411"},
        {"first": "Tomás", "last": "Castro", "email": "tomas.castro@gmail.com", "phone": "+54 9 11 7711-2255"},
        {"first": "Elena", "last": "Benítez", "email": "elena.benitez@yahoo.com", "phone": "+54 9 11 3344-9900"},
        {"first": "Agustín", "last": "Pérez", "email": "agustin.perez@live.com", "phone": "+54 9 11 2299-8811"},
    ]
    client_objs = []
    for c in clients_data:
        cl, _ = Client.objects.get_or_create(
            business=business,
            email=c["email"],
            defaults={
                "first_name": c["first"],
                "last_name": c["last"],
                "phone": c["phone"]
            }
        )
        client_objs.append(cl)

    # 7. Citas para Hoy, Ayer y Próximos Días
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    in_2_days = today + timedelta(days=2)

    appointments_data = [
        # Ayer (Completadas)
        {"client": client_objs[0], "srv": srv_dental, "staff": staff_objs[0], "d": yesterday, "h": time(10, 0), "eh": time(11, 0), "status": "COMPLETED"},
        {"client": client_objs[1], "srv": srv_kine, "staff": staff_objs[1], "d": yesterday, "h": time(11, 30), "eh": time(12, 20), "status": "COMPLETED"},
        {"client": client_objs[2], "srv": srv_facial, "staff": staff_objs[2], "d": yesterday, "h": time(15, 0), "eh": time(16, 0), "status": "COMPLETED"},
        {"client": client_objs[3], "srv": srv_corte, "staff": staff_objs[3], "d": yesterday, "h": time(16, 30), "eh": time(17, 15), "status": "COMPLETED"},
        
        # Hoy (Confirmadas / En curso)
        {"client": client_objs[4], "srv": srv_botox, "staff": staff_objs[0], "d": today, "h": time(9, 30), "eh": time(10, 15), "status": "CONFIRMED"},
        {"client": client_objs[5], "srv": srv_kine, "staff": staff_objs[1], "d": today, "h": time(11, 0), "eh": time(11, 50), "status": "CONFIRMED"},
        {"client": client_objs[6], "srv": srv_facial, "staff": staff_objs[2], "d": today, "h": time(14, 0), "eh": time(15, 0), "status": "CONFIRMED"},
        {"client": client_objs[7], "srv": srv_dental, "staff": staff_objs[0], "d": today, "h": time(16, 0), "eh": time(17, 0), "status": "CONFIRMED"},
        {"client": client_objs[0], "srv": srv_corte, "staff": staff_objs[3], "d": today, "h": time(17, 30), "eh": time(18, 15), "status": "CONFIRMED"},

        # Mañana y próximos días
        {"client": client_objs[1], "srv": srv_peeling, "staff": staff_objs[2], "d": tomorrow, "h": time(10, 30), "eh": time(11, 15), "status": "CONFIRMED"},
        {"client": client_objs[2], "srv": srv_kine, "staff": staff_objs[1], "d": tomorrow, "h": time(15, 30), "eh": time(16, 20), "status": "CONFIRMED"},
        {"client": client_objs[3], "srv": srv_dental, "staff": staff_objs[0], "d": in_2_days, "h": time(11, 0), "eh": time(12, 0), "status": "PENDING"},
        {"client": client_objs[4], "srv": srv_facial, "staff": staff_objs[2], "d": in_2_days, "h": time(14, 0), "eh": time(15, 0), "status": "CONFIRMED"},
    ]

    for apt in appointments_data:
        Appointment.objects.get_or_create(
            business=business,
            client=apt["client"],
            service=apt["srv"],
            staff=apt["staff"],
            date=apt["d"],
            start_time=apt["h"],
            defaults={
                "end_time": apt["eh"],
                "status": apt["status"],
                "total_price": apt["srv"].price,
                "branch": apt["staff"].branch or branch_palermo
            }
        )

    # 8. Inventario de Productos
    cat_prod, _ = ProductCategory.objects.get_or_create(business=business, name="Dermocosmética & Cuidado Clínico")
    Product.objects.get_or_create(
        business=business,
        name="Serum Reparador Ácido Hialurónico 30ml",
        defaults={"sku": "SER-AH-30", "category": cat_prod, "cost_price": Decimal("8500.00"), "sale_price": Decimal("16500.00"), "stock": 24, "min_stock": 6}
    )
    Product.objects.get_or_create(
        business=business,
        name="Protector Solar Toque Seco FPS 50+",
        defaults={"sku": "PROT-SOL-50", "category": cat_prod, "cost_price": Decimal("9200.00"), "sale_price": Decimal("18000.00"), "stock": 18, "min_stock": 5}
    )
    Product.objects.get_or_create(
        business=business,
        name="Aceite Esencial Masaje Terapéutico 250ml",
        defaults={"sku": "ACE-TER-250", "category": cat_prod, "cost_price": Decimal("5500.00"), "sale_price": Decimal("11800.00"), "stock": 12, "min_stock": 4}
    )

    # 9. Apertura de Caja y Ventas POS Hoy
    reg, _ = CashRegister.objects.get_or_create(
        business=business,
        branch=branch_palermo,
        opened_by=user,
        closed_at__isnull=True,
        defaults={
            "initial_amount": Decimal("15000.00"),
            "status": "OPEN",
        }
    )

    # Ventas de hoy
    sale1, s1_created = Sale.objects.get_or_create(
        business=business,
        branch=branch_palermo,
        cash_register=reg,
        client=client_objs[4],
        staff=staff_objs[0],
        total_amount=Decimal("55000.00"),
        defaults={"status": "COMPLETED"}
    )
    if s1_created:
        SaleItem.objects.create(sale=sale1, item_type='SERVICE', service=srv_botox, quantity=1, unit_price=Decimal("55000.00"), total_price=Decimal("55000.00"))
        SalePayment.objects.create(sale=sale1, payment_method="Tarjeta", amount=Decimal("55000.00"))

    sale2, s2_created = Sale.objects.get_or_create(
        business=business,
        branch=branch_palermo,
        cash_register=reg,
        client=client_objs[5],
        staff=staff_objs[1],
        total_amount=Decimal("18500.00"),
        defaults={"status": "COMPLETED"}
    )
    if s2_created:
        SaleItem.objects.create(sale=sale2, item_type='SERVICE', service=srv_kine, quantity=1, unit_price=Decimal("18500.00"), total_price=Decimal("18500.00"))
        SalePayment.objects.create(sale=sale2, payment_method="Transferencia", amount=Decimal("18500.00"))

    # 10. Facturas Emitidas
    inv1, inv1_created = Invoice.objects.get_or_create(
        business=business,
        invoice_number="FAC-2026-00142",
        defaults={
            "client": client_objs[4],
            "sale": sale1,
            "issue_date": today,
            "due_date": today + timedelta(days=15),
            "status": "PAID",
            "subtotal": Decimal("45454.55"),
            "tax_amount": Decimal("9545.45"),
            "total_amount": Decimal("55000.00"),
            "notes": "Comprobante emitido electrónicamente. Pago con tarjeta de crédito."
        }
    )
    if inv1_created:
        InvoiceItem.objects.create(
            invoice=inv1,
            description="Aplicación de Botox Facial Completo (3 Zonas)",
            quantity=1,
            unit_price=Decimal("45454.55"),
            total_price=Decimal("45454.55")
        )

    inv2, inv2_created = Invoice.objects.get_or_create(
        business=business,
        invoice_number="FAC-2026-00143",
        defaults={
            "client": client_objs[5],
            "sale": sale2,
            "issue_date": today,
            "due_date": today + timedelta(days=15),
            "status": "PAID",
            "subtotal": Decimal("15289.26"),
            "tax_amount": Decimal("3210.74"),
            "total_amount": Decimal("18500.00"),
            "notes": "Transferencia bancaria recibida. Kinesiología sesión 1."
        }
    )
    if inv2_created:
        InvoiceItem.objects.create(
            invoice=inv2,
            description="Sesión de Kinesiología y Rehabilitación Funcional",
            quantity=1,
            unit_price=Decimal("15289.26"),
            total_price=Decimal("15289.26")
        )

    # 11. Marketing / Programa de Fidelización
    loyalty, _ = LoyaltyProgram.objects.get_or_create(
        business=business,
        name="Club RauDie VIP",
        defaults={
            "points_per_currency": Decimal("1.00"),
            "minimum_points_to_redeem": 100,
            "is_active": True
        }
    )
    for cl in client_objs[:4]:
        LoyaltyCard.objects.get_or_create(
            program=loyalty,
            client=cl,
            defaults={
                "points": 340,
                "is_active": True
            }
        )

    Coupon.objects.get_or_create(
        business=business,
        code="BIENVENIDA20",
        defaults={
            "discount_percentage": Decimal("20.00"),
            "valid_until": today + timedelta(days=90),
            "max_uses": 100,
            "uses_count": 14,
            "is_active": True
        }
    )

    print("\n" + "="*60)
    print("✅ DATOS DE DEMOSTRACIÓN CREADOS EXITOSAMENTE")
    print("="*60)
    print(f"🏢 Negocio:        {business.name}")
    print(f"👤 Usuario:        demo_showcase")
    print(f"🔑 Contraseña:     Raudie2026!")
    print(f"🌐 Enlace Login:   http://localhost:8000/login/")
    print(f"📱 Panel Control:  http://localhost:8000/dashboard/")
    print("="*60)
    print("Incluye:")
    print("  • 2 Sucursales (Palermo y Belgrano)")
    print("  • 4 Especialistas con comisiones y fotos asignadas")
    print("  • 6 Servicios y 3 Productos con stock")
    print("  • 8 Clientes con historial y teléfonos reales")
    print("  • 13 Citas programadas (Ayer, Hoy y Próximos días)")
    print("  • Caja abierta con $15,000 iniciales y ventas registradas")
    print("  • Facturas emitidas con IVA desglosado")
    print("  • Club de Fidelización con puntos acumulados y cupón de 20%")
    print("="*60 + "\n")

if __name__ == '__main__':
    populate_showcase()
