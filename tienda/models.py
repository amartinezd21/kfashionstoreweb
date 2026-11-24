from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

MEDIOS_PAGO = [
    ("efectivo", "Efectivo"), ("nequi", "Nequi"), ("bancolombia", "Bancolombia"),
    ("daviplata", "Daviplata"), ("datafono", "Datáfono Bold"), ("link", "Link de pago"),
]
CERO = Decimal("0")


class Perfil(models.Model):
    ROLES = [("propietaria", "Propietaria"), ("vendedora", "Vendedora")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(max_length=20, choices=ROLES, default="vendedora")
    debe_cambiar_password = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"


def es_propietaria(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = getattr(user, "perfil", None)
    return bool(perfil and perfil.rol == "propietaria")


class Categoria(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    telefono = models.CharField("Teléfono", max_length=30, blank=True)
    ciudad = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "proveedores"

    def __str__(self):
        return self.nombre

    @property
    def saldo(self):
        return self.entradas.filter(pagada=False).aggregate(t=Sum("valor_compra"))["t"] or CERO


class Prenda(models.Model):
    codigo = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    nombre = models.CharField(max_length=120)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    descripcion = models.TextField("Descripción", blank=True)
    costo = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(0)])
    gastos_presentacion = models.DecimalField(
        "Gastos de presentación (etiquetas, bolsas, empaque)",
        max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    margen = models.DecimalField("% de ganancia deseado", max_digits=5, decimal_places=1, default=50)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(0)])
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f"KF-{self.pk:04d}"
            super().save(update_fields=["codigo"])

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"

    @property
    def precio_sugerido(self):
        return ((self.costo + self.gastos_presentacion) * (1 + self.margen / 100)).quantize(Decimal("1"))


class Variante(models.Model):
    """Una prenda en una talla y color concretos: aquí vive el inventario."""
    prenda = models.ForeignKey(Prenda, on_delete=models.CASCADE, related_name="variantes")
    talla = models.CharField(max_length=10)
    color = models.CharField(max_length=40)
    stock = models.PositiveIntegerField(default=0)
    minimo = models.PositiveIntegerField("Cantidad mínima", default=1)
    proveedor = models.ForeignKey(Proveedor, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("prenda", "talla", "color")
        ordering = ["prenda__nombre", "talla", "color"]

    def __str__(self):
        return f"{self.prenda.nombre} · {self.talla} · {self.color}"

    @property
    def por_reponer(self):
        return self.stock <= self.minimo


class EntradaMercancia(models.Model):
    variante = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="entradas")
    proveedor = models.ForeignKey(Proveedor, null=True, blank=True, on_delete=models.SET_NULL, related_name="entradas")
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    valor_compra = models.DecimalField("Valor de la compra", max_digits=12, decimal_places=0)
    fecha = models.DateField(default=timezone.localdate)
    pagada = models.BooleanField("Ya se le pagó al proveedor", default=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.cantidad} x {self.variante} ({self.fecha})"


class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    celular = models.CharField(max_length=30, blank=True)
    ciudad = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def saldo(self):
        return sum((v.saldo for v in self.ventas.filter(modalidad="credito")), CERO)


class Venta(models.Model):
    CANALES = [("tienda", "Tienda física"), ("whatsapp", "WhatsApp"), ("instagram", "Instagram"),
               ("facebook", "Facebook / Messenger"), ("tiktok", "TikTok")]
    MODALIDADES = [("contado", "Contado"), ("credito", "Crédito")]

    fecha = models.DateTimeField(default=timezone.now)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT, related_name="ventas")
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT)
    canal = models.CharField(max_length=20, choices=CANALES, default="tienda")
    modalidad = models.CharField(max_length=10, choices=MODALIDADES, default="contado")
    medio_pago = models.CharField(max_length=20, choices=MEDIOS_PAGO, default="efectivo")
    comprobante = models.FileField(upload_to="comprobantes/%Y/%m/", blank=True)
    fecha_limite = models.DateField("Fecha límite de pago", null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def numero(self):
        return f"R-{self.pk:06d}"

    @property
    def pagado(self):
        if self.modalidad == "contado":
            return self.total
        return self.abonos.aggregate(t=Sum("valor"))["t"] or CERO

    @property
    def saldo(self):
        return self.total - self.pagado

    def __str__(self):
        return self.numero


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    variante = models.ForeignKey(Variante, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=0)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario


class Abono(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="abonos")
    fecha = models.DateField(default=timezone.localdate)
    valor = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(1)])
    medio_pago = models.CharField(max_length=20, choices=MEDIOS_PAGO, default="efectivo")
    comprobante = models.FileField(upload_to="comprobantes/%Y/%m/", blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]


class Gasto(models.Model):
    CATEGORIAS = [("mercancia", "Mercancía"), ("arriendo", "Arriendo"), ("servicios", "Servicios"),
                  ("salario", "Salario de la propietaria"), ("otros", "Otros")]
    AMBITOS = [("negocio", "Del negocio"), ("personal", "Personal")]

    fecha = models.DateField(default=timezone.localdate)
    ambito = models.CharField("Tipo de gasto", max_length=10, choices=AMBITOS, default="negocio")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="otros")
    descripcion = models.CharField("Descripción", max_length=200)
    monto = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(1)])
    medio_pago = models.CharField(max_length=20, choices=MEDIOS_PAGO, default="efectivo")

    class Meta:
        ordering = ["-fecha", "-id"]


class CambioPrenda(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="cambios")
    fecha = models.DateTimeField(default=timezone.now)
    variante_devuelta = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="cambios_devueltos",
                                         verbose_name="Prenda que entrega la clienta")
    variante_nueva = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="cambios_entregados",
                                       verbose_name="Prenda nueva que se lleva")
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    diferencia_precio = models.DecimalField("Diferencia a cobrar", max_digits=12, decimal_places=0, default=0,
                                           help_text="Cobro extra si la nueva prenda cuesta más; 0 si fue mano a mano")
    motivo = models.CharField("Motivo del cambio", max_length=200, blank=True,
                              help_text="Ej: Cambio de talla, color o modelo")
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "Cambio de prenda"
        verbose_name_plural = "Cambios de prendas"

    def __str__(self):
        return f"Cambio en {self.venta.numero}: {self.variante_devuelta} → {self.variante_nueva}"


class Merma(models.Model):
    TIPOS = [
        ("dano", "Prenda rota / manchada"),
        ("perdida", "Pérdida / Faltante"),
        ("defecto", "Defecto de fábrica"),
        ("ajuste", "Ajuste de inventario"),
    ]
    fecha = models.DateField(default=timezone.localdate)
    variante = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="mermas")
    tipo = models.CharField(max_length=20, choices=TIPOS, default="dano")
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    motivo = models.CharField("Motivo / Explicación", max_length=250)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "Merma / Ajuste de inventario"
        verbose_name_plural = "Mermas y Ajustes"

    def __str__(self):
        return f"{self.cantidad} x {self.variante} ({self.get_tipo_display()})"

    @property
    def costo_total(self):
        return self.cantidad * self.variante.prenda.costo


class Caja(models.Model):
    ESTADOS = [("abierta", "Abierta"), ("cerrada", "Cerrada")]

    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name="cajas")
    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_apertura = models.DecimalField("Base inicial en efectivo", max_digits=12, decimal_places=0, default=0,
                                         validators=[MinValueValidator(0)])
    estado = models.CharField(max_length=10, choices=ESTADOS, default="abierta")

    # Medios reportados físicamente al cierre
    efectivo_cierre = models.DecimalField("Efectivo contado", max_digits=12, decimal_places=0, default=0)
    nequi_cierre = models.DecimalField("Nequi comprobado", max_digits=12, decimal_places=0, default=0)
    bancolombia_cierre = models.DecimalField("Bancolombia comprobado", max_digits=12, decimal_places=0, default=0)
    daviplata_cierre = models.DecimalField("Daviplata comprobado", max_digits=12, decimal_places=0, default=0)
    datafono_cierre = models.DecimalField("Datáfono Bold comprobado", max_digits=12, decimal_places=0, default=0)
    link_cierre = models.DecimalField("Link de pago comprobado", max_digits=12, decimal_places=0, default=0)

    # Totales del sistema calculados al momento de cerrar
    sistema_efectivo = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    sistema_digital = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    diferencia = models.DecimalField("Diferencia (+ sobrante / - faltante)", max_digits=12, decimal_places=0, default=0)
    observaciones = models.TextField("Observaciones del cierre", blank=True)

    class Meta:
        ordering = ["-fecha_apertura", "-id"]

    def __str__(self):
        return f"Caja #{self.pk} · {self.usuario.username} ({self.get_estado_display()})"
