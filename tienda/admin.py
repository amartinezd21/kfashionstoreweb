from django.contrib import admin
from . import models

for m in (models.Perfil, models.Categoria, models.Proveedor, models.Prenda, models.Variante,
          models.EntradaMercancia, models.Cliente, models.Venta, models.DetalleVenta,
          models.Abono, models.Gasto):
    admin.site.register(m)
