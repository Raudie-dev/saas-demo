from django.utils import timezone
from apps.superadmin.models import SystemAnnouncement, AnnouncementDismissal

def announcement_context(request):
    """
    Inyecta el anuncio/modal más importante (activo) en el contexto
    siempre y cuando aplique al usuario actual y no lo haya cerrado.
    """
    if not request.user.is_authenticated or getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
        return {}

    user = request.user
    business = getattr(user, 'business', None)

    if not business:
        return {}

    # Get active announcements ordered by priority/creation
    announcements = SystemAnnouncement.objects.filter(is_active=True).order_by('-created_at')

    # Get dismissed IDs for this user
    dismissed_ids = set(AnnouncementDismissal.objects.filter(user=user).values_list('announcement_id', flat=True))

    for ann in announcements:
        if ann.id in dismissed_ids:
            continue

        # Check filters
        if ann.target_regions.exists():
            if not business.region or not ann.target_regions.filter(id=business.region.id).exists():
                continue
            
        if ann.target_missing_region and business.region is not None:
            continue

        # If it passes all filters, we found the active announcement
        return {
            'active_announcement': ann
        }

    return {}
