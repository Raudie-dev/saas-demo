import uuid
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.business.models import Business, User, Branch, StaffMember, UserProfileRole
from apps.superadmin.models import (
    SuperAdminUser, BusinessSubscription, SubscriptionPlan, SystemAuditLog, SubscriptionPayment
)
from apps.agenda.models import ServiceCategory, Service, Appointment
from apps.crm.models import Client as CRMClient
from apps.invoicing.models import Invoice
from apps.pos.models import CashRegister, Sale
from apps.superadmin.views import delete_business_and_all_records

class DeleteBusinessAccountTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create SuperAdmin
        self.superadmin = SuperAdminUser.objects.create_user(
            email="admin@platform.com",
            username="superadmin",
            password="adminpassword123"
        )

        # Create Subscription Plan
        self.plan = SubscriptionPlan.objects.create(
            name="Plan Pro Test",
            code="PRO_TEST",
            monthly_price=Decimal("49.00")
        )

        # Create Business
        self.business = Business.objects.create(
            name="Agencia Marketing Total",
            slug="agencia-marketing-total",
            email="contacto@agenciamarketing.com",
            phone="+5491112345678",
            business_type="MARKETING"
        )

        # Create Subscription
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="ACTIVE",
            expiration_date=timezone.now().date() + timezone.timedelta(days=30)
        )

        # Create Users linked to the business
        self.user1 = User.objects.create_user(
            username="owner_marketing",
            email="owner@marketing.com",
            password="password123",
            role="OWNER",
            business=self.business
        )
        self.user2 = User.objects.create_user(
            username="staff_marketing",
            email="staff@marketing.com",
            password="password123",
            role="PROFESSIONAL",
            business=self.business
        )

        # Create Branch
        self.branch = Branch.objects.create(
            business=self.business,
            name="Sede Central",
            address="Av. Corrientes 1234"
        )

        # Create StaffMember
        self.staff = StaffMember.objects.create(
            business=self.business,
            branch=self.branch,
            user=self.user2,
            first_name="Carlos",
            last_name="Gomez",
            email="carlos@marketing.com"
        )

        # Create CRM Client
        self.crm_client = CRMClient.objects.create(
            business=self.business,
            first_name="Laura",
            last_name="Fernandez",
            email="laura@cliente.com"
        )

        # Create Service & Appointment
        self.service_cat = ServiceCategory.objects.create(
            business=self.business,
            name="Consultoría"
        )
        self.service = Service.objects.create(
            business=self.business,
            category=self.service_cat,
            name="Estrategia SEO",
            price=Decimal("150.00")
        )
        self.appointment = Appointment.objects.create(
            business=self.business,
            branch=self.branch,
            client=self.crm_client,
            staff=self.staff,
            service=self.service,
            date=timezone.now().date(),
            start_time="10:00",
            end_time="11:00",
            status="CONFIRMED",
            total_price=Decimal("150.00")
        )

        # Create Cash Register & Sale
        self.cash_register = CashRegister.objects.create(
            business=self.business,
            branch=self.branch,
            opened_by=self.user1,
            initial_amount=Decimal("100.00")
        )
        self.sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cash_register=self.cash_register,
            total_amount=Decimal("150.00")
        )

    def login_superadmin(self):
        session = self.client.session
        session['superadmin_id'] = str(self.superadmin.id)
        session.save()

    def test_delete_business_and_all_records_helper(self):
        """
        Verifica que delete_business_and_all_records elimine completamente la empresa,
        sus usuarios y todos los registros asociados en cascada.
        """
        biz_id = self.business.id
        u1_id = self.user1.id
        u2_id = self.user2.id
        branch_id = self.branch.id
        staff_id = self.staff.id
        client_id = self.crm_client.id
        appointment_id = self.appointment.id
        sale_id = self.sale.id

        result = delete_business_and_all_records(self.business, actor_email=self.superadmin.email)

        self.assertEqual(result['name'], "Agencia Marketing Total")
        self.assertEqual(result['users_count'], 2)

        # Verificar que Business ya no existe
        self.assertFalse(Business.objects.filter(id=biz_id).exists())

        # Verificar que los Users del negocio fueron eliminados
        self.assertFalse(User.objects.filter(id__in=[u1_id, u2_id]).exists())

        # Verificar que los registros relacionados fueron eliminados en cascada
        self.assertFalse(Branch.objects.filter(id=branch_id).exists())
        self.assertFalse(StaffMember.objects.filter(id=staff_id).exists())
        self.assertFalse(CRMClient.objects.filter(id=client_id).exists())
        self.assertFalse(Appointment.objects.filter(id=appointment_id).exists())
        self.assertFalse(Sale.objects.filter(id=sale_id).exists())
        self.assertFalse(BusinessSubscription.objects.filter(business_id=biz_id).exists())

        # Verificar log de auditoría
        audit = SystemAuditLog.objects.filter(action="ELIMINACION_CUENTA").latest('created_at')
        self.assertIn("Agencia Marketing Total", audit.details)
        self.assertEqual(audit.actor_email, self.superadmin.email)

    def test_delete_business_view_requires_superadmin(self):
        """
        Verifica que usuarios no autenticados o usuarios normales no puedan invocar la vista de borrado.
        """
        url = reverse('superadmin_delete_business', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'confirmation': 'ELIMINAR'})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.url.startswith(reverse('superadmin_login')))
        self.assertTrue(Business.objects.filter(id=self.business.id).exists())

    def test_delete_business_view_requires_post(self):
        """
        Verifica que una solicitud GET a la URL de borrado no elimine el registro.
        """
        self.login_superadmin()
        url = reverse('superadmin_delete_business', kwargs={'business_id': self.business.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Business.objects.filter(id=self.business.id).exists())

    def test_delete_business_view_confirmation_required(self):
        """
        Verifica que si no se envía la palabra ELIMINAR, no se borre la cuenta.
        """
        self.login_superadmin()
        url = reverse('superadmin_delete_business', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'confirmation': 'OTRA_COSA'})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Business.objects.filter(id=self.business.id).exists())

    def test_delete_business_view_success(self):
        """
        Verifica que al enviar la confirmación 'ELIMINAR', la cuenta y todos sus registros se eliminan.
        """
        self.login_superadmin()
        biz_id = self.business.id
        u1_id = self.user1.id

        url = reverse('superadmin_delete_business', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'confirmation': 'ELIMINAR'})
        self.assertRedirects(res, reverse('superadmin_users'))

        self.assertFalse(Business.objects.filter(id=biz_id).exists())
        self.assertFalse(User.objects.filter(id=u1_id).exists())

    def test_delete_business_via_action_in_user_detail_view(self):
        """
        Verifica que se pueda eliminar la cuenta desde user_detail_view pasando action=DELETE_BUSINESS.
        """
        self.login_superadmin()
        biz_id = self.business.id

        url = reverse('superadmin_user_detail', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'action': 'DELETE_BUSINESS', 'confirmation': 'ELIMINAR'})
        self.assertRedirects(res, reverse('superadmin_users'))

        self.assertFalse(Business.objects.filter(id=biz_id).exists())

    def test_delete_business_view_with_confirm_flag(self):
        """
        Verifica que confirm_delete='1' también confirme la eliminación.
        """
        self.login_superadmin()
        biz_id = self.business.id

        url = reverse('superadmin_delete_business', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'confirm_delete': '1'})
        self.assertRedirects(res, reverse('superadmin_users'))

        self.assertFalse(Business.objects.filter(id=biz_id).exists())

    def test_delete_business_agency_alias_url(self):
        """
        Verifica que la URL alias 'superadmin_delete_business_agency' funcione exactamente igual.
        """
        self.login_superadmin()
        biz_id = self.business.id

        url = reverse('superadmin_delete_business_agency', kwargs={'business_id': self.business.id})
        res = self.client.post(url, {'confirmation': 'ELIMINAR'})
        self.assertRedirects(res, reverse('superadmin_users'))

        self.assertFalse(Business.objects.filter(id=biz_id).exists())
