from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.business.models import Business, User
from apps.agenda.models import Service

class ServiceViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testagenda",
            email="agenda@example.com",
            password="password123"
        )
        self.business = Business.objects.create(
            name="Test Salon",
            slug="test-salon",
            currency="USD"
        )
        self.user.business = self.business
        self.user.save()
        self.client.force_login(self.user)

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

import json
from apps.business.models import StaffMember
from apps.crm.models import Client as CRMClient
from apps.agenda.models import Appointment, AppointmentService

class AppointmentMultiServiceTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmulti",
            email="multi@example.com",
            password="password123"
        )
        self.business = Business.objects.create(
            name="Salon Multi",
            slug="salon-multi",
            currency="$"
        )
        self.user.business = self.business
        self.user.save()
        self.client.force_login(self.user)

        self.staff = StaffMember.objects.create(
            business=self.business,
            first_name="Carlos",
            last_name="Barbero",
            role_title="Barbero Pro"
        )
        self.crm_client = CRMClient.objects.create(
            business=self.business,
            first_name="Pedro",
            last_name="Gómez",
            phone="123456789"
        )
        self.srv_corte = Service.objects.create(
            business=self.business,
            name="Corte Clásico",
            price=Decimal("20.00"),
            duration_minutes=30
        )
        self.srv_barba = Service.objects.create(
            business=self.business,
            name="Arreglo de Barba",
            price=Decimal("15.00"),
            duration_minutes=20
        )

    def test_appointment_create_with_multiple_different_services(self):
        url = reverse('appointment_create')
        services_data = [
            {'id': str(self.srv_corte.id), 'quantity': 1},
            {'id': str(self.srv_barba.id), 'quantity': 1}
        ]
        response = self.client.post(url, {
            'client_id': str(self.crm_client.id),
            'staff_id': str(self.staff.id),
            'services_data': json.dumps(services_data),
            'date': '2026-10-20',
            'start_time': '10:00',
            'status': 'CONFIRMED',
            'notes': 'Cita combinada corte + barba'
        })
        self.assertEqual(response.status_code, 302)
        app = Appointment.objects.get(client=self.crm_client)
        self.assertEqual(app.total_price, Decimal('35.00'))
        self.assertEqual(app.total_duration_minutes, 50)
        self.assertEqual(app.appointment_services.count(), 2)
        self.assertIn("Corte Clásico", app.services_summary)
        self.assertIn("Arreglo de Barba", app.services_summary)
        self.assertEqual(app.start_time.strftime("%H:%M"), "10:00")
        self.assertEqual(app.end_time.strftime("%H:%M"), "10:50")

    def test_appointment_create_with_same_service_multiple_times(self):
        url = reverse('appointment_create')
        services_data = [
            {'id': str(self.srv_corte.id), 'quantity': 3}
        ]
        response = self.client.post(url, {
            'client_id': str(self.crm_client.id),
            'staff_id': str(self.staff.id),
            'services_data': json.dumps(services_data),
            'date': '2026-10-20',
            'start_time': '14:00',
            'status': 'CONFIRMED',
            'notes': '3 cortes familiares'
        })
        self.assertEqual(response.status_code, 302)
        app = Appointment.objects.get(client=self.crm_client, start_time='14:00')
        self.assertEqual(app.total_price, Decimal('60.00'))
        self.assertEqual(app.total_duration_minutes, 90)
        self.assertEqual(app.appointment_services.count(), 1)
        item = app.appointment_services.first()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(app.services_summary, "Corte Clásico (x3)")
        self.assertEqual(app.end_time.strftime("%H:%M"), "15:30")

    def test_appointment_edit_services_and_quantities(self):
        # Create initially with 1 corte
        app = Appointment.objects.create(
            business=self.business,
            client=self.crm_client,
            staff=self.staff,
            service=self.srv_corte,
            date='2026-10-21',
            start_time='09:00',
            end_time='09:30',
            total_price=Decimal('20.00'),
            status='CONFIRMED'
        )
        AppointmentService.objects.create(
            appointment=app,
            service=self.srv_corte,
            quantity=1,
            unit_price=self.srv_corte.price,
            duration_minutes=self.srv_corte.duration_minutes
        )

        url = reverse('appointment_edit', kwargs={'appointment_id': app.id})
        new_services_data = [
            {'id': str(self.srv_corte.id), 'quantity': 2},
            {'id': str(self.srv_barba.id), 'quantity': 1}
        ]
        response = self.client.post(url, {
            'client_id': str(self.crm_client.id),
            'staff_id': str(self.staff.id),
            'services_data': json.dumps(new_services_data),
            'date': '2026-10-21',
            'start_time': '09:00',
            'status': 'CONFIRMED',
            'notes': 'Editada: 2 cortes + 1 barba'
        })
        self.assertEqual(response.status_code, 302)
        app.refresh_from_db()
        self.assertEqual(app.total_price, Decimal('55.00')) # (20*2) + 15
        self.assertEqual(app.total_duration_minutes, 80) # (30*2) + 20
        self.assertEqual(app.appointment_services.count(), 2)
        self.assertEqual(app.end_time.strftime("%H:%M"), "10:20")
