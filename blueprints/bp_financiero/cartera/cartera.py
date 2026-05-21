# =============================================
# VITACORE · Blueprint Cartera
# Archivo: blueprints/bp_financiero/cartera/cartera.py
# =============================================

from flask import Blueprint, render_template, request, jsonify, session
from repositories.fin_cartera_repo import (
    obtener_todas_facturas,
    obtener_factura_por_numero,
    obtener_pagos_por_factura,
    registrar_pago,
    obtener_kpis_cartera,
    actualizar_dias_mora,
)

from flask import Blueprint, render_template, request, jsonify, session, Response
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

bp_financiero_cartera = Blueprint("cartera", __name__, url_prefix="/financiero/cartera")


# --------------------------------------------------
# LISTA DE CARTERA
# --------------------------------------------------
@bp_financiero_cartera.route("/")
def index():
    actualizar_dias_mora()
    facturas = obtener_todas_facturas()
    kpis     = obtener_kpis_cartera()
    return render_template(
    "financiero/cartera/cartera.html",
        facturas=facturas,
        kpis=kpis,
    )


# --------------------------------------------------
# DETALLE DE UNA FACTURA
# --------------------------------------------------
@bp_financiero_cartera.route("/detalle/<numero_factura>")
def detalle(numero_factura):
    factura = obtener_factura_por_numero(numero_factura)
    pagos   = obtener_pagos_por_factura(numero_factura)

    if not factura:
        return "Factura no encontrada", 404

    return render_template(
        "financiero/cartera/cartera_detalle.html",
        data=factura,
        pagos=pagos,
    )


# --------------------------------------------------
# REGISTRAR PAGO (API JSON)
# --------------------------------------------------
@bp_financiero_cartera.route("/registrar-pago", methods=["POST"])
def api_registrar_pago():
    # Recibe multipart/form-data (archivo + campos)
    factura_id      = request.form.get("factura_id")
    numero_factura  = request.form.get("numero_factura")
    valor_pago      = request.form.get("valor_pago")
    fecha_pago      = request.form.get("fecha_pago")

    if not all([factura_id, numero_factura, valor_pago, fecha_pago]):
        return jsonify({"ok": False, "error": "Faltan campos obligatorios"}), 400

    usuario = session.get("user", {}).get("username", "Sistema")

    data = {
        "factura_id":          factura_id,
        "numero_factura":      numero_factura,
        "valor_pago":          valor_pago,
        "fecha_pago":          fecha_pago,
        "banco":               request.form.get("banco"),
        "tipo_pago":           request.form.get("tipo_pago", "Transferencia"),
        "referencia_bancaria": request.form.get("referencia_bancaria"),
        "observacion":         request.form.get("observacion"),
        "registrado_por":      usuario,
    }

    archivo = request.files.get("soporte")

    try:
        registrar_pago(data, archivo=archivo)
        return jsonify({"ok": True, "mensaje": "Pago registrado correctamente"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    
def obtener_facturas_para_excel():
    """Retorna todas las facturas con formato listo para Excel."""
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_facturas")
        .select("numero_factura, eps, nit_eps, valor_factura, valor_pagado, valor_glosas, saldo_pendiente, dias_mora, estado, fecha_radicacion, fecha_vencimiento, ultimo_pago, responsable")
        .order("dias_mora", desc=True)
        .execute()
    )
    return response.data or []

@bp_financiero_cartera.route("/exportar-excel")
def exportar_excel():
    from repositories.fin_cartera_repo import obtener_facturas_para_excel

    facturas = obtener_facturas_para_excel()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cartera"

    # ── Estilos ──────────────────────────────────
    color_header  = "0D5C63"
    color_alt     = "F0F7F8"

    fuente_header = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    fuente_normal = Font(name="Calibri", size=10)
    fuente_total  = Font(name="Calibri", bold=True, size=11)

    relleno_header = PatternFill("solid", fgColor=color_header)
    relleno_alt    = PatternFill("solid", fgColor=color_alt)

    borde = Border(
        left=Side(style="thin", color="D9E4E7"),
        right=Side(style="thin", color="D9E4E7"),
        top=Side(style="thin", color="D9E4E7"),
        bottom=Side(style="thin", color="D9E4E7"),
    )

    centro = Alignment(horizontal="center", vertical="center")
    derecha = Alignment(horizontal="right", vertical="center")

    # ── Título ───────────────────────────────────
    ws.merge_cells("A1:M1")
    titulo = ws["A1"]
    titulo.value = "VITACORE · REPORTE DE CARTERA HOSPITALARIA"
    titulo.font = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    titulo.fill = PatternFill("solid", fgColor=color_header)
    titulo.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:M2")
    from datetime import date
    subtitulo = ws["A2"]
    subtitulo.value = f"Generado: {date.today().strftime('%d/%m/%Y')}  ·  Total facturas: {len(facturas)}"
    subtitulo.font = Font(name="Calibri", size=10, color="5E7278")
    subtitulo.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # ── Encabezados ──────────────────────────────
    encabezados = [
        "Factura", "EPS", "NIT EPS",
        "Valor factura", "Pagado", "Glosas",
        "Saldo pendiente", "Días mora", "Estado",
        "F. radicación", "F. vencimiento", "Último pago",
        "Responsable"
    ]

    anchos = [18, 20, 16, 16, 14, 12, 16, 10, 14, 14, 14, 14, 18]

    for col, (titulo_col, ancho) in enumerate(zip(encabezados, anchos), start=1):
        celda = ws.cell(row=3, column=col, value=titulo_col)
        celda.font      = fuente_header
        celda.fill      = relleno_header
        celda.alignment = centro
        celda.border    = borde
        ws.column_dimensions[celda.column_letter].width = ancho

    ws.row_dimensions[3].height = 24

    # ── Datos ────────────────────────────────────
    total_factura  = 0
    total_pagado   = 0
    total_glosas   = 0
    total_saldo    = 0

    for idx, f in enumerate(facturas, start=4):
        relleno_fila = relleno_alt if idx % 2 == 0 else PatternFill()

        valores = [
            f.get("numero_factura", ""),
            f.get("eps", ""),
            f.get("nit_eps", ""),
            f.get("valor_factura", 0),
            f.get("valor_pagado", 0),
            f.get("valor_glosas", 0),
            f.get("saldo_pendiente", 0),
            f.get("dias_mora", 0),
            f.get("estado", "").replace("_", " ").title(),
            f.get("fecha_radicacion", ""),
            f.get("fecha_vencimiento", ""),
            f.get("ultimo_pago", ""),
            f.get("responsable", ""),
        ]

        for col, valor in enumerate(valores, start=1):
            celda = ws.cell(row=idx, column=col, value=valor)
            celda.font   = fuente_normal
            celda.fill   = relleno_fila
            celda.border = borde

            # Formato moneda
            if col in [4, 5, 6, 7]:
                celda.number_format = '$#,##0'
                celda.alignment = derecha
            elif col == 8:
                celda.alignment = centro
            else:
                celda.alignment = Alignment(vertical="center")

        # Acumular totales
        total_factura += f.get("valor_factura", 0) or 0
        total_pagado  += f.get("valor_pagado",  0) or 0
        total_glosas  += f.get("valor_glosas",  0) or 0
        total_saldo   += f.get("saldo_pendiente", 0) or 0

    # ── Fila de totales ──────────────────────────
    fila_total = len(facturas) + 4
    relleno_total = PatternFill("solid", fgColor="0D5C63")

    ws.merge_cells(f"A{fila_total}:C{fila_total}")
    celda_label = ws[f"A{fila_total}"]
    celda_label.value     = "TOTALES"
    celda_label.font      = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    celda_label.fill      = relleno_total
    celda_label.alignment = centro
    celda_label.border    = borde

    for col, total in enumerate([total_factura, total_pagado, total_glosas, total_saldo], start=4):
        celda = ws.cell(row=fila_total, column=col, value=total)
        celda.font          = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
        celda.fill          = relleno_total
        celda.number_format = '$#,##0'
        celda.alignment     = derecha
        celda.border        = borde

    for col in range(8, 14):
        celda = ws.cell(row=fila_total, column=col, value="")
        celda.fill   = relleno_total
        celda.border = borde

    ws.row_dimensions[fila_total].height = 24

    # ── Freeze panes y filtros ───────────────────
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:M{fila_total - 1}"

    # ── Exportar ─────────────────────────────────
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"cartera_vitacore_{date.today().strftime('%Y%m%d')}.xlsx"

    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )
    