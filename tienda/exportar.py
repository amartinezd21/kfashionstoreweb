import csv
import io
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet


VINO_HEX = "5A0F2E"
CREMA_HEX = "F7EED9"
DURAZNO_HEX = "FDBDA0"
DURAZNO_SUAVE_HEX = "FDF3EE"


def _cop_str(valor):
    return f"$ {int(valor or 0):,}".replace(",", ".")


def respuesta_csv(nombre_archivo, encabezados, filas):
    """Genera un CSV compatible con Excel (UTF-8 con BOM y separador ';')."""
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.csv"'
    writer = csv.writer(resp, delimiter=";")
    writer.writerow(encabezados)
    for fila in filas:
        writer.writerow(fila)
    return resp


def respuesta_excel(nombre_archivo, hojas):
    """
    Genera un archivo .xlsx estilizado con identidad K Fashion Store.
    `hojas`: lista de tuplas (titulo_hoja, encabezados, filas, columnas_moneda)
    """
    wb = Workbook()
    wb.remove(wb.active)

    fill_header = PatternFill(start_color=VINO_HEX, end_color=VINO_HEX, fill_type="solid")
    fill_alt = PatternFill(start_color=DURAZNO_SUAVE_HEX, end_color=DURAZNO_SUAVE_HEX, fill_type="solid")
    font_header = Font(name="Calibri", size=11, bold=True, color=CREMA_HEX)
    font_body = Font(name="Calibri", size=10, color="2B1020")
    border_thin = Border(
        bottom=Side(style="thin", color=DURAZNO_HEX),
        top=Side(style="thin", color=DURAZNO_HEX),
    )

    for titulo, encabezados, filas, cols_moneda in hojas:
        ws = wb.create_sheet(title=titulo[:31])
        ws.append(encabezados)

        for col_idx in range(1, len(encabezados) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = fill_header
            cell.font = font_header
            cell.alignment = Alignment(horizontal="center" if col_idx in cols_moneda else "left", vertical="center")
        ws.row_dimensions[1].height = 24

        for row_idx, fila in enumerate(filas, start=2):
            ws.append(list(fila))
            for col_idx in range(1, len(encabezados) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = font_body
                cell.border = border_thin
                if row_idx % 2 == 0:
                    cell.fill = fill_alt
                if col_idx in cols_moneda and isinstance(cell.value, (int, float, Decimal)):
                    cell.number_format = '"$ "#,##0'
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(vertical="center")

        # Ajuste automático de anchos
        for col_idx in range(1, len(encabezados) + 1):
            max_len = max(
                [len(str(ws.cell(row=r, column=col_idx).value or "")) for r in range(1, len(filas) + 2)],
                default=10,
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 4, 12), 42)

        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.xlsx"'
    return resp


MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def generar_recibo_pdf(venta):
    """Genera un recibo PDF minimalista idéntico a la factura de la tienda."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )

    oscuro = colors.HexColor("#1E1D1D")
    borde_tabla = colors.HexColor("#2B2929")
    gris_linea = colors.HexColor("#D4D4D4")
    gris_texto = colors.HexColor("#555252")
    rojo = colors.HexColor("#A4161A")

    styles = getSampleStyleSheet()
    st_eyebrow = ParagraphStyle("Eyebrow", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=oscuro, spaceAfter=4)
    st_titulo = ParagraphStyle("Titulo", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=26, textColor=oscuro, alignment=0, spaceAfter=18)
    st_meta_izq = ParagraphStyle("MetaIzq", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=oscuro, leading=14)
    st_meta_der = ParagraphStyle("MetaDer", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=oscuro, alignment=2, leading=14)
    st_celda = ParagraphStyle("Celda", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=oscuro, leading=13)
    st_celda_sub = ParagraphStyle("CeldaSub", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, textColor=gris_texto, leading=11)
    st_cred = ParagraphStyle("Cred", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, textColor=oscuro, alignment=2, spaceBefore=8)
    st_pie = ParagraphStyle("Pie", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=oscuro, leading=14, spaceBefore=22)

    elementos = []

    # Encabezado superior: FACTURA / Recibo de pago
    elementos.append(Paragraph("FACTURA", st_eyebrow))
    elementos.append(Paragraph("Recibo de pago", st_titulo))

    # Dos columnas de metadatos
    f_loc = timezone.localtime(venta.fecha)
    fecha_txt = f"{f_loc.day} de {MESES_ES[f_loc.month - 1]} de {f_loc.year}"
    cliente_nombre = venta.cliente.nombre if venta.cliente else "Cliente de mostrador"
    cliente_tel = venta.cliente.celular if venta.cliente and venta.cliente.celular else ""
    cliente_ciudad = venta.cliente.ciudad if venta.cliente and venta.cliente.ciudad else "Cartagena, Colombia"

    izq_html = f"<font color='#555252'>Número:</font><br/>{venta.numero}<br/><br/><font color='#555252'>Fecha:</font><br/>{fecha_txt}"
    der_partes = [f"<b>{cliente_nombre}</b>"]
    if cliente_tel:
        der_partes.append(cliente_tel)
    der_partes.append(cliente_ciudad)
    der_partes.append(f"<font color='#555252' size='8.5'>{venta.get_modalidad_display()} · {venta.get_medio_pago_display()}</font>")
    der_html = "<br/>".join(der_partes)

    t_meta = Table(
        [[Paragraph(izq_html, st_meta_izq), Paragraph(der_html, st_meta_der)]],
        colWidths=[86 * mm, 86 * mm],
    )
    t_meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(t_meta)
    elementos.append(Spacer(1, 10 * mm))

    # Tabla principal: N° | Nombre | Cantidad | Precio | Subtotal
    tabla_data = [["N°", "Nombre", "Cantidad", "Precio", "Subtotal"]]
    detalles = list(venta.detalles.select_related("variante__prenda"))
    for idx, d in enumerate(detalles, start=1):
        desc = Paragraph(
            f"{d.variante.prenda.nombre}<br/><font size='8.5' color='#555252'>{d.variante.talla} · {d.variante.color}</font>",
            st_celda,
        )
        tabla_data.append([
            str(idx),
            desc,
            str(d.cantidad),
            _cop_str(d.precio_unitario),
            _cop_str(d.subtotal),
        ])

    # Fila espaciadora para mantener el cuerpo amplio estilo factura de hoja
    tabla_data.append(["", "", "", "", ""])
    fila_spacer_idx = len(tabla_data) - 1

    # Fila Total
    tabla_data.append(["Total", "", "", "", _cop_str(venta.total)])
    fila_total_idx = len(tabla_data) - 1

    col_widths = [14 * mm, 76 * mm, 24 * mm, 28 * mm, 30 * mm]
    row_heights = [None] * len(tabla_data)
    row_heights[0] = 9.5 * mm
    row_heights[fila_spacer_idx] = 42 * mm
    row_heights[fila_total_idx] = 10 * mm

    t_fact = Table(tabla_data, colWidths=col_widths, rowHeights=row_heights)
    t_fact.setStyle(TableStyle([
        # Caja exterior
        ("BOX", (0, 0), (-1, -1), 1, borde_tabla),
        # Cabecera oscura
        ("BACKGROUND", (0, 0), (-1, 0), oscuro),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("LINEBEFORE", (1, 0), (-1, 0), 0.5, colors.HexColor("#4A4848")),
        # Cuerpo con líneas verticales finas
        ("FONTNAME", (0, 1), (-1, fila_spacer_idx), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, fila_spacer_idx), 10),
        ("TEXTCOLOR", (0, 1), (-1, fila_spacer_idx), oscuro),
        ("LINEBEFORE", (1, 1), (-1, fila_spacer_idx), 0.5, gris_linea),
        # Alineaciones
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("VALIGN", (0, 1), (-1, fila_spacer_idx), "TOP"),
        # Fila Total oscura
        ("SPAN", (0, fila_total_idx), (3, fila_total_idx)),
        ("BACKGROUND", (0, fila_total_idx), (-1, fila_total_idx), oscuro),
        ("TEXTCOLOR", (0, fila_total_idx), (-1, fila_total_idx), colors.white),
        ("FONTNAME", (0, fila_total_idx), (-1, fila_total_idx), "Helvetica-Bold"),
        ("FONTSIZE", (0, fila_total_idx), (-1, fila_total_idx), 10.5),
        ("ALIGN", (0, fila_total_idx), (3, fila_total_idx), "RIGHT"),
        ("VALIGN", (0, fila_total_idx), (-1, fila_total_idx), "MIDDLE"),
        ("LINEBEFORE", (4, fila_total_idx), (4, fila_total_idx), 0.5, colors.HexColor("#4A4848")),
        # Paddings
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(t_fact)

    if venta.modalidad == "credito":
        elementos.append(Paragraph(
            f"Abonado: <b>{_cop_str(venta.pagado)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Saldo pendiente: <font color='#A4161A'><b>{_cop_str(venta.saldo)}</b></font>",
            st_cred,
        ))

    cambios = list(venta.cambios.select_related("variante_devuelta__prenda", "variante_nueva__prenda"))
    if cambios:
        elementos.append(Spacer(1, 4 * mm))
        for c in cambios:
            elementos.append(Paragraph(
                f"Cambio ({c.fecha.strftime('%d/%m/%Y')}): {c.variante_devuelta} → {c.variante_nueva}",
                st_celda_sub,
            ))

    # Pie abajo izquierda
    elementos.append(Paragraph(
        "<b>K Fashion Store</b><br/>Moda casual para mujeres reales · Cartagena, Colombia<br/>Gracias por tu compra.",
        st_pie,
    ))

    doc.build(elementos)
    buf.seek(0)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Recibo_{venta.numero}.pdf"'
    return resp
