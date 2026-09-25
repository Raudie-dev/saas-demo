import uuid
from django.utils.text import slugify

class BusinessMiddleware:
    """
    Middleware que garantiza que `request.current_business`, `request.current_branch`
    y `request.available_branches` siempre estén disponibles para el usuario autenticado.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        business = None
        current_branch = None
        available_branches = []

        if hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'business') and request.user.business:
                business = request.user.business
            else:
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

            if business:
                from apps.business.models import Branch
                available_branches = list(Branch.objects.filter(business=business).order_by('-is_main', 'name'))

                if not available_branches:
                    main_b = Branch.objects.create(
                        business=business,
                        name='Sede Principal',
                        address=business.address or 'Dirección Principal',
                        phone=business.phone or '',
                        is_main=True
                    )
                    available_branches = [main_b]

                active_branch_id = request.session.get('active_branch_id')
                if active_branch_id:
                    current_branch = next((b for b in available_branches if str(b.id) == str(active_branch_id)), None)

                if not current_branch:
                    current_branch = available_branches[0]
                    request.session['active_branch_id'] = str(current_branch.id)

        request.current_business = business
        request.current_branch = current_branch
        request.available_branches = available_branches

        response = self.get_response(request)
        return response
