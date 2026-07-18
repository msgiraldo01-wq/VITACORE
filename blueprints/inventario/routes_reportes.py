import csv
import io
from datetime import date

from flask import Response, flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp

# Definición de cada reporte: título, función y columnas (clave → encabezado CSV)
REPORTES = {
    "sismed": {
        "titulo": "SISMED — Compras de medicamentos",
        "ayuda": "Precios y cantidades de adquisición por período (Circular 06 y ss.). "
                 "Base para el reporte al SISMED.",
        "cols": [("fecha_recepcion", "FECHA"), ("nit_proveedor", "NIT PROVEEDOR"),
                 ("proveedor", "PROVEEDOR"), ("factura", "FACTURA"), ("cum", "CUM"),
                 ("producto", "PRODUCTO"), ("concentracion", "CONCENTRACION"),
                 ("forma_farmaceutica", "FORMA FARMACEUTICA"), ("laboratorio", "LABORATORIO"),
                 ("registro_invima", "REGISTRO INVIMA"), ("numero_lote", "LOTE"),
                 ("fecha_vencimiento", "VENCIMIENTO"), ("cantidad", "CANTIDAD"),
                 ("valor_unitario", "VALOR UNITARIO"), ("valor_total", "VALOR TOTAL")],
        "fechas": True,
    },
    "control_especial": {
        "titulo": "Control especial — Libro de movimientos (FNE)",
        "ayuda": "Entradas, salidas y saldos de medicamentos de control especial y "
                 "monopolio del Estado. Soporte del reporte al Fondo Nacional de Estupefacientes.",
        "cols": [("fecha", "FECHA"), ("codigo_interno", "CODIGO"), ("medicamento", "MEDICAMENTO"),
                 ("concentracion", "CONCENTRACION"), ("cum", "CUM"),
                 ("registro_invima", "REGISTRO INVIMA"), ("tipo_control", "TIPO CONTROL"),
                 ("numero_lote", "LOTE"), ("movimiento", "MOVIMIENTO"),
                 ("cantidad", "CANTIDAD"), ("saldo", "SALDO"),
                 ("paciente_id", "PACIENTE"), ("numero_formula", "N° FORMULA"),
                 ("registrado_por", "REGISTRO POR")],
        "fechas": True,
    },
    "consumo": {
        "titulo": "Consumo por producto y mes",
        "ayuda": "Unidades y costo de lo dispensado/consumido. Base para rotación y presupuesto.",
        "cols": [("mes", "MES"), ("codigo_interno", "CODIGO"), ("producto", "PRODUCTO"),
                 ("concentracion", "CONCENTRACION"), ("tipo_producto", "TIPO"),
                 ("unidades_salidas", "UNIDADES"), ("costo_total", "COSTO TOTAL")],
        "fechas": True,
    },
    "vencimientos": {
        "titulo": "Próximos a vencer y vencidos",
        "ayuda": "Semáforo por lote: VENCIDO, ROJO (≤3 meses), AMARILLO (≤6), VERDE.",
        "cols": [("semaforo", "SEMAFORO"), ("fecha_vencimiento", "VENCE"),
                 ("producto", "PRODUCTO"), ("concentracion", "CONCENTRACION"),
                 ("bodega", "BODEGA"), ("numero_lote", "LOTE"),
                 ("cantidad", "CANTIDAD"), ("costo_promedio", "COSTO PROM"), ("valor", "VALOR")],
        "fechas": False,
    },
    "valorizacion": {
        "titulo": "Valorización de inventario",
        "ayuda": "Existencias por bodega y lote con su valor a costo promedio ponderado.",
        "cols": [("bodega", "BODEGA"), ("producto", "PRODUCTO"), ("concentracion", "CONCENTRACION"),
                 ("tipo_producto", "TIPO"), ("numero_lote", "LOTE"),
                 ("fecha_vencimiento", "VENCE"), ("cantidad", "CANTIDAD"),
                 ("costo_promedio", "COSTO PROM"), ("valor", "VALOR")],
        "fechas": False,
    },
    "sin_movimiento": {
        "titulo": "Inventario sin movimiento",
        "ayuda": "Existencias con su última fecha de salida. Detecta capital inmovilizado.",
        "cols": [("codigo_interno", "CODIGO"), ("producto", "PRODUCTO"),
                 ("concentracion", "CONCENTRACION"), ("bodega", "BODEGA"),
                 ("existencia", "EXISTENCIA"), ("valor", "VALOR"),
                 ("ultima_salida", "ULTIMA SALIDA")],
        "fechas": False,
    },
}


def _datos(clave, empresa_id, desde, hasta):
    if clave == "sismed":
        return repo.rep_sismed(empresa_id, desde, hasta)
    if clave == "control_especial":
        return repo.rep_control_especial(empresa_id, desde, hasta)
    if clave == "consumo":
        return repo.rep_consumo(empresa_id, desde, hasta)
    if clave == "vencimientos":
        return repo.rep_vencimientos(empresa_id, request.args.get("semaforo", ""))
    if clave == "valorizacion":
        return repo.rep_valorizacion(empresa_id)
    if clave == "sin_movimiento":
        return repo.rep_sin_movimiento(empresa_id)
    return []


@inventario_bp.route("/reportes")
@contexto_empresa
def reportes(empresa_id, usuario_id):
    return render_template("inventario/reportes/index.html", reportes=REPORTES)


@inventario_bp.route("/reportes/<clave>")
@contexto_empresa
def reportes_ver(empresa_id, usuario_id, clave):
    if clave not in REPORTES:
        flash("Reporte no disponible.", "error")
        return redirect(url_for("inventario.reportes"))
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    filas = _datos(clave, empresa_id, desde, hasta)
    return render_template("inventario/reportes/ver.html",
                           clave=clave, cfg=REPORTES[clave], filas=filas,
                           desde=desde, hasta=hasta,
                           semaforo=request.args.get("semaforo", ""))


@inventario_bp.route("/reportes/<clave>/csv")
@contexto_empresa
def reportes_csv(empresa_id, usuario_id, clave):
    if clave not in REPORTES:
        flash("Reporte no disponible.", "error")
        return redirect(url_for("inventario.reportes"))
    cfg = REPORTES[clave]
    filas = _datos(clave, empresa_id, request.args.get("desde", ""),
                   request.args.get("hasta", ""))
    salida = io.StringIO()
    # delimiter ';' y BOM: Excel en español abre el archivo con las columnas separadas
    w = csv.writer(salida, delimiter=";")
    w.writerow([h for _, h in cfg["cols"]])
    for f in filas:
        w.writerow([f.get(k) if f.get(k) is not None else "" for k, _ in cfg["cols"]])
    contenido = "\ufeff" + salida.getvalue()
    nombre = f"{clave}_{date.today().isoformat()}.csv"
    return Response(contenido, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


# ============================ FARMACOVIGILANCIA ============================

@inventario_bp.route("/farmacovigilancia", methods=["GET", "POST"])
@contexto_empresa
def farmacovigilancia(empresa_id, usuario_id):
    if request.method == "POST":
        descripcion = request.form.get("descripcion", "").strip()
        fecha_evento = request.form.get("fecha_evento")
        if not descripcion or not fecha_evento:
            flash("La fecha y la descripción del evento son obligatorias.", "error")
        else:
            repo.crear_evento_fv({
                "empresa_id": empresa_id,
                "paciente_id": int(request.form["paciente_id"]) if request.form.get("paciente_id") else None,
                "producto_id": request.form.get("producto_id") or None,
                "fecha_evento": fecha_evento,
                "tipo": request.form.get("tipo", "EVENTO_ADVERSO"),
                "descripcion": descripcion,
                "gravedad": request.form.get("gravedad") or None,
                "desenlace": request.form.get("desenlace", "").strip() or None,
                "reportado_por": usuario_id,
            })
            flash("Evento registrado. Recuerde reportarlo al INVIMA según su gravedad.", "success")
        return redirect(url_for("inventario.farmacovigilancia"))
    return render_template("inventario/reportes/farmacovigilancia.html",
                           eventos=repo.listar_eventos_fv(empresa_id),
                           productos=repo.listar_productos(empresa_id))


@inventario_bp.route("/farmacovigilancia/<evento_id>/reportado", methods=["POST"])
@contexto_empresa
def farmacovigilancia_reportado(empresa_id, usuario_id, evento_id):
    repo.marcar_fv_reportado(evento_id, request.form.get("fecha") or date.today().isoformat())
    flash("Evento marcado como reportado al INVIMA.", "success")
    return redirect(url_for("inventario.farmacovigilancia"))