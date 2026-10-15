import base64
import uuid
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import JsonResponse
from apps.properties.models import Property

@login_required
def property_list_view(request):
    business = getattr(request, 'current_business', None)
    if not business:
        messages.error(request, "No tienes un negocio activo seleccionado.")
        return redirect('dashboard')

    properties_qs = Property.objects.filter(business=business).select_related('agent', 'owner_client')

    # Metrics
    total_count = properties_qs.count()
    for_sale_count = properties_qs.filter(operation_type='SALE').count()
    for_rent_count = properties_qs.filter(operation_type__in=['RENT', 'TEMPORARY_RENT']).count()
    featured_count = properties_qs.filter(is_featured=True).count()

    # Search & Filters
    search_query = request.GET.get('q', '').strip()
    operation_filter = request.GET.get('operation', 'all')
    type_filter = request.GET.get('type', 'all')
    status_filter = request.GET.get('status', 'all')
    agent_filter = request.GET.get('agent', 'all')

    if search_query:
        properties_qs = properties_qs.filter(
            Q(title__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(zone__icontains=search_query) |
            Q(reference_code__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(owner_client__first_name__icontains=search_query) |
            Q(owner_client__last_name__icontains=search_query) |
            Q(agent__first_name__icontains=search_query) |
            Q(agent__last_name__icontains=search_query)
        )

    if operation_filter and operation_filter != 'all':
        properties_qs = properties_qs.filter(operation_type=operation_filter)

    if type_filter and type_filter != 'all':
        properties_qs = properties_qs.filter(property_type=type_filter)

    if status_filter and status_filter != 'all':
        properties_qs = properties_qs.filter(status=status_filter)

    if agent_filter and agent_filter != 'all':
        properties_qs = properties_qs.filter(agent_id=agent_filter)

    staff_members = business.staff_members.filter(is_active=True).order_by('first_name', 'last_name')

    return render(request, 'properties/property_list.html', {
        'properties': properties_qs,
        'total_count': total_count,
        'for_sale_count': for_sale_count,
        'for_rent_count': for_rent_count,
        'featured_count': featured_count,
        'search_query': search_query,
        'operation_filter': operation_filter,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'agent_filter': agent_filter,
        'staff_members': staff_members,
        'property_types': Property.PROPERTY_TYPE_CHOICES,
        'operation_types': Property.OPERATION_TYPE_CHOICES,
        'status_choices': Property.STATUS_CHOICES,
    })

@login_required
def property_create_view(request):
    business = getattr(request, 'current_business', None)
    if not business:
        messages.error(request, "No tienes un negocio activo seleccionado.")
        return redirect('dashboard')

    staff_members = business.staff_members.filter(is_active=True).order_by('first_name', 'last_name')
    clients = business.clients.all().order_by('first_name', 'last_name')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        reference_code = request.POST.get('reference_code', '').strip() or None
        property_type = request.POST.get('property_type', 'APARTMENT')
        operation_type = request.POST.get('operation_type', 'SALE')
        price_raw = request.POST.get('price', '0').strip().replace(',', '.')
        currency = request.POST.get('currency', 'USD')
        expenses_raw = request.POST.get('expenses', '0').strip().replace(',', '.')
        address = request.POST.get('address', '').strip()
        zone = request.POST.get('zone', '').strip()
        description = request.POST.get('description', '').strip()

        # Internal Real Estate Control: Agent & Owner Client
        agent_id = request.POST.get('agent_id')
        agent = business.staff_members.filter(id=agent_id).first() if agent_id else None

        owner_client_id = request.POST.get('owner_client_id')
        owner_client = business.clients.filter(id=owner_client_id).first() if owner_client_id else None
        
        try:
            bedrooms = max(0, int(request.POST.get('bedrooms', 1)))
        except (ValueError, TypeError):
            bedrooms = 1

        try:
            bathrooms = max(0, int(request.POST.get('bathrooms', 1)))
        except (ValueError, TypeError):
            bathrooms = 1

        try:
            garages = max(0, int(request.POST.get('garages', 0)))
        except (ValueError, TypeError):
            garages = 0

        try:
            total_surface = Decimal(request.POST.get('total_surface', '0').strip().replace(',', '.') or '0')
        except (InvalidOperation, TypeError):
            total_surface = Decimal('0')

        try:
            covered_surface = Decimal(request.POST.get('covered_surface', '0').strip().replace(',', '.') or '0')
        except (InvalidOperation, TypeError):
            covered_surface = Decimal('0')

        try:
            price = Decimal(price_raw)
        except (InvalidOperation, TypeError):
            price = Decimal('0')

        try:
            expenses = Decimal(expenses_raw) if expenses_raw else Decimal('0')
        except (InvalidOperation, TypeError):
            expenses = Decimal('0')

        portal_url = request.POST.get('portal_url', '').strip() or None
        portal_name = request.POST.get('portal_name', '').strip() or None
        status = request.POST.get('status', 'AVAILABLE')
        is_featured = (request.POST.get('is_featured') == 'on' or request.POST.get('is_featured') == 'true')

        if not title:
            messages.error(request, "El título de la propiedad es obligatorio.")
            return render(request, 'properties/property_form.html', {
                'property_types': Property.PROPERTY_TYPE_CHOICES,
                'operation_types': Property.OPERATION_TYPE_CHOICES,
                'status_choices': Property.STATUS_CHOICES,
                'currency_choices': Property.CURRENCY_CHOICES,
                'staff_members': staff_members,
                'clients': clients,
                'is_edit': False,
            })

        prop = Property(
            business=business,
            title=title,
            reference_code=reference_code,
            property_type=property_type,
            operation_type=operation_type,
            price=price,
            currency=currency,
            expenses=expenses,
            address=address,
            zone=zone,
            description=description,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            garages=garages,
            total_surface=total_surface,
            covered_surface=covered_surface,
            portal_url=portal_url,
            portal_name=portal_name,
            status=status,
            is_featured=is_featured,
            agent=agent,
            owner_client=owner_client,
        )

        # Handle up to 3 photos (cropped Base64 or standard file upload)
        for idx in [1, 2, 3]:
            field_name = f'photo_{idx}'
            cropped_b64 = request.POST.get(f'cropped_photo_{idx}_base64')
            if cropped_b64 and ';base64,' in cropped_b64:
                try:
                    format_meta, imgstr = cropped_b64.split(';base64,')
                    ext = format_meta.split('/')[-1] if '/' in format_meta else 'jpg'
                    if ext == 'jpeg':
                        ext = 'jpg'
                    data = base64.b64decode(imgstr)
                    file_name = f"prop_{uuid.uuid4().hex[:8]}_p{idx}.{ext}"
                    setattr(prop, field_name, ContentFile(data, name=file_name))
                except Exception as e:
                    print(f"Error decoding cropped photo {idx}: {e}")
            elif field_name in request.FILES:
                setattr(prop, field_name, request.FILES[field_name])

        prop.save()
        messages.success(request, f"¡Propiedad '{prop.title}' publicada con éxito!")
        return redirect('property_list')

    return render(request, 'properties/property_form.html', {
        'property_types': Property.PROPERTY_TYPE_CHOICES,
        'operation_types': Property.OPERATION_TYPE_CHOICES,
        'status_choices': Property.STATUS_CHOICES,
        'currency_choices': Property.CURRENCY_CHOICES,
        'staff_members': staff_members,
        'clients': clients,
        'is_edit': False,
    })

@login_required
def property_edit_view(request, property_id):
    business = getattr(request, 'current_business', None)
    prop = get_object_or_404(
        Property.objects.select_related('agent', 'owner_client'),
        id=property_id,
        business=business
    )
    staff_members = business.staff_members.filter(is_active=True).order_by('first_name', 'last_name')
    clients = business.clients.all().order_by('first_name', 'last_name')

    if request.method == 'POST':
        prop.title = request.POST.get('title', prop.title).strip()
        prop.reference_code = request.POST.get('reference_code', '').strip() or None
        prop.property_type = request.POST.get('property_type', prop.property_type)
        prop.operation_type = request.POST.get('operation_type', prop.operation_type)
        
        price_raw = request.POST.get('price', str(prop.price)).strip().replace(',', '.')
        try:
            prop.price = Decimal(price_raw)
        except (InvalidOperation, TypeError):
            pass

        prop.currency = request.POST.get('currency', prop.currency)
        
        expenses_raw = request.POST.get('expenses', str(prop.expenses or 0)).strip().replace(',', '.')
        try:
            prop.expenses = Decimal(expenses_raw) if expenses_raw else Decimal('0')
        except (InvalidOperation, TypeError):
            prop.expenses = Decimal('0')

        prop.address = request.POST.get('address', prop.address).strip()
        prop.zone = request.POST.get('zone', prop.zone).strip()
        prop.description = request.POST.get('description', prop.description).strip()

        # Internal Real Estate Control: Agent & Owner Client
        agent_id = request.POST.get('agent_id')
        prop.agent = business.staff_members.filter(id=agent_id).first() if agent_id else None

        owner_client_id = request.POST.get('owner_client_id')
        prop.owner_client = business.clients.filter(id=owner_client_id).first() if owner_client_id else None

        try:
            prop.bedrooms = max(0, int(request.POST.get('bedrooms', prop.bedrooms)))
        except (ValueError, TypeError):
            pass

        try:
            prop.bathrooms = max(0, int(request.POST.get('bathrooms', prop.bathrooms)))
        except (ValueError, TypeError):
            pass

        try:
            prop.garages = max(0, int(request.POST.get('garages', prop.garages)))
        except (ValueError, TypeError):
            pass

        try:
            prop.total_surface = Decimal(request.POST.get('total_surface', str(prop.total_surface)).strip().replace(',', '.') or '0')
        except (InvalidOperation, TypeError):
            pass

        try:
            prop.covered_surface = Decimal(request.POST.get('covered_surface', str(prop.covered_surface)).strip().replace(',', '.') or '0')
        except (InvalidOperation, TypeError):
            pass

        prop.portal_url = request.POST.get('portal_url', '').strip() or None
        prop.portal_name = request.POST.get('portal_name', '').strip() or None
        prop.status = request.POST.get('status', prop.status)
        prop.is_featured = (request.POST.get('is_featured') == 'on' or request.POST.get('is_featured') == 'true')

        # Replace photos if cropped Base64 uploaded, new files uploaded, or cleared
        for idx in [1, 2, 3]:
            field_name = f'photo_{idx}'
            cropped_b64 = request.POST.get(f'cropped_photo_{idx}_base64')
            if cropped_b64 and ';base64,' in cropped_b64:
                try:
                    format_meta, imgstr = cropped_b64.split(';base64,')
                    ext = format_meta.split('/')[-1] if '/' in format_meta else 'jpg'
                    if ext == 'jpeg':
                        ext = 'jpg'
                    data = base64.b64decode(imgstr)
                    file_name = f"prop_{uuid.uuid4().hex[:8]}_p{idx}.{ext}"
                    setattr(prop, field_name, ContentFile(data, name=file_name))
                except Exception as e:
                    print(f"Error decoding cropped photo {idx}: {e}")
            elif field_name in request.FILES:
                setattr(prop, field_name, request.FILES[field_name])
            elif request.POST.get(f'clear_photo_{idx}') == 'true':
                setattr(prop, field_name, None)

        prop.save()
        messages.success(request, f"Propiedad '{prop.title}' actualizada correctamente.")
        return redirect('property_list')

    return render(request, 'properties/property_form.html', {
        'property': prop,
        'property_types': Property.PROPERTY_TYPE_CHOICES,
        'operation_types': Property.OPERATION_TYPE_CHOICES,
        'status_choices': Property.STATUS_CHOICES,
        'currency_choices': Property.CURRENCY_CHOICES,
        'staff_members': staff_members,
        'clients': clients,
        'is_edit': True,
    })

@login_required
def property_detail_view(request, property_id):
    business = getattr(request, 'current_business', None)
    prop = get_object_or_404(
        Property.objects.select_related('agent', 'owner_client'),
        id=property_id,
        business=business
    )
    return render(request, 'properties/property_detail.html', {
        'property': prop,
    })

@login_required
def property_delete_view(request, property_id):
    business = getattr(request, 'current_business', None)
    prop = get_object_or_404(Property, id=property_id, business=business)
    
    if request.method == 'POST':
        title = prop.title
        prop.delete()
        messages.success(request, f"La propiedad '{title}' fue eliminada.")
        return redirect('property_list')

    return render(request, 'properties/property_confirm_delete.html', {
        'property': prop,
    })

@login_required
def property_toggle_status_view(request, property_id):
    business = getattr(request, 'current_business', None)
    prop = get_object_or_404(Property, id=property_id, business=business)
    
    new_status = request.POST.get('status') or request.GET.get('status')
    if new_status in dict(Property.STATUS_CHOICES):
        prop.status = new_status
        prop.save()
        messages.success(request, f"Estado de '{prop.title}' actualizado a {prop.get_status_display()}.")
    
    return redirect(request.META.get('HTTP_REFERER') or 'property_list')
