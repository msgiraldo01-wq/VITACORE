from flask import (
    Blueprint, render_template, request, redirect, session, jsonify, Response
)

from . import rda_service
from . import visor_service
from .fhir import client as ihce
from repositories import rda_envios_repo as repo_envios
from repositories import rda_catalogos_repo as repo_catalogos

bp_rda = Blueprint(
    "bp_rda",
    __name__,
    url_prefix="/rda",
    template_folder="templates",
)


# =========================
# HELPERS
# =========================

def _empresa_id():
    return session.get("empresa_id")


def es_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


# =========================
# PANEL DE CONTROL
# =========================

@bp_rda.route("/")
def panel():
    """Tablero de control de envíos RDA."""
    if not _empresa_id():
        return redirect("/")

    estado = request.args.get("estado", "")
    envios = repo_envios.listar(estado=estado)
    resumen = repo_envios.resumen()
    return render_template(
        "rda/panel_envios.html",
        envios=envios,
        resumen=resumen,
        estado_filtro=estado,
        ihce_activo=ihce.esta_habilitado(),
    )


# =========================
# API · DATOS DEL PANEL (para refresco AJAX)
# =========================

@bp_rda.route("/api/datos")
def api_datos():
    estado = request.args.get("estado", "")
    return jsonify({
        "resumen": repo_envios.resumen(),
        "envios": repo_envios.listar(estado=estado),
    })


# =========================
# TRANSMITIR UNA EVOLUCIÓN (prueba / manual)
# =========================

@bp_rda.route("/transmitir/<int:evolucion_id>", methods=["POST"])
def transmitir(evolucion_id):
    """Genera y transmite el RDA de una evolución. Registra el resultado."""
    empresa_id = _empresa_id()
    if not empresa_id:
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 400

    envio = rda_service.transmitir_evolucion(evolucion_id, empresa_id)
    if not envio:
        return jsonify({"ok": False, "message": "No se pudo registrar el envío"}), 500

    ok = envio.get("estado") == "aceptado"
    return jsonify({
        "ok": ok,
        "estado": envio.get("estado"),
        "http_status": envio.get("http_status"),
        "motivo": envio.get("motivo"),
        "composition_id": envio.get("composition_id"),
        "envio_id": envio.get("id"),
    })


# =========================
# REINTENTAR UN ENVÍO FALLIDO
# =========================

@bp_rda.route("/reintentar/<int:envio_id>", methods=["POST"])
def reintentar(envio_id):
    empresa_id = _empresa_id()
    if not empresa_id:
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 400

    try:
        envio = rda_service.reintentar_envio(envio_id, empresa_id)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

    ok = envio and envio.get("estado") == "aceptado"
    return jsonify({
        "ok": bool(ok),
        "estado": envio.get("estado") if envio else "error",
        "motivo": envio.get("motivo") if envio else "Sin respuesta",
    })


# =========================
# CONSULTAR RDA REGISTRADOS EN EL MINISTERIO
# =========================

@bp_rda.route("/consultar", methods=["POST"])
def consultar():
    """Lee de vuelta los RDA de un paciente desde el Ministerio."""
    if not _empresa_id():
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 400

    data = request.get_json(force=True) or {}
    tipo_doc = data.get("tipo_doc", "CC")
    num_doc = data.get("num_doc", "")
    if not num_doc:
        return jsonify({"ok": False, "message": "Falta el número de documento"}), 400

    try:
        res = ihce.consultar_rda_paciente(tipo_doc=tipo_doc, num_doc=num_doc)
    except ihce.IhceError as e:
        return jsonify({"ok": False, "message": str(e)}), 502

    # resumen legible de los Composition encontrados
    rdas = []
    resp = res.get("respuesta")
    if isinstance(resp, dict):
        for e in resp.get("entry", []) or []:
            r = e.get("resource", {}) or {}
            if r.get("resourceType") == "Composition":
                tipo = ""
                try:
                    tipo = r["type"]["coding"][0].get("display", "")
                except Exception:
                    pass
                rdas.append({
                    "id": r.get("id", ""),
                    "fecha": r.get("date", ""),
                    "titulo": r.get("title", ""),
                    "tipo": tipo,
                    "estado": r.get("status", ""),
                })

    return jsonify({"ok": res["ok"], "status": res["status"], "rdas": rdas})


# =========================
# DETALLE DE UN ENVÍO
# =========================

@bp_rda.route("/detalle/<int:envio_id>")
def detalle(envio_id):
    if not _empresa_id():
        return redirect("/")
    envio = repo_envios.obtener(envio_id)
    if not envio:
        return redirect("/rda/")
    return render_template("rda/detalle_rda.html", envio=envio)


# =========================
# VISOR DE RDA DEL MINISTERIO
# =========================

@bp_rda.route("/visor")
def visor():
    """Pantalla del visor: consulta los RDA de un paciente en el Ministerio."""
    if not _empresa_id():
        return redirect("/")
    return render_template("rda/visor.html", ihce_activo=ihce.esta_habilitado())


@bp_rda.route("/visor/atenciones", methods=["POST"])
def visor_atenciones():
    """Fase 1: lista rápida de atenciones (sin bajar recursos)."""
    if not _empresa_id():
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 403

    data = request.get_json(silent=True) or {}
    tipo_doc = (data.get("tipo_doc") or "CC").strip().upper()
    num_doc = (data.get("num_doc") or "").strip()
    if not num_doc.isdigit():
        return jsonify({"ok": False, "message": "Número de documento inválido"}), 400

    try:
        resultado = visor_service.listar_atenciones(tipo_doc, num_doc)
    except ihce.IhceError as e:
        return jsonify({"ok": False, "message": str(e)}), 502
    except Exception as e:
        print("[VISOR] error listando:", e)
        return jsonify({"ok": False, "message": "Error consultando al Ministerio"}), 500

    return jsonify({"ok": True, **resultado})


@bp_rda.route("/visor/detalle", methods=["POST"])
def visor_detalle():
    """Fase 2: detalle de las atenciones visibles (baja sus recursos)."""
    if not _empresa_id():
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 403

    data = request.get_json(silent=True) or {}
    atenciones = data.get("atenciones") or []
    paciente_ref = data.get("paciente_ref")

    if not isinstance(atenciones, list) or not atenciones:
        return jsonify({"ok": False, "message": "No hay atenciones que detallar"}), 400
    # límite defensivo: nunca detallar más de 10 por página
    atenciones = atenciones[:10]

    try:
        resultado = visor_service.detallar_atenciones(atenciones, paciente_ref)
    except ihce.IhceError as e:
        return jsonify({"ok": False, "message": str(e)}), 502
    except Exception as e:
        print("[VISOR] error detallando:", e)
        return jsonify({"ok": False, "message": "Error obteniendo el detalle"}), 500

    return jsonify({"ok": True, **resultado})


@bp_rda.route("/visor/epicrisis/<doc_id>")
def visor_epicrisis(doc_id):
    """Descarga el PDF de epicrisis de un DocumentReference del Ministerio."""
    if not _empresa_id():
        return redirect("/")

    try:
        pdf, nombre = visor_service.descargar_epicrisis(doc_id)
    except ihce.IhceError as e:
        return jsonify({"ok": False, "message": str(e)}), 502
    except ValueError as e:
        return jsonify({"ok": False, "message": str(e)}), 404
    except Exception as e:
        print("[VISOR] error descargando epicrisis:", e)
        return jsonify({"ok": False, "message": "No se pudo descargar"}), 500

    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


# =========================
# CONFIGURACIÓN DE CATÁLOGOS RDA
# =========================

# Tipos de catálogo que se administran, con su etiqueta para la pantalla.
CATALOGOS_ADMIN = [
    ("causa_externa", "Causa externa", "Motivo por el que el paciente recibe la atención."),
    ("tipo_diagnostico", "Tipo de diagnóstico", "Cómo se clasifica el diagnóstico principal."),
    ("entorno", "Entorno de atención", "Dónde se presta la atención."),
]


@bp_rda.route("/catalogos")
def catalogos():
    """Pantalla para activar/desactivar las opciones de cada catálogo del RDA."""
    if not _empresa_id():
        return redirect("/")

    grupos = []
    for tipo, titulo, descripcion in CATALOGOS_ADMIN:
        opciones = repo_catalogos.listar(tipo, solo_activos=False)
        grupos.append({
            "tipo": tipo,
            "titulo": titulo,
            "descripcion": descripcion,
            "opciones": opciones,
            "activas": sum(1 for o in opciones if o["activo"]),
            "total": len(opciones),
        })

    return render_template("rda/catalogos.html", grupos=grupos)


@bp_rda.route("/catalogos/estado/<int:catalogo_id>", methods=["POST"])
def catalogos_estado(catalogo_id):
    """Activa o desactiva una opción del catálogo (toggle)."""
    if not _empresa_id():
        return jsonify({"ok": False, "message": "Sin empresa activa"}), 403

    data = request.get_json(silent=True) or {}
    activo = bool(data.get("activo"))

    actualizado = repo_catalogos.cambiar_estado(catalogo_id, activo)
    if not actualizado:
        return jsonify({"ok": False, "message": "No se pudo actualizar"}), 500

    return jsonify({"ok": True, "activo": actualizado["activo"]})