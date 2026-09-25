from django.db import models
from apps.core.models import TimeStampedModel
from apps.business.models import Business, Branch
from apps.crm.models import Supplier

class ProductCategory(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="product_categories")
    name = models.CharField(max_length=100, verbose_name="Nombre de Categoría")

    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Productos"

    def __str__(self):
        return self.name

class Product(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="products")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="products", verbose_name="Sucursal")
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="supplied_products")
    name = models.CharField(max_length=150, verbose_name="Nombre del Producto")
    sku = models.CharField(max_length=50, verbose_name="SKU / Código de Barras")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Precio de Costo / Compra")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de Venta")
    stock = models.IntegerField(default=0, verbose_name="Stock Actual")
    min_stock = models.IntegerField(default=5, verbose_name="Stock Mínimo (Alerta)")
    unit = models.CharField(max_length=30, default="Unidad", verbose_name="Unidad de Medida")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    @property
    def is_low_stock(self):
        return self.stock <= self.min_stock

    def __str__(self):
        return f"{self.name} (SKU: {self.sku}) - Stock: {self.stock}"

class StockMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ('SALE', 'Venta POS'),
        ('PURCHASE', 'Ingreso de Compra'),
        ('ADJUSTMENT', 'Ajuste de Inventario'),
        ('RETURN', 'Devolución de Cliente'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    quantity = models.IntegerField()
    previous_stock = models.IntegerField()
    new_stock = models.IntegerField()
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.product.name}: {self.movement_type} ({self.quantity}) -> Nuevo Stock: {self.new_stock}"
