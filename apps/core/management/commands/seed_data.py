import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.business.models import Business, Branch, User, StaffMember, WorkSchedule, PaymentMethodConfig
from apps.crm.models import Client, Supplier, ClientNote
from apps.agenda.models import ServiceCategory, Service, Appointment
from apps.inventory.models import ProductCategory, Product, StockMovement
from apps.pos.models import CashRegister, Sale, SaleItem
from apps.invoicing.models import ExpenseCategory, Expense, Invoice, InvoiceItem, AccountReceivable
from apps.commissions.models import CommissionRecord

class Command(BaseCommand):
    help = 'Puebla la base de datos con información inicial de demostración para BusinessOS SaaS'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando sembrado de datos reales para BusinessOS...'))

        # 1. Business & Branch
        business, created = Business.objects.get_or_create(
            slug='barberia-deluxe',
            defaults={
                'name': 'Barbería & Spa Deluxe',
                'tax_id': '20-44983210-9',
                'email': 'contacto@barberiadeluxe.com',
                'phone': '+54 11 5544-3322',
                'address': 'Av. Santa Fe 3240, Palermo, Buenos Aires',
                'currency': '$',
                'branding_color': '#6366f1'
            }
        )

        branch, _ = Branch.objects.get_or_create(
            business=business,
            name='Sucursal Central Palermo',
            defaults={'address': 'Av. Santa Fe 3240', 'phone': '+54 11 5544-3322', 'is_main': True}
        )

        # Payment methods
        PaymentMethodConfig.objects.get_or_create(business=business, name='Efectivo', defaults={'is_enabled': True})
        PaymentMethodConfig.objects.get_or_create(business=business, name='Tarjeta de Débito/Crédito', defaults={'is_enabled': True})
        PaymentMethodConfig.objects.get_or_create(business=business, name='MercadoPago / QR', defaults={'is_enabled': True})
        PaymentMethodConfig.objects.get_or_create(business=business, name='Transferencia Bancaria', defaults={'is_enabled': True})

        # 2. Users & Staff
        owner_user, _ = User.objects.get_or_create(
            username='carlos_owner',
            defaults={
                'first_name': 'Carlos',
                'last_name': 'Mendoza',
                'email': 'carlos@barberiadeluxe.com',
                'role': 'OWNER',
                'business': business
            }
        )
        owner_user.set_password('admin123')
        owner_user.save()

        staff_esteban, _ = StaffMember.objects.get_or_create(
            business=business,
            first_name='Esteban',
            last_name='Sosa',
            defaults={
                'branch': branch,
                'email': 'esteban@barberiadeluxe.com',
                'phone': '+54 11 9988-1122',
                'role_title': 'Barber Master',
                'commission_rate': Decimal('40.00'),
                'avatar_color': '#6366f1'
            }
        )

        staff_sofia, _ = StaffMember.objects.get_or_create(
            business=business,
            first_name='Sofía',
            last_name='Stylist',
            defaults={
                'branch': branch,
                'email': 'sofia@barberiadeluxe.com',
                'phone': '+54 11 9988-3344',
                'role_title': 'Especialista Capilar & Facial',
                'commission_rate': Decimal('35.00'),
                'avatar_color': '#ec4899'
            }
        )

        # Work Schedules
        for staff in [staff_esteban, staff_sofia]:
            for day in range(0, 6): # Mon-Sat
                WorkSchedule.objects.get_or_create(
                    staff=staff,
                    day_of_week=day,
                    defaults={'start_time': '09:00', 'end_time': '19:00', 'is_working_day': True}
                )

        # 3. CRM Clients & Suppliers
        supplier, _ = Supplier.objects.get_or_create(
            business=business,
            company_name="Distribuidora Grooming & Spa Pro",
            defaults={
                'contact_name': 'Roberto Gómez',
                'tax_id': '30-71122334-5',
                'email': 'ventas@groomingpro.com',
                'phone': '+54 11 4433-2211',
                'category': 'Productos e Insumos'
            }
        )

        client_juan, _ = Client.objects.get_or_create(
            phone='+5491133221100',
            business=business,
            defaults={
                'first_name': 'Juan',
                'last_name': 'Pérez',
                'email': 'juan.perez@email.com',
                'status': 'VIP',
                'total_spent': Decimal('185.00'),
                'last_visit': datetime.datetime.now() - datetime.timedelta(days=5)
            }
        )
        ClientNote.objects.get_or_create(client=client_juan, defaults={'author': 'Esteban Sosa', 'content': 'Prefiere café negro sin azúcar y corte degradado en 0.5 mm.'})

        client_maria, _ = Client.objects.get_or_create(
            phone='+5491144556677',
            business=business,
            defaults={
                'first_name': 'María',
                'last_name': 'Rodríguez',
                'email': 'maria.rod@email.com',
                'status': 'ACTIVE',
                'total_spent': Decimal('95.00'),
                'last_visit': datetime.datetime.now() - datetime.timedelta(days=12)
            }
        )

        client_lucas, _ = Client.objects.get_or_create(
            phone='+5491199887766',
            business=business,
            defaults={
                'first_name': 'Lucas',
                'last_name': 'Gómez',
                'email': 'lucas.gomez@email.com',
                'status': 'INACTIVE',
                'total_spent': Decimal('40.00'),
                'last_visit': datetime.datetime.now() - datetime.timedelta(days=75)
            }
        )

        # 4. Service Categories & Services
        cat_corte, _ = ServiceCategory.objects.get_or_create(business=business, name='Cortes & Barba', defaults={'color': '#6366f1'})
        cat_spa, _ = ServiceCategory.objects.get_or_create(business=business, name='Tratamientos Spa & Facial', defaults={'color': '#10b981'})

        service_corte, _ = Service.objects.get_or_create(
            business=business,
            name='Corte de Cabello VIP',
            defaults={'category': cat_corte, 'duration_minutes': 45, 'price': Decimal('25.00'), 'commission_rate': Decimal('40.00')}
        )

        service_barba, _ = Service.objects.get_or_create(
            business=business,
            name='Perfilado de Barba & Toalla Caliente',
            defaults={'category': cat_corte, 'duration_minutes': 30, 'price': Decimal('15.00'), 'commission_rate': Decimal('40.00')}
        )

        service_facial, _ = Service.objects.get_or_create(
            business=business,
            name='Tratamiento Facial Exfoliante',
            defaults={'category': cat_spa, 'duration_minutes': 60, 'price': Decimal('40.00'), 'commission_rate': Decimal('35.00')}
        )

        # 5. Products & Inventory
        cat_prod, _ = ProductCategory.objects.get_or_create(business=business, name='Cosmética Capilar')
        
        prod_cera, _ = Product.objects.get_or_create(
            business=business,
            sku='CERA-001',
            defaults={
                'category': cat_prod,
                'supplier': supplier,
                'name': 'Cera Modeladora Mate (100g)',
                'cost_price': Decimal('6.00'),
                'sale_price': Decimal('14.00'),
                'stock': 18,
                'min_stock': 5
            }
        )

        prod_aceite, _ = Product.objects.get_or_create(
            business=business,
            sku='OIL-002',
            defaults={
                'category': cat_prod,
                'supplier': supplier,
                'name': 'Aceite de Barba de Argán (50ml)',
                'cost_price': Decimal('8.00'),
                'sale_price': Decimal('18.00'),
                'stock': 2, # Low Stock Alert!
                'min_stock': 5
            }
        )

        # 6. Today's Appointments
        today = datetime.date.today()
        Appointment.objects.get_or_create(
            business=business,
            client=client_juan,
            staff=staff_esteban,
            service=service_corte,
            date=today,
            start_time='10:00',
            defaults={'end_time': '10:45', 'total_price': Decimal('25.00'), 'status': 'CONFIRMED'}
        )

        Appointment.objects.get_or_create(
            business=business,
            client=client_maria,
            staff=staff_sofia,
            service=service_facial,
            date=today,
            start_time='14:30',
            defaults={'end_time': '15:30', 'total_price': Decimal('40.00'), 'status': 'CONFIRMED'}
        )

        # 7. Cash Register & Sales
        register, _ = CashRegister.objects.get_or_create(
            business=business,
            status='OPEN',
            defaults={'opened_by': owner_user, 'initial_amount': Decimal('100.00')}
        )

        sale, _ = Sale.objects.get_or_create(
            business=business,
            client=client_juan,
            defaults={
                'branch': branch,
                'cash_register': register,
                'staff': staff_esteban,
                'subtotal': Decimal('39.00'),
                'discount_amount': Decimal('0.00'),
                'tip_amount': Decimal('3.00'),
                'total_amount': Decimal('42.00'),
                'payment_method': 'MercadoPago / QR',
                'status': 'COMPLETED'
            }
        )
        SaleItem.objects.get_or_create(sale=sale, item_type='SERVICE', service=service_corte, defaults={'unit_price': Decimal('25.00'), 'quantity': 1, 'total_price': Decimal('25.00')})
        SaleItem.objects.get_or_create(sale=sale, item_type='PRODUCT', product=prod_cera, defaults={'unit_price': Decimal('14.00'), 'quantity': 1, 'total_price': Decimal('14.00')})

        # Commission
        CommissionRecord.objects.get_or_create(
            business=business,
            staff=staff_esteban,
            sale=sale,
            defaults={'amount': Decimal('10.00'), 'concept': 'Comisión Venta Corte de Cabello VIP'}
        )

        # 8. Invoicing & Expenses
        Invoice.objects.get_or_create(
            business=business,
            invoice_number='FAC-2026-0001',
            defaults={
                'client': client_juan,
                'sale': sale,
                'issue_date': today,
                'due_date': today + datetime.timedelta(days=7),
                'subtotal': Decimal('39.00'),
                'tax_amount': Decimal('8.19'),
                'total_amount': Decimal('47.19'),
                'status': 'PAID'
            }
        )

        cat_exp_alquiler, _ = ExpenseCategory.objects.get_or_create(business=business, name='Alquiler & Inmueble')
        cat_exp_insumos, _ = ExpenseCategory.objects.get_or_create(business=business, name='Insumos Operativos')

        Expense.objects.get_or_create(
            business=business,
            concept='Alquiler de Local Comercial Palermo',
            defaults={'category': cat_exp_alquiler, 'amount': Decimal('850.00'), 'issue_date': today - datetime.timedelta(days=5), 'status': 'PAID', 'receipt_number': 'REC-8892'}
        )

        Expense.objects.get_or_create(
            business=business,
            concept='Insumos de Toallas y Productos de Grooming',
            defaults={'category': cat_exp_insumos, 'supplier': supplier, 'amount': Decimal('240.00'), 'issue_date': today - datetime.timedelta(days=2), 'status': 'PAID', 'receipt_number': 'FAC-3391'}
        )

        self.stdout.write(self.style.SUCCESS('[SUCCESS] Sembrado completado con éxito. ¡BusinessOS listo para operar!'))
