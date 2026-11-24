from django.contrib.auth import views as auth
from django.urls import path

from . import views as v

urlpatterns = [
    path("login/", auth.LoginView.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("cambiar-clave/", v.CambiarClave.as_view(), name="cambiar_clave"),
    path("usuarios/", v.usuarios, name="usuarios"),
    path("usuarios/<int:pk>/eliminar/", v.usuario_eliminar, name="usuario_eliminar"),
    path("", v.dashboard, name="dashboard"),

    path("inventario/", v.inventario, name="inventario"),
    path("inventario/exportar/", v.inventario_exportar, name="inventario_exportar"),
    path("inventario/prenda/nueva/", v.prenda_nueva, name="prenda_nueva"),
    path("inventario/prenda/<int:pk>/", v.prenda_editar, name="prenda_editar"),
    path("inventario/variante/nueva/", v.variante_nueva, name="variante_nueva"),
    path("inventario/variante/<int:pk>/", v.variante_editar, name="variante_editar"),
    path("inventario/prenda/<int:pk>/eliminar/", v.prenda_eliminar, name="prenda_eliminar"),
    path("inventario/variante/<int:pk>/eliminar/", v.variante_eliminar, name="variante_eliminar"),
    path("inventario/categorias/", v.categorias, name="categorias"),
    path("inventario/categoria/nueva/", v.categoria_nueva, name="categoria_nueva"),
    path("inventario/categoria/<int:pk>/", v.categoria_editar, name="categoria_editar"),
    path("inventario/categoria/<int:pk>/eliminar/", v.categoria_eliminar, name="categoria_eliminar"),
    path("inventario/entrada/", v.entrada_nueva, name="entrada_nueva"),
    path("inventario/entrada/<int:pk>/eliminar/", v.entrada_eliminar, name="entrada_eliminar"),
    path("inventario/reponer/", v.reponer, name="reponer"),
    path("inventario/mermas/", v.mermas, name="mermas"),
    path("inventario/mermas/nueva/", v.merma_nueva, name="merma_nueva"),
    path("inventario/mermas/exportar/", v.mermas_exportar, name="mermas_exportar"),

    path("clientas/", v.clientes, name="clientes"),
    path("clientas/nueva/", v.cliente_nuevo, name="cliente_nuevo"),
    path("clientas/<int:pk>/", v.cliente_detalle, name="cliente_detalle"),
    path("clientas/<int:pk>/editar/", v.cliente_editar, name="cliente_editar"),
    path("clientas/<int:pk>/eliminar/", v.cliente_eliminar, name="cliente_eliminar"),

    path("ventas/", v.ventas, name="ventas"),
    path("ventas/exportar/", v.ventas_exportar, name="ventas_exportar"),
    path("ventas/nueva/", v.venta_nueva, name="venta_nueva"),
    path("ventas/<int:pk>/recibo/", v.recibo, name="recibo"),
    path("ventas/<int:pk>/pdf/", v.recibo_pdf, name="recibo_pdf"),
    path("ventas/<int:pk>/cambio/", v.venta_cambio, name="venta_cambio"),
    path("ventas/<int:pk>/abono/", v.abono_nuevo, name="abono_nuevo"),
    path("ventas/<int:pk>/anular/", v.venta_anular, name="venta_anular"),
    path("abonos/<int:pk>/eliminar/", v.abono_eliminar, name="abono_eliminar"),
    path("caja/", v.caja_control, name="caja_control"),

    path("proveedores/", v.proveedores, name="proveedores"),
    path("proveedores/nuevo/", v.proveedor_nuevo, name="proveedor_nuevo"),
    path("proveedores/<int:pk>/", v.proveedor_editar, name="proveedor_editar"),
    path("proveedores/<int:pk>/eliminar/", v.proveedor_eliminar, name="proveedor_eliminar"),

    path("gastos/", v.gastos, name="gastos"),
    path("gastos/nuevo/", v.gasto_nuevo, name="gasto_nuevo"),
    path("gastos/<int:pk>/", v.gasto_editar, name="gasto_editar"),
    path("gastos/<int:pk>/eliminar/", v.gasto_eliminar, name="gasto_eliminar"),
    path("reporte/", v.reporte, name="reporte"),
    path("balance/", v.balance, name="balance"),
    path("balance/exportar/", v.balance_exportar, name="balance_exportar"),
]
