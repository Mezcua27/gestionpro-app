"""
Genera un PDF profesional de presupuesto usando ReportLab.
"""
from io import BytesIO
from datetime import datetime, timedelta
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image
)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

# ── Colores fijos ─────────────────────────────────────────────────────────────
GRIS_OSCURO = colors.HexColor("#1F2937")
GRIS        = colors.HexColor("#6B7280")
GRIS_CLARO  = colors.HexColor("#F3F4F6")
GRIS_LINEA  = colors.HexColor("#E5E7EB")
ROJO        = colors.HexColor("#B91C1C")
BLANCO      = colors.white

TIPO_COLORES = {
    "Material":      colors.HexColor("#DBEAFE"),
    "Mano de Obra":  colors.HexColor("#D1FAE5"),
    "Mano de obra":  colors.HexColor("#D1FAE5"),
    "Varios":        colors.HexColor("#F3E8FF"),
}


def _corp(empresa) -> colors.HexColor:
    hex_val = getattr(empresa, "color_corporativo", None) or "#1E40AF"
    try:
        return colors.HexColor(hex_val)
    except Exception:
        return colors.HexColor("#1E40AF")


def _corp_claro(c: colors.HexColor) -> colors.Color:
    return colors.Color(
        c.red   + (1 - c.red)   * 0.85,
        c.green + (1 - c.green) * 0.85,
        c.blue  + (1 - c.blue)  * 0.85,
    )


def _estilos(CORP, CORP_CLARO):
    base = getSampleStyleSheet()

    def add(name, **kw):
        if name not in base:
            base.add(ParagraphStyle(name=name, **kw))

    add("EmpresaNombre",   fontSize=17, textColor=CORP,        fontName="Helvetica-Bold", leading=21)
    add("EmpresaDetalle",  fontSize=8,  textColor=GRIS,        fontName="Helvetica",      leading=12)
    add("NumPres",         fontSize=22, textColor=CORP,        fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=26)
    add("FechaLabel",      fontSize=7,  textColor=GRIS,        fontName="Helvetica",      alignment=TA_RIGHT, leading=10)
    add("FechaValor",      fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=12)
    add("SeccionTitulo",   fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold", leading=12)
    add("ClienteValor",    fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold", leading=13)
    add("ClienteDetalle",  fontSize=8,  textColor=GRIS,        fontName="Helvetica",      leading=11)
    add("TablaHeader",     fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_CENTER, leading=11)
    add("TablaHeaderL",    fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_LEFT,   leading=11)
    add("TablaHeaderR",    fontSize=8,  textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_RIGHT,  leading=11)
    add("TablaCell",       fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica",      leading=11)
    add("TablaCellMuted",  fontSize=7,  textColor=GRIS,        fontName="Helvetica",      leading=10)
    add("TablaCellR",      fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica",      alignment=TA_RIGHT, leading=11)
    add("TablaCellBold",   fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=11)
    add("TipoTag",         fontSize=7,  textColor=GRIS_OSCURO, fontName="Helvetica",      leading=10)
    add("GrupoTitulo",     fontSize=8,  textColor=CORP,        fontName="Helvetica-Bold", leading=12)
    add("GrupoSubtotal",   fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=11)
    add("TotalLabel",      fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica",      alignment=TA_RIGHT, leading=13)
    add("TotalValor",      fontSize=9,  textColor=GRIS_OSCURO, fontName="Helvetica",      alignment=TA_RIGHT, leading=13)
    add("TotalFinalLabel", fontSize=12, textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=16)
    add("TotalFinalValor", fontSize=12, textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=16)
    add("Notas",           fontSize=8,  textColor=GRIS,        fontName="Helvetica",      leading=12)
    add("EstadoBadge",     fontSize=9,  textColor=BLANCO,      fontName="Helvetica-Bold", alignment=TA_CENTER, leading=12)
    add("FirmaLabel",      fontSize=7,  textColor=GRIS,        fontName="Helvetica",      alignment=TA_CENTER, leading=10)
    add("FirmaValor",      fontSize=8,  textColor=GRIS_OSCURO, fontName="Helvetica-Bold", alignment=TA_CENTER, leading=12)
    return base


def _fmt(valor: float) -> str:
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _estado_color(estado: str) -> colors.HexColor:
    return {
        "borrador":  colors.HexColor("#6B7280"),
        "enviado":   colors.HexColor("#1D4ED8"),
        "aceptado":  colors.HexColor("#15803D"),
        "rechazado": colors.HexColor("#B91C1C"),
    }.get(estado, colors.HexColor("#6B7280"))


def _barra(texto: str, color, ancho, st) -> Table:
    t = Table([[Paragraph(f"  {texto}", st["SeccionTitulo"])]], colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), color),
        ("TOPPADDING",    (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
    ]))
    return t


def _agrupar_lineas(lineas):
    """
    Detecta líneas que actúan como cabecera de capítulo:
      - tipo vacío o 'Grupo' / 'Capítulo'
      - descripción en MAYÚSCULAS con precio=0 y cantidad=0
    """
    grupos = []
    actual = {"titulo": None, "lineas": []}

    for l in lineas:
        tipo = (l.tipo or "").strip()
        desc = (l.descripcion or "").strip()
        es_cabecera = (
            tipo in ("", "Grupo", "Capítulo", "capitulo", "grupo")
            or (desc == desc.upper() and len(desc) > 3
                and (l.precio_unitario or 0) == 0
                and (l.cantidad or 0) == 0)
        )
        if es_cabecera:
            if actual["lineas"] or actual["titulo"]:
                grupos.append(actual)
            actual = {"titulo": desc, "lineas": []}
        else:
            actual["lineas"].append(l)

    if actual["lineas"] or actual["titulo"]:
        grupos.append(actual)

    # Sin agrupación real → devolver tal cual
    if len(grupos) == 1 and not grupos[0]["titulo"]:
        return [{"titulo": None, "lineas": lineas}]
    return grupos


def generar_pdf(presupuesto, empresa, cliente, static_dir: str = None) -> bytes:
    """
    Parámetros
    ----------
    presupuesto : models.Presupuesto
    empresa     : models.Empresa
    cliente     : models.Cliente | None
    static_dir  : ruta a app/static  (para cargar el logo)
                  Pasa BASE_DIR desde main.py:
                  from app.pdf_generator import generar_pdf
                  pdf = generar_pdf(p, empresa, cliente,
                                    static_dir=os.path.join(BASE_DIR, "static"))
    """
    buf    = BytesIO()
    CORP   = _corp(empresa)
    CORP_C = _corp_claro(CORP)
    st     = _estilos(CORP, CORP_C)
    W      = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN + 10 * mm,
        title=f"{presupuesto.numero} - {presupuesto.titulo}",
        author=empresa.nombre,
    )
    story = []

    # ── CABECERA ──────────────────────────────────────────────────────────────
    izq = []

    # Logo — guardado como data URI en PostgreSQL
    logo_field = getattr(empresa, "logo", None)
    if logo_field and logo_field.startswith("data:"):
        try:
            import base64 as _b64, tempfile
            header, b64data = logo_field.split(",", 1)
            logo_bytes = _b64.b64decode(b64data)
            ext = "jpg" if ("jpeg" in header or "jpg" in header) else "png"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            tmp.write(logo_bytes)
            tmp.flush()
            tmp.close()
            img = Image(tmp.name)
            img._restrictSize(W * 0.40, 20 * mm)  # fuerza la carga y limita tamaño
            img.drawHeight = min(img.drawHeight, 14 * mm)
            img.drawWidth  = img.drawWidth * (img.drawHeight / max(img.drawHeight, 0.1))
            izq.append(img)
            izq.append(Spacer(1, 3))
            import atexit as _atexit
            _atexit.register(lambda p=tmp.name: os.remove(p) if os.path.exists(p) else None)
        except Exception as _e:
            print(f"[PDF] Error cargando logo: {_e}")

    izq.append(Paragraph(empresa.nombre, st["EmpresaNombre"]))
    for campo, prefijo in [("nif", "NIF: "), ("direccion", ""), ("telefono", "Tel: "), ("email", "")]:
        val = getattr(empresa, campo, None)
        if val:
            izq.append(Paragraph(f"{prefijo}{val}", st["EmpresaDetalle"]))

    fecha_emision = presupuesto.fecha.strftime("%d/%m/%Y") if presupuesto.fecha else datetime.today().strftime("%d/%m/%Y")
    fecha_validez = (
        (presupuesto.fecha + timedelta(days=presupuesto.validez_dias)).strftime("%d/%m/%Y")
        if presupuesto.fecha and presupuesto.validez_dias else "—"
    )

    der = [
        Paragraph(presupuesto.numero, st["NumPres"]),
        Spacer(1, 4),
        Paragraph("Fecha de emisión", st["FechaLabel"]),
        Paragraph(fecha_emision,      st["FechaValor"]),
        Paragraph("Válido hasta",     st["FechaLabel"]),
        Paragraph(fecha_validez,      st["FechaValor"]),
    ]

    cab = Table([[izq, der]], colWidths=[W * 0.58, W * 0.42])
    cab.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cab)
    story.append(Spacer(1, 4 * mm))

    # Badge estado
    badge = Table([[Paragraph(presupuesto.estado.upper(), st["EstadoBadge"])]], colWidths=[28 * mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), _estado_color(presupuesto.estado)),
        ("TOPPADDING",    (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ("LEFTPADDING",   (0, 0), (0, 0), 8),
        ("RIGHTPADDING",  (0, 0), (0, 0), 8),
    ]))
    story.append(badge)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width=W, color=CORP_C, thickness=1.5))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(presupuesto.titulo, ParagraphStyle(
        "Tit", fontSize=13, textColor=GRIS_OSCURO, fontName="Helvetica-Bold", leading=17
    )))
    story.append(Spacer(1, 5 * mm))

    # ── CLIENTE ───────────────────────────────────────────────────────────────
    if cliente:
        story.append(_barra("DATOS DEL CLIENTE", CORP, W, st))
        story.append(Spacer(1, 2 * mm))

        col1 = [Paragraph(cliente.nombre, st["ClienteValor"])]
        if cliente.nif:
            col1.append(Paragraph(f"NIF/CIF: {cliente.nif}", st["ClienteDetalle"]))
        col2, col3 = [], []
        if cliente.telefono:
            col2.append(Paragraph(f"📞 {cliente.telefono}", st["ClienteDetalle"]))
        if cliente.email:
            col2.append(Paragraph(f"✉ {cliente.email}", st["ClienteDetalle"]))
        if cliente.direccion:
            col3.append(Paragraph(f"📍 {cliente.direccion}", st["ClienteDetalle"]))

        ct = Table([[col1, col2, col3]], colWidths=[W * 0.4, W * 0.3, W * 0.3])
        ct.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND",   (0, 0), (-1, -1), GRIS_CLARO),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ]))
        story.append(ct)
        story.append(Spacer(1, 5 * mm))

    # ── LÍNEAS ────────────────────────────────────────────────────────────────
    story.append(_barra("DETALLE DEL PRESUPUESTO", CORP, W, st))
    story.append(Spacer(1, 1 * mm))

    # Tipo | Descripción+Ref | Cant | Ud | P.Unit | Total
    CW = [W*0.10, W*0.44, W*0.07, W*0.07, W*0.14, W*0.16]

    datos = [[
        Paragraph("TIPO",        st["TablaHeader"]),
        Paragraph("DESCRIPCIÓN", st["TablaHeaderL"]),
        Paragraph("CANT.",       st["TablaHeaderR"]),
        Paragraph("UD.",         st["TablaHeader"]),
        Paragraph("P. UNIT.",    st["TablaHeaderR"]),
        Paragraph("TOTAL",       st["TablaHeaderR"]),
    ]]
    estilo = [
        ("BACKGROUND",    (0, 0), (-1, 0), CORP),
        ("TOPPADDING",    (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, 0), 0.5, CORP),
    ]

    grupos   = _agrupar_lineas(presupuesto.lineas)
    hay_grps = any(g["titulo"] for g in grupos)
    subtots  = []
    ri       = 1  # row index (0 = header)

    for grupo in grupos:
        titulo = grupo["titulo"]
        lins   = grupo["lineas"]

        # Fila de cabecera de capítulo
        if hay_grps and titulo:
            datos.append([
                Paragraph("", st["TablaCell"]),
                Paragraph(titulo, st["GrupoTitulo"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
            ])
            estilo += [
                ("BACKGROUND", (0, ri), (-1, ri), CORP_C),
                ("TOPPADDING", (0, ri), (-1, ri), 5),
                ("BOTTOMPADDING", (0, ri), (-1, ri), 5),
                ("LINEABOVE",  (0, ri), (-1, ri), 0.5, CORP),
                ("SPAN",       (0, ri), (-1, ri)),
            ]
            ri += 1

        subtotal = 0.0
        for i, linea in enumerate(lins):
            total_l  = (linea.cantidad or 0) * (linea.precio_unitario or 0)
            subtotal += total_l
            bg_row   = GRIS_CLARO if i % 2 == 0 else BLANCO
            bg_tipo  = TIPO_COLORES.get(linea.tipo, GRIS_CLARO)
            ref      = getattr(linea, "referencia", None) or ""
            unidad   = getattr(linea, "unidad", None) or "ud"

            celda_desc = [Paragraph(linea.descripcion or "", st["TablaCell"])]
            if ref:
                celda_desc.append(Paragraph(f"Ref: {ref}", st["TablaCellMuted"]))

            datos.append([
                Paragraph(linea.tipo or "", st["TipoTag"]),
                celda_desc,
                Paragraph(f"{linea.cantidad:g}", st["TablaCellR"]),
                Paragraph(unidad, st["TablaCell"]),
                Paragraph(_fmt(linea.precio_unitario or 0), st["TablaCellR"]),
                Paragraph(_fmt(total_l), st["TablaCellBold"]),
            ])
            estilo += [
                ("BACKGROUND",    (0, ri), (0, ri), bg_tipo),
                ("BACKGROUND",    (1, ri), (-1, ri), bg_row),
                ("TOPPADDING",    (0, ri), (-1, ri), 4),
                ("BOTTOMPADDING", (0, ri), (-1, ri), 4),
                ("LINEBELOW",     (0, ri), (-1, ri), 0.3, GRIS_LINEA),
            ]
            ri += 1

        # Fila subtotal del capítulo
        if hay_grps and titulo and lins:
            subtots.append((titulo, subtotal))
            datos.append([
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("", st["TablaCell"]),
                Paragraph("Subtotal", st["GrupoSubtotal"]),
                Paragraph(_fmt(subtotal), st["GrupoSubtotal"]),
            ])
            estilo += [
                ("BACKGROUND",    (0, ri), (-1, ri), CORP_C),
                ("TOPPADDING",    (0, ri), (-1, ri), 4),
                ("BOTTOMPADDING", (0, ri), (-1, ri), 4),
                ("LINEABOVE",     (0, ri), (-1, ri), 0.5, CORP),
                ("LINEBELOW",     (0, ri), (-1, ri), 0.8, CORP),
            ]
            ri += 1

    if not presupuesto.lineas:
        datos.append([
            Paragraph("", st["TablaCell"]),
            Paragraph("Sin líneas", st["TablaCell"]),
            Paragraph("", st["TablaCellR"]),
            Paragraph("", st["TablaCell"]),
            Paragraph("", st["TablaCellR"]),
            Paragraph("", st["TablaCellR"]),
        ])

    tbl = Table(datos, colWidths=CW, repeatRows=1)
    tbl.setStyle(TableStyle(estilo))
    story.append(tbl)
    story.append(Spacer(1, 4 * mm))

    # ── TOTALES ───────────────────────────────────────────────────────────────
    total_base  = sum(
        (l.cantidad or 0) * (l.precio_unitario or 0)
        for l in presupuesto.lineas
        if not ((l.tipo or "") in ("", "Grupo", "Capítulo")
                and (l.precio_unitario or 0) == 0
                and (l.cantidad or 0) == 0)
    )
    descuento   = presupuesto.descuento or 0
    iva_pct     = presupuesto.iva or 21
    total_dto   = total_base * (descuento / 100)
    total_iva   = (total_base - total_dto) * (iva_pct / 100)
    total_final = total_base - total_dto + total_iva

    tots = [
        ["", Paragraph("Base imponible", st["TotalLabel"]),
              Paragraph(_fmt(total_base), st["TotalValor"])],
    ]
    if descuento > 0:
        tots.append(["", Paragraph(f"Descuento ({descuento}%)", st["TotalLabel"]),
                         Paragraph(f"- {_fmt(total_dto)}", st["TotalValor"])])
    tots.append(["", Paragraph(f"IVA ({iva_pct}%)", st["TotalLabel"]),
                     Paragraph(_fmt(total_iva), st["TotalValor"])])

    ts = Table(tots, colWidths=[W*0.55, W*0.25, W*0.20])
    ts_style = [
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("ALIGN",        (2, 0), (2, -1), "RIGHT"),
    ]
    if descuento > 0:
        for i, row in enumerate(tots):
            if "escuento" in str(row[1]):
                ts_style.append(("TEXTCOLOR", (2, i), (2, i), ROJO))
    ts.setStyle(TableStyle(ts_style))
    story.append(ts)
    story.append(Spacer(1, 1 * mm))

    tf = Table(
        [["", Paragraph("TOTAL", st["TotalFinalLabel"]),
               Paragraph(_fmt(total_final), st["TotalFinalValor"])]],
        colWidths=[W*0.55, W*0.25, W*0.20]
    )
    tf.setStyle(TableStyle([
        ("BACKGROUND",    (1, 0), (2, 0), CORP),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(tf)

    # ── NOTAS ─────────────────────────────────────────────────────────────────
    if presupuesto.notas:
        story.append(Spacer(1, 5 * mm))
        story.append(_barra("NOTAS Y CONDICIONES", GRIS_OSCURO, W, st))
        story.append(Spacer(1, 2 * mm))
        nt = Table([[Paragraph(presupuesto.notas, st["Notas"])]], colWidths=[W])
        nt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), GRIS_CLARO),
            ("TOPPADDING",    (0, 0), (0, 0), 6),
            ("BOTTOMPADDING", (0, 0), (0, 0), 6),
            ("LEFTPADDING",   (0, 0), (0, 0), 8),
            ("RIGHTPADDING",  (0, 0), (0, 0), 8),
        ]))
        story.append(nt)

    # ── FIRMA Y ACEPTACIÓN ────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(_barra("FIRMA Y ACEPTACIÓN", CORP, W, st))
    story.append(Spacer(1, 4 * mm))

    fecha_acept = (
        presupuesto.fecha_aceptacion.strftime("%d/%m/%Y")
        if presupuesto.fecha_aceptacion else "______/______/________"
    )

    def _bloque_firma(titulo_linea, nombre_linea, nif_linea):
        return Table([
            [Paragraph(titulo_linea, st["FirmaLabel"])],
            [Spacer(1, 14 * mm)],
            [HRFlowable(width=W * 0.28, color=GRIS, thickness=0.5)],
            [Paragraph(nombre_linea, st["FirmaValor"])],
            [Paragraph(nif_linea, st["FirmaLabel"])],
            [Paragraph(f"Fecha: {fecha_acept}", st["FirmaLabel"])],
        ], colWidths=[W * 0.40])

    firma = Table(
        [[
            _bloque_firma(
                "Conforme — Firma del cliente",
                cliente.nombre if cliente else "",
                f"NIF/CIF: {cliente.nif}" if cliente and cliente.nif else "",
            ),
            Spacer(W * 0.05, 1),
            _bloque_firma(
                f"Por {empresa.nombre}",
                empresa.nombre,
                f"NIF: {empresa.nif}" if empresa.nif else "",
            ),
        ]],
        colWidths=[W * 0.45, W * 0.10, W * 0.45]
    )
    firma.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",   (0, 0), (0, 0), GRIS_CLARO),
        ("BACKGROUND",   (2, 0), (2, 0), GRIS_CLARO),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(KeepTogether(firma))

    # ── PIE DE PÁGINA ─────────────────────────────────────────────────────────
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(CORP_C)
        canvas.rect(MARGIN, 8 * mm, W, 0.4 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIS)
        txt = empresa.nombre
        if empresa.email:    txt += f"  ·  {empresa.email}"
        if empresa.telefono: txt += f"  ·  {empresa.telefono}"
        canvas.drawCentredString(PAGE_W / 2, 5 * mm, txt)
        canvas.drawRightString(PAGE_W - MARGIN, 5 * mm, f"Pág. {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
