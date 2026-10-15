from decimal import Decimal
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.business.models import Business
from apps.properties.models import Property

User = get_user_model()

class PropertyModelTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Inmobiliaria Norte",
            slug="inmobiliaria-norte",
            business_type="REAL_ESTATE",
            currency="USD",
            is_booking_enabled=True
        )
        self.user = User.objects.create_user(
            username="realtor@example.com",
            email="realtor@example.com",
            password="secretpassword123",
            business=self.business,
            role="OWNER"
        )

    def test_property_creation_and_properties(self):
        prop = Property.objects.create(
            business=self.business,
            title="Departamento 3 Ambientes con Balcón",
            reference_code="DEP-101",
            property_type="APARTMENT",
            operation_type="SALE",
            price=Decimal("125000.00"),
            currency="USD",
            expenses=Decimal("15000.00"),
            address="Av. del Libertador 4500",
            zone="Palermo",
            description="Excelente piso alto con vista abierta",
            bedrooms=2,
            bathrooms=2,
            total_surface=Decimal("78.50"),
            covered_surface=Decimal("72.00"),
            garages=1,
            portal_url="https://www.zonaprop.com.ar/propiedades/dep-101.html"
        )

        self.assertEqual(prop.formatted_price, "USD 125.000")
        self.assertEqual(prop.formatted_expenses, "USD 15.000")
        self.assertEqual(prop.portal_display_name, "Zonaprop")
        self.assertEqual(prop.photos_count, 0)
        self.assertIsNone(prop.main_photo_url)
        self.assertIn("Departamento 3 Ambientes", str(prop))

    def test_portal_display_name_detection(self):
        prop1 = Property.objects.create(
            business=self.business,
            title="Casa 1",
            price=Decimal("200000"),
            portal_url="https://www.argenprop.com/propiedad-123",
            address="Calle 1",
            zone="Belgrano"
        )
        self.assertEqual(prop1.portal_display_name, "Argenprop")

        prop2 = Property.objects.create(
            business=self.business,
            title="Casa 2",
            price=Decimal("200000"),
            portal_url="https://departamento.mercadolibre.com.ar/MLA-999",
            address="Calle 2",
            zone="Recoleta"
        )
        self.assertEqual(prop2.portal_display_name, "Mercado Libre")

        prop3 = Property.objects.create(
            business=self.business,
            title="Casa 3",
            price=Decimal("200000"),
            portal_name="Portal Personalizado",
            portal_url="https://otropostal.com/test",
            address="Calle 3",
            zone="Colegiales"
        )
        self.assertEqual(prop3.portal_display_name, "Portal Personalizado")


class PropertyViewTests(TestCase):
    def setUp(self):
        self.client = HttpClient()
        self.business = Business.objects.create(
            name="Inmobiliaria Sur",
            slug="inmobiliaria-sur",
            business_type="REAL_ESTATE",
            currency="USD"
        )
        self.user = User.objects.create_user(
            username="agente@example.com",
            email="agente@example.com",
            password="secretpassword123",
            business=self.business,
            role="OWNER"
        )

        # Other business for multi-tenant isolation test
        self.other_business = Business.objects.create(
            name="Otra Inmobiliaria",
            slug="otra-inmo",
            business_type="REAL_ESTATE"
        )
        self.other_prop = Property.objects.create(
            business=self.other_business,
            title="Depto Ajeno",
            price=Decimal("90000"),
            address="Calle Ajena 100",
            zone="Centro"
        )

        self.client.login(username="agente@example.com", password="secretpassword123")
        # Ensure session current_business_id is set
        session = self.client.session
        session['current_business_id'] = str(self.business.id)
        session.save()

    def test_property_list_view(self):
        Property.objects.create(
            business=self.business,
            title="Casa en Pilar",
            property_type="HOUSE",
            operation_type="SALE",
            price=Decimal("250000"),
            address="Los Robles 123",
            zone="Pilar",
            is_featured=True
        )
        Property.objects.create(
            business=self.business,
            title="Depto en Nuñez",
            property_type="APARTMENT",
            operation_type="RENT",
            price=Decimal("800"),
            address="Cabildo 3000",
            zone="Nuñez"
        )

        url = reverse('property_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casa en Pilar")
        self.assertContains(response, "Depto en Nuñez")
        self.assertNotContains(response, "Depto Ajeno")
        self.assertEqual(response.context['total_count'], 2)
        self.assertEqual(response.context['for_sale_count'], 1)
        self.assertEqual(response.context['for_rent_count'], 1)
        self.assertEqual(response.context['featured_count'], 1)

    def test_property_create_view(self):
        url = reverse('property_create')
        post_data = {
            'title': 'Oficina Moderna en Belgrano',
            'reference_code': 'OFI-501',
            'property_type': 'COMMERCIAL',
            'operation_type': 'RENT',
            'price': '1500',
            'currency': 'USD',
            'expenses': '200',
            'address': 'Juramento 2100',
            'zone': 'Belgrano',
            'description': 'Oficina comercial lista para entrar',
            'bedrooms': '0',
            'bathrooms': '2',
            'garages': '1',
            'total_surface': '85',
            'covered_surface': '85',
            'portal_url': 'https://www.zonaprop.com.ar/oficina-501',
            'status': 'AVAILABLE',
            'is_featured': 'on'
        }
        response = self.client.post(url, post_data)
        self.assertRedirects(response, reverse('property_list'))

        prop = Property.objects.filter(business=self.business, reference_code='OFI-501').first()
        self.assertIsNotNone(prop)
        self.assertEqual(prop.title, 'Oficina Moderna en Belgrano')
        self.assertEqual(prop.price, Decimal('1500.00'))
        self.assertTrue(prop.is_featured)

    def test_property_create_with_cropped_photos(self):
        url = reverse('property_create')
        # 1x1 valid PNG base64
        tiny_png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        post_data = {
            'title': 'Casa con Fotos Recortadas',
            'price': '250000',
            'currency': 'USD',
            'address': 'Libertador 1000',
            'zone': 'Vicente López',
            'cropped_photo_1_base64': tiny_png_b64,
            'cropped_photo_2_base64': tiny_png_b64,
        }
        response = self.client.post(url, post_data)
        self.assertRedirects(response, reverse('property_list'))

        prop = Property.objects.filter(business=self.business, title='Casa con Fotos Recortadas').first()
        self.assertIsNotNone(prop)
        self.assertTrue(bool(prop.photo_1))
        self.assertTrue(bool(prop.photo_2))
        self.assertFalse(bool(prop.photo_3))
        self.assertEqual(prop.photos_count, 2)

    def test_property_edit_view(self):
        prop = Property.objects.create(
            business=self.business,
            title="Monoambiente Luminoso",
            property_type="APARTMENT",
            operation_type="RENT",
            price=Decimal("400"),
            address="Santa Fe 2000",
            zone="Barrio Norte"
        )

        url = reverse('property_edit', kwargs={'property_id': prop.id})
        response = self.client.post(url, {
            'title': 'Monoambiente Luminoso Editado',
            'price': '450',
            'currency': 'USD',
            'address': 'Santa Fe 2000 piso 5',
            'zone': 'Recoleta',
            'status': 'AVAILABLE',
            'operation_type': 'RENT',
            'property_type': 'APARTMENT',
        })
        self.assertRedirects(response, reverse('property_list'))

        prop.refresh_from_db()
        self.assertEqual(prop.title, 'Monoambiente Luminoso Editado')
        self.assertEqual(prop.price, Decimal('450.00'))
        self.assertEqual(prop.zone, 'Recoleta')

    def test_property_delete_view(self):
        prop = Property.objects.create(
            business=self.business,
            title="Propiedad a borrar",
            price=Decimal("10000"),
            address="Calle Test",
            zone="Test"
        )
        url = reverse('property_delete', kwargs={'property_id': prop.id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('property_list'))
        self.assertFalse(Property.objects.filter(id=prop.id).exists())

    def test_cannot_access_other_business_property(self):
        url = reverse('property_edit', kwargs={'property_id': self.other_prop.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_property_with_agent_and_owner_client(self):
        from apps.business.models import StaffMember
        from apps.crm.models import Client

        agent = StaffMember.objects.create(
            business=self.business,
            first_name="Valeria",
            last_name="Broker",
            role_title="Asesora Inmobiliaria Senior",
            phone="1155443322",
            is_active=True
        )
        owner = Client.objects.create(
            business=self.business,
            first_name="Roberto",
            last_name="Propietario",
            phone="1199887766",
            email="roberto@propietario.com",
            tax_id="3012345678"
        )

        # Create with agent and owner_client
        url = reverse('property_create')
        post_data = {
            'title': 'Penthouse en Puerto Madero',
            'reference_code': 'PM-100',
            'property_type': 'APARTMENT',
            'operation_type': 'SALE',
            'price': '850000',
            'currency': 'USD',
            'address': 'Juana Manso 1500',
            'zone': 'Puerto Madero',
            'description': 'Vista panorámica al río',
            'bedrooms': '3',
            'bathrooms': '3',
            'garages': '2',
            'agent_id': str(agent.id),
            'owner_client_id': str(owner.id),
            'status': 'AVAILABLE',
        }
        response = self.client.post(url, post_data)
        self.assertRedirects(response, reverse('property_list'))

        prop = Property.objects.filter(business=self.business, reference_code='PM-100').first()
        self.assertIsNotNone(prop)
        self.assertEqual(prop.agent, agent)
        self.assertEqual(prop.owner_client, owner)

        # Detail view renders agent and owner info
        detail_url = reverse('property_detail', kwargs={'property_id': prop.id})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Valeria Broker")
        self.assertContains(detail_res, "Roberto Propietario")
        self.assertContains(detail_res, "1199887766")

        # List view filter by agent
        list_url = f"{reverse('property_list')}?agent={agent.id}"
        list_res = self.client.get(list_url)
        self.assertEqual(list_res.status_code, 200)
        self.assertContains(list_res, "Penthouse en Puerto Madero")

