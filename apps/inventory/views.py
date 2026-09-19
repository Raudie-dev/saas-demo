from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from apps.business.models import Business
from apps.inventory.models import Product, ProductCategory, StockMovement
from apps.crm.models import Supplier
from apps.core.utils import parse_decimal, parse_int

def inventory_list_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    products = Product.objects.filter(business=business) if business else []
    categories = ProductCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'adjust_stock':
            product_id = request.POST.get('product_id')
            new_qty = parse_int(request.POST.get('new_stock'), 0)
            prod = get_object_or_404(Product, id=product_id, business=business)
            
            old_s = prod.stock
            prod.stock = new_qty
            prod.save()
            
            StockMovement.objects.create(
                product=prod,
                movement_type='ADJUSTMENT',
                quantity=new_qty - old_s,
                previous_stock=old_s,
                new_stock=new_qty,
                notes="Ajuste manual de inventario"
            )
        return redirect('inventory_list')

    return render(request, 'inventory/inventory_list.html', {
        'business': business,
        'products': products,
        'categories': categories,
        'suppliers': suppliers,
    })

def product_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    categories = ProductCategory.objects.filter(business=business) if business else []
    suppliers = Supplier.objects.filter(business=business) if business else []
    
    if request.method == 'POST':
        name = request.POST.get('name')
        sku = request.POST.get('sku')
        cost_price = parse_decimal(request.POST.get('cost_price'), '0.00')
        sale_price = parse_decimal(request.POST.get('sale_price'), '0.00')
        stock = parse_int(request.POST.get('stock'), 0)
        min_stock = parse_int(request.POST.get('min_stock'), 5)
        unit = request.POST.get('unit', 'Unidad')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        
        category = ProductCategory.objects.filter(id=category_id).first() if category_id else None
        supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        
        Product.objects.create(
            business=business,
            name=name,
            sku=sku,
            cost_price=cost_price,
            sale_price=sale_price,
            stock=stock,
            min_stock=min_stock,
            unit=unit,
            category=category,
            supplier=supplier,
            is_active=True
        )
        return redirect('inventory_list')

    return render(request, 'inventory/product_form.html', {
        'business': business,
        'product': None,
        'categories': categories,
        'suppliers': suppliers,
        'title': 'Crear Nuevo Producto en Inventario'
    })

def product_edit_view(request, product_id):
    business = getattr(request, 'current_business', None) or Business.objects.first()
    product = get_object_or_404(Product, id=product_id, business=business)
    categories = ProductCategory.objects.filter(business=business)
    suppliers = Supplier.objects.filter(business=business)

    if request.method == 'POST':
        product.name = request.POST.get('name')
        product.sku = request.POST.get('sku')
        product.cost_price = parse_decimal(request.POST.get('cost_price'), '0.00')
        product.sale_price = parse_decimal(request.POST.get('sale_price'), '0.00')
        product.stock = parse_int(request.POST.get('stock'), 0)
        product.min_stock = parse_int(request.POST.get('min_stock'), 5)
        product.unit = request.POST.get('unit', 'Unidad')
        category_id = request.POST.get('category_id')
        supplier_id = request.POST.get('supplier_id')
        
        product.category = ProductCategory.objects.filter(id=category_id).first() if category_id else None
        product.supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None
        product.save()
        return redirect('inventory_list')

    return render(request, 'inventory/product_form.html', {
        'business': business,
        'product': product,
        'categories': categories,
        'suppliers': suppliers,
        'title': f'Editar Producto: {product.name}'
    })

def product_category_create_view(request):
    business = getattr(request, 'current_business', None) or Business.objects.first()

    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            ProductCategory.objects.create(
                business=business,
                name=name
            )
        return redirect('inventory_list')

    return render(request, 'inventory/product_category_form.html', {
        'business': business,
        'title': 'Crear Nueva Categoría de Producto'
    })
