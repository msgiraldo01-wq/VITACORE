# =============================================
# VITACORE · Blueprint Radicación
# Archivo: blueprints/bp_financiero/radicacion/radicacion.py
# =============================================

from flask import Blueprint, render_template, request, jsonify, session
from repositories.fin_radicacion_repo import (
    obtener_todas_radicaciones,
    obtener_radicacion_por_id,
    obtener_facturas_para_radicar,
    crear_radicacion,
    actualizar_estado_radicacion,
    obtener_kpis_radicacion,
)

bp_financiero_radicacion = Blueprint(
    "bp_financiero_radicacion",
    __name__,
    url_prefix="/financiero/radicacion"
)


# --------------------------------------------------
# LISTA DE RADICACIONES
# --------------------------------------------------
@bp_financiero_radicacion.route("/")
def radicacion():
    kpis          = obtener_kpis_radicacion()
    radicaciones  = obtener_todas_radicaciones()
    para_radicar  = obtener_facturas_para_radicar()
    return render_template(
        "financiero/radicacion/radicacion.html",
        kpis=kpis,
        radicaciones=radicaciones,
        para_radicar=para_radicar,
    )


# --------------------------------------------------
# API — REGISTRAR RADICACIÓN
# --------------------------------------------------
@bp_financiero_radicacion.route("/registrar", methods=["POST"])
def api_registrar():
    numero_factura  = request.form.get("numero_factura")
    eps             = request.form.get("eps")
    fecha_radicacion = request.form.get("fecha_radicacion")
    canal           = request.form.get("canal", "presencial")
    numero_radicado = request.form.get("numero_radicado")
    observaciones   = request.form.get("observaciones")
    factura_id      = request.form.get("factura_id")
    nit_eps         = request.form.get("nit_eps")
    valor_factura   = request.form.get("valor_factura", 0)

    if not all([numero_factura, eps, fecha_radicacion]):
        return jsonify({"ok": False, "error": "Faltan campos obligatorios"}), 400

    usuario = session.get("user", {}).get("username", "Sistema")
    archivo = request.files.get("soporte")

    try:
        resultado = crear_radicacion({
            "factura_id":      factura_id,
            "numero_factura":  numero_factura,
            "eps":             eps,
            "nit_eps":         nit_eps,
            "valor_factura":   valor_factura,
            "numero_radicado": numero_radicado,
            "fecha_radicacion": fecha_radicacion,
            "canal":           canal,
            "observaciones":   observaciones,
            "registrado_por":  usuario,
        }, archivo=archivo)

        return jsonify({
            "ok":  True,
            "id":  resultado.get("id"),
            "msg": f"Factura {numero_factura} radicada correctamente"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API — ACTUALIZAR ESTADO
# --------------------------------------------------
@bp_financiero_radicacion.route("/actualizar-estado", methods=["POST"])
def api_actualizar_estado():
    body          = request.get_json(silent=True) or {}
    radicacion_id = body.get("radicacion_id")
    nuevo_estado  = body.get("estado")
    motivo        = body.get("motivo")

    if not radicacion_id or not nuevo_estado:
        return jsonify({"ok": False, "error": "Faltan campos obligatorios"}), 400

    usuario = session.get("user", {}).get("username", "Sistema")

    try:
        actualizar_estado_radicacion(radicacion_id, nuevo_estado, motivo, usuario)
        return jsonify({"ok": True, "msg": "Estado actualizado correctamente"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API — FACTURAS DISPONIBLES PARA RADICAR
# --------------------------------------------------
@bp_financiero_radicacion.route("/api/facturas-pendientes", methods=["GET"])
def api_facturas_pendientes():
    try:
        facturas = obtener_facturas_para_radicar()
        return jsonify({"ok": True, "data": facturas})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500