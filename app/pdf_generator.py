"""
Genera un PDF profesional de presupuesto usando ReportLab.
"""
from io import BytesIO
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Colores de marca ──────────────────────────────────────────────────────────
AZUL        = colors.HexColor("#1E40AF")   # azul corporativo
AZUL_CLARO  = colors.HexColor("#DBEAFE")
GRIS_OSCURO = colors.HexColor("#1F2937")
GRIS        = colors.HexColor("#6B7280")
GRIS_CLARO  = colors.HexColor("#F3F4F6")
VERDE       = colors.HexColor("#15803D")
ROJO        = colors.HexColor("#B91C1C")
BLANCO      = colors.white

# Colores por tipo de línea
TIPO_COLORES = {
    "Material":     colors.HexColor("#DBEAFE"),
    "Mano de Obra": colors.HexColor("#D1FAE5"),
    "Varios":       colors.HexColor("#F3E8FF"),
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _estilos():
    base = getSampleStyleSheet()

    def add(name, **kw):
        base.add(ParagraphStyle(name=name, **kw))

    add("EmpresaNombre",   fontSize=18, textColor=AZUL,        fontName="Helvetica-Bold",  leading=22)
    add("EmpresaDetalle",  fontSize=8,  textColor=GRIS,        fontName="Helvetica",       leading=12)
    add("NumPres",         fontSize=22, textColor=AZUL,        fontName="Helvetica-Bold",  alignment=TA_RIGHT, leading=26)
    add("FechaLabel",      fontSize=7,  textColor=GRIS,        fontName="Helvetica",       alignment=TA_RIGHT, leading=10)
    add("FechaValor",      fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold",  alignment=TA_RIGHT, leading=12)
    add("SeccionTitulo",   fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold",  leading=12)
    add("ClienteLabel",    fontSize=7,  textColor=GRIS,        fontName="Helvetica",       leading=10)
    add("ClienteValor",    fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold",  leading=13)
    add("ClienteDetalle",  fontSize=8,  textColor=GRIS,        fontName="Helvetica",       leading=11)
    add("TablaHeader",     fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold",  alignment=TA_CENTER, leading=11)
    add("TablaHeaderR",    fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold",  alignment=TA_RIGHT,  leading=11)
    add("TablaCell",       fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica",       leading=11)
    add("TablaCellR",      fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica",       alignment=TA_RIGHT,  leading=11)
    add("TablaCellBold",   fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold",  leading=11)
    add("TipoTag",         fontSize=7,  textColor=GRIS_OSCURO, fontName="Helvetica",       leading=10)
    add("TotalLabel",      fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica",       alignment=TA_RIGHT,  leading=13)
    add("TotalValor",      fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica",       alignment=TA_RIGHT,  leading=13)
    add("TotalFinalLabel", fontSize=12, textColor=BLANCO,      fontName="Helvetica-Bold",  alignment=TA_RIGHT,  leading=16)
    add("TotalFinalValor", fontSize=12, textColor=BLANCO,      fontName="Helvetica-Bold",  alignment=TA_RIGHT,  leading=16)
    add("Notas",           fontSize=8,  textColor=GRIS,        fontName="Helvetica",       leading=12)
    add("NotasTitulo",     fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold",  leading=12)
    add("Footer",          fontSize=7,  textColor=GRIS,        fontName="Helvetica",       alignment=TA_CENTER, leading=10)
    add("EstadoBadge",     fontSize=9,  textColor=BLANCO,      fontName="Helvetica-Bold",  alignment=TA_CENTER, leading=12)
    return base


def _fmt(valor: float) -> str:
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _estado_color(estado: str):
    return {
        "borrador":  colors.HexColor("#6B7280"),
        "enviado":   colors.HexColor("#1D4ED8"),
        "aceptado":  colors.HexColor("#15803D"),
        "rechazado": colors.HexColor("#B91C1C"),
    }.get(estado, GRIS)


def generar_pdf(presupuesto, empresa, cliente) -> bytes:
    buf = BytesIO()
    st = _estilos()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN + 10 * mm,
        title=f"{presupuesto.numero} - {presupuesto.titulo}",
        author=empresa.nombre,
    )

    story = []
    W = PAGE_W - 2 * MARGIN

    # ── CABECERA: empresa (izq) + número presupuesto (der) ───────────────────
    empresa_lines = [Paragraph(empresa.nombre, st["EmpresaNombre"])]
    if empresa.nif:
        empresa_lines.append(Paragraph(f"NIF: {empresa.nif}", st["EmpresaDetalle"]))
    if empresa.direccion:
        empresa_lines.append(Paragraph(empresa.direccion, st["EmpresaDetalle"]))
    if empresa.telefono:
        empresa_lines.append(Paragraph(f"Tel: {empresa.telefono}", st["EmpresaDetalle"]))
    if empresa.email:
        empresa_lines.append(Paragraph(empresa.email, st["EmpresaDetalle"]))

    fecha_emision = presupuesto.fecha.strftime("%d/%m/%Y") if presupuesto.fecha else datetime.today().strftime("%d/%m/%Y")
    fecha_validez = (presupuesto.fecha + timedelta(days=presupuesto.validez_dias)).strftime("%d/%m/%Y") \
        if presupuesto.fecha else "—"

    pres_lines = [
        Paragraph(presupuesto.numero, st["NumPres"]),
        Spacer(1, 4),
        Paragraph("Fecha de emisión",  st["FechaLabel"]),
        Paragraph(fecha_emision,       st["FechaValor"]),
        Paragraph("Válido hasta",      st["FechaLabel"]),
        Paragraph(fecha_validez,       st["FechaValor"]),
    ]

    header_tbl = Table(
        [[empresa_lines, pres_lines]],
        colWidths=[W * 0.58, W * 0.42]
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4 * mm))

    # Estado badge
    estado_col = _estado_color(presupuesto.estado)
    estado_tbl = Table(
        [[Paragraph(presupuesto.estado.upper(), st["EstadoBadge"])]],
        colWidths=[28 * mm]
    )
    estado_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, 0), estado_col),
        ("ROUNDEDCORNERS", [3]),
        ("TOPPADDING",   (0, 0), (0, 0), 4),
        ("BOTTOMPADDING",(0, 0), (0, 0), 4),
        ("LEFTPADDING",  (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
    ]))
    story.append(estado_tbl)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width=W, color=AZUL_CLARO, thickness=1.5))
    story.append(Spacer(1, 4 * mm))

    # ── TÍTULO DEL PRESUPUESTO ────────────────────────────────────────────────
    titulo_style = ParagraphStyle("T", fontSize=13, textColor=GRIS_OSCURO,
                                  fontName="Helvetica-Bold", leading=17)
    story.append(Paragraph(presupuesto.titulo, titulo_style))
    story.append(Spacer(1, 5 * mm))

    # ── BLOQUE CLIENTE ────────────────────────────────────────────────────────
    if cliente:
        sec_header = Table(
            [[Paragraph("  DATOS DEL CLIENTE", st["SeccionTitulo"])]],
            colWidths=[W]
        )
        sec_header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), AZUL),
            ("TOPPADDING",    (0, 0), (0, 0), 4),
            ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ]))
        story.append(sec_header)
        story.append(Spacer(1, 2 * mm))

        cli_data = []
        col1 = [Paragraph(cliente.nombre, st["ClienteValor"])]
        if cliente.nif:
            col1.append(Paragraph(f"NIF/CIF: {cliente.nif}", st["ClienteDetalle"]))
        col2 = []
        if cliente.telefono:
            col2.append(Paragraph(f"📞 {cliente.telefono}", st["ClienteDetalle"]))
        if cliente.email:
            col2.append(Paragraph(f"✉ {cliente.email}", st["ClienteDetalle"]))
        col3 = []
        if cliente.direccion:
            col3.append(Paragraph(f"📍 {cliente.direccion}", st["ClienteDetalle"]))

        cli_tbl = Table([[col1, col2, col3]], colWidths=[W * 0.4, W * 0.3, W * 0.3])
        cli_tbl.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND",   (0, 0), (-1, -1), GRIS_CLARO),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(cli_tbl)
        story.append(Spacer(1, 5 * mm))

    # ── TABLA DE LÍNEAS ───────────────────────────────────────────────────────
    sec_lineas = Table(
        [[Paragraph("  DETALLE DEL PRESUPUESTO", st["SeccionTitulo"])]],
        colWidths=[W]
    )
    sec_lineas.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), AZUL),
        ("TOPPADDING",    (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
    ]))
    story.append(sec_lineas)
    story.append(Spacer(1, 1 * mm))

    # Anchos columnas: Tipo | Descripción | Cant | P.Unit | Total
    CW = [W * 0.12, W * 0.46, W * 0.10, W * 0.16, W * 0.16]

    lineas_data = [[
        Paragraph("TIPO",          st["TablaHeader"]),
        Paragraph("DESCRIPCIÓN",   st["TablaHeader"]),
        Paragraph("CANT.",         st["TablaHeaderR"]),
        Paragraph("P. UNIT.",      st["TablaHeaderR"]),
        Paragraph("TOTAL",         st["TablaHeaderR"]),
    ]]

    lineas_style = [
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0), AZUL),
        ("TOPPADDING",   (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",    (0, 0), (-1, 0), 0.5, AZUL),
    ]

    for i, linea in enumerate(presupuesto.lineas):
        total_linea = linea.cantidad * linea.precio_unitario
        row_bg = GRIS_CLARO if i % 2 == 0 else BLANCO
        tipo_bg = TIPO_COLORES.get(linea.tipo, GRIS_CLARO)

        row = [
            Paragraph(linea.tipo, st["TipoTag"]),
            Paragraph(linea.descripcion, st["TablaCell"]),
            Paragraph(f"{linea.cantidad:g}", st["TablaCellR"]),
            Paragraph(_fmt(linea.precio_unitario), st["TablaCellR"]),
            Paragraph(_fmt(total_linea), st["TablaCellBold"] if True else st["TablaCellR"]),
        ]
        lineas_data.append(row)
        idx = i + 1
        lineas_style += [
            ("BACKGROUND",    (0, idx), (0, idx), tipo_bg),
            ("BACKGROUND",    (1, idx), (-1, idx), row_bg),
            ("TOPPADDING",    (0, idx), (-1, idx), 4),
            ("BOTTOMPADDING", (0, idx), (-1, idx), 4),
            ("LINEBELOW",     (0, idx), (-1, idx), 0.3, colors.HexColor("#E5E7EB")),
        ]

    if not presupuesto.lineas:
        lineas_data.append([
            Paragraph("", st["TablaCell"]),
            Paragraph("Sin líneas", st["TablaCell"]),
            Paragraph("", st["TablaCellR"]),
            Paragraph("", st["TablaCellR"]),
            Paragraph("", st["TablaCellR"]),
        ])

    lineas_tbl = Table(lineas_data, colWidths=CW, repeatRows=1)
    lineas_tbl.setStyle(TableStyle(lineas_style))
    story.append(lineas_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── TOTALES ───────────────────────────────────────────────────────────────
    total_base = sum(l.cantidad * l.precio_unitario for l in presupuesto.lineas)
    total_dto  = total_base * (presupuesto.descuento / 100)
    total_iva  = (total_base - total_dto) * (presupuesto.iva / 100)
    total_final = total_base - total_dto + total_iva

    tot_data = []
    tot_data.append(["", Paragraph("Base imponible", st["TotalLabel"]), Paragraph(_fmt(total_base), st["TotalValor"])])
    if presupuesto.descuento > 0:
        tot_data.append(["", Paragraph(f"Descuento ({presupuesto.descuento}%)", st["TotalLabel"]),
                         Paragraph(f"- {_fmt(total_dto)}", st["TotalValor"])])
    tot_data.append(["", Paragraph(f"IVA ({presupuesto.iva}%)", st["TotalLabel"]), Paragraph(_fmt(total_iva), st["TotalValor"])])

    tot_tbl = Table(tot_data, colWidths=[W * 0.55, W * 0.25, W * 0.20])
    tot_tbl_style = [
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
    ]
    if presupuesto.descuento > 0:
        for row_i in range(len(tot_data)):
            if "escuento" in str(tot_data[row_i][1]):
                tot_tbl_style.append(("TEXTCOLOR", (2, row_i), (2, row_i), ROJO))
    tot_tbl.setStyle(TableStyle(tot_tbl_style))
    story.append(tot_tbl)
    story.append(Spacer(1, 1 * mm))

    # Línea total final
    final_tbl = Table(
        [["", Paragraph("TOTAL", st["TotalFinalLabel"]), Paragraph(_fmt(total_final), st["TotalFinalValor"])]],
        colWidths=[W * 0.55, W * 0.25, W * 0.20]
    )
    final_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (1, 0), (2, 0), AZUL),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(final_tbl)

    # ── NOTAS ─────────────────────────────────────────────────────────────────
    if presupuesto.notas:
        story.append(Spacer(1, 5 * mm))
        sec_notas = Table(
            [[Paragraph("  NOTAS Y CONDICIONES", st["SeccionTitulo"])]],
            colWidths=[W]
        )
        sec_notas.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), GRIS_OSCURO),
            ("TOPPADDING",    (0, 0), (0, 0), 4),
            ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ]))
        story.append(sec_notas)
        story.append(Spacer(1, 2 * mm))
        notas_tbl = Table(
            [[Paragraph(presupuesto.notas, st["Notas"])]],
            colWidths=[W]
        )
        notas_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (0, 0), GRIS_CLARO),
            ("TOPPADDING",   (0, 0), (0, 0), 6),
            ("BOTTOMPADDING",(0, 0), (0, 0), 6),
            ("LEFTPADDING",  (0, 0), (0, 0), 8),
            ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ]))
        story.append(notas_tbl)

    # ── PIE DE PÁGINA ─────────────────────────────────────────────────────────
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(AZUL_CLARO)
        canvas.rect(MARGIN, 8 * mm, W, 0.3 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIS)
        texto = f"{empresa.nombre}"
        if empresa.email:
            texto += f"  ·  {empresa.email}"
        if empresa.telefono:
            texto += f"  ·  {empresa.telefono}"
        canvas.drawCentredString(PAGE_W / 2, 5 * mm, texto)
        canvas.drawRightString(PAGE_W - MARGIN, 5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
