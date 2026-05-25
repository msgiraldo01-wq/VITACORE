"""
Rutas del módulo de caja — Vitacore
Blueprint: bp_caja  →  /caja/...
"""

from flask import Blueprint, render_template, request, jsonify, session
from repositories import fin_caja_repo as caja_repo

bp_caja = Blueprint(
    "caja",
    __name__,
    url_prefix="/caja",
    template_folder="templates",
)


def _get_usuario():
    """Obtiene datos del usuario logueado desde la sesión."""
    user = session.get("user", {})
    return {
        "id": user.get("id", ""),
        "nombre": user.get("full_name") or user.get("username", ""),
    }


# =============================================================
# VISTAS HTML
# =============================================================

@bp_caja.route("/")
def index():
    """Página principal del módulo de caja."""
    return render_template("financiero/caja/caja.html")


# =============================================================
# API — ESTADO DE CAJA DEL USUARIO
# =============================================================

@bp_caja.route("/api/estado", methods=["GET"])
def api_estado_caja():
    """Consulta si el usuario tiene caja abierta."""
    try:
        usuario = _get_usuario()
        caja = caja_repo.obtener_caja_abierta(usuario["id"])

        if caja:
            sede = caja.pop("hc_sedes", None) or {}
            caja["sede_nombre"] = sede.get("nombre", "")

        return jsonify({
            "ok": True,
            "caja_abierta": caja is not None,
            "caja": caja,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — ABRIR CAJA
# =============================================================

@bp_caja.route("/api/abrir", methods=["POST"])
def api_abrir_caja():
    """Abre una caja para el usuario logueado."""
    try:
        usuario = _get_usuario()
        data = request.get_json(force=True, silent=True) or {}

        sede_id = data.get("sede_id")
        if not sede_id:
            return jsonify({"ok": False, "error": "Seleccione una sede"}), 400

        # Verificar que no tenga caja abierta
        existente = caja_repo.obtener_caja_abierta(usuario["id"])
        if existente:
            return jsonify({"ok": False, "error": "Ya tiene una caja abierta"}), 400

        caja = caja_repo.abrir_caja({
            "sede_id": int(sede_id),
            "usuario_id": usuario["id"],
            "usuario_nombre": usuario["nombre"],
            "valor_base": float(data.get("valor_base", 0)),
        })

        if not caja:
            return jsonify({"ok": False, "error": "Error al abrir caja"}), 500

        return jsonify({"ok": True, "caja": caja})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — CERRAR CAJA
# =============================================================

@bp_caja.route("/api/cerrar", methods=["POST"])
def api_cerrar_caja():
    """Cierra la caja del usuario con los datos del conteo."""
    try:
        usuario = _get_usuario()
        data = request.get_json(force=True, silent=True) or {}

        caja_id = data.get("caja_id")
        if not caja_id:
            return jsonify({"ok": False, "error": "caja_id es requerido"}), 400

        # Verificar que la caja sea del usuario
        caja = caja_repo.obtener_caja(caja_id)
        if not caja:
            return jsonify({"ok": False, "error": "Caja no encontrada"}), 404

        if caja.get("usuario_id") != usuario["id"]:
            return jsonify({"ok": False, "error": "Solo el usuario que abrió la caja puede cerrarla"}), 403

        if caja.get("estado") == "CERRADA":
            return jsonify({"ok": False, "error": "La caja ya está cerrada"}), 400

        resultado = caja_repo.cerrar_caja(caja_id, data)

        return jsonify({
            "ok": True,
            "caja": resultado,
            "msg": "Caja cerrada correctamente",
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — MOVIMIENTOS DE LA CAJA
# =============================================================

@bp_caja.route("/api/movimientos/<int:caja_id>", methods=["GET"])
def api_movimientos(caja_id):
    """Lista los movimientos de una caja."""
    try:
        movimientos = caja_repo.listar_movimientos(caja_id)
        resumen = caja_repo.resumen_movimientos(caja_id)
        return jsonify({"ok": True, "data": movimientos, "resumen": resumen})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — REGISTRAR MOVIMIENTO MANUAL
# =============================================================

@bp_caja.route("/api/movimiento", methods=["POST"])
def api_registrar_movimiento():
    """Registra un movimiento manual en la caja."""
    try:
        usuario = _get_usuario()
        data = request.get_json(force=True, silent=True) or {}

        # Verificar caja abierta
        caja = caja_repo.obtener_caja_abierta(usuario["id"])
        if not caja:
            return jsonify({"ok": False, "error": "No tiene caja abierta"}), 400

        tipo = data.get("tipo")
        medio_pago = data.get("medio_pago")
        valor = data.get("valor")

        if not all([tipo, medio_pago, valor]):
            return jsonify({"ok": False, "error": "tipo, medio_pago y valor son requeridos"}), 400

        movimiento = caja_repo.registrar_movimiento({
            "caja_id": caja["id"],
            "tipo": tipo,
            "medio_pago": medio_pago,
            "valor": float(valor),
            "descripcion": data.get("descripcion", ""),
            "paciente_id": data.get("paciente_id"),
            "paciente_nombre": data.get("paciente_nombre", ""),
        })

        return jsonify({"ok": True, "data": movimiento})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — CONTEO EN TIEMPO REAL
# =============================================================

@bp_caja.route("/api/conteo/<int:caja_id>", methods=["GET"])
def api_obtener_conteo(caja_id):
    """Obtiene el conteo actual de la caja."""
    try:
        conteo = caja_repo.obtener_conteo(caja_id)
        return jsonify({"ok": True, "data": conteo})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_caja.route("/api/conteo/<int:caja_id>", methods=["POST"])
def api_guardar_conteo(caja_id):
    """Guarda el conteo completo y registra cambios en historial."""
    try:
        usuario = _get_usuario()
        data = request.get_json(force=True, silent=True) or {}

        conteo = caja_repo.guardar_conteo_completo(
            caja_id, data, usuario["id"], usuario["nombre"]
        )

        return jsonify({"ok": True, "data": conteo})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — HISTORIAL DE CONTEO (AUDITORÍA)
# =============================================================

@bp_caja.route("/api/conteo/<int:caja_id>/historial", methods=["GET"])
def api_conteo_historial(caja_id):
    """Lista el historial de cambios del conteo."""
    try:
        historial = caja_repo.listar_conteo_historial(caja_id)
        return jsonify({"ok": True, "data": historial})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — DETALLE DE CAJA (para reporte)
# =============================================================

@bp_caja.route("/api/detalle/<int:caja_id>", methods=["GET"])
def api_detalle_caja(caja_id):
    """Obtiene todos los datos de una caja para el reporte."""
    try:
        caja = caja_repo.obtener_caja(caja_id)
        if not caja:
            return jsonify({"ok": False, "error": "Caja no encontrada"}), 404

        sede = caja.pop("hc_sedes", None) or {}
        caja["sede_nombre"] = sede.get("nombre", "")

        movimientos = caja_repo.listar_movimientos(caja_id)
        resumen = caja_repo.resumen_movimientos(caja_id)

        return jsonify({
            "ok": True,
            "caja": caja,
            "movimientos": movimientos,
            "resumen": resumen,
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — HISTORIAL DE CAJAS
# =============================================================

@bp_caja.route("/api/historial", methods=["GET"])
def api_historial_cajas():
    """Lista las últimas cajas del usuario logueado."""
    try:
        usuario = _get_usuario()
        sede_id = request.args.get("sede_id", type=int)
        cajas = caja_repo.listar_cajas(sede_id=sede_id, usuario_id=usuario["id"])

        for c in cajas:
            sede = c.pop("hc_sedes", None) or {}
            c["sede_nombre"] = sede.get("nombre", "")

        return jsonify({"ok": True, "data": cajas})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_caja.route("/cuadre/<int:caja_id>/reporte")
def reporte_cuadre(caja_id):
    """Vista HTML del reporte de cuadre de caja para imprimir/PDF."""
    return render_template("financiero/caja/caja_reporte.html", caja_id=caja_id)