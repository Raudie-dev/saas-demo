import datetime
from decimal import Decimal
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.business.models import Business, StaffMember
from apps.crm.models import Client, ClientNote
from apps.properties.models import Property, PropertyInquiry
from apps.agenda.models import Appointment, Service

User = get_user_model()

class RealEstateCRMTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="agente@inmobiliaria.com",
            email="agente@inmobiliaria.com",
            password="securepassword123",
            first_name="Carlos",
            last_name="Broker"
        )
        self.business = Business.objects.create(
            name="Inmobiliaria Central",
            slug="inmobiliaria-central",
            email="contacto@inmobiliaria.com",
            phone="+5491100001111",
            business_type="REAL_ESTATE"
        )
        self.user.business = self.business
        self.user.save()

        self.staff = StaffMember.objects.create(
            business=self.business,
            first_name="Martín",
            last_name="Asesor",
            email="martin@inmobiliaria.com",
            phone="+5491133334444",
            role_title="Asesor Inmobiliario Senior",
            is_active=True
        )

        self.service = Service.objects.create(
            business=self.business,
            name="Visita a Propiedad",
            duration_minutes=45,
            price=Decimal("0.00"),
            is_active=True
        )

        self.property = Property.objects.create(
            business=self.business,
            title="Departamento 3 Ambientes con Balcón",
            reference_code="DEP-101",
            property_type="APARTMENT",
            operation_type="SALE",
            price=Decimal("125000.00"),
            currency="USD",
            address="Av. Cabildo 2400",
            zone="Belgrano",
            description="Excelente semipiso al frente muy luminoso.",
            agent=self.staff
        )

        self.client_user = TestClient()
        self.client_user.login(username="agente@inmobiliaria.com", password="securepassword123")

    def test_client_real_estate_role_detection(self):
        """Verifica que el rol inmobiliario (comprador, vendedor, ambos) se detecte correctamente."""
        # Cliente nuevo sin actividad
        client = Client.objects.create(
            business=self.business,
            first_name="Lucas",
            last_name="Pérez",
            phone="+5491122223333"
        )
        self.assertEqual(client.real_estate_role['type'], 'PROSPECT')

        # Se convierte en interesado en comprar
        inq_buyer = PropertyInquiry.objects.create(
            business=self.business,
            client=client,
            inquiry_type='BUYER',
            property=self.property,
            operation_type='Compra'
        )
        self.assertEqual(client.real_estate_role['type'], 'BUYER')

        # Se convierte también en propietario vendedor
        inq_seller = PropertyInquiry.objects.create(
            business=self.business,
            client=client,
            inquiry_type='SELLER',
            operation_type='Venta',
            property_type='Casa'
        )
        self.assertEqual(client.real_estate_role['type'], 'SELL_TO_BUY')

    def test_client_detail_renders_seller_inquiry_data(self):
        """Verifica que en el CRM del cliente se muestren los datos que agregó el interesado en vender."""
        client_seller = Client.objects.create(
            business=self.business,
            first_name="Mariana",
            last_name="Gómez",
            phone="+5491155556666",
            email="mariana@gmail.com"
        )
        PropertyInquiry.objects.create(
            business=self.business,
            client=client_seller,
            inquiry_type='SELLER',
            operation_type='Vender',
            property_type='Departamento',
            address_zone='Recoleta, Av. Santa Fe 1500',
            rooms='3 ambientes con dependencia',
            estimated_price='USD 180.000',
            notes='Piso alto, vista abierta, cochera fija cubierta.',
            status='PENDING'
        )

        url = reverse('client_detail', kwargs={'client_id': client_seller.id})
        response = self.client_user.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solicitudes de Propietario / Vendedor")
        self.assertContains(response, "Recoleta, Av. Santa Fe 1500")
        self.assertContains(response, "USD 180.000")
        self.assertContains(response, "3 ambientes con dependencia")
        self.assertContains(response, "Piso alto, vista abierta")

    def test_client_detail_renders_buyer_inquiry_and_visit_data(self):
        """Verifica que en el CRM del cliente se muestren los datos que agregó el interesado en comprar y sus visitas."""
        client_buyer = Client.objects.create(
            business=self.business,
            first_name="Gonzalo",
            last_name="Álvarez",
            phone="+5491177778888",
            email="gonzalo@gmail.com"
        )

        # Cita de visita al departamento
        appointment = Appointment.objects.create(
            business=self.business,
            client=client_buyer,
            staff=self.staff,
            service=self.service,
            related_property=self.property,
            date=datetime.date.today(),
            start_time=datetime.time(15, 0),
            end_time=datetime.time(15, 45),
            total_price=Decimal("0.00"),
            status='CONFIRMED',
            notes="Visita a propiedad: Departamento 3 Ambientes con Balcón\nConsulta: Me interesa saber si aceptan permuta por menor valor."
        )

        PropertyInquiry.objects.create(
            business=self.business,
            client=client_buyer,
            inquiry_type='BUYER',
            property=self.property,
            operation_type='Compra',
            property_type='Departamento',
            address_zone='Belgrano',
            estimated_price='USD 125.000',
            notes="Consulta: Me interesa saber si aceptan permuta por menor valor.",
            status='VISITING',
            agent=self.staff
        )

        url = reverse('client_detail', kwargs={'client_id': client_buyer.id})
        response = self.client_user.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Interés de Compra & Visitas")
        self.assertContains(response, "Departamento 3 Ambientes con Balcón")
        self.assertContains(response, "Av. Cabildo 2400")
        self.assertContains(response, "Me interesa saber si aceptan permuta por menor valor")

    def test_legacy_seller_notes_parsed_and_displayed(self):
        """Verifica que notas históricas en texto plano de propietarios también se presenten adecuadamente."""
        legacy_notes = "[PROPIETARIO - SOLICITUD DE VENDER]: Operación: Vender · Tipo: Casa · Ubicación: Nuñez · Ambientes: 4 amb · Precio estimado: USD 250.000 · Comentarios: Jardín con pileta"
        client_legacy = Client.objects.create(
            business=self.business,
            first_name="Valeria",
            last_name="Ríos",
            phone="+5491199990000",
            notes=legacy_notes
        )

        url = reverse('client_detail', kwargs={'client_id': client_legacy.id})
        response = self.client_user.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nuñez")
        self.assertContains(response, "USD 250.000")
        self.assertContains(response, "4 amb")

    def test_add_client_property_inquiry_view(self):
        """Verifica que un asesor pueda cargar directamente una solicitud inmobiliaria desde el CRM."""
        client = Client.objects.create(
            business=self.business,
            first_name="Federico",
            last_name="Méndez",
            phone="+5491144445555"
        )
        url = reverse('add_client_property_inquiry', kwargs={'client_id': client.id})
        post_data = {
            'inquiry_type': 'BUYER',
            'operation_type': 'Venta',
            'property_type': 'Casa',
            'address_zone': 'Nordelta / Tigre',
            'rooms': '4 ambientes',
            'estimated_price': 'USD 350.000',
            'notes': 'Busca casa en barrio cerrado con amarra propia.',
            'agent_id': str(self.staff.id),
            'status': 'PENDING'
        }
        response = self.client_user.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        inquiry = PropertyInquiry.objects.filter(client=client).first()
        self.assertIsNotNone(inquiry)
        self.assertEqual(inquiry.inquiry_type, 'BUYER')
        self.assertEqual(inquiry.address_zone, 'Nordelta / Tigre')
        self.assertEqual(inquiry.agent, self.staff)

    def test_update_property_inquiry_status_view(self):
        """Verifica que se pueda actualizar el estado de seguimiento de una solicitud inmobiliaria."""
        client = Client.objects.create(
            business=self.business,
            first_name="Santiago",
            last_name="Paz",
            phone="+5491111112222"
        )
        inquiry = PropertyInquiry.objects.create(
            business=self.business,
            client=client,
            inquiry_type='SELLER',
            operation_type='Venta',
            status='PENDING'
        )
        url = reverse('update_property_inquiry_status', kwargs={'inquiry_id': inquiry.id})
        response = self.client_user.post(url, {'status': 'NEGOTIATING'})
        self.assertEqual(response.status_code, 302)

        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, 'NEGOTIATING')

    def test_client_list_view_real_estate_columns_and_filters(self):
        """Verifica que la lista de clientes muestre columnas y filtros inmobiliarios."""
        # Vendedor
        c1 = Client.objects.create(business=self.business, first_name="Ana", last_name="Vendedora", phone="111")
        PropertyInquiry.objects.create(business=self.business, client=c1, inquiry_type='SELLER', operation_type='Venta')

        # Comprador
        c2 = Client.objects.create(business=self.business, first_name="Beto", last_name="Comprador", phone="222")
        PropertyInquiry.objects.create(business=self.business, client=c2, inquiry_type='BUYER', operation_type='Compra')

        # Lista general
        url = reverse('client_list')
        response = self.client_user.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Perfil")
        self.assertContains(response, "Propietario")
        self.assertContains(response, "Comprador")

        # Filtro de vendedores
        response_sellers = self.client_user.get(url + "?re_filter=sellers")
        self.assertEqual(response_sellers.status_code, 200)
        self.assertContains(response_sellers, "Ana Vendedora")
        self.assertNotContains(response_sellers, "Beto Comprador")

        # Filtro de compradores
        response_buyers = self.client_user.get(url + "?re_filter=buyers")
        self.assertEqual(response_buyers.status_code, 200)
        self.assertContains(response_buyers, "Beto Comprador")
        self.assertNotContains(response_buyers, "Ana Vendedora")
