from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from tienda.models import Categoria, Cliente, Perfil, Prenda, Proveedor, Variante


class Command(BaseCommand):
    help = "Crea la usuaria propietaria y datos de ejemplo para probar la aplicación."

    def handle(self, *args, **opts):
        if not User.objects.filter(username="propietaria").exists():
            u = User.objects.create_user("propietaria", first_name="Propietaria", password="kfashion123")
            Perfil.objects.create(user=u, rol="propietaria")
            self.stdout.write("Usuaria creada: propietaria / kfashion123  (cámbiala al entrar)")
        prov, _ = Proveedor.objects.get_or_create(nombre="Confecciones Medellín", defaults={"telefono": "3000000000", "ciudad": "Medellín"})
        Cliente.objects.get_or_create(nombre="Clienta de ejemplo", defaults={"celular": "3100000000", "ciudad": "Cartagena"})
        datos = [("Enterizo", "Enterizos", 45000, 89900), ("Vestido", "Vestidos", 52000, 99900),
                 ("Crop top", "Crop tops", 15000, 39900), ("Falda", "Faldas", 28000, 64900)]
        for nombre, cat, costo, precio in datos:
            c, _ = Categoria.objects.get_or_create(nombre=cat)
            p, creada = Prenda.objects.get_or_create(
                nombre=nombre, defaults={"categoria": c, "costo": costo, "gastos_presentacion": 1500, "precio_venta": precio})
            if creada:
                for talla in ("S", "M", "L"):
                    Variante.objects.create(prenda=p, talla=talla, color="Negro", stock=5, minimo=2, proveedor=prov)
        self.stdout.write(self.style.SUCCESS("Datos de ejemplo listos."))
