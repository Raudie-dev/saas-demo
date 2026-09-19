from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.business.views import landing_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', landing_view, name='landing'),
    path('dashboard/', include('apps.analytics.urls')),
    path('business/', include('apps.business.urls')),
    path('crm/', include('apps.crm.urls')),
    path('agenda/', include('apps.agenda.urls')),
    path('reservas/', include('apps.booking.urls')),
    path('pos/', include('apps.pos.urls')),
    path('facturacion/', include('apps.invoicing.urls')),
    path('inventario/', include('apps.inventory.urls')),
    path('comisiones/', include('apps.commissions.urls')),
    path('ia/', include('apps.ai_engine.urls')),
    path('marketing/', include('apps.marketing.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
