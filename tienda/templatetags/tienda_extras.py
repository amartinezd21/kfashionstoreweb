from django import template

register = template.Library()


@register.filter
def cop(valor):
    """Formato de pesos colombianos: $ 89.900"""
    try:
        return "$ " + f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$ 0"
