from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from . import forms
from .models import (CERO, Abono, Categoria, Cliente, DetalleVenta, EntradaMercancia, Gasto, Prenda,
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


def formulario(request, clase, titulo, volver, instancia=None, eliminar=None, **kw):
    """Crear o editar con un formulario. `eliminar` es la URL de borrado (solo al editar)."""
    form = clase(request.POST or None, request.FILES or None, instance=instancia, **kw)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Guardado correctamente.")
        return redirect(volver)
    return render(request, "tienda/form.html", {"form": form, "titulo": titulo, "volver": volver, "eliminar": eliminar})


def confirmar_eliminar(request, obj, volver, *, que, aviso="", accion=None, bloqueado="", boton="Sí, eliminar"):
    """CRUD - eliminar: pide confirmación (GET) y borra (POST).
    `accion` reemplaza el borrado normal; `bloqueado` explica por qué no se puede borrar."""
    if request.method == "POST" and not bloqueado:
        try:
            with transaction.atomic():
                mensaje = accion() if accion else None
                if not accion:
                    obj.delete()
            messages.success(request, mensaje or f"{que} eliminado correctamente.")
        except ProtectedError:
            messages.error(request, f"No se puede eliminar: {que.lower()} tiene registros asociados.")
        return redirect(volver)
    return render(request, "tienda/confirmar.html", {
        "obj": obj, "que": que, "aviso": aviso, "bloqueado": bloqueado, "volver": volver, "boton": boton})


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


def inicio_del_dia(dia):
    """Medianoche de ese día en hora de Colombia. Se usa en vez de fecha__date,
    que necesita las zonas horarias cargadas en MySQL y sin ellas devuelve vacío."""
    return timezone.make_aware(datetime.combine(dia, time.min))


def resumen(desde, hasta):
    """Cifras del negocio entre dos fechas (RF-13 y RF-14)."""
    fin = inicio_del_dia(hasta + timedelta(days=1))
    ventas = Venta.objects.filter(fecha__gte=inicio_del_dia(desde), fecha__lt=fin)
    total_vendido = ventas.aggregate(t=Sum("total"))["t"] or CERO
    contado = ventas.filter(modalidad="contado").aggregate(t=Sum("total"))["t"] or CERO
    abonos = Abono.objects.filter(fecha__range=(desde, hasta)).aggregate(t=Sum("valor"))["t"] or CERO
    cobrado = contado + abonos
    gastos = Gasto.objects.filter(ambito="negocio", fecha__range=(desde, hasta))
    por_cat = {c: gastos.filter(categoria=c).aggregate(t=Sum("monto"))["t"] or CERO
               for c, _ in Gasto.CATEGORIAS}
    total_gastos = sum(por_cat.values(), CERO)
    por_cobrar = sum((v.saldo for v in Venta.objects.filter(modalidad="credito", fecha__lt=fin)), CERO)
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
        if form.is_valid():
            form.save()
            messages.success(request, "Vendedora creada. Deberá cambiar la contraseña al entrar.")
            return redirect("usuarios")
    lista = User.objects.filter(perfil__rol="vendedora")
    return render(request, "tienda/usuarios.html", {"form": form, "lista": lista})


@propietaria_required
def usuario_eliminar(request, pk):
    u = get_object_or_404(User, pk=pk, perfil__rol="vendedora")
    tiene_ventas = Venta.objects.filter(vendedor=u).exists()
    return confirmar_eliminar(
        request, u, "usuarios", que="Vendedora",
        bloqueado=(
            f"«{u.first_name or u.username}» tiene ventas registradas. "
            "Desactívala en vez de eliminarla para conservar el historial."
            if tiene_ventas else ""
        ),
        aviso=f"Se eliminará el usuario «{u.first_name or u.username}» de forma permanente.",
    )


# ---------- inicio ----------
@login_required
def dashboard(request):
    hoy = timezone.localdate()
    ahora = timezone.localtime()
    hace_6_dias = hoy - timedelta(days=6)
    desde_semana = timezone.make_aware(datetime.combine(hace_6_dias, time.min))
    ventas_semana = list(Venta.objects.filter(fecha__gte=desde_semana).only("fecha", "total"))
    por_reponer = (Variante.objects.select_related("prenda")
                   .filter(stock__lte=F("minimo"), prenda__activa=True).order_by("stock"))
    ctx = {
        "alertas": por_reponer.count(),
        "reponer": por_reponer[:3],
        "ultimas": Venta.objects.select_related("cliente")[:3],
        "hoy": hoy,
        "saludo": "Buenos días" if ahora.hour < 12 else "Buenas tardes" if ahora.hour < 19 else "Buenas noches",
        "ventas_hoy": sum(1 for v in ventas_semana if timezone.localtime(v.fecha).date() == hoy),
        "prendas_tienda": Variante.objects.filter(prenda__activa=True).aggregate(t=Sum("stock"))["t"] or 0,
    }
    if es_propietaria(request.user):
        ctx["r"] = resumen(hoy.replace(day=1), hoy)
        # Créditos con saldo pendiente: primero los que vencen antes
        creditos = [v for v in Venta.objects.select_related("cliente").filter(modalidad="credito") if v.saldo > 0]
        creditos.sort(key=lambda v: v.fecha_limite or date.max)
        ctx["cobros"] = creditos[:3]
        # Ventas de los últimos 7 días para la gráfica
        totales = {hace_6_dias + timedelta(days=i): CERO for i in range(7)}
        for v in ventas_semana:
            dia = timezone.localtime(v.fecha).date()
            if dia in totales:
                totales[dia] += v.total
        maximo = max(totales.values()) or 1
        ctx["semana"] = [{"dia": d, "total": t, "alto": max(3, round(t / maximo * 80)), "es_hoy": d == hoy}
                         for d, t in totales.items()]
        ctx["total_semana"] = sum(totales.values(), CERO)
        ctx["escala"] = (maximo if maximo != 1 else CERO, maximo / 2 if maximo != 1 else CERO)
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
    return formulario(request, forms.PrendaForm, "Editar prenda", "inventario", get_object_or_404(Prenda, pk=pk),
                      eliminar=reverse("prenda_eliminar", args=[pk]))


@propietaria_required
def variante_nueva(request):
    return formulario(request, forms.VarianteForm, "Agregar talla y color", "inventario")


@propietaria_required
def variante_editar(request, pk):
    return formulario(request, forms.VarianteForm, "Editar talla y color (mínimo / proveedor)",
                      "inventario", get_object_or_404(Variante, pk=pk), eliminar=reverse("variante_eliminar", args=[pk]))


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
    q = request.GET.get("q", "").strip()
    qs = Cliente.objects.annotate(compras=Count("ventas"))
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(celular__icontains=q) | Q(ciudad__icontains=q))
    lista = list(qs)
    return render(request, "tienda/clientes.html", {
        "lista": lista, "q": q,
        "total_clientas": Cliente.objects.count(),
        "con_saldo": sum(1 for c in lista if c.saldo > 0),
        "total_compras": sum(c.compras for c in lista),
    })


@login_required
def cliente_nuevo(request):
    return formulario(request, forms.ClienteForm, "Nueva clienta", "clientes")


@login_required
def cliente_detalle(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    ventas = list(c.ventas.prefetch_related("detalles"))
    for v in ventas:
        v.num_prendas = sum(d.cantidad for d in v.detalles.all())
    iniciales = "".join(p[0] for p in c.nombre.split()[:2]).upper()
    celular = "".join(ch for ch in c.celular if ch.isdigit())
    if len(celular) == 10:      # número colombiano sin indicativo
        celular = "57" + celular
    return render(request, "tienda/cliente_detalle.html", {
        "c": c, "ventas": ventas, "iniciales": iniciales, "whatsapp": celular,
        "total_comprado": sum((v.total for v in ventas), CERO),
        "creditos_pendientes": [v for v in ventas if v.modalidad == "credito" and v.saldo > 0],
    })


# ---------- ventas ----------
@login_required
def ventas(request):
    if request.GET.get("credito") == "1":
        return cuentas_por_cobrar(request)

    hoy = timezone.localdate()
    periodo = request.GET.get("periodo", "mes")
    modalidad = request.GET.get("modalidad", "")
    q = request.GET.get("q", "").strip()
    rangos = {"hoy": (hoy, hoy), "semana": (hoy - timedelta(days=6), hoy), "mes": (hoy.replace(day=1), hoy)}
    if periodo == "fechas":
        desde, hasta = rango_fechas(request)
    elif periodo in rangos:
        desde, hasta = rangos[periodo]
    else:
        periodo, desde, hasta = "todo", None, None

    qs = Venta.objects.select_related("cliente").prefetch_related("detalles__variante__prenda")
    if desde:
        qs = qs.filter(fecha__gte=inicio_del_dia(desde), fecha__lt=inicio_del_dia(hasta + timedelta(days=1)))
    if modalidad in ("contado", "credito"):
        qs = qs.filter(modalidad=modalidad)
    if q:
        numero = "".join(ch for ch in q if ch.isdigit())
        filtro = Q(cliente__nombre__icontains=q)
        if numero:
            filtro |= Q(pk=int(numero))
        qs = qs.filter(filtro)

    totales = qs.aggregate(n=Count("id"), t=Sum("total"))
    pagina = Paginator(qs, 10).get_page(request.GET.get("pagina"))

    def enlace(**cambios):
        """URL del histórico conservando los filtros actuales."""
        p = {"periodo": periodo, "modalidad": modalidad, "q": q}
        if periodo == "fechas":
            p.update(desde=desde.isoformat(), hasta=hasta.isoformat())
        p.update(cambios)
        return "?" + urlencode({k: v for k, v in p.items() if v})

    ctx = {
        "pagina": pagina, "q": q, "periodo": periodo, "modalidad": modalidad, "desde": desde, "hasta": hasta,
        "num_ventas": totales["n"], "total_periodo": totales["t"] or CERO,
        "periodos": [(clave, nombre, enlace(periodo=clave, pagina="")) for clave, nombre in
                     [("hoy", "Hoy"), ("semana", "Semana"), ("mes", "Mes"), ("todo", "Todo")]],
        "modalidades": [(clave, nombre, enlace(modalidad=clave, pagina="")) for clave, nombre in
                        [("", "Todas"), ("contado", "Contado"), ("credito", "Crédito")]],
        "anterior": enlace(pagina=pagina.previous_page_number()) if pagina.has_previous() else "",
        "siguiente": enlace(pagina=pagina.next_page_number()) if pagina.has_next() else "",
    }
    return render(request, "tienda/ventas.html", ctx)


def cuentas_por_cobrar(request):
    """Ventas a crédito con saldo pendiente (antes: ventas?credito=1)."""
    hoy = timezone.localdate()
    creditos = list(Venta.objects.select_related("cliente").filter(modalidad="credito").prefetch_related("abonos"))
    pendientes = sorted((v for v in creditos if v.saldo > 0), key=lambda v: v.fecha_limite or date.max)
    vencidas = [v for v in pendientes if v.fecha_limite and v.fecha_limite < hoy]
    inicio_mes = hoy.replace(day=1)
    pagadas_mes = [v for v in creditos if v.saldo <= 0 and any(a.fecha >= inicio_mes for a in v.abonos.all())]
    return render(request, "tienda/cuentas.html", {
        "pendientes": pendientes, "hoy": hoy,
        "total_deben": sum((v.saldo for v in pendientes), CERO),
        "vencidas": len(vencidas), "total_vencido": sum((v.saldo for v in vencidas), CERO),
        "pagadas_mes": pagadas_mes,
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
    return render(request, "tienda/recibo.html", {"v": v, "detalles": v.detalles.select_related("variante__prenda")})


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

    # Separar el salario de los demás gastos del negocio
    r["salario"] = r["por_cat"].get("salario", CERO)
    r["gastos_sin_salario"] = r["total_gastos"] - r["salario"]
    r["lineas_gasto"] = [(nombre, r["por_cat"][clave]) for clave, nombre in Gasto.CATEGORIAS if clave != "salario"]

    # Botones de periodo: Semana, Mes, Trimestre
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    inicio_trimestre = (inicio_mes - timedelta(days=62)).replace(day=1)
    periodos = [("Semana", hoy - timedelta(days=6)), ("Mes", inicio_mes), ("Trimestre", inicio_trimestre)]
    r["periodos"] = [{"nombre": n, "desde": d, "hasta": hoy, "activo": (d, hoy) == (desde, hasta)} for n, d in periodos]
    r["fechas_propias"] = not any(p["activo"] for p in r["periodos"])

    # Ventas de los últimos 5 meses hasta el mes de "hasta"
    meses = []
    primero = hasta.replace(day=1)
    for _ in range(5):
        siguiente = (primero + timedelta(days=32)).replace(day=1)
        rango = [timezone.make_aware(datetime.combine(d, time.min)) for d in (primero, siguiente)]
        total = Venta.objects.filter(fecha__gte=rango[0], fecha__lt=rango[1]).aggregate(t=Sum("total"))["t"] or CERO
        meses.append({"mes": primero, "total": total})
        primero = (primero - timedelta(days=1)).replace(day=1)
    meses.reverse()
    maximo = max(m["total"] for m in meses) or 1
    for m in meses:
        m["alto"] = max(3, round(m["total"] / maximo * 165))
    meses[-1]["actual"] = True
    r["meses"] = meses
    r["escala"] = (maximo if maximo != 1 else CERO, maximo / 2 if maximo != 1 else CERO)
    return render(request, "tienda/balance.html", {"r": r})


# ======================================================================
# CRUD: editar y eliminar lo que faltaba
# ======================================================================

# ---------- categorías ----------
@propietaria_required
def categorias(request):
    lista = Categoria.objects.annotate(num_prendas=Count("prenda"))
    return render(request, "tienda/categorias.html", {"lista": lista})


@propietaria_required
def categoria_editar(request, pk):
    return formulario(request, forms.CategoriaForm, "Editar categoría", "categorias",
                      get_object_or_404(Categoria, pk=pk), eliminar=reverse("categoria_eliminar", args=[pk]))


@propietaria_required
def categoria_eliminar(request, pk):
    c = get_object_or_404(Categoria, pk=pk)
    n = c.prenda_set.count()
    return confirmar_eliminar(request, c, "categorias", que="Categoría",
                              bloqueado=f"Tiene {n} prenda(s). Cámbialas de categoría antes de eliminarla." if n else "")


# ---------- prendas y variantes ----------
@propietaria_required
def prenda_eliminar(request, pk):
    p = get_object_or_404(Prenda, pk=pk)
    con_historia = (DetalleVenta.objects.filter(variante__prenda=p).exists()
                    or EntradaMercancia.objects.filter(variante__prenda=p).exists())
    if con_historia:
        def ocultar():
            p.activa = False
            p.save(update_fields=["activa"])
            return f"«{p.nombre}» ya tiene ventas o compras, así que se ocultó del inventario en vez de borrarse."
        return confirmar_eliminar(request, p, "inventario", que="Prenda", accion=ocultar, boton="Sí, ocultar prenda",
                                  aviso="Esta prenda ya tiene ventas o entradas registradas. Para no perder esa historia, "
                                        "se ocultará del inventario y de las ventas nuevas, pero sus recibos seguirán intactos.")
    return confirmar_eliminar(request, p, "inventario", que="Prenda",
                              aviso="Se borrarán también todas sus tallas y colores.")


@propietaria_required
def variante_eliminar(request, pk):
    v = get_object_or_404(Variante, pk=pk)
    con_historia = v.entradas.exists() or DetalleVenta.objects.filter(variante=v).exists()
    return confirmar_eliminar(request, v, "inventario", que="Talla y color", bloqueado=(
        "Ya tiene ventas o entradas registradas, así que no se puede borrar sin dañar los recibos. "
        "Si ya no la vas a vender, déjala con 0 unidades." if con_historia else ""))


# ---------- entradas de mercancía ----------
@propietaria_required
def entrada_eliminar(request, pk):
    e = get_object_or_404(EntradaMercancia.objects.select_related("variante", "proveedor"), pk=pk)
    if e.pagada:
        bloqueo = "Esta compra ya se pagó y quedó registrada como gasto. Por eso no se puede eliminar desde aquí."
    elif e.variante.stock < e.cantidad:
        bloqueo = f"Ya se vendieron prendas de esta entrada: quedan {e.variante.stock} y la entrada sumó {e.cantidad}."
    else:
        bloqueo = ""

    def borrar():
        v = Variante.objects.select_for_update().get(pk=e.variante_id)
        v.stock -= e.cantidad
        v.save(update_fields=["stock"])
        e.delete()
        return f"Entrada eliminada. Se restaron {e.cantidad} unidades de {v}."
    return confirmar_eliminar(request, e, "proveedores", que="Entrada de mercancía", accion=borrar, bloqueado=bloqueo,
                              aviso=f"Se restarán {e.cantidad} unidades del inventario y desaparecerá la deuda con {e.proveedor}.")


# ---------- clientas ----------
@login_required
def cliente_editar(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    return formulario(request, forms.ClienteForm, "Editar clienta", "clientes", c,
                      eliminar=reverse("cliente_eliminar", args=[pk]) if es_propietaria(request.user) else None)


@propietaria_required
def cliente_eliminar(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    n = c.ventas.count()
    return confirmar_eliminar(request, c, "clientes", que="Clienta", bloqueado=(
        f"Tiene {n} compra(s) registradas. Para no perder su historial no se puede eliminar." if n else ""))


# ---------- proveedores ----------
@propietaria_required
def proveedor_editar(request, pk):
    return formulario(request, forms.ProveedorForm, "Editar proveedor", "proveedores",
                      get_object_or_404(Proveedor, pk=pk), eliminar=reverse("proveedor_eliminar", args=[pk]))


@propietaria_required
def proveedor_eliminar(request, pk):
    p = get_object_or_404(Proveedor, pk=pk)
    n = p.entradas.count()
    return confirmar_eliminar(request, p, "proveedores", que="Proveedor",
                              aviso="Las prendas que tenían este proveedor quedarán sin proveedor asignado.",
                              bloqueado=f"Tiene {n} entrada(s) de mercancía registradas. No se puede eliminar." if n else "")


# ---------- gastos ----------
@propietaria_required
def gasto_editar(request, pk):
    return formulario(request, forms.GastoForm, "Editar gasto", "gastos",
                      get_object_or_404(Gasto, pk=pk), eliminar=reverse("gasto_eliminar", args=[pk]))


@propietaria_required
def gasto_eliminar(request, pk):
    return confirmar_eliminar(request, get_object_or_404(Gasto, pk=pk), "gastos", que="Gasto")


# ---------- ventas y abonos ----------
@propietaria_required
def venta_anular(request, pk):
    venta = get_object_or_404(Venta, pk=pk)

    def anular():
        for d in venta.detalles.select_related("variante"):
            v = Variante.objects.select_for_update().get(pk=d.variante_id)
            v.stock += d.cantidad        # las prendas vuelven al inventario
            v.save(update_fields=["stock"])
        numero = venta.numero
        venta.delete()                   # borra también sus líneas y abonos
        return f"Venta {numero} anulada. Las prendas volvieron al inventario."
    abonos = venta.abonos.count()
    return confirmar_eliminar(request, venta, "ventas", que="Venta", accion=anular, boton="Sí, anular venta",
                              aviso="Las prendas de esta venta volverán al inventario"
                                    + (f" y se borrarán sus {abonos} abono(s)." if abonos else "."))


@propietaria_required
def abono_eliminar(request, pk):
    a = get_object_or_404(Abono.objects.select_related("venta"), pk=pk)
    venta_pk = a.venta_id
    if request.method == "POST":
        a.delete()
        messages.success(request, "Abono eliminado. El saldo de la venta se actualizó.")
        return redirect("recibo", pk=venta_pk)
    return render(request, "tienda/confirmar.html", {
        "obj": a, "que": "Abono", "aviso": f"El saldo de la venta {a.venta.numero} volverá a subir {a.valor:,.0f} pesos.".replace(",", "."),
        "volver_url": reverse("recibo", args=[venta_pk]), "boton": "Sí, eliminar"})
