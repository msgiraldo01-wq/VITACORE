# =============================================
# VITACORE · Blueprint Contabilidad (núcleo)
# Archivo: blueprints/bp_financiero/contabilidad/contabilidad.py
# =============================================

from flask import Blueprint, render_template, request, jsonify, session
from blueprints.auth.decorators import login_required
from services.permisos_service import requiere_permiso
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
from services import error_service
from services import contabilizacion_service

bp_financiero_contabilidad = Blueprint(
    "contabilidad", __name__, url_prefix="/financiero/contabilidad"
)


def _usuario():
    return session.get("user", {}).get("username", "Sistema")


# --------------------------------------------------
# DASHBOARD / INICIO DEL MÓDULO
# --------------------------------------------------
@bp_financiero_contabilidad.route("/")
@login_required
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
@login_required
def puc():
    cuentas = listar_puc()
    return render_template(
        "financiero/contabilidad/puc.html",
        cuentas=cuentas,
    )


@bp_financiero_contabilidad.route("/api/buscar-cuentas")
@login_required
def api_buscar_cuentas():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    return jsonify(buscar_cuentas(q))


# --------------------------------------------------
# TERCEROS
# --------------------------------------------------
@bp_financiero_contabilidad.route("/terceros")
@login_required
def terceros():
    lista = listar_terceros()
    return render_template(
        "financiero/contabilidad/terceros.html",
        terceros=lista,
    )


@bp_financiero_contabilidad.route("/api/buscar-terceros")
@login_required
def api_buscar_terceros():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    return jsonify(buscar_terceros(q))


@bp_financiero_contabilidad.route("/api/crear-tercero", methods=["POST"])
@login_required
@requiere_permiso("contabilidad", "create")
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
        codigo = error_service.registrar(e)
        return jsonify({"ok": False, "error": f"Ocurrió un error inesperado. Código: {codigo}", "codigo": codigo}), 500


# --------------------------------------------------
# NUEVO COMPROBANTE (formulario)
# --------------------------------------------------
@bp_financiero_contabilidad.route("/comprobante/nuevo")
@login_required
def nuevo_comprobante():
    catalogos = catalogos_para_formulario()
    return render_template(
        "financiero/contabilidad/comprobante_nuevo.html",
        **catalogos,
    )


@bp_financiero_contabilidad.route("/comprobante/registrar", methods=["POST"])
@login_required
@requiere_permiso("contabilidad", "create")
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
@login_required
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
@login_required
@requiere_permiso("contabilidad", "edit")
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
@login_required
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
@login_required
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
@login_required
@requiere_permiso("contabilidad", "edit")
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
        codigo = error_service.registrar(e)
        return jsonify({"ok": False, "error": f"Ocurrió un error inesperado. Código: {codigo}", "codigo": codigo}), 500


# --------------------------------------------------
# ASIENTOS PROPUESTOS
#
# El puente entre facturación y los libros. El sistema propone el
# asiento de cada factura y lo deja aquí; nada entra en la
# contabilidad hasta que alguien lo aprueba, que es cuando se
# consume el consecutivo.
# --------------------------------------------------

@bp_financiero_contabilidad.route("/propuestos")
@login_required
@requiere_permiso("contabilidad", "view")
def propuestos():
    empresa_id = session.get("empresa_id") or 1

    # Se proponen aquí y no al emitir la factura: hay dos caminos
    # distintos que crean facturas, y enganchar los dos significaría
    # tocar código de facturación, que no puede romperse por un fallo
    # contable. Al abrir esta pantalla el contador ve todo lo que falta,
    # que para él es lo mismo que si se hubiera hecho solo.
    try:
        contabilizacion_service.proponer_lote(empresa_id, _usuario())
    except Exception as e:
        # Que falle proponer no puede impedir ver lo que ya hay.
        error_service.registrar(e)

    pendientes = contabilizacion_service.pendientes(empresa_id)

    # Las líneas guardan cuenta_id, que es un número interno. Un contador
    # lee "130505 Clientes nacionales (EPS)", no "9".
    puc = {c["id"]: c for c in listar_puc(empresa_id)}
    for p in pendientes:
        for l in (p.get("lineas") or []):
            cuenta = puc.get(l.get("cuenta_id")) or {}
            l["cuenta_codigo"] = cuenta.get("codigo") or f"#{l.get('cuenta_id')}"
            l["cuenta_nombre"] = cuenta.get("nombre") or ""

    return render_template(
        "financiero/contabilidad/propuestos.html",
        pendientes=pendientes,
        fallidos=[p for p in pendientes if p["estado"] == "FALLIDO"],
    )


@bp_financiero_contabilidad.route("/propuestos/generar", methods=["POST"])
@login_required
@requiere_permiso("contabilidad", "create")
def propuestos_generar():
    """Revisa las facturas emitidas y propone las que aún no tienen asiento."""
    empresa_id = session.get("empresa_id") or 1
    try:
        return jsonify({"ok": True, **contabilizacion_service.proponer_lote(empresa_id, _usuario())})
    except Exception as e:
        codigo = error_service.registrar(e)
        return jsonify({"ok": False, "error": f"Ocurrió un error. Código: {codigo}"}), 500


@bp_financiero_contabilidad.route("/propuestos/aprobar", methods=["POST"])
@login_required
@requiere_permiso("contabilidad", "create")
def propuestos_aprobar():
    """
    Lleva una propuesta a los libros. Aquí sí se escribe contabilidad:
    se consume el consecutivo y el asiento queda registrado.
    """
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
    if not ids:
        return jsonify({"ok": False, "error": "No se indicó qué aprobar."}), 400

    hechos, fallidos = [], []
    for pid in ids:
        try:
            r = contabilizacion_service.aprobar(int(pid), _usuario())
        except Exception as e:
            r = {"ok": False, "error": f"Error inesperado. Código: {error_service.registrar(e)}"}
        (hechos if r.get("ok") else fallidos).append({"id": pid, **r})

    return jsonify({"ok": True, "aprobados": hechos, "fallidos": fallidos})


@bp_financiero_contabilidad.route("/propuestos/descartar", methods=["POST"])
@login_required
@requiere_permiso("contabilidad", "create")
def propuestos_descartar():
    body = request.get_json(silent=True) or {}
    if not body.get("id"):
        return jsonify({"ok": False, "error": "Falta la propuesta."}), 400
    contabilizacion_service.descartar(int(body["id"]), _usuario(), body.get("motivo"))
    return jsonify({"ok": True})
