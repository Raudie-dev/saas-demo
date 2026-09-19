from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.business.models import Business
from apps.agenda.models import Service

class ServiceViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.business = Business.objects.create(
            name="Test Salon",
            slug="test-salon",
            currency="USD"
        )

    def test_service_create_view_with_empty_commission_rate(self):
        url = reverse('service_create')
        response = self.client.post(url, {
            'name': 'Corte Regular',
            'price': '25.00',
            'duration_minutes': '45',
            'commission_rate': '',  # Empty string from form input
            'description': 'Servicio de prueba'
        })
        self.assertEqual(response.status_code, 302)
        service = Service.objects.get(name='Corte Regular')
        self.assertEqual(service.price, Decimal('25.00'))
        self.assertEqual(service.commission_rate, Decimal('0.00'))

    def test_service_create_view_with_comma_decimal(self):
        url = reverse('service_create')
        response = self.client.post(url, {
            'name': 'Barba VIP',
            'price': '15,50',
            'duration_minutes': '30',
            'commission_rate': '10,50',
            'description': ''
        })
        self.assertEqual(response.status_code, 302)
        service = Service.objects.get(name='Barba VIP')
        self.assertEqual(service.price, Decimal('15.50'))
        self.assertEqual(service.commission_rate, Decimal('10.50'))
