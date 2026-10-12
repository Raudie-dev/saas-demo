import json
from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.business.models import (
    Business, User, StaffMember, UserProfileRole, ensure_default_profiles
)
from apps.superadmin.models import SubscriptionPlan, BusinessSubscription
from apps.crm.models import Client as CRMClient
from apps.agenda.models import Service, Appointment
from apps.commissions.models import CommissionRecord
from apps.pos.models import Sale, SalePayment


class UserRolesAndPermissionsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Business
        self.business = Business.objects.create(
            name="Clínica Estética Demo",
            slug="clinica-estetica-demo",
            currency="USD"
        )

        # Plan with starter modules (agenda, pos, commissions) and max_users=2
        self.plan = SubscriptionPlan.objects.create(
            name="Plan Inicial",
            code="STARTER_TEST",
            monthly_price=Decimal("29.00"),
            max_users=2,
            included_modules=["agenda", "pos", "commissions"]
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status="ACTIVE",
            expiration_date=timezone.now().date() + datetime.timedelta(days=365)
        )

        # Owner User
        self.owner = User.objects.create_user(
            username="owner@demo.com",
            email="owner@demo.com",
            password="password123",
            business=self.business,
            role="OWNER"
        )

        # Staff Members
        self.staff_a = StaffMember.objects.create(
            business=self.business,
            first_name="Dra. Ana",
            last_name="García",
            email="ana@demo.com",
            role_title="Dermatología",
            commission_rate=Decimal("20.00"),
            is_active=True
        )
        self.staff_b = StaffMember.objects.create(
            business=self.business,
            first_name="Dr. Beto",
            last_name="Pérez",
            email="beto@demo.com",
            role_title="Estética",
            commission_rate=Decimal("15.00"),
            is_active=True
        )

        # Ensure default roles
        self.roles = ensure_default_profiles(self.business)
        self.role_admin = UserProfileRole.objects.get(business=self.business, name="Administrador de Clínica")
        self.role_professional = UserProfileRole.objects.get(business=self.business, name="Profesional / Especialista")
        self.role_reception = UserProfileRole.objects.get(business=self.business, name="Recepción & Caja")

        # Professional User (linked to staff_a)
        self.prof_user = User.objects.create_user(
            username="ana@demo.com",
            email="ana@demo.com",
            password="password123",
            business=self.business,
            role="PROFESSIONAL",
            profile_role=self.role_professional
        )
        self.staff_a.user = self.prof_user
        self.staff_a.save()

        # Receptionist User
        self.reception_user = User.objects.create_user(
            username="recepcion@demo.com",
            email="recepcion@demo.com",
            password="password123",
            business=self.business,
            role="COLLABORATOR",
            profile_role=self.role_reception
        )

        # Client for appointments
        self.crm_client = CRMClient.objects.create(
            business=self.business,
            first_name="Carlos",
            last_name="Méndez",
            phone="+123456789"
        )

        # Service
        self.service = Service.objects.create(
            business=self.business,
            name="Limpieza Facial Profunda",
            price=Decimal("50.00"),
            duration_minutes=60,
            is_active=True
        )

    def test_default_profiles_created_with_expected_permissions(self):
        """Verify that ensure_default_profiles properly configures default roles."""
        self.assertEqual(len(self.roles), 3)

        # Admin
        self.assertTrue(self.role_admin.can_manage_settings)
        self.assertTrue(self.role_admin.can_view_financial_reports)
        self.assertTrue(self.role_admin.can_charge_pos)
        self.assertEqual(self.role_admin.scope_appointments, 'ALL')
        self.assertEqual(self.role_admin.scope_commissions, 'ALL')

        # Professional
        self.assertFalse(self.role_professional.can_manage_settings)
        self.assertFalse(self.role_professional.can_view_financial_reports)
        self.assertFalse(self.role_professional.can_charge_pos)
        self.assertEqual(self.role_professional.scope_appointments, 'OWN')
        self.assertEqual(self.role_professional.scope_commissions, 'OWN')
        self.assertTrue(self.prof_user.is_restricted_professional)

        # Reception
        self.assertFalse(self.role_reception.can_manage_settings)
        self.assertFalse(self.role_reception.can_view_financial_reports)
        self.assertTrue(self.role_reception.can_charge_pos)
        self.assertEqual(self.role_reception.scope_appointments, 'ALL')
        self.assertEqual(self.role_reception.scope_commissions, 'NONE')
        self.assertFalse(self.reception_user.is_restricted_professional)

    def test_role_create_filters_modules_by_active_subscription(self):
        """
        Verify that creating a custom role cannot enable modules outside
        the active subscription plan.
        """
        self.client.force_login(self.owner)
        url = reverse('role_create')

        # Attempt to enable modules: agenda, pos, and inventory/crm (which are not in plan)
        response = self.client.post(url, {
            'name': 'Perfil Personalizado',
            'description': 'Rol de prueba',
            'allowed_modules': ['agenda', 'pos', 'inventory', 'crm'],
            'scope_appointments': 'OWN',
            'scope_commissions': 'NONE',
            'can_charge_pos': 'on',
        })
        self.assertEqual(response.status_code, 302)

        created_role = UserProfileRole.objects.get(business=self.business, name='Perfil Personalizado')
        # Only agenda and pos should be in allowed_modules
        self.assertIn('agenda', created_role.allowed_modules)
        self.assertIn('pos', created_role.allowed_modules)
        self.assertNotIn('inventory', created_role.allowed_modules)
        self.assertNotIn('crm', created_role.allowed_modules)

    def test_user_creation_quota_enforcement(self):
        """
        Verify that user creation enforces subscription plan max_users limit.
        Currently: owner (1), prof_user (2), reception_user (3) -> count is 3, max_users is 2.
        """
        self.client.force_login(self.owner)
        url = reverse('user_create')

        # Since current_users (3) >= max_users (2), user_create GET should show warning and POST should block
        response = self.client.post(url, {
            'email': 'nuevo@demo.com',
            'password': 'password123',
            'first_name': 'Nuevo',
            'last_name': 'Usuario',
            'profile_role_id': self.role_reception.id,
        })
        self.assertEqual(response.status_code, 302)
        # Verify user was NOT created
        self.assertFalse(User.objects.filter(email='nuevo@demo.com').exists())

    def test_unauthorized_users_blocked_from_settings_and_user_management(self):
        """
        Verify that receptionists and professionals cannot access business configuration
        or user administration.
        """
        # Test as Professional
        self.client.force_login(self.prof_user)

        res_config = self.client.get(reverse('business_config'))
        self.assertEqual(res_config.status_code, 302)
        self.assertEqual(res_config.url, reverse('dashboard'))

        res_users = self.client.get(reverse('user_list'))
        self.assertEqual(res_users.status_code, 302)
        self.assertEqual(res_users.url, reverse('dashboard'))

        # Test as Receptionist
        self.client.force_login(self.reception_user)

        res_config = self.client.get(reverse('business_config'))
        self.assertEqual(res_config.status_code, 302)
        self.assertEqual(res_config.url, reverse('dashboard'))

        res_users = self.client.get(reverse('user_list'))
        self.assertEqual(res_users.status_code, 302)
        self.assertEqual(res_users.url, reverse('dashboard'))

    def test_owner_can_access_user_and_role_views_with_uuid(self):
        """
        Verify that user_list renders correctly without NoReverseMatch on role_edit / role_delete,
        and role_edit GET works cleanly with UUID.
        """
        self.client.force_login(self.owner)
        res_users = self.client.get(reverse('user_list'))
        self.assertEqual(res_users.status_code, 200)

        # Verify editing a role works with UUID
        res_role_edit = self.client.get(reverse('role_edit', args=[self.role_professional.id]))
        self.assertEqual(res_role_edit.status_code, 200)

    def test_user_profile_config_hides_branches_and_subscription_for_unauthorized_users(self):
        """
        Verify that in user_profile_config, non-privileged users do not see
        'Empresa, Sucursales & Módulos' or agency subscription sections.
        """
        # Professional without can_manage_settings
        self.client.force_login(self.prof_user)
        res_prof = self.client.get(reverse('user_profile_config'))
        self.assertEqual(res_prof.status_code, 200)
        self.assertNotContains(res_prof, "Empresa, Sucursales & Módulos")
        self.assertNotContains(res_prof, "subscription-section")

        # Owner with can_manage_settings
        self.client.force_login(self.owner)
        res_owner = self.client.get(reverse('user_profile_config'))
        self.assertEqual(res_owner.status_code, 200)
        self.assertContains(res_owner, "Empresa, Sucursales & Módulos")
        self.assertContains(res_owner, "subscription-section")

    def test_professional_agenda_isolation(self):
        """
        Verify that a professional only sees their own appointments in agenda.
        """
        today = timezone.now().date()
        # Appointment for Staff A (Prof user)
        apt_a = Appointment.objects.create(
            business=self.business,
            client=self.crm_client,
            staff=self.staff_a,
            service=self.service,
            date=today,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            status='CONFIRMED',
            total_price=Decimal('50.00')
        )
        # Appointment for Staff B
        apt_b = Appointment.objects.create(
            business=self.business,
            client=self.crm_client,
            staff=self.staff_b,
            service=self.service,
            date=today,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            status='CONFIRMED',
            total_price=Decimal('50.00')
        )

        self.client.force_login(self.prof_user)
        response = self.client.get(reverse('agenda'), {'date': today.isoformat()})
        self.assertEqual(response.status_code, 200)

        appointments_in_context = response.context['appointments']
        self.assertIn(apt_a, appointments_in_context)
        self.assertNotIn(apt_b, appointments_in_context)

    def test_professional_commissions_isolation(self):
        """
        Verify that a professional only sees their own commissions.
        """
        comm_a = CommissionRecord.objects.create(
            business=self.business,
            staff=self.staff_a,
            amount=Decimal("15.00"),
            concept="Comisión por Limpieza Facial"
        )
        comm_b = CommissionRecord.objects.create(
            business=self.business,
            staff=self.staff_b,
            amount=Decimal("25.00"),
            concept="Comisión Dr. Beto"
        )

        self.client.force_login(self.prof_user)
        response = self.client.get(reverse('commission_report'))
        self.assertEqual(response.status_code, 200)

        records_in_context = response.context['records']
        self.assertIn(comm_a, records_in_context)
        self.assertNotIn(comm_b, records_in_context)

    def test_financial_reports_access_control(self):
        """
        Verify that users without can_view_financial_reports are blocked from analytics reports.
        """
        # Professional blocked
        self.client.force_login(self.prof_user)
        res_prof = self.client.get(reverse('reports'))
        self.assertEqual(res_prof.status_code, 302)
        self.assertEqual(res_prof.url, reverse('dashboard'))

        # Receptionist blocked
        self.client.force_login(self.reception_user)
        res_rec = self.client.get(reverse('reports'))
        self.assertEqual(res_rec.status_code, 302)
        self.assertEqual(res_rec.url, reverse('dashboard'))

        # Owner allowed
        self.client.force_login(self.owner)
        res_owner = self.client.get(reverse('reports'))
        self.assertEqual(res_owner.status_code, 200)

    def test_pos_access_control(self):
        """
        Verify that receptionists with can_charge_pos can access POS,
        while professionals without it are redirected.
        """
        # Receptionist allowed
        self.client.force_login(self.reception_user)
        res_rec = self.client.get(reverse('pos_terminal'))
        self.assertEqual(res_rec.status_code, 200)

        # Professional blocked
        self.client.force_login(self.prof_user)
        res_prof = self.client.get(reverse('pos_terminal'))
        self.assertEqual(res_prof.status_code, 302)
        self.assertEqual(res_prof.url, reverse('dashboard'))

    def test_financial_report_payment_methods_pie_chart(self):
        """
        Verify that reports_view calculates dynamic percentages and displays
        the payment methods pie chart and breakdown in the main KPI tab.
        """
        # Create completed sales with different payment methods
        Sale.objects.create(
            business=self.business,
            status='COMPLETED',
            total_amount=Decimal('100.00'),
            payment_method='Efectivo'
        )
        Sale.objects.create(
            business=self.business,
            status='COMPLETED',
            total_amount=Decimal('50.00'),
            payment_method='Mercado Pago'
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)

        # Context contains dynamic payment methods summary
        summary = response.context['payment_methods_summary']
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]['name'], 'Efectivo')
        self.assertEqual(summary[0]['amount'], 100.00)
        self.assertEqual(summary[0]['percentage'], 66.7)
        self.assertEqual(summary[1]['name'], 'Mercado Pago')
        self.assertEqual(summary[1]['amount'], 50.00)
        self.assertEqual(summary[1]['percentage'], 33.3)

        # Canvas for pie chart is rendered in HTML
        self.assertContains(response, 'id="kpiPaymentPieChart"')
        self.assertContains(response, 'Participación por Método de Pago')
        content = response.content.decode('utf-8')
        self.assertTrue('66,7%' in content or '66.7%' in content)
        self.assertTrue('33,3%' in content or '33.3%' in content)
        self.assertContains(response, 'width: 66.7%')
