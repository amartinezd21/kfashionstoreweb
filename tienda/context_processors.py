from .models import es_propietaria


def rol(request):
    return {"es_propietaria": es_propietaria(request.user)}
