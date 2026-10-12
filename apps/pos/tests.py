import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.business.models import Business, User, StaffMember, PaymentMethodConfig
from apps.agenda.models import Service
from apps.inventory.models import Product
from apps.pos.models import CashRegister, Sale, SaleItem

class POSTerminalTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testcashier",
            email="cashier@example.com",
            password="password123"
        )
        self.business = Business.objects.create(
            name="Test Barber",
            slug="test-barber",
            currency="$"
        )
        self.user.business = self.business
        self.user.save()
        self.client.force_login(self.user)

        self.service1 = Service.objects.create(
            business=self.business,
            name="Corte Clásico",
            price=Decimal("1500.00"),
            duration_minutes=30,
            is_active=True
        )
        self.service2 = Service.objects.create(
            business=self.business,
            name="Barba",
            price=Decimal("800.00"),
            duration_minutes=20,
            is_active=True
        )

        self.product1 = Product.objects.create(
            business=self.business,
            name="Pomada Mate",
            sale_price=Decimal("1200.00"),
            cost_price=Decimal("600.00"),
            stock=10,
            is_active=True
        )
        self.product2 = Product.objects.create(
            business=self.business,
            name="Shampoo Barba",
            sale_price=Decimal("950.00"),
            cost_price=Decimal("450.00"),
            stock=5,
            is_active=True
        )

        PaymentMethodConfig.objects.create(
            business=self.business,
            name="Efectivo",
            is_enabled=True
        )

    def test_pos_sale_with_multiple_services_and_products_and_auto_open_register(self):
        """
        Verify that a sale with multiple services and products is processed,
        and if the cash register is closed, it opens with the specified initial amount.
        """
        self.assertFalse(CashRegister.objects.filter(business=self.business, status='OPEN').exists())

        services_data = [
            {"id": str(self.service1.id), "name": self.service1.name, "price": 1500.00, "quantity": 1},
            {"id": str(self.service2.id), "name": self.service2.name, "price": 800.00, "quantity": 2},
        ]
        products_data = [
            {"id": str(self.product1.id), "name": self.product1.name, "price": 1200.00, "quantity": 2},
            {"id": str(self.product2.id), "name": self.product2.name, "price": 950.00, "quantity": 1},
        ]

        response = self.client.post(reverse('pos_terminal'), {
            'services_data': json.dumps(services_data),
            'products_data': json.dumps(products_data),
            'initial_register_amount': '250.00',
            'payment_method': 'Efectivo',
            'tip_amount': '50.00',
            'discount_amount': '100.00',
        })

        self.assertEqual(response.status_code, 302)

        # Cash register should now be open with initial_amount 250.00
        open_register = CashRegister.objects.filter(business=self.business, status='OPEN').first()
        self.assertIsNotNone(open_register)
        self.assertEqual(open_register.initial_amount, Decimal('250.00'))

        # Check sale
        sale = Sale.objects.filter(business=self.business, cash_register=open_register).first()
        self.assertIsNotNone(sale)
        # Subtotal: (1500*1 + 800*2) + (1200*2 + 950*1) = (1500 + 1600) + (2400 + 950) = 3100 + 3350 = 6450.00
        # Total: 6450 - 100 + 50 = 6400.00
        self.assertEqual(sale.subtotal, Decimal('6450.00'))
        self.assertEqual(sale.total_amount, Decimal('6400.00'))

        # Check sale items
        items = list(sale.items.all())
        self.assertEqual(len(items), 4)

        # Check stock deduction
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock, 8)
        self.product2.refresh_from_db()
        self.assertEqual(self.product2.stock, 4)

    def test_manual_open_register_action(self):
        """
        Verify that action='open_register' opens a register without making a sale.
        """
        response = self.client.post(reverse('pos_terminal'), {
            'action': 'open_register',
            'initial_amount': '500.00',
        })
        self.assertEqual(response.status_code, 302)
        open_register = CashRegister.objects.filter(business=self.business, status='OPEN').first()
        self.assertIsNotNone(open_register)
        self.assertEqual(open_register.initial_amount, Decimal('500.00'))

    def test_backwards_compatibility_single_item(self):
        """
        Verify that legacy POST with service_id and product_id still works cleanly.
        """
        response = self.client.post(reverse('pos_terminal'), {
            'service_id': str(self.service1.id),
            'product_id': str(self.product1.id),
            'initial_register_amount': '100.00',
            'payment_method': 'Efectivo',
        })
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.filter(business=self.business).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.total_amount, Decimal('2700.00'))
