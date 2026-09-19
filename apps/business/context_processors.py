from apps.business.models import Business

def business_context(request):
    """Proporciona el negocio activo y la configuración de módulos a todas las plantillas HTML."""
    business = None
    if request.user.is_authenticated and hasattr(request.user, 'business') and request.user.business:
        business = request.user.business
    else:
        business = Business.objects.first()

    all_module_keys = ['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing']
    modules_enabled = {}
    
    if business:
        enabled_list = business.enabled_modules or all_module_keys
        for key in all_module_keys:
            modules_enabled[key] = (key in enabled_list) if enabled_list else True
    else:
        for key in all_module_keys:
            modules_enabled[key] = True

    return {
        'current_business': business,
        'modules_enabled': modules_enabled,
        'business_type_display': business.get_business_type_display() if business else 'Agencia'
    }
