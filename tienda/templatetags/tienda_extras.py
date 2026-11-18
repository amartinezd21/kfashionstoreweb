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


@register.filter
def total_prendas(variantes):
    try:
        return sum(v.stock for v in variantes)
    except Exception:
        return 0


@register.filter
def total_reponer_count(variantes):
    try:
        return sum(1 for v in variantes if getattr(v, "por_reponer", False))
    except Exception:
        return 0


@register.filter
def total_costo_inventario(variantes):
    try:
        return sum(v.stock * getattr(v.prenda, "costo", 0) for v in variantes)
    except Exception:
        return 0


@register.filter
def color_hex(color_nombre):
    c = str(color_nombre or "").strip().lower()
    colores = {
        "negro": "#222222",
        "blanco": "#f0f0f0",
        "beige": "#dfc9ab",
        "pistacho": "#9bb885",
        "terracota": "#c45b43",
        "chocolate": "#533324",
        "azul": "#2a52be",
        "rojo": "#c82a3b",
        "rosa": "#e899a8",
        "rosado": "#e899a8",
        "verde": "#42824a",
        "amarillo": "#dfb135",
        "gris": "#8c8c8c",
        "morado": "#6f2c7a",
        "lila": "#b391b5"
    }
    return colores.get(c, "#a87c74")



