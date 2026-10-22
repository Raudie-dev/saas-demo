import logging
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.utils import timezone
from apps.crm.models import Client

logger = logging.getLogger(__name__)

def get_audience_clients(business, audience_code):
    """
    Retorna el queryset de clientes pertenecientes al negocio que tengan email válido
    filtrados según el segmento de audiencia seleccionado.
    """
    base_qs = Client.objects.filter(
        business=business,
        email__isnull=False
    ).exclude(email='').order_by('first_name', 'last_name')

    if audience_code == 'VIP':
        return base_qs.filter(status='VIP')
    elif audience_code == 'INACTIVE':
        return base_qs.filter(status='INACTIVE')
    elif audience_code == 'PROSPECT':
        return base_qs.filter(status='PROSPECT')
    return base_qs


def render_campaign_email_content(business, subject, body_text, client=None):
    """
    Reemplaza variables dinámicas y construye la versión HTML profesional
    junto con la versión de texto plano del correo.
    """
    client_name = client.first_name if client else "Estimado/a Cliente"
    client_fullname = client.full_name if client else client_name

    replacements = {
        '{client_name}': client_name,
        '{client_fullname}': client_fullname,
        '{nombre}': client_name,
        '{business}': business.name,
        '{business_name}': business.name,
        '{empresa}': business.name,
        '{phone}': business.phone or '',
        '{telefono}': business.phone or '',
        '{email}': business.email or '',
        '{currency}': getattr(business, 'currency', '$') or '$',
        '{date}': timezone.now().strftime('%d/%m/%Y'),
        '{fecha}': timezone.now().strftime('%d/%m/%Y'),
    }

    personalized_subject = subject
    personalized_body = body_text

    for var, val in replacements.items():
        personalized_subject = personalized_subject.replace(var, val)
        personalized_body = personalized_body.replace(var, val)

    brand_color = getattr(business, 'branding_color', '#881337') or '#881337'
    paragraphs = personalized_body.split('\n\n')
    formatted_body_html = "".join(
        f"<p style='margin: 0 0 16px 0; line-height: 1.6; color: #334155; font-size: 15px;'>{p.replace(chr(10), '<br>')}</p>"
        for p in paragraphs if p.strip()
    )

    logo_html = ""
    if getattr(business, 'logo_url', None):
        try:
            logo_html = f"<img src='{business.logo_url.url}' alt='{business.name}' style='max-height: 48px; max-width: 180px; margin-bottom: 12px; display: block;' />"
        except Exception:
            logo_html = ""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{personalized_subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 30px 15px;">
        <tr>
            <td align="center">
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                    <tr>
                        <td style="padding: 28px 32px; background-color: #ffffff; border-bottom: 3px solid {brand_color};">
                            {logo_html}
                            <h2 style="margin: 0; font-size: 20px; font-weight: 800; color: #0f172a;">{business.name}</h2>
                            <p style="margin: 4px 0 0 0; font-size: 12px; color: #64748b;">Comunicaciones & Novedades</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 32px 32px 24px 32px;">
                            <h1 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: #0f172a;">{personalized_subject}</h1>
                            {formatted_body_html}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 24px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; line-height: 1.5;">
                            <p style="margin: 0 0 6px 0; font-weight: 700; color: #334155;">{business.name}</p>
                            <p style="margin: 0 0 6px 0;">{business.address or ''} {('• Tel: ' + business.phone) if business.phone else ''}</p>
                            <p style="margin: 8px 0 0 0; font-size: 11px; color: #94a3b8;">
                                Recibes este correo porque eres cliente de {business.name}.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    return personalized_subject, personalized_body, html


def send_email_campaign_dispatch(campaign, test_email=None):
    """
    Ejecuta el envío de una campaña.
    Si se proporciona `test_email`, envía solo un correo de prueba a esa dirección.
    Si no, envía a todos los clientes de la audiencia del negocio.
    """
    business = campaign.business
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'notificaciones@raudie.com'
    if business.name and '<' not in from_email:
        sender = f"{business.name} <{from_email}>"
    else:
        sender = from_email

    # Determinar conexión de correo
    # Si no hay credenciales SMTP configuradas en entorno de desarrollo, usar consola para evitar fallos
    is_smtp_configured = bool(getattr(settings, 'EMAIL_HOST_USER', None) and getattr(settings, 'EMAIL_HOST_PASSWORD', None))
    if not is_smtp_configured:
        connection = get_connection('django.core.mail.backends.console.EmailBackend')
    else:
        connection = get_connection()

    if test_email:
        # Enviar correo de prueba a una sola dirección
        subj, text_body, html_body = render_campaign_email_content(
            business=business,
            subject=f"[PRUEBA] {campaign.subject}",
            body_text=campaign.body,
            client=None
        )
        msg = EmailMultiAlternatives(
            subject=subj,
            body=text_body,
            from_email=sender,
            to=[test_email.strip()],
            connection=connection
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        return {
            'success': True,
            'is_test': True,
            'recipients_count': 1,
            'is_smtp_configured': is_smtp_configured,
            'message': f"Correo de prueba enviado exitosamente a {test_email}."
        }

    # Envío a la audiencia completa
    clients_qs = get_audience_clients(business, campaign.audience)
    total_clients = clients_qs.count()

    if total_clients == 0:
        return {
            'success': False,
            'recipients_count': 0,
            'is_smtp_configured': is_smtp_configured,
            'message': "No hay clientes con correo electrónico en la audiencia seleccionada."
        }

    sent_count = 0
    errors = []

    try:
        connection.open()
        for client in clients_qs:
            try:
                subj, text_body, html_body = render_campaign_email_content(
                    business=business,
                    subject=campaign.subject,
                    body_text=campaign.body,
                    client=client
                )
                msg = EmailMultiAlternatives(
                    subject=subj,
                    body=text_body,
                    from_email=sender,
                    to=[client.email.strip()],
                    connection=connection
                )
                msg.attach_alternative(html_body, "text/html")
                msg.send(fail_silently=False)
                sent_count += 1
            except Exception as e:
                logger.error(f"Error enviando campaña a {client.email}: {e}")
                errors.append(f"{client.email}: {str(e)}")
        connection.close()

        # Actualizar campaña
        campaign.status = 'SENT'
        campaign.sent_at = timezone.now()
        campaign.recipients_count = sent_count
        if errors:
            campaign.last_error = f"{len(errors)} envíos fallidos: " + "; ".join(errors[:3])
        campaign.save(update_fields=['status', 'sent_at', 'recipients_count', 'last_error', 'updated_at'])

        msg_detail = f"Campaña enviada con éxito a {sent_count} destinatarios."
        if not is_smtp_configured:
            msg_detail += " (Nota: Servidor SMTP no configurado en .env; los correos se generaron en consola/prueba)."

        return {
            'success': True,
            'is_test': False,
            'recipients_count': sent_count,
            'is_smtp_configured': is_smtp_configured,
            'message': msg_detail
        }

    except Exception as exc:
        logger.exception("Fallo general al despachar campaña de email:")
        campaign.status = 'FAILED'
        campaign.last_error = str(exc)
        campaign.save(update_fields=['status', 'last_error', 'updated_at'])
        return {
            'success': False,
            'recipients_count': sent_count,
            'is_smtp_configured': is_smtp_configured,
            'message': f"Error al procesar el envío: {str(exc)}"
        }
