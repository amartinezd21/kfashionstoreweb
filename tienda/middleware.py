from django.shortcuts import redirect
from django.urls import reverse


class CambioClaveObligatorio:
    """RF-01: la vendedora debe cambiar la contraseña inicial al entrar por primera vez."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = request.user
        if u.is_authenticated and getattr(getattr(u, "perfil", None), "debe_cambiar_password", False):
            permitidas = (reverse("cambiar_clave"), reverse("logout"))
            if request.path not in permitidas and not request.path.startswith(("/static/", "/media/")):
                return redirect("cambiar_clave")
        return self.get_response(request)
