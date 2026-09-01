# =============================================
# VITACORE · Blueprint Contabilidad (núcleo)
# Archivo: blueprints/bp_financiero/contabilidad/contabilidad.py
# =============================================

from flask import Blueprint, render_template, request, jsonify, session
from repositories.fin_contabilidad_repo import (
    listar_puc,
    buscar_cuentas,
    listar_terceros,
    buscar_terceros,
    crear_tercero,
    listar_centros_costo,
    listar_comprobantes,
    listar_periodos,
    cambiar_estado_periodo,
    listar_consecutivos,
)
from services.contabilidad_service import (
    preparar_y_registrar_comprobante,
    anular,
    detalle_comprobante,
    obtener_libro_diario,
    obtener_libro_mayor,
    catalogos_para_formulario,
)

bp_financiero_contabilidad = Blueprint(
    "contabilidad", __name__, url_prefix="/financiero/contabilidad"
)


def _usuario():
    return session.get("user", {}).get("username", "Sistema")


# --------------------------------------------------
# DASHBOARD / INICIO DEL MÓDULO
# --------------------------------------------------
@bp_financiero_contabilidad.route("/")
def index():
    comprobantes = listar_comprobantes(limite=20)
    periodos = listar_periodos()
    consecutivos = listar_consecutivos()
    return render_template(
        "financiero/contabilidad/index.html",
        comprobantes=comprobantes,
        periodos=periodos,
        consecutivos=consecutivos,
    )


# --------------------------------------------------
# PLAN DE CUENTAS (PUC)
# --------------------------------------------------
@bp_financiero_contabilidad.route("/puc")
def puc():
    cuentas = listar_puc()
    return render_template(
        "financiero/contabilidad/puc.html",
        cuentas=cuentas,
    )


@bp_financiero_contabilidad.route("/api/buscar-cuentas")
def api_buscar_cuentas():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    return jsonify(buscar_cuentas(q))


# --------------------------------------------------
# TERCEROS
# --------------------------------------------------
@bp_financiero_contabilidad.route("/terceros")
def terceros():
    lista = listar_terceros()
    return render_template(
        "financiero/contabilidad/terceros.html",
        terceros=lista,
    )


@bp_financiero_contabilidad.route("/api/buscar-terceros")
def api_buscar_terceros():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    return jsonify(buscar_terceros(q))


@bp_financiero_contabilidad.route("/api/crear-tercero", methods=["POST"])
def api_crear_tercero():
    body = request.get_json(silent=True) or {}
    if not body.get("numero_documento") or not body.get("razon_social"):
        return jsonify({"ok": False, "error": "Documento y razón social son obligatorios"}), 400

    data = {
        "empresa_id": 1,
        "tipo_documento": body.get("tipo_documento", "NIT"),
        "numero_documento": body.get("numero_documento"),
        "dv": body.get("dv"),
        "tipo_persona": body.get("tipo_persona", "JURIDICA"),
        "razon_social": body.get("razon_social"),
        "es_cliente": body.get("es_cliente", False),
        "es_proveedor": body.get("es_proveedor", False),
        "es_empleado": body.get("es_empleado", False),
        "es_entidad_salud": body.get("es_entidad_salud", False),
        "email": body.get("email"),
        "telefono": body.get("telefono"),
        "created_by": _usuario(),
    }
    try:
        tercero = crear_tercero(data)
        return jsonify({"ok": True, "tercero": tercero})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# NUEVO COMPROBANTE (formulario)
# --------------------------------------------------
@bp_financiero_contabilidad.route("/comprobante/nuevo")
def nuevo_comprobante():
    catalogos = catalogos_para_formulario()
    return render_template(
        "financiero/contabilidad/comprobante_nuevo.html",
        **catalogos,
    )


@bp_financiero_contabilidad.route("/comprobante/registrar", methods=["POST"])
def api_registrar_comprobante():
    body = request.get_json(silent=True) or {}
    form = {
        "tipo_comprobante": body.get("tipo_comprobante"),
        "fecha": body.get("fecha"),
        "descripcion": body.get("descripcion", ""),
        "empresa_id": 1,
        "sede_id": body.get("sede_id"),
    }
    lineas = body.get("lineas", [])

    ok, resultado = preparar_y_registrar_comprobante(form, lineas, _usuario())
    if ok:
        return jsonify({"ok": True, **resultado})
    return jsonify({"ok": False, "error": resultado}), 400


# --------------------------------------------------
# DETALLE DE COMPROBANTE
# --------------------------------------------------
@bp_financiero_contabilidad.route("/comprobante/<int:comprobante_id>")
def detalle(comprobante_id):
    cab, movs = detalle_comprobante(comprobante_id)
    if not cab:
        return "Comprobante no encontrado", 404
    return render_template(
        "financiero/contabilidad/comprobante_detalle.html",
        comprobante=cab,
        movimientos=movs,
    )


@bp_financiero_contabilidad.route("/comprobante/anular", methods=["POST"])
def api_anular_comprobante():
    body = request.get_json(silent=True) or {}
    comprobante_id = body.get("comprobante_id")
    motivo = body.get("motivo", "")
    if not comprobante_id:
        return jsonify({"ok": False, "error": "Falta el comprobante"}), 400

    ok, resultado = anular(int(comprobante_id), _usuario(), motivo)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": resultado}), 400


# --------------------------------------------------
# LIBRO DIARIO
# --------------------------------------------------
@bp_financiero_contabilidad.route("/libro-diario")
def libro_diario():
    periodo = request.args.get("periodo") or None
    filas = obtener_libro_diario(periodo=periodo)
    total_debito = sum(f["debito"] for f in filas)
    total_credito = sum(f["credito"] for f in filas)
    return render_template(
        "financiero/contabilidad/libro_diario.html",
        filas=filas,
        periodo=periodo,
        total_debito=total_debito,
        total_credito=total_credito,
    )


# --------------------------------------------------
# LIBRO MAYOR
# --------------------------------------------------
@bp_financiero_contabilidad.route("/libro-mayor")
def libro_mayor():
    cuenta_id = request.args.get("cuenta_id", type=int)
    periodo = request.args.get("periodo") or None
    cuentas = listar_puc(solo_movimiento=True)

    cuenta = None
    movimientos = []
    totales = {}
    if cuenta_id:
        cuenta, movimientos, totales = obtener_libro_mayor(cuenta_id, periodo=periodo)

    return render_template(
        "financiero/contabilidad/libro_mayor.html",
        cuentas=cuentas,
        cuenta=cuenta,
        cuenta_id=cuenta_id,
        movimientos=movimientos,
        totales=totales,
        periodo=periodo,
    )


# --------------------------------------------------
# PERIODOS (abrir / cerrar)
# --------------------------------------------------
@bp_financiero_contabilidad.route("/periodos/cambiar-estado", methods=["POST"])
def api_cambiar_periodo():
    body = request.get_json(silent=True) or {}
    periodo = body.get("periodo")
    estado = body.get("estado")
    if estado not in ("ABIERTO", "CERRADO"):
        return jsonify({"ok": False, "error": "Estado inválido"}), 400
    try:
        cambiar_estado_periodo(1, periodo, estado, _usuario())
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
