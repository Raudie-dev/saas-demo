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

    def test_payment_methods_catalog_and_multi_region_anchoring(self):
        """
        Verifica que el desarrollo de cada método de pago esté guardado en el catálogo maestro
        y pueda ser anclado a múltiples regiones (en código y base de datos).
        """
        from apps.superadmin.models import Region, GlobalPaymentMethod, RegionPaymentMethod
        from apps.superadmin.regional_payment_registry import (
            PAYMENT_METHOD_CATALOG,
            anchor_method_to_region,
            anchor_method_to_regions,
            unanchor_method_from_region,
            get_anchored_regions,
            get_regional_payment_methods,
            get_payment_method_by_code,
            get_payment_method_definition,
        )

        # 1. Verificar que los métodos desarrollados están guardados en el catálogo
        developed_codes = ['MERCADOPAGO', 'ALIAS_CBU', 'PAGOMOVIL', 'TRANSFERENCIA_BS', 'BINANCE_PAY', 'TRANSFERENCIA_INTL']
        for code in developed_codes:
            def_obj = get_payment_method_definition(code)
            self.assertIsNotNone(def_obj, f"El método {code} debe estar guardado en el catálogo maestro.")
            self.assertEqual(def_obj.code, code)

        # Verificar datos específicos guardados
        mp_def = get_payment_method_definition('MERCADOPAGO')
        self.assertEqual(mp_def.type, 'GATEWAY')
        self.assertEqual(mp_def.provider, 'MERCADOPAGO')

        alias_def = get_payment_method_definition('ALIAS_CBU')
        self.assertEqual(alias_def.type, 'MANUAL')
        labels = [f['label'] for f in alias_def.fields]
        self.assertIn('Alias', labels)
        self.assertIn('CVU', labels)

        pm_def = get_payment_method_definition('PAGOMOVIL')
        self.assertEqual(pm_def.type, 'MANUAL')
        self.assertTrue(pm_def.qr_image.endswith('.jpg'))

        binance_def = get_payment_method_definition('BINANCE_PAY')
        self.assertEqual(binance_def.type, 'MANUAL')
        self.assertTrue(binance_def.qr_image.endswith('.jpg'))

        # 2. Anclar Binance Pay a múltiples regiones (ej: Chile, Colombia, Uruguay)
        anchor_method_to_regions('BINANCE_PAY', ['CL', 'CO', 'UY'])
        anchored = get_anchored_regions('BINANCE_PAY')
        self.assertIn('CL', anchored)
        self.assertIn('CO', anchored)
        self.assertIn('UY', anchored)

        # Verificar que get_regional_payment_methods para Chile incluye Binance Pay
        methods_cl = get_regional_payment_methods('CL')
        codes_cl = [m.code for m in methods_cl]
        self.assertIn('BINANCE_PAY', codes_cl)
        # Y tiene su QR e información completa heredada del catálogo
        binance_cl = next(m for m in methods_cl if m.code == 'BINANCE_PAY')
        self.assertEqual(binance_cl.qr_image, binance_def.qr_image)
        self.assertEqual(len(binance_cl.fields), len(binance_def.fields))

        # 3. Anclaje dinámico vía Base de Datos (RegionPaymentMethod con use_for_billing=True)
        region_pe = Region.objects.create(name="Perú Test", code="PE_TEST", currency_symbol="S/.", is_active=True)
        gpm_binance, _ = GlobalPaymentMethod.objects.get_or_create(code="BINANCE_PAY", defaults={"name": "Binance Pay"})
        RegionPaymentMethod.objects.create(
            region=region_pe,
            payment_method=gpm_binance,
            use_for_billing=True,
            is_active=True
        )

        methods_pe = get_regional_payment_methods(region_pe)
        codes_pe = [m.code for m in methods_pe]
        self.assertIn('BINANCE_PAY', codes_pe)
        binance_pe = next(m for m in methods_pe if m.code == 'BINANCE_PAY')
        # Heredó automáticamente el QR y campos de Binance
        self.assertEqual(binance_pe.qr_image, binance_def.qr_image)

    def test_structured_card_fields_and_copy_buttons(self):
        """
        Verifica que todos los métodos de pago anclados presenten sus datos
        en filas estructuradas y respeten la regla de botones de copiado 1 a 1:
        - Cuentas, Cédulas, Alias, Teléfonos, CVU tienen can_copy=True.
        - Titular (Raulymar De Abreu), Billetera, Moneda y Tasas tienen can_copy=False.
        """
        from apps.superadmin.regional_payment_registry import (
            parse_instructions_into_fields,
            get_regional_payment_methods,
            PAYMENT_METHOD_CATALOG
        )

        # 1. Probar parser automático
        sample_text = (
            "• Banco: Banco BNC (Código 0191)\n"
            "• Cuenta Corriente: 0191-0025-11-2125078240\n"
            "• Cédula: V-31473363\n"
            "• Titular: Raulymar De Abreu\n"
            "• Moneda: Bolívares (Bs.)"
        )
        parsed = parse_instructions_into_fields(sample_text)
        self.assertEqual(len(parsed), 5)
        self.assertTrue(parsed[0]['can_copy'])  # Banco
        self.assertEqual(parsed[0]['copy_value'], '0191')
        self.assertTrue(parsed[1]['can_copy'])  # Cuenta
        self.assertEqual(parsed[1]['copy_value'], '01910025112125078240')
        self.assertTrue(parsed[2]['can_copy'])  # Cédula
        self.assertEqual(parsed[2]['copy_value'], '31473363')
        self.assertFalse(parsed[3]['can_copy'])  # Titular Raulymar De Abreu no debe ser copiable
        self.assertFalse(parsed[4]['can_copy'])  # Moneda no debe ser copiable

        # 2. Verificar métodos de Argentina
        ar_methods = get_regional_payment_methods('AR')
        alias_method = next((m for m in ar_methods if m.code == 'ALIAS_CBU'), None)
        self.assertIsNotNone(alias_method)
        self.assertGreaterEqual(len(alias_method.fields), 3)
        # En Argentina solo Alias y CVU son copiables
        for f in alias_method.fields:
            if f['label'] in ('Alias', 'CVU'):
                self.assertTrue(f['can_copy'])
                self.assertTrue(len(f['copy_value']) > 0)
            elif f['label'] in ('Titular', 'Billetera / Banco'):
                self.assertFalse(f['can_copy'])

        # 3. Verificar métodos de Venezuela
        ve_methods = get_regional_payment_methods('VE')
        for vm in ve_methods:
            if vm.type == 'MANUAL':
                self.assertTrue(len(vm.fields) > 0)
                # Confirmar que el titular siempre es Raulymar De Abreu y no es copiable
                titular_field = next((f for f in vm.fields if 'Titular' in f['label']), None)
                if titular_field:
                    self.assertEqual(titular_field['value'], 'Raulymar De Abreu')
                    self.assertFalse(titular_field['can_copy'])

    def test_anchor_multi_region_view_action(self):
        """
        Verifica que la acción ANCHOR_MULTI_REGION permita al SuperAdmin
        anclar un método de pago a múltiples regiones con un solo clic
        sin tener que crearlo desde cero para cada país.
        """
        from apps.superadmin.models import Region, GlobalPaymentMethod, RegionPaymentMethod
        
        r_bo, _ = Region.objects.get_or_create(code="591", defaults={"name": "Bolivia", "currency_symbol": "Bs."})
        r_br, _ = Region.objects.get_or_create(code="55", defaults={"name": "Brasil", "currency_symbol": "R$"})
        pm_binance, _ = GlobalPaymentMethod.objects.get_or_create(code="BINANCE_PAY", defaults={"name": "Binance Pay / USDT"})

        # Simular sesión de SuperAdmin
        session = self.client.session
        session['superadmin_id'] = str(self.superadmin.id)
        session.save()

        response = self.client.post(reverse('superadmin_regions'), {
            'action': 'ANCHOR_MULTI_REGION',
            'payment_method_id': str(pm_binance.id),
            'region_ids': [str(r_bo.id), str(r_br.id)],
        }, follow=True)

        self.assertEqual(response.status_code, 200)

        # Confirmar que ambas regiones tienen ahora Binance Pay activo para facturación
        rpm_bo = RegionPaymentMethod.objects.filter(region=r_bo, payment_method=pm_binance).first()
        rpm_br = RegionPaymentMethod.objects.filter(region=r_br, payment_method=pm_binance).first()
        self.assertIsNotNone(rpm_bo)
        self.assertIsNotNone(rpm_br)
        self.assertTrue(rpm_bo.use_for_billing)
        self.assertTrue(rpm_br.use_for_billing)
        self.assertIn('raudie.dev@gmail.com', rpm_bo.instructions)
        self.assertIn('raudie.dev@gmail.com', rpm_br.instructions)

    def test_active_regions_and_developed_methods_filtering(self):
        """
        Verifica que en la gestión de regiones:
        1. Solo los métodos desarrollados estén activos en global_methods.
        2. Solo las regiones activas en uso aparezcan en regions_data.
        3. Se pueda activar y desactivar una región limpiamente.
        """
        from apps.superadmin.models import Region, GlobalPaymentMethod
        from apps.superadmin.views import DEVELOPED_PAYMENT_METHOD_CODES

        session = self.client.session
        session['superadmin_id'] = str(self.superadmin.id)
        session.save()

        response = self.client.get(reverse('superadmin_regions'))
        self.assertEqual(response.status_code, 200)

        # 1. global_methods solo contiene métodos desarrollados
        global_methods = response.context['global_methods']
        for gm in global_methods:
            self.assertIn(gm.code, DEVELOPED_PAYMENT_METHOD_CODES)

        # 2. regions_data solo contiene regiones con is_active=True
        regions_data = response.context['regions_data']
        for data in regions_data:
            self.assertTrue(data['region'].is_active)

        # 3. Probar activación de una región inactiva
        r_cl, _ = Region.objects.get_or_create(code="56", defaults={"name": "Chile", "is_active": False})
        r_cl.is_active = False
        r_cl.save()

        post_resp = self.client.post(reverse('superadmin_regions'), {
            'action': 'ACTIVATE_REGION',
            'region_id': str(r_cl.id),
        }, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        r_cl.refresh_from_db()
        self.assertTrue(r_cl.is_active)

        # 4. Probar desactivación
        deact_resp = self.client.post(reverse('superadmin_regions'), {
            'action': 'DEACTIVATE_REGION',
            'region_id': str(r_cl.id),
        }, follow=True)
        self.assertEqual(deact_resp.status_code, 200)
        r_cl.refresh_from_db()
        self.assertFalse(r_cl.is_active)
