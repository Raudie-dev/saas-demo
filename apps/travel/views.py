import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.business.models import StaffMember
from apps.crm.models import Client
from .models import TravelPackage, TravelBooking

@login_required(login_url='login')
def package_list_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    packages_qs = TravelPackage.objects.filter(business=business)

    # Search & Filters
    search_query = request.GET.get('q', '').strip()
    travel_type = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        packages_qs = packages_qs.filter(
            Q(title__icontains=search_query) |
            Q(destination__icontains=search_query) |
            Q(code__icontains=search_query)
        )

    if travel_type:
        packages_qs = packages_qs.filter(travel_type=travel_type)

    if status_filter:
        packages_qs = packages_qs.filter(status=status_filter)

    paginator = Paginator(packages_qs, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    stats = {
        'total': packages_qs.count(),
        'available': packages_qs.filter(status='AVAILABLE').count(),
        'active_bookings': TravelBooking.objects.filter(business=business).exclude(status__in=['COMPLETED', 'CANCELLED']).count(),
    }

    return render(request, 'travel/package_list.html', {
        'business': business,
        'packages': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'selected_type': travel_type,
        'selected_status': status_filter,
        'travel_types': TravelPackage.TRAVEL_TYPE_CHOICES,
        'statuses': TravelPackage.STATUS_CHOICES,
        'stats': stats,
        'title': 'Catálogo de Paquetes & Viajes',
    })

@login_required(login_url='login')
def package_create_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        destination = request.POST.get('destination', '').strip()
        travel_type = request.POST.get('travel_type', 'PACKAGE')
        duration_days = int(request.POST.get('duration_days') or 5)
        duration_nights = int(request.POST.get('duration_nights') or 4)
        price_per_person = Decimal(request.POST.get('price_per_person') or '0.00')
        currency = request.POST.get('currency', business.currency or 'USD')
        available_slots = int(request.POST.get('available_slots') or 10)
        status = request.POST.get('status', 'AVAILABLE')
        hotel_name = request.POST.get('hotel_name', '').strip()
        airline = request.POST.get('airline', '').strip()
        includes = request.POST.get('includes', '').strip()
        excludes = request.POST.get('excludes', '').strip()
        itinerary = request.POST.get('itinerary', '').strip()
        notes = request.POST.get('notes', '').strip()
        start_date = request.POST.get('start_date') or None
        end_date = request.POST.get('end_date') or None
        is_featured = request.POST.get('is_featured') == '1'

        package = TravelPackage.objects.create(
            business=business,
            title=title,
            destination=destination,
            travel_type=travel_type,
            duration_days=duration_days,
            duration_nights=duration_nights,
            price_per_person=price_per_person,
            currency=currency,
            available_slots=available_slots,
            status=status,
            hotel_name=hotel_name,
            airline=airline,
            includes=includes,
            excludes=excludes,
            itinerary=itinerary,
            notes=notes,
            start_date=start_date,
            end_date=end_date,
            is_featured=is_featured,
        )

        if 'image' in request.FILES:
            package.image = request.FILES['image']
            package.save()

        messages.success(request, f"¡Paquete de viaje '{package.title}' creado exitosamente!")
        return redirect('travel_package_detail', package_id=package.id)

    return render(request, 'travel/package_form.html', {
        'business': business,
        'package': None,
        'travel_types': TravelPackage.TRAVEL_TYPE_CHOICES,
        'statuses': TravelPackage.STATUS_CHOICES,
        'currencies': TravelPackage.CURRENCY_CHOICES,
        'title': 'Crear Nuevo Paquete de Viaje',
    })

@login_required(login_url='login')
def package_detail_view(request, package_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    package = get_object_or_404(TravelPackage, id=package_id, business=business)
    bookings = package.bookings.select_related('client', 'agent').order_by('-departure_date')

    # WhatsApp Share message
    wa_text = f"¡Hola! Te comparto información de nuestro viaje: *{package.title}* ({package.destination}). " \
              f"Duración: {package.duration_display}. Precio: {package.currency}{package.price_per_person:,.2f} por persona. " \
              f"¿Te gustaría recibir el itinerario completo o cotizar fechas?"
    wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"

    return render(request, 'travel/package_detail.html', {
        'business': business,
        'package': package,
        'bookings': bookings,
        'whatsapp_url': wa_url,
        'title': f"{package.title} - {package.destination}",
    })

@login_required(login_url='login')
def package_edit_view(request, package_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    package = get_object_or_404(TravelPackage, id=package_id, business=business)

    if request.method == 'POST':
        package.title = request.POST.get('title', '').strip()
        package.destination = request.POST.get('destination', '').strip()
        package.travel_type = request.POST.get('travel_type', 'PACKAGE')
        package.duration_days = int(request.POST.get('duration_days') or 5)
        package.duration_nights = int(request.POST.get('duration_nights') or 4)
        package.price_per_person = Decimal(request.POST.get('price_per_person') or '0.00')
        package.currency = request.POST.get('currency', business.currency or 'USD')
        package.available_slots = int(request.POST.get('available_slots') or 10)
        package.status = request.POST.get('status', 'AVAILABLE')
        package.hotel_name = request.POST.get('hotel_name', '').strip()
        package.airline = request.POST.get('airline', '').strip()
        package.includes = request.POST.get('includes', '').strip()
        package.excludes = request.POST.get('excludes', '').strip()
        package.itinerary = request.POST.get('itinerary', '').strip()
        package.notes = request.POST.get('notes', '').strip()
        package.start_date = request.POST.get('start_date') or None
        package.end_date = request.POST.get('end_date') or None
        package.is_featured = request.POST.get('is_featured') == '1'

        if 'image' in request.FILES:
            package.image = request.FILES['image']

        package.save()
        messages.success(request, f"Paquete '{package.title}' actualizado correctamente.")
        return redirect('travel_package_detail', package_id=package.id)

    return render(request, 'travel/package_form.html', {
        'business': business,
        'package': package,
        'travel_types': TravelPackage.TRAVEL_TYPE_CHOICES,
        'statuses': TravelPackage.STATUS_CHOICES,
        'currencies': TravelPackage.CURRENCY_CHOICES,
        'title': f"Editar Paquete: {package.title}",
    })

@login_required(login_url='login')
def package_delete_view(request, package_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    package = get_object_or_404(TravelPackage, id=package_id, business=business)
    if request.method == 'POST':
        name = package.title
        package.delete()
        messages.success(request, f"Paquete de viaje '{name}' eliminado.")
    return redirect('travel_package_list')


# ==============================================================================
# TRAVEL BOOKINGS / EXPEDIENTES DE PASAJEROS
# ==============================================================================

@login_required(login_url='login')
def booking_list_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    bookings_qs = TravelBooking.objects.filter(business=business).select_related('client', 'package', 'agent')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if search_query:
        bookings_qs = bookings_qs.filter(
            Q(booking_number__icontains=search_query) |
            Q(pnr_locator__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query) |
            Q(package__title__icontains=search_query)
        )

    if status_filter:
        bookings_qs = bookings_qs.filter(status=status_filter)

    paginator = Paginator(bookings_qs, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'travel/booking_list.html', {
        'business': business,
        'bookings': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'selected_status': status_filter,
        'statuses': TravelBooking.STATUS_CHOICES,
        'title': 'Reservas de Viajes & Expedientes',
    })

@login_required(login_url='login')
def booking_create_view(request):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    packages = TravelPackage.objects.filter(business=business, is_active=True).order_by('title')
    agents = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    # Preset package if requested
    package_id = request.GET.get('package_id')
    selected_package = packages.filter(id=package_id).first() if package_id else None

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        pkg_id = request.POST.get('package_id')
        agent_id = request.POST.get('agent_id')
        departure_date = request.POST.get('departure_date')
        return_date = request.POST.get('return_date') or None
        num_adults = int(request.POST.get('num_adults') or 1)
        num_children = int(request.POST.get('num_children') or 0)
        total_amount = Decimal(request.POST.get('total_amount') or '0.00')
        deposit_amount = Decimal(request.POST.get('deposit_amount') or '0.00')
        currency = request.POST.get('currency', business.currency or 'USD')
        status = request.POST.get('status', 'CONFIRMED')
        pnr_locator = request.POST.get('pnr_locator', '').strip().upper()
        airline_flight_details = request.POST.get('airline_flight_details', '').strip()
        hotel_confirmation = request.POST.get('hotel_confirmation', '').strip()
        passengers_info = request.POST.get('passengers_info', '').strip()
        special_requests = request.POST.get('special_requests', '').strip()
        notes = request.POST.get('notes', '').strip()

        client = get_object_or_404(Client, id=client_id, business=business)
        package = TravelPackage.objects.filter(id=pkg_id, business=business).first() if pkg_id else None
        agent = StaffMember.objects.filter(id=agent_id, business=business).first() if agent_id else None

        # Generate unique booking reference number
        count = TravelBooking.objects.filter(business=business).count() + 1
        booking_number = f"EXP-{timezone.now().year}-{count:04d}"

        booking = TravelBooking.objects.create(
            business=business,
            booking_number=booking_number,
            client=client,
            package=package,
            agent=agent,
            departure_date=departure_date,
            return_date=return_date,
            num_adults=num_adults,
            num_children=num_children,
            total_amount=total_amount,
            deposit_amount=deposit_amount,
            currency=currency,
            status=status,
            pnr_locator=pnr_locator,
            airline_flight_details=airline_flight_details,
            hotel_confirmation=hotel_confirmation,
            passengers_info=passengers_info,
            special_requests=special_requests,
            notes=notes,
        )

        messages.success(request, f"¡Reserva #{booking.booking_number} para {client.full_name} registrada con éxito!")
        return redirect('travel_booking_detail', booking_id=booking.id)

    return render(request, 'travel/booking_form.html', {
        'business': business,
        'booking': None,
        'clients': clients,
        'packages': packages,
        'agents': agents,
        'selected_package': selected_package,
        'statuses': TravelBooking.STATUS_CHOICES,
        'title': 'Nueva Reserva de Viaje',
    })

@login_required(login_url='login')
def booking_detail_view(request, booking_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    booking = get_object_or_404(TravelBooking, id=booking_id, business=business)

    # WhatsApp notification message
    wa_text = f"¡Hola {booking.client.first_name}! Te confirmamos tu expediente de viaje *#{booking.booking_number}* " \
              f"con destino a *{booking.package.destination if booking.package else 'tu destino reservado'}* " \
              f"para el día *{booking.departure_date.strftime('%d/%m/%Y')}*. " \
              f"{'Localizador PNR: *' + booking.pnr_locator + '*. ' if booking.pnr_locator else ''}" \
              f"Saldo pendiente: {booking.currency}{booking.balance_due:,.2f}. " \
              f"¡Cualquier consulta estamos a tu disposición!"
    wa_url = f"https://wa.me/{booking.client.phone.replace('+', '').replace(' ', '')}?text={urllib.parse.quote(wa_text)}" if booking.client.phone else None

    return render(request, 'travel/booking_detail.html', {
        'business': business,
        'booking': booking,
        'whatsapp_url': wa_url,
        'title': f"Reserva #{booking.booking_number} - {booking.client.full_name}",
    })

@login_required(login_url='login')
def booking_edit_view(request, booking_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    booking = get_object_or_404(TravelBooking, id=booking_id, business=business)
    clients = Client.objects.filter(business=business).order_by('first_name', 'last_name')
    packages = TravelPackage.objects.filter(business=business, is_active=True).order_by('title')
    agents = StaffMember.objects.filter(business=business, is_active=True).order_by('first_name')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        pkg_id = request.POST.get('package_id')
        agent_id = request.POST.get('agent_id')
        booking.departure_date = request.POST.get('departure_date')
        booking.return_date = request.POST.get('return_date') or None
        booking.num_adults = int(request.POST.get('num_adults') or 1)
        booking.num_children = int(request.POST.get('num_children') or 0)
        booking.total_amount = Decimal(request.POST.get('total_amount') or '0.00')
        booking.deposit_amount = Decimal(request.POST.get('deposit_amount') or '0.00')
        booking.currency = request.POST.get('currency', business.currency or 'USD')
        booking.status = request.POST.get('status', 'CONFIRMED')
        booking.pnr_locator = request.POST.get('pnr_locator', '').strip().upper()
        booking.airline_flight_details = request.POST.get('airline_flight_details', '').strip()
        booking.hotel_confirmation = request.POST.get('hotel_confirmation', '').strip()
        booking.passengers_info = request.POST.get('passengers_info', '').strip()
        booking.special_requests = request.POST.get('special_requests', '').strip()
        booking.notes = request.POST.get('notes', '').strip()

        if client_id:
            booking.client = get_object_or_404(Client, id=client_id, business=business)
        if pkg_id:
            booking.package = TravelPackage.objects.filter(id=pkg_id, business=business).first()
        else:
            booking.package = None
        if agent_id:
            booking.agent = StaffMember.objects.filter(id=agent_id, business=business).first()
        else:
            booking.agent = None

        booking.save()
        messages.success(request, f"Reserva #{booking.booking_number} actualizada.")
        return redirect('travel_booking_detail', booking_id=booking.id)

    return render(request, 'travel/booking_form.html', {
        'business': business,
        'booking': booking,
        'clients': clients,
        'packages': packages,
        'agents': agents,
        'selected_package': booking.package,
        'statuses': TravelBooking.STATUS_CHOICES,
        'title': f"Editar Reserva #{booking.booking_number}",
    })

@login_required(login_url='login')
def booking_status_update_view(request, booking_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    booking = get_object_or_404(TravelBooking, id=booking_id, business=business)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(TravelBooking.STATUS_CHOICES):
            booking.status = new_status
            booking.save()
            messages.success(request, f"Estado de la reserva #{booking.booking_number} actualizado a '{booking.get_status_display()}'.")
    return redirect('travel_booking_detail', booking_id=booking.id)

@login_required(login_url='login')
def booking_voucher_view(request, booking_id):
    business = getattr(request, 'current_business', None) or getattr(request.user, 'business', None)
    if not business:
        return redirect('onboarding')

    booking = get_object_or_404(TravelBooking, id=booking_id, business=business)
    return render(request, 'travel/voucher.html', {
        'business': business,
        'booking': booking,
        'title': f"Voucher de Viaje #{booking.booking_number}",
    })
