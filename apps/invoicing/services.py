from decimal import Decimal
from django.utils import timezone
from apps.invoicing.models import Invoice, InvoiceItem, PaymentInstallment, PaymentPlan, Quote
from apps.pos.models import Sale, SalePayment, SaleItem


def get_next_invoice_number(business):
    year = timezone.now().year
    count = Invoice.objects.filter(business=business).count() + 1
    return f"FAC-{year}-{count:04d}"


def create_invoice_for_installment(installment, charge_amount, payment_method='Transferencia', paid_date=None, reference=None, notes=None):
    """
    Crea una Factura oficial pagada a partir del cobro de una cuota o cobro directo.
    """
    business = installment.business
    paid_date = paid_date or installment.paid_date or timezone.now().date()
    plan_title = installment.plan.title if installment.plan else "Cobro de Servicios"
    client_name = installment.client.full_name if installment.client else "Cliente General"

    invoice_number = get_next_invoice_number(business)
    invoice_notes = (
        f"Cobro Cuota #{installment.installment_number}: {installment.concept} "
        f"(Plan: {plan_title}). Cliente: {client_name}. Ref: {reference or installment.reference or 'S/R'}. {notes or ''}"
    ).strip()

    # Evita violar la restricción OneToOne de Sale si la venta ya tuviera factura
    sale_to_link = None
    if installment.sale:
        try:
            if not hasattr(installment.sale, 'invoice') or installment.sale.invoice is None:
                sale_to_link = installment.sale
        except Exception:
            sale_to_link = None

    invoice = Invoice.objects.create(
        business=business,
        client=installment.client,
        sale=sale_to_link,
        payment_plan=installment.plan,
        installment=installment,
        quote=installment.quote or (installment.plan.quote if installment.plan else None),
        invoice_number=invoice_number,
        issue_date=paid_date,
        due_date=paid_date,
        status='PAID',
        payment_method=payment_method,
        subtotal=charge_amount,
        tax_amount=Decimal('0.00'),
        total_amount=charge_amount,
        notes=invoice_notes
    )

    InvoiceItem.objects.create(
        invoice=invoice,
        description=f"{installment.concept} (Cuota #{installment.installment_number} - {plan_title})",
        quantity=1,
        unit_price=charge_amount,
        total_price=charge_amount
    )

    installment.invoice = invoice
    installment.save(update_fields=['invoice'])
    return invoice


def charge_and_invoice_quote(quote, payment_method='Transferencia', reference=None, paid_date=None, notes=None):
    """
    Registra el cobro completo de una cotización y genera su factura pagada oficial,
    creando la venta financiera y el plan de cuota liquidado.
    """
    business = quote.business
    paid_date = paid_date or timezone.now().date()
    client = quote.client
    client_label = client.full_name if client else "Cliente General"
    total_amount = quote.total_amount

    # 1. Crear venta financiera oficial
    sale = Sale.objects.create(
        business=business,
        client=client,
        total_amount=total_amount,
        subtotal=quote.subtotal,
        status='COMPLETED',
        payment_method=payment_method,
        notes=f"Cobro Total Cotización #{quote.quote_number} ({quote.get_pricing_type_display()}). Ref: {reference or 'S/R'}. {notes or ''}".strip()
    )

    SalePayment.objects.create(
        sale=sale,
        payment_method=payment_method,
        amount=total_amount
    )

    for item in quote.items.all():
        qty_int = int(round(item.quantity)) if item.quantity else 1
        unit_display = f" ({item.quantity} {item.unit_label})" if item.item_type != 'FIXED' else ""
        SaleItem.objects.create(
            sale=sale,
            item_type='SERVICE',
            quantity=max(1, qty_int),
            unit_price=item.unit_price,
            total_price=item.total_price
        )

    # 2. Crear Factura Oficial Pagada
    invoice_number = get_next_invoice_number(business)
    invoice = Invoice.objects.create(
        business=business,
        client=client,
        sale=sale,
        quote=quote,
        invoice_number=invoice_number,
        issue_date=paid_date,
        due_date=paid_date,
        status='PAID',
        payment_method=payment_method,
        subtotal=quote.subtotal,
        tax_amount=quote.tax_amount,
        total_amount=total_amount,
        notes=f"Factura generada y cobrada desde Cotización #{quote.quote_number}. Ref: {reference or 'S/R'}."
    )

    for item in quote.items.all():
        qty_int = int(round(item.quantity)) if item.quantity else 1
        unit_display = f" ({item.quantity} {item.unit_label})" if item.item_type != 'FIXED' else ""
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f"{item.description}{unit_display}",
            quantity=max(1, qty_int),
            unit_price=item.unit_price,
            total_price=item.total_price
        )

    # 3. Vincular cotización
    quote.status = 'ACCEPTED'
    quote.converted_to_invoice = invoice
    quote.save(update_fields=['status', 'converted_to_invoice'])

    # 4. Crear o actualizar plan de cobro como liquidado
    plan, _ = PaymentPlan.objects.get_or_create(
        business=business,
        quote=quote,
        defaults={
            'client': client,
            'title': f"Cobro Liquidado: Cotización #{quote.quote_number}",
            'total_amount': total_amount,
            'status': 'COMPLETED',
            'notes': f"Liquidado al 100% el {paid_date}"
        }
    )

    PaymentInstallment.objects.create(
        plan=plan,
        business=business,
        client=client,
        quote=quote,
        installment_number=1,
        concept=f"Liquidación Total Cotización #{quote.quote_number}",
        amount=total_amount,
        amount_paid=total_amount,
        due_date=paid_date,
        paid_date=paid_date,
        status='PAID',
        payment_method=payment_method,
        reference=reference,
        sale=sale,
        invoice=invoice,
        notes=notes
    )
    plan.update_status()

    return invoice


def mark_invoice_as_paid(invoice, payment_method='Transferencia', reference=None, paid_date=None, notes=None):
    """
    Marca una factura emitida como PAGADA e impacta el flujo financiero.
    """
    paid_date = paid_date or timezone.now().date()
    business = invoice.business

    if not invoice.sale:
        sale = Sale.objects.create(
            business=business,
            client=invoice.client,
            total_amount=invoice.total_amount,
            subtotal=invoice.subtotal,
            status='COMPLETED',
            payment_method=payment_method,
            notes=f"Cobro Factura #{invoice.invoice_number}. Ref: {reference or 'S/R'}. {notes or ''}".strip()
        )
        SalePayment.objects.create(
            sale=sale,
            payment_method=payment_method,
            amount=invoice.total_amount
        )
        for item in invoice.items.all():
            SaleItem.objects.create(
                sale=sale,
                item_type='SERVICE',
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price
            )
        invoice.sale = sale

    invoice.status = 'PAID'
    invoice.payment_method = payment_method
    if notes:
        invoice.notes = f"{invoice.notes or ''}\n{notes}".strip()
    invoice.save()

    if invoice.installment:
        inst = invoice.installment
        inst.amount_paid = invoice.total_amount
        inst.status = 'PAID'
        inst.paid_date = paid_date
        inst.payment_method = payment_method
        inst.reference = reference
        inst.save()
        if inst.plan:
            inst.plan.update_status()

    return invoice


def backfill_invoices_for_paid_installments():
    """Genera facturas oficiales para todas las cuotas cobradas que no tengan factura asociada."""
    paid_installments = PaymentInstallment.objects.filter(
        status='PAID',
        invoice__isnull=True
    ).select_related('business', 'client', 'plan', 'sale', 'quote')

    created = []
    for inst in paid_installments:
        inv = create_invoice_for_installment(
            installment=inst,
            charge_amount=inst.amount_paid or inst.amount,
            payment_method=inst.payment_method or 'Transferencia',
            paid_date=inst.paid_date or (inst.updated_at.date() if hasattr(inst, 'updated_at') else None) or timezone.now().date(),
            reference=inst.reference,
            notes=inst.notes
        )
        created.append(inv)
    return created
