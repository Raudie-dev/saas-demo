import json
from decimal import Decimal
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from apps.business.models import Business, StaffMember, WorkSchedule
from apps.agenda.models import Service, Appointment, AppointmentService
from apps.crm.models import Client

class PublicBookingMultiServiceTests(TestCase):
    def setUp(self):
        self.client = HttpClient()
        self.business = Business.objects.create(
            name="Salon Bella",
            slug="salon-bella",
            is_booking_enabled=True,
            currency="$"
        )
        self.staff = StaffMember.objects.create(
            business=self.business,
            first_name="Carlos",
            last_name="Gomez",
            is_active=True
        )
        # Create work schedule for all days
        for day in range(7):
            WorkSchedule.objects.create(
                staff=self.staff,
                day_of_week=day,
                is_working_day=True,
                start_time="09:00",
                end_time="19:00"
            )
        self.service1 = Service.objects.create(
            business=self.business,
            name="Corte de Pelo",
            duration_minutes=30,
            price=Decimal("20.00"),
            is_active=True
        )
        self.service2 = Service.objects.create(
            business=self.business,
            name="Perfilado de Barba",
            duration_minutes=15,
            price=Decimal("10.00"),
            is_active=True
        )

    def test_public_booking_page_renders_catalog(self):
        url = reverse('public_booking', kwargs={'business_slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corte de Pelo")
        self.assertContains(response, "Perfilado de Barba")
        self.assertIn('services_catalog_json', response.context)
        catalog = json.loads(response.context['services_catalog_json'])
        self.assertEqual(len(catalog), 2)

    def test_public_booking_with_multiple_services_and_quantities(self):
        url = reverse('public_booking', kwargs={'business_slug': self.business.slug})
        services_data = json.dumps([
            {"id": str(self.service1.id), "quantity": 2},  # 2 x $20 = $40, 2 x 30m = 60m
            {"id": str(self.service2.id), "quantity": 1},  # 1 x $10 = $10, 1 x 15m = 15m
        ])
        post_data = {
            'staff_id': str(self.staff.id),
            'booking_date': '2026-10-20',
            'booking_time': '11:00',
            'client_name': 'Maria Gonzalez',
            'client_phone': '1122334455',
            'client_email': 'maria@example.com',
            'services_data': services_data,
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('booking_success'))

        appointment = Appointment.objects.filter(business=self.business).first()
        self.assertIsNotNone(appointment)
        # Total price: 2*20 + 1*10 = 50.00
        self.assertEqual(appointment.total_price, Decimal("50.00"))
        # End time: 11:00 + 75 minutes = 12:15
        self.assertEqual(appointment.end_time.strftime("%H:%M") if hasattr(appointment.end_time, 'strftime') else str(appointment.end_time)[:5], "12:15")
        
        # Verify AppointmentService items
        items = list(appointment.appointment_services.all().order_by('service__name'))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].service, self.service1)
        self.assertEqual(items[0].quantity, 2)
        self.assertEqual(items[0].unit_price, Decimal("20.00"))

        self.assertEqual(items[1].service, self.service2)
        self.assertEqual(items[1].quantity, 1)
        self.assertEqual(items[1].unit_price, Decimal("10.00"))

        # Verify services_summary property
        self.assertIn("Corte de Pelo (x2)", appointment.services_summary)
        self.assertIn("Perfilado de Barba", appointment.services_summary)


from apps.properties.models import Property

class PublicBookingRealEstatePropertyTests(TestCase):
    def setUp(self):
        self.client = HttpClient()
        self.business = Business.objects.create(
            name="Inmobiliaria Premium",
            slug="inmo-premium",
            business_type="REAL_ESTATE",
            is_booking_enabled=True,
            currency="USD"
        )
        self.staff = StaffMember.objects.create(
            business=self.business,
            first_name="Lucas",
            last_name="Broker",
            is_active=True
        )
        for day in range(7):
            WorkSchedule.objects.create(
                staff=self.staff,
                day_of_week=day,
                is_working_day=True,
                start_time="09:00",
                end_time="19:00"
            )
        self.property = Property.objects.create(
            business=self.business,
            title="Departamento 2 Ambientes en Palermo Hollywood",
            reference_code="PH-202",
            property_type="APARTMENT",
            operation_type="RENT",
            price=Decimal("650.00"),
            currency="USD",
            address="Honduras 5500",
            zone="Palermo",
            portal_url="https://www.zonaprop.com.ar/prop-202"
        )

    def test_public_booking_page_renders_properties_for_real_estate(self):
        url = reverse('public_booking', kwargs={'business_slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('is_real_estate'))
        self.assertContains(response, "Departamento 2 Ambientes en Palermo Hollywood")
        self.assertContains(response, "Honduras 5500")
        self.assertContains(response, "Zonaprop")

    def test_booking_property_visit(self):
        url = reverse('public_booking', kwargs={'business_slug': self.business.slug})
        post_data = {
            'staff_id': str(self.staff.id),
            'booking_date': '2026-10-25',
            'booking_time': '15:00',
            'client_name': 'Esteban Comprador',
            'client_phone': '1199887766',
            'client_email': 'esteban@example.com',
            'property_id': str(self.property.id),
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('booking_success'))

        appointment = Appointment.objects.filter(business=self.business).first()
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.related_property, self.property)
        self.assertIn("Visita a propiedad", appointment.notes)
        self.assertIn("Honduras 5500", appointment.notes)

    def test_public_booking_page_contains_property_detail_and_seller_modals(self):
        url = reverse('public_booking', kwargs={'business_slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="propertyDetailModal"')
        self.assertContains(response, 'id="sellerRegisterModal"')
        self.assertContains(response, 'Vender Propiedad')
        self.assertIn('properties_catalog_json', response.context)
        catalog = json.loads(response.context['properties_catalog_json'])
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]['reference_code'], 'PH-202')
        self.assertEqual(catalog[0]['portal_display_name'], 'Zonaprop')

    def test_seller_register_api_success(self):
        url = reverse('api_seller_register', kwargs={'business_slug': self.business.slug})
        data = {
            'name': 'Ana María Propietaria',
            'phone_prefix': '+54',
            'phone_number': '11 4455-6677',
            'email': 'ana.propietaria@example.com',
            'operation_type': 'Vender',
            'property_type': 'Casa',
            'address_zone': 'Belgrano R',
            'rooms': '4 ambientes con jardín',
            'estimated_price': 'USD 350.000',
            'comments': 'Excelente estado, pileta y cochera cubierta.'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        json_resp = response.json()
        self.assertTrue(json_resp.get('success'))
        self.assertIn('Recibimos la información', json_resp.get('message', ''))

        # Check Client in CRM
        client = Client.objects.filter(business=self.business, email='ana.propietaria@example.com').first()
        self.assertIsNotNone(client)
        self.assertEqual(client.first_name, 'Ana')
        self.assertEqual(client.last_name, 'María Propietaria')
        self.assertIn('+54', client.phone)
        self.assertIn('PROPIETARIO - SOLICITUD DE VENDER', client.notes)
        self.assertIn('Belgrano R', client.notes)
        self.assertIn('USD 350.000', client.notes)

    def test_seller_register_api_validation_errors(self):
        url = reverse('api_seller_register', kwargs={'business_slug': self.business.slug})
        # Missing required phone
        response = self.client.post(url, {'name': 'Juan Pérez', 'address_zone': 'Centro'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json().get('success'))
        self.assertIn('teléfono', response.json().get('error', '').lower())

