from decimal import Decimal
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.utils import timezone
from apps.business.models import Business, StaffMember, User
from apps.crm.models import Client
from apps.travel.models import TravelPackage, TravelBooking

class TravelModuleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='travel_admin',
            email='travel@agency.com',
            password='password123',
            role='ADMIN'
        )
        self.business = Business.objects.create(
            name='Agencia Paraíso Viajes',
            slug='paraiso-viajes',
            business_type='TRAVEL',
            email='contacto@paraisoviajes.com',
            phone='+54 9 11 1234-5678',
            currency='USD'
        )
        self.user.business = self.business
        self.user.save()

        self.client_crm = Client.objects.create(
            business=self.business,
            first_name='Laura',
            last_name='Fernández',
            email='laura@example.com',
            phone='+54 9 11 9876-5432',
            tax_id='PAS-998877'
        )

        self.package = TravelPackage.objects.create(
            business=self.business,
            title='Caribe Soñado Punta Cana',
            destination='Punta Cana, República Dominicana',
            travel_type='PACKAGE',
            duration_days=7,
            duration_nights=6,
            price_per_person=Decimal('980.00'),
            currency='USD',
            available_slots=20,
            status='AVAILABLE',
            hotel_name='Iberostar Dominicana 5★',
            airline='Copa Airlines',
            includes='Vuelos + Hotel All Inclusive + Traslados',
            is_featured=True
        )

        self.http_client = HttpClient()
        self.http_client.login(username='travel_admin', password='password123')

    def test_travel_business_properties(self):
        self.assertTrue(self.business.is_travel)
        self.assertIn('travel', self.business.get_allowed_modules())
        self.assertEqual(self.business.client_label_singular, 'Pasajero / Cliente')
        self.assertEqual(self.business.client_label_plural, 'Pasajeros & Clientes')

    def test_travel_package_creation(self):
        self.assertTrue(self.package.code.startswith('VIAJE-'))
        self.assertEqual(self.package.duration_display, '7D / 6N')
        self.assertEqual(self.package.price_per_person, Decimal('980.00'))

    def test_travel_booking_creation_and_balance(self):
        booking = TravelBooking.objects.create(
            business=self.business,
            booking_number='EXP-2026-TEST',
            client=self.client_crm,
            package=self.package,
            departure_date=timezone.now().date() + timezone.timedelta(days=15),
            num_adults=2,
            num_children=1,
            total_amount=Decimal('2500.00'),
            deposit_amount=Decimal('1000.00'),
            currency='USD',
            status='CONFIRMED',
            pnr_locator='KLM882',
            airline_flight_details='CM 450 EZE -> PTY -> PUJ',
            hotel_confirmation='CONF-PUJ-123'
        )
        self.assertEqual(booking.total_passengers, 3)
        self.assertEqual(booking.balance_due, Decimal('1500.00'))

    def test_views_response(self):
        # 1. Package list
        resp = self.http_client.get(reverse('travel_package_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Caribe Soñado Punta Cana')

        # 2. Package detail
        resp = self.http_client.get(reverse('travel_package_detail', args=[self.package.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Punta Cana, República Dominicana')

        # 3. Booking list
        resp = self.http_client.get(reverse('travel_booking_list'))
        self.assertEqual(resp.status_code, 200)

        # 4. Booking creation via POST
        post_data = {
            'client_id': str(self.client_crm.id),
            'package_id': str(self.package.id),
            'departure_date': (timezone.now().date() + timezone.timedelta(days=20)).strftime('%Y-%m-%d'),
            'num_adults': 2,
            'num_children': 0,
            'total_amount': '1960.00',
            'deposit_amount': '500.00',
            'currency': 'USD',
            'status': 'CONFIRMED',
            'pnr_locator': 'TEST99',
            'airline_flight_details': 'Vuelo directo',
            'hotel_confirmation': 'HTL-99',
            'passengers_info': '1. Laura Fernández (Adulto)\n2. Juan Pérez (Adulto)',
            'special_requests': 'Habitación no fumador',
            'notes': 'Cliente VIP'
        }
        resp = self.http_client.post(reverse('travel_booking_create'), post_data)
        self.assertEqual(resp.status_code, 302)

        booking = TravelBooking.objects.filter(pnr_locator='TEST99').first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.balance_due, Decimal('1460.00'))

        # 5. Booking voucher
        resp = self.http_client.get(reverse('travel_booking_voucher', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Voucher de Servicio')
        self.assertContains(resp, 'TEST99')
