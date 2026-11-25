from django import forms
from django.contrib.auth.models import User

from .models import (Abono, Categoria, Cliente, EntradaMercancia, Gasto, Perfil, Prenda,
                     Proveedor, Variante, Venta, CambioPrenda, Merma, Caja)


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, forms.Select):
                w.attrs["class"] = "form-select"
            else:
                w.attrs["class"] = "form-control"


class FechaInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        super().__init__(format="%Y-%m-%d", **kw)


class CategoriaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]


class PrendaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Prenda
        fields = ["nombre", "categoria", "descripcion", "costo", "gastos_presentacion", "margen", "precio_venta"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}


class VarianteForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Variante
        fields = ["prenda", "talla", "color", "minimo", "proveedor"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prenda"].queryset = Prenda.objects.filter(activa=True)


class EntradaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = EntradaMercancia
        fields = ["variante", "proveedor", "cantidad", "valor_compra", "fecha", "pagada"]
        widgets = {"fecha": FechaInput()}

    def save(self, commit=True):
        entrada = super().save(commit=commit)
        if commit:
            v = entrada.variante
            v.stock += entrada.cantidad          # RF-03: suma al inventario
            v.save(update_fields=["stock"])
            if entrada.pagada:                    # compra pagada = gasto de mercancía
                Gasto.objects.create(
                    fecha=entrada.fecha, categoria="mercancia", monto=entrada.valor_compra,
                    descripcion=f"Compra: {entrada.cantidad} x {v} ({entrada.proveedor})")
        return entrada


class ProveedorForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "telefono", "ciudad"]


class ClienteForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "celular", "ciudad"]


class VentaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Venta
        fields = ["cliente", "canal", "modalidad", "medio_pago", "comprobante", "fecha_limite"]
        widgets = {"fecha_limite": FechaInput()}

    def clean(self):
        datos = super().clean()
        if datos.get("modalidad") == "credito":
            if not datos.get("cliente"):
                self.add_error("cliente", "Una venta a crédito necesita una clienta.")
            if not datos.get("fecha_limite"):
                self.add_error("fecha_limite", "Indica la fecha límite de pago.")
        return datos


class AbonoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Abono
        fields = ["fecha", "valor", "medio_pago", "comprobante"]
        widgets = {"fecha": FechaInput()}

    def __init__(self, *args, venta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.venta = venta

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if self.venta and valor > self.venta.saldo:
            raise forms.ValidationError("El abono no puede ser mayor al saldo pendiente.")
        return valor


class GastoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ["fecha", "ambito", "categoria", "descripcion", "monto", "medio_pago"]
        widgets = {"fecha": FechaInput()}


class VendedoraForm(BootstrapMixin, forms.Form):
    username = forms.CharField(label="Usuario", max_length=150)
    first_name = forms.CharField(label="Nombre", max_length=60)
    password = forms.CharField(label="Contraseña inicial", min_length=6, widget=forms.TextInput)

    def clean_username(self):
        u = self.cleaned_data["username"]
        if User.objects.filter(username=u).exists():
            raise forms.ValidationError("Ese usuario ya existe.")
        return u

    def save(self):
        d = self.cleaned_data
        user = User.objects.create_user(d["username"], first_name=d["first_name"], password=d["password"])
        Perfil.objects.create(user=user, rol="vendedora", debe_cambiar_password=False)
        return user


class CambioPrendaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = CambioPrenda
        fields = ["variante_devuelta", "variante_nueva", "cantidad", "diferencia_precio", "motivo"]

    def __init__(self, *args, venta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.venta = venta
        if venta:
            # Solo permitir devolver prendas que formen parte de la venta
            variantes_venta_ids = venta.detalles.values_list("variante_id", flat=True)
            self.fields["variante_devuelta"].queryset = Variante.objects.filter(pk__in=variantes_venta_ids)
        self.fields["variante_nueva"].queryset = Variante.objects.filter(prenda__activa=True, stock__gt=0).select_related("prenda")

    def clean(self):
        cleaned_data = super().clean()
        nueva = cleaned_data.get("variante_nueva")
        cant = cleaned_data.get("cantidad") or 1
        devuelta = cleaned_data.get("variante_devuelta")

        if nueva and cant > nueva.stock:
            self.add_error("cantidad", f"No hay stock suficiente de {nueva} (quedan {nueva.stock}).")
        if devuelta and nueva and devuelta == nueva:
            self.add_error("variante_nueva", "La prenda nueva debe ser distinta a la que se devuelve (diferente talla, color o modelo).")
        return cleaned_data


class MermaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Merma
        fields = ["variante", "tipo", "cantidad", "motivo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["variante"].queryset = Variante.objects.filter(prenda__activa=True, stock__gt=0).select_related("prenda")

    def clean_cantidad(self):
        cant = self.cleaned_data["cantidad"]
        variante = self.cleaned_data.get("variante")
        if variante and cant > variante.stock:
            raise forms.ValidationError(f"Solo hay {variante.stock} unidades en inventario para dar de baja.")
        return cant


class AperturaCajaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Caja
        fields = ["monto_apertura"]
        labels = {"monto_apertura": "Base en efectivo inicial ($)"}


class CierreCajaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Caja
        fields = [
            "efectivo_cierre",
            "nequi_cierre",
            "bancolombia_cierre",
            "daviplata_cierre",
            "datafono_cierre",
            "link_cierre",
            "observaciones",
        ]
        labels = {
            "efectivo_cierre": "Efectivo físico en caja ($)",
            "nequi_cierre": "Total recibido en Nequi ($)",
            "bancolombia_cierre": "Total recibido en Bancolombia ($)",
            "daviplata_cierre": "Total recibido en Daviplata ($)",
            "datafono_cierre": "Total vouchers Datáfono Bold ($)",
            "link_cierre": "Total recibido en Link de pago ($)",
            "observaciones": "Observaciones / Notas del cierre",
        }
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }

