from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from tienda.models import Categoria, Prenda, Variante, Proveedor, Cliente, Venta, DetalleVenta, Abono, Perfil
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


@pytest.mark.django_db
def test_propietaria_puede_eliminar_vendedora_y_reasignar_ventas(client, usuaria_propietaria, usuaria_vendedora, cliente):
    """La propietaria puede eliminar a una vendedora y reubicar sus ventas antes de borrar el usuario."""
    venta = Venta.objects.create(
        cliente=cliente,
        vendedor=usuaria_vendedora,
        canal="tienda",
        modalidad="contado",
        total=Decimal("50000"),
    )
    client.force_login(usuaria_propietaria)

    response = client.post(reverse("usuarios"), {"eliminar": usuaria_vendedora.pk})

    assert response.status_code == 302
    assert response.url == reverse("usuarios")
    assert not User.objects.filter(pk=usuaria_vendedora.pk).exists()
    venta.refresh_from_db()
    assert venta.vendedor == usuaria_propietaria


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
