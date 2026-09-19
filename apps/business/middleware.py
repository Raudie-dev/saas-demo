import uuid
from django.utils.text import slugify

class BusinessMiddleware:
    """
    Middleware que garantiza que `request.current_business` siempre apunte
    al negocio asignado al usuario autenticado.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        business = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'business') and request.user.business:
                business = request.user.business
            else:
                # Si el usuario no tiene negocio asignado, le creamos uno propio
                from apps.business.models import Business, Branch
                agency_name = f"Agencia {request.user.first_name or request.user.username}".strip()
                raw_slug = slugify(agency_name) or "agencia"
                business = Business.objects.create(
                    name=agency_name,
                    slug=f"{raw_slug}-{uuid.uuid4().hex[:4]}",
                    email=request.user.email or "contacto@agencia.com",
                    phone=request.user.phone or "+1 555-0000",
                    currency="$",
                    branding_color="#881337",
                    business_type='MARKETING',
                    primary_goal='Captar clientes y automatizar ventas',
                    enabled_modules=['crm', 'agenda', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing'],
                    onboarding_completed=False
                )
                
                Branch.objects.get_or_create(
                    business=business,
                    is_main=True,
                    defaults={
                        'name': 'Sede Principal',
                        'address': 'Dirección Principal',
                        'phone': request.user.phone or ''
                    }
                )

                request.user.business = business
                request.user.save()

        if not business:
            from apps.business.models import Business
            business = Business.objects.first()

        request.current_business = business
        response = self.get_response(request)
        return response
