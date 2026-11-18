from django import template

register = template.Library()


@register.filter
def cop(valor):
    """Formato de pesos colombianos: $ 89.900"""
    try:
        return "$ " + f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$ 0"


@register.filter
def total_negocio(gastos):
    try:
        return sum(g.monto for g in gastos if getattr(g, "ambito", "") == "negocio" and getattr(g, "categoria", "") != "salario")
    except Exception:
        return 0


@register.filter
def total_salario(gastos):
    try:
        return sum(g.monto for g in gastos if getattr(g, "categoria", "") == "salario")
    except Exception:
        return 0


@register.filter
def total_personal(gastos):
    try:
        return sum(g.monto for g in gastos if getattr(g, "ambito", "") == "personal")
    except Exception:
        return 0


@register.filter
def total_deuda_proveedores(proveedores):
    try:
        return sum(p.saldo for p in proveedores)
    except Exception:
        return 0


@register.filter
def con_saldo_count(proveedores):
    try:
        return sum(1 for p in proveedores if p.saldo > 0)
    except Exception:
        return 0


