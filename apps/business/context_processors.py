from apps.business.models import Business

def business_context(request):
    """Proporciona el negocio activo, configuración de módulos y permisos de usuario a todas las plantillas HTML."""
    business = getattr(request, 'current_business', None)
    if not business and hasattr(request, 'user') and request.user.is_authenticated and getattr(request.user, 'business', None):
        business = request.user.business

    all_module_keys = ['crm', 'agenda', 'booking', 'invoicing', 'pos', 'inventory', 'commissions', 'ai_engine', 'marketing', 'projects']
    modules_enabled = {}
    
    user = getattr(request, 'user', None)
    is_auth = user and user.is_authenticated

    if business:
        for key in all_module_keys:
            biz_allowed = business.is_module_enabled(key)
            if not biz_allowed:
                modules_enabled[key] = False
            elif is_auth and hasattr(user, 'has_module_access'):
                modules_enabled[key] = user.has_module_access(key)
            else:
                modules_enabled[key] = True
    else:
        for key in all_module_keys:
            modules_enabled[key] = True

    # User permissions flags
    can_charge_pos = is_auth and getattr(user, 'has_perm_flag', lambda f: True)('can_charge_pos')
    can_view_financial_reports = is_auth and getattr(user, 'has_perm_flag', lambda f: True)('can_view_financial_reports')
    can_manage_settings = is_auth and getattr(user, 'has_perm_flag', lambda f: True)('can_manage_settings')
    can_manage_clients = is_auth and getattr(user, 'has_perm_flag', lambda f: True)('can_manage_clients')
    is_professional = is_auth and getattr(user, 'is_restricted_professional', False)

    return {
        'current_business': business,
        'modules_enabled': modules_enabled,
        'business_type_display': business.get_business_type_display() if business else 'Agencia',
        'is_real_estate': business.is_real_estate if business else False,
        'is_marketing_agency': business.is_marketing_agency if business else False,
        'is_health_beauty': business.is_health_beauty if business else False,
        'is_consulting': business.is_consulting if business else False,
        'is_travel': business.is_travel if business else False,
        'is_retail': business.is_retail if business else False,
        'business_entity_label': business.business_entity_label if business else 'la Empresa',
        'client_label_singular': business.client_label_singular if business else 'Cliente',
        'client_label_plural': business.client_label_plural if business else 'Clientes',
        'user_can_charge_pos': can_charge_pos,
        'user_can_view_financial_reports': can_view_financial_reports,
        'user_can_manage_settings': can_manage_settings,
        'user_can_manage_clients': can_manage_clients,
        'user_is_professional': is_professional,
        'user_appointment_scope': getattr(user, 'appointment_scope', 'ALL') if is_auth else 'ALL',
        'user_commission_scope': getattr(user, 'commission_scope', 'ALL') if is_auth else 'ALL',
    }

