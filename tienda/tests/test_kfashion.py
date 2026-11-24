from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from tienda.models import Categoria, Prenda, Variante, Proveedor, Cliente, Venta, DetalleVenta, EntradaMercancia, Perfil, CambioPrenda, Merma, Caja
from tienda.forms import VentaForm, AbonoForm


@pytest.fixture
def categoria(db):
    return Categoria.objects.create(nombre="Vestidos")


@pytest.fixture
def proveedor(db):
    return Proveedor.objects.create(nombre="Proveedor Central", telefono="3001234567", ciudad="Medellin")


@pytest.fixture
def prenda(db, categoria):
    return Prenda.objects.create(
        nombre="Vestido Floral",
        categoria=categoria,
        costo=Decimal("40000"),
        gastos_presentacion=Decimal("5000"),
        margen=Decimal("50.0"),
        precio_venta=Decimal("70000"),
    )


@pytest.fixture
def variante(db, prenda, proveedor):
    return Variante.objects.create(
        prenda=prenda,
        talla="M",
        color="Rojo",
        stock=10,
        minimo=2,
        proveedor=proveedor,
    )


@pytest.fixture
def usuaria_propietaria(db):
    user = User.objects.create_user(username="propietaria_test", password="password123")
    Perfil.objects.create(user=user, rol="propietaria", debe_cambiar_password=False)
    return user


@pytest.fixture
def usuaria_vendedora(db):
    user = User.objects.create_user(username="vendedora_test", password="password123")
    Perfil.objects.create(user=user, rol="vendedora", debe_cambiar_password=False)
    return user


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(nombre="Mariana Gomez", celular="3119876543", ciudad="Medellin")


# ==========================================
# 1. PRUEBAS DE MODELOS
# ==========================================
@pytest.mark.django_db
def test_modelo_prenda_codigo_automatico_y_precio_sugerido(prenda):
    """Verifica que el código KF-XXXX se genere y que el precio sugerido calcule bien los márgenes."""
    assert prenda.codigo.startswith("KF-")
    # costo=40000, gastos=5000, margen=50% -> (45000) * 1.5 = 67500
    assert prenda.precio_sugerido == Decimal("67500")


@pytest.mark.django_db
def test_modelo_variante_alerta_por_reponer(variante):
    """Verifica que la propiedad por_reponer se active cuando stock <= minimo."""
    variante.stock = 2
    variante.minimo = 2
    assert variante.por_reponer is True

    variante.stock = 5
    assert variante.por_reponer is False


# ==========================================
# 2. PRUEBAS DE FORMULARIOS
# ==========================================
@pytest.mark.django_db
def test_formulario_venta_credito_requiere_cliente_y_fecha():
    """Valida que una venta a crédito rechace el formulario si falta cliente o fecha límite."""
    datos_invalidos = {
        "canal": "tienda",
        "modalidad": "credito",
        "medio_pago": "efectivo",
        "cliente": "",
        "fecha_limite": "",
    }
    form = VentaForm(data=datos_invalidos)
    assert not form.is_valid()
    assert "cliente" in form.errors
    assert "fecha_limite" in form.errors


@pytest.mark.django_db
def test_formulario_abono_no_puede_superar_saldo(usuaria_vendedora, cliente):
    """Valida que el formulario de abono no permita montos superiores al saldo pendiente de la venta."""
    venta = Venta.objects.create(
        cliente=cliente,
        vendedor=usuaria_vendedora,
        canal="tienda",
        modalidad="credito",
        total=Decimal("50000"),
    )
    # Saldo es 50000, intentamos abonar 60000
    datos = {
        "fecha": "2026-11-12",
        "valor": Decimal("60000"),
        "medio_pago": "efectivo",
    }
    form = AbonoForm(data=datos, venta=venta)
    assert not form.is_valid()
    assert "valor" in form.errors


# ==========================================
# 3. PRUEBAS DE PERMISOS Y ROLES
# ==========================================
@pytest.mark.django_db
def test_permiso_vendedora_restringida_en_finanzas(client, usuaria_vendedora):
    """RNF-01: La vendedora no puede ver gastos, reportes ni balance."""
    client.force_login(usuaria_vendedora)

    rutas_restringidas = [
        reverse("gastos"),
        reverse("reporte"),
        reverse("balance"),
        reverse("usuarios"),
    ]

    for ruta in rutas_restringidas:
        response = client.get(ruta)
        # Debe redirigir al dashboard
        assert response.status_code == 302
        assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_permiso_propietaria_acceso_completo(client, usuaria_propietaria):
    """La propietaria puede acceder a las secciones financieras y administrativas."""
    client.force_login(usuaria_propietaria)

    rutas = [
        reverse("gastos"),
        reverse("reporte"),
        reverse("balance"),
        reverse("usuarios"),
    ]

    for ruta in rutas:
        response = client.get(ruta)
        assert response.status_code == 200


# ==========================================
# 4. PRUEBAS DE FLUJOS CRÍTICOS
# ==========================================
@pytest.mark.django_db
def test_flujo_venta_contado_descuenta_stock(client, usuaria_vendedora, variante, cliente):
    """RF-05 y RF-06: Venta de contado descuenta stock en tiempo real y emite recibo."""
    client.force_login(usuaria_vendedora)
    stock_inicial = variante.stock

    payload = {
        "cliente": cliente.id,
        "canal": "tienda",
        "modalidad": "contado",
        "medio_pago": "efectivo",
        "variante": [variante.id],
        "cantidad": [3],
        "precio": [variante.prenda.precio_venta],
    }

    response = client.post(reverse("venta_nueva"), data=payload)
    assert response.status_code == 302  # Redirige a recibo

    # Verificar que el stock disminuyó exactamente en 3
    variante.refresh_from_db()
    assert variante.stock == stock_inicial - 3

    # Verificar venta y detalle en base de datos
    venta = Venta.objects.latest("id")
    assert venta.total == Decimal("210000")  # 3 * 70000
    assert venta.saldo == Decimal("0")       # Al ser contado, saldo = 0


@pytest.mark.django_db
def test_flujo_venta_bloquea_stock_insuficiente(client, usuaria_vendedora, variante, cliente):
    """RNF-02: El inventario nunca puede quedar en negativo; se rechaza la venta si no hay stock suficiente."""
    client.force_login(usuaria_vendedora)
    variante.stock = 2
    variante.save()

    payload = {
        "cliente": cliente.id,
        "canal": "tienda",
        "modalidad": "contado",
        "medio_pago": "efectivo",
        "variante": [variante.id],
        "cantidad": [5],  # Solicita 5 cuando solo hay 2
        "precio": [variante.prenda.precio_venta],
    }

    response = client.post(reverse("venta_nueva"), data=payload)
    # Permanece en el formulario (status 200) mostrando mensaje de error
    assert response.status_code == 200

    # Stock permanece intacto
    variante.refresh_from_db()
    assert variante.stock == 2
    assert not Venta.objects.filter(total=Decimal("350000")).exists()


@pytest.mark.django_db
def test_flujo_venta_credito_y_abono(client, usuaria_vendedora, variante, cliente):
    """RF-08 y RF-09: Venta a crédito deja saldo pendiente y abono actualiza el saldo de la clienta."""
    client.force_login(usuaria_vendedora)

    # 1. Crear venta a crédito por 1 unidad ($70.000)
    payload_venta = {
        "cliente": cliente.id,
        "canal": "tienda",
        "modalidad": "credito",
        "medio_pago": "efectivo",
        "fecha_limite": "2026-12-31",
        "variante": [variante.id],
        "cantidad": [1],
        "precio": [variante.prenda.precio_venta],
    }
    client.post(reverse("venta_nueva"), data=payload_venta)
    venta = Venta.objects.latest("id")
    assert venta.saldo == Decimal("70000")
    assert cliente.saldo == Decimal("70000")

    # 2. Registrar un abono de $30.000
    payload_abono = {
        "fecha": "2026-11-12",
        "valor": Decimal("30000"),
        "medio_pago": "bancolombia",
    }
    resp_abono = client.post(reverse("abono_nuevo", kwargs={"pk": venta.pk}), data=payload_abono)
    assert resp_abono.status_code == 302

    # 3. Validar nuevo saldo
    assert venta.saldo == Decimal("40000")
    assert cliente.saldo == Decimal("40000")


@pytest.mark.django_db
def test_flujo_cambio_prenda(client, usuaria_vendedora, prenda, proveedor, cliente):
    """Punto 3: Cambio de talla/color devuelve la prenda vieja y descuenta la nueva."""
    client.force_login(usuaria_vendedora)

    v_m = Variante.objects.create(prenda=prenda, talla="M", color="Azul", stock=5, minimo=1, proveedor=proveedor)
    v_l = Variante.objects.create(prenda=prenda, talla="L", color="Azul", stock=3, minimo=1, proveedor=proveedor)

    # Venta de v_m
    venta = Venta.objects.create(vendedor=usuaria_vendedora, cliente=cliente, modalidad="contado", total=Decimal("70000"))
    DetalleVenta.objects.create(venta=venta, variante=v_m, cantidad=1, precio_unitario=Decimal("70000"))
    v_m.stock -= 1
    v_m.save()
    assert v_m.stock == 4
    assert v_l.stock == 3

    # Ejecutar cambio de v_m por v_l
    payload_cambio = {
        "variante_devuelta": v_m.id,
        "variante_nueva": v_l.id,
        "cantidad": 1,
        "diferencia_precio": 0,
        "motivo": "Cliente pidió cambio por talla L",
    }
    resp = client.post(reverse("venta_cambio", kwargs={"pk": venta.pk}), data=payload_cambio)
    assert resp.status_code == 302

    v_m.refresh_from_db()
    v_l.refresh_from_db()
    assert v_m.stock == 5  # se le devolvió la unidad
    assert v_l.stock == 2  # se descontó la nueva talla
    assert CambioPrenda.objects.filter(venta=venta).count() == 1


@pytest.mark.django_db
def test_flujo_merma_descuenta_stock(client, usuaria_propietaria, variante):
    """Punto 3: Registrar merma descuenta stock de la variante y no permite superar stock."""
    client.force_login(usuaria_propietaria)
    variante.stock = 4
    variante.save()

    # Dar de baja 1 unidad por mancha
    payload = {
        "variante": variante.id,
        "tipo": "dano",
        "cantidad": 1,
        "motivo": "Manchada con café en el perchero",
    }
    resp = client.post(reverse("merma_nueva"), data=payload)
    assert resp.status_code == 302

    variante.refresh_from_db()
    assert variante.stock == 3
    assert Merma.objects.filter(variante=variante).count() == 1


@pytest.mark.django_db
def test_flujo_arqueo_y_cierre_caja(client, usuaria_vendedora, variante, cliente):
    """Punto 4: Apertura y Cierre de Caja calcula esperado y detecta sobrantes/faltantes."""
    client.force_login(usuaria_vendedora)

    # 1. Abrir caja con base de $50.000
    resp_abrir = client.post(reverse("caja_control"), data={"abrir_caja": "1", "monto_apertura": "50000"})
    assert resp_abrir.status_code == 302
    caja = Caja.objects.get(estado="abierta")
    assert caja.monto_apertura == Decimal("50000")

    # 2. Registrar venta de contado en efectivo de $70.000
    payload_venta = {
        "cliente": "",
        "canal": "tienda",
        "modalidad": "contado",
        "medio_pago": "efectivo",
        "variante": [variante.id],
        "cantidad": [1],
        "precio": [variante.prenda.precio_venta],
    }
    client.post(reverse("venta_nueva"), data=payload_venta)

    # 3. Cerrar caja: Se espera base ($50.000) + venta ($70.000) = $120.000
    # Cajera cuenta $120.000 (cuadre exacto)
    payload_cierre = {
        "cerrar_caja": "1",
        "efectivo_cierre": "120000",
        "nequi_cierre": "0",
        "bancolombia_cierre": "0",
        "daviplata_cierre": "0",
        "datafono_cierre": "0",
        "link_cierre": "0",
        "observaciones": "Turno sin novedades",
    }
    resp_cierre = client.post(reverse("caja_control"), data=payload_cierre)
    assert resp_cierre.status_code == 302

    caja.refresh_from_db()
    assert caja.estado == "cerrada"
    assert caja.sistema_efectivo == Decimal("120000")
    assert caja.diferencia == Decimal("0")


@pytest.mark.django_db
def test_todas_las_vistas_renderizan_ok(client, usuaria_propietaria, variante, cliente):
    """Verifica que todas las rutas principales renderizan sus plantillas sin errores 500."""
    client.force_login(usuaria_propietaria)
    rutas = [
        "dashboard", "venta_nueva", "ventas", "inventario", "reponer",
        "mermas", "merma_nueva", "clientes", "cliente_nuevo",
        "caja_control", "proveedores", "gastos", "reporte", "balance", "usuarios",
    ]
    for nombre in rutas:
        resp = client.get(reverse(nombre))
        assert resp.status_code == 200, f"Fallo al renderizar {nombre}"


@pytest.mark.django_db
def test_eliminar_clienta_con_y_sin_deuda(client, usuaria_propietaria, cliente):
    """Permite eliminar clienta sin deudas (conservando factura como Mostrador) y bloquea si tiene deuda."""
    client.force_login(usuaria_propietaria)
    # Con venta a crédito pendiente -> bloqueada
    v_cred = Venta.objects.create(
        vendedor=usuaria_propietaria, cliente=cliente, modalidad="credito", total=Decimal("50000")
    )
    resp_bloq = client.post(reverse("cliente_eliminar", args=[cliente.pk]))
    assert resp_bloq.status_code == 200
    assert Cliente.objects.filter(pk=cliente.pk).exists()

    # Cambia a contado (sin deuda) -> permite eliminar y pasa venta a Mostrador
    v_cred.modalidad = "contado"
    v_cred.save()
    resp_ok = client.post(reverse("cliente_eliminar", args=[cliente.pk]))
    assert resp_ok.status_code == 302
    assert not Cliente.objects.filter(pk=cliente.pk).exists()
    v_cred.refresh_from_db()
    assert v_cred.cliente is None


@pytest.mark.django_db
def test_eliminar_proveedor_con_y_sin_deuda(client, usuaria_propietaria, proveedor, variante):
    """Permite eliminar proveedor sin deudas conservando entradas; bloquea si se le debe."""
    client.force_login(usuaria_propietaria)
    entrada = EntradaMercancia.objects.create(
        variante=variante, proveedor=proveedor, cantidad=2, valor_compra=Decimal("40000"), pagada=False
    )
    client.post(reverse("proveedor_eliminar", args=[proveedor.pk]))
    assert Proveedor.objects.filter(pk=proveedor.pk).exists()

    entrada.pagada = True
    entrada.save()
    client.post(reverse("proveedor_eliminar", args=[proveedor.pk]))
    assert not Proveedor.objects.filter(pk=proveedor.pk).exists()
    entrada.refresh_from_db()
    assert entrada.proveedor is None


@pytest.mark.django_db
def test_eliminar_vendedora_reasigna_ventas(client, usuaria_propietaria, usuaria_vendedora):
    """Permite eliminar vendedora reasignando sus ventas a la propietaria."""
    client.force_login(usuaria_propietaria)
    venta = Venta.objects.create(vendedor=usuaria_vendedora, modalidad="contado", total=Decimal("60000"))

    resp = client.post(reverse("usuario_eliminar", args=[usuaria_vendedora.pk]))
    assert resp.status_code == 302
    assert not User.objects.filter(pk=usuaria_vendedora.pk).exists()
    venta.refresh_from_db()
    assert venta.vendedor == usuaria_propietaria


@pytest.mark.django_db
def test_exportar_excel_csv_y_recibo_pdf(client, usuaria_propietaria, variante, cliente):
    """Valida descarga real de Excel (.xlsx), CSV y recibo en PDF."""
    client.force_login(usuaria_propietaria)
    venta = Venta.objects.create(vendedor=usuaria_propietaria, cliente=cliente, modalidad="contado", total=Decimal("70000"))
    DetalleVenta.objects.create(venta=venta, variante=variante, cantidad=1, precio_unitario=Decimal("70000"))

    # PDF del recibo
    r_pdf = client.get(reverse("recibo_pdf", args=[venta.pk]))
    assert r_pdf.status_code == 200
    assert r_pdf["Content-Type"] == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF")

    # Exportar Excel en todas las secciones
    for ruta in ("ventas_exportar", "inventario_exportar", "mermas_exportar", "balance_exportar"):
        r_xlsx = client.get(reverse(ruta))
        assert r_xlsx.status_code == 200
        assert "spreadsheetml.sheet" in r_xlsx["Content-Type"]
        assert r_xlsx.content[:2] == b"PK"  # firma ZIP de .xlsx

        r_csv = client.get(reverse(ruta) + "?formato=csv")
        assert r_csv.status_code == 200
        assert "text/csv" in r_csv["Content-Type"]



