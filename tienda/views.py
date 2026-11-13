from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from secrets import compare_digest

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from . import forms
from .models import (CERO, Abono, Cliente, DetalleVenta, EntradaMercancia, Gasto, Prenda,
                     Proveedor, Variante, Venta, es_propietaria)


# ---------- utilidades ----------
def propietaria_required(view):
    """RNF-01: la vendedora no puede ver gastos, reportes ni balance."""
    @wraps(view)
    def envoltura(request, *args, **kwargs):
        if not es_propietaria(request.user):
            messages.error(request, "No tienes permiso para entrar a esa sección.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return login_required(envoltura)


def formulario(request, clase, titulo, volver, instancia=None, **kw):
    form = clase(request.POST or None, request.FILES or None, instance=instancia, **kw)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Guardado correctamente.")
        return redirect(volver)
    return render(request, "tienda/form.html", {"form": form, "titulo": titulo, "volver": volver})


def rango_fechas(request):
    hoy = timezone.localdate()
    try:
        desde = date.fromisoformat(request.GET.get("desde", ""))
    except ValueError:
        desde = hoy.replace(day=1)
    try:
        hasta = date.fromisoformat(request.GET.get("hasta", ""))
    except ValueError:
        hasta = hoy
    return desde, hasta


def resumen(desde, hasta):
    """Cifras del negocio entre dos fechas (RF-13 y RF-14)."""
    ventas = Venta.objects.filter(fecha__date__range=(desde, hasta))
    total_vendido = ventas.aggregate(t=Sum("total"))["t"] or CERO
    contado = ventas.filter(modalidad="contado").aggregate(t=Sum("total"))["t"] or CERO
    abonos = Abono.objects.filter(fecha__range=(desde, hasta)).aggregate(t=Sum("valor"))["t"] or CERO
    cobrado = contado + abonos
    gastos = Gasto.objects.filter(ambito="negocio", fecha__range=(desde, hasta))
    por_cat = {c: gastos.filter(categoria=c).aggregate(t=Sum("monto"))["t"] or CERO
               for c, _ in Gasto.CATEGORIAS}
    total_gastos = sum(por_cat.values(), CERO)
    por_cobrar = sum((v.saldo for v in Venta.objects.filter(modalidad="credito", fecha__date__lte=hasta)), CERO)
    por_pagar = EntradaMercancia.objects.filter(pagada=False).aggregate(t=Sum("valor_compra"))["t"] or CERO
    return {
        "desde": desde, "hasta": hasta, "num_ventas": ventas.count(),
        "total_vendido": total_vendido, "cobrado": cobrado, "por_cat": por_cat,
        "categorias": Gasto.CATEGORIAS, "total_gastos": total_gastos,
        "ganancia": cobrado - total_gastos, "por_cobrar": por_cobrar, "por_pagar": por_pagar,
    }


# ---------- acceso ----------
class CambiarClave(PasswordChangeView):
    template_name = "registration/cambiar_clave.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        resp = super().form_valid(form)
        perfil = getattr(self.request.user, "perfil", None)
        if perfil and perfil.debe_cambiar_password:
            perfil.debe_cambiar_password = False
            perfil.save(update_fields=["debe_cambiar_password"])
        messages.success(self.request, "Contraseña actualizada.")
        return resp


@propietaria_required
def usuarios(request):
    form = forms.VendedoraForm(request.POST or None)
    if request.method == "POST":
        if "alternar" in request.POST:
            u = get_object_or_404(User, pk=request.POST["alternar"], perfil__rol="vendedora")
            u.is_active = not u.is_active
            u.save(update_fields=["is_active"])
            return redirect("usuarios")
        if "eliminar" in request.POST:
            u = get_object_or_404(User, pk=request.POST["eliminar"], perfil__rol="vendedora")
            if u == request.user:
                messages.error(request, "No puedes eliminar tu propia cuenta de propietaria.")
            else:
                Venta.objects.filter(vendedor=u).update(vendedor=request.user)
                u.delete()
                messages.success(request, "Vendedora eliminada correctamente.")
            return redirect("usuarios")
        if form.is_valid():
            form.save()
            messages.success(request, "Vendedora creada. Deberá cambiar la contraseña al entrar.")
            return redirect("usuarios")
    lista = User.objects.filter(perfil__rol="vendedora")
    return render(request, "tienda/usuarios.html", {"form": form, "lista": lista})


# ---------- inicio ----------
@login_required
def dashboard(request):
    hoy = timezone.localdate()
    ctx = {
        "alertas": Variante.objects.filter(stock__lte=F("minimo"), prenda__activa=True).count(),
        "ultimas": Venta.objects.select_related("cliente")[:6],
        "hoy": hoy,
    }
    if es_propietaria(request.user):
        ctx["r"] = resumen(hoy.replace(day=1), hoy)
    return render(request, "tienda/dashboard.html", ctx)


# ---------- inventario ----------
@login_required
def inventario(request):
    q = request.GET.get("q", "").strip()
    variantes = Variante.objects.select_related("prenda", "prenda__categoria").filter(prenda__activa=True)
    if q:
        variantes = variantes.filter(prenda__nombre__icontains=q) | variantes.filter(
            prenda__codigo__icontains=q) | variantes.filter(color__icontains=q) | variantes.filter(talla__iexact=q)
    return render(request, "tienda/inventario.html", {"variantes": variantes.distinct(), "q": q})


@propietaria_required
def prenda_nueva(request):
    return formulario(request, forms.PrendaForm, "Nueva prenda", "inventario")


@propietaria_required
def prenda_editar(request, pk):
    return formulario(request, forms.PrendaForm, "Editar prenda", "inventario", get_object_or_404(Prenda, pk=pk))


@propietaria_required
def variante_nueva(request):
    return formulario(request, forms.VarianteForm, "Agregar talla y color", "inventario")


@propietaria_required
def variante_editar(request, pk):
    return formulario(request, forms.VarianteForm, "Editar talla y color (mínimo / proveedor)",
                      "inventario", get_object_or_404(Variante, pk=pk))


@propietaria_required
def categoria_nueva(request):
    return formulario(request, forms.CategoriaForm, "Nueva categoría", "inventario")


@propietaria_required
def entrada_nueva(request):
    return formulario(request, forms.EntradaForm, "Registrar entrada de mercancía", "inventario")


@propietaria_required
def reponer(request):
    lista = Variante.objects.select_related("prenda", "proveedor").filter(
        stock__lte=F("minimo"), prenda__activa=True).order_by("proveedor__nombre", "prenda__nombre")
    return render(request, "tienda/reponer.html", {"lista": lista})


# ---------- clientas ----------
@login_required
def clientes(request):
    return render(request, "tienda/clientes.html", {"lista": Cliente.objects.all()})


@login_required
def cliente_nuevo(request):
    return formulario(request, forms.ClienteForm, "Nueva clienta", "clientes")


@login_required
def cliente_detalle(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    return render(request, "tienda/cliente_detalle.html", {"c": c, "ventas": c.ventas.all()})


# ---------- ventas ----------
@login_required
def ventas(request):
    qs = Venta.objects.select_related("cliente", "vendedor")
    solo_credito = request.GET.get("credito") == "1"
    if solo_credito:
        qs = qs.filter(modalidad="credito")
    lista = [v for v in qs[:200] if not solo_credito or v.saldo > 0]
    perfil = getattr(request.user, "perfil", None)
    return render(request, "tienda/ventas.html", {
        "lista": lista,
        "solo_credito": solo_credito,
        "es_propietaria": es_propietaria(request.user),
        "es_vendedora": bool(perfil and perfil.rol == "vendedora"),
    })


@login_required
def venta_nueva(request):
    form = forms.VentaForm(request.POST or None, request.FILES or None)
    variantes = Variante.objects.select_related("prenda").filter(stock__gt=0, prenda__activa=True)
    if request.method == "POST" and form.is_valid():
        ids = request.POST.getlist("variante")
        cants = request.POST.getlist("cantidad")
        precios = request.POST.getlist("precio")
        try:
            with transaction.atomic():
                lineas = []
                for vid, c, p in zip(ids, cants, precios):
                    if not vid:
                        continue
                    lineas.append((int(vid), int(c), Decimal(p)))
                if not lineas:
                    raise ValueError("Agrega al menos una prenda a la venta.")
                venta = form.save(commit=False)
                venta.vendedor = request.user
                venta.total = 0
                venta.save()
                total = CERO
                for vid, cant, precio in lineas:
                    v = Variante.objects.select_for_update().select_related("prenda").get(pk=vid)
                    if cant < 1 or precio < 0:
                        raise ValueError("Cantidad o precio inválido.")
                    if cant > v.stock:   # RNF-02: el inventario nunca queda en negativo
                        raise ValueError(f"Solo quedan {v.stock} unidades de {v}.")
                    v.stock -= cant       # RF-06: descuenta el inventario
                    v.save(update_fields=["stock"])
                    DetalleVenta.objects.create(venta=venta, variante=v, cantidad=cant, precio_unitario=precio)
                    total += cant * precio
                venta.total = total       # RF-06: queda como ingreso (contado) o por cobrar (crédito)
                venta.save(update_fields=["total"])
                inicial = request.POST.get("abono_inicial")
                if venta.modalidad == "credito" and inicial:
                    valor = Decimal(inicial)
                    if 0 < valor <= total:
                        Abono.objects.create(venta=venta, valor=valor, medio_pago=venta.medio_pago)
            messages.success(request, f"Venta registrada. Recibo {venta.numero}.")
            return redirect("recibo", pk=venta.pk)
        except (ValueError, InvalidOperation, Variante.DoesNotExist) as e:
            messages.error(request, str(e) if isinstance(e, ValueError) else "Revisa los datos de las prendas.")
    return render(request, "tienda/venta_form.html", {"form": form, "variantes": variantes})


@login_required
def recibo(request, pk):
    v = get_object_or_404(Venta.objects.select_related("cliente", "vendedor"), pk=pk)
    perfil = getattr(request.user, "perfil", None)
    return render(request, "tienda/recibo.html", {
        "v": v,
        "detalles": v.detalles.select_related("variante__prenda"),
        "es_propietaria": es_propietaria(request.user),
        "es_vendedora": bool(perfil and perfil.rol == "vendedora"),
    })


@login_required
def venta_eliminar(request, pk):
    if request.method != "POST":
        messages.error(request, "La factura solo se puede eliminar desde el botón de eliminar.")
        return redirect("ventas")

    venta = get_object_or_404(Venta, pk=pk)
    if not es_propietaria(request.user):
        perfil = getattr(request.user, "perfil", None)
        clave_configurada = settings.VENTA_DELETE_PASSWORD
        if not perfil or perfil.rol != "vendedora":
            messages.error(request, "No tienes permiso para eliminar facturas.")
            return redirect("ventas")
        if not clave_configurada:
            messages.error(request, "La clave de autorización para vendedoras no está configurada.")
            return redirect("ventas")
        if not compare_digest(request.POST.get("password", ""), clave_configurada):
            messages.error(request, "La clave de autorización es incorrecta.")
            return redirect("recibo", pk=pk)

    numero = venta.numero
    with transaction.atomic():
        detalles = list(venta.detalles.all())
        for detalle in detalles:
            Variante.objects.filter(pk=detalle.variante_id).update(
                stock=F("stock") + detalle.cantidad)
        venta.delete()

    messages.success(request, f"Factura {numero} eliminada y stock restablecido.")
    return redirect("ventas")


@login_required
def abono_nuevo(request, pk):
    venta = get_object_or_404(Venta, pk=pk, modalidad="credito")
    if venta.saldo <= 0:
        messages.info(request, "Esta venta ya está pagada.")
        return redirect("recibo", pk=pk)
    form = forms.AbonoForm(request.POST or None, request.FILES or None, venta=venta)
    if request.method == "POST" and form.is_valid():
        ab = form.save(commit=False)
        ab.venta = venta
        ab.save()
        messages.success(request, "Abono registrado.")
        return redirect("recibo", pk=pk)
    return render(request, "tienda/form.html", {
        "form": form, "titulo": f"Abono a {venta.numero} (saldo {venta.saldo})", "volver": "ventas"})


# ---------- proveedores ----------
@propietaria_required
def proveedores(request):
    if request.method == "POST":   # marcar una compra como pagada
        e = get_object_or_404(EntradaMercancia, pk=request.POST.get("pagar"), pagada=False)
        e.pagada = True
        e.save(update_fields=["pagada"])
        Gasto.objects.create(fecha=timezone.localdate(), categoria="mercancia", monto=e.valor_compra,
                             descripcion=f"Pago a {e.proveedor}: {e.cantidad} x {e.variante}")
        messages.success(request, "Pago registrado como gasto de mercancía.")
        return redirect("proveedores")
    return render(request, "tienda/proveedores.html", {
        "lista": Proveedor.objects.all(),
        "pendientes": EntradaMercancia.objects.filter(pagada=False).select_related("proveedor", "variante__prenda")})


@propietaria_required
def proveedor_nuevo(request):
    return formulario(request, forms.ProveedorForm, "Nuevo proveedor", "proveedores")


# ---------- dinero ----------
@propietaria_required
def gastos(request):
    desde, hasta = rango_fechas(request)
    lista = Gasto.objects.filter(fecha__range=(desde, hasta))
    return render(request, "tienda/gastos.html", {"lista": lista, "desde": desde, "hasta": hasta})


@propietaria_required
def gasto_nuevo(request):
    return formulario(request, forms.GastoForm, "Registrar gasto", "gastos")


@propietaria_required
def reporte(request):
    desde, hasta = rango_fechas(request)
    return render(request, "tienda/reporte.html", {"r": resumen(desde, hasta)})


@propietaria_required
def balance(request):
    desde, hasta = rango_fechas(request)
    r = resumen(desde, hasta)
    r["deudoras"] = [c for c in Cliente.objects.all() if c.saldo > 0]
    return render(request, "tienda/balance.html", {"r": r})
