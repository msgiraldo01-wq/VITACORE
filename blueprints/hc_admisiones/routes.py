# blueprints/hc_admisiones/routes.py
#
# Admisiones: pantalla operativa para el personal de recepción/portería.
# Muestra las citas del día que todavía no han sido llamadas a consulta
# (PENDIENTE y CONFIRMADA) y permite registrar la llegada del paciente.
#
# Registrar la llegada SOLO deja timestamp en hora_llegada -- no cambia
# el estado de la cita. Así el paciente queda visible en esta pantalla
# como "en sala de espera" con un cronómetro de tiempo de espera, hasta
# que el profesional lo llama a consulta desde su propia agenda (acción
# "Iniciar atención", que sigue intacta y es la que de verdad pasa la
# cita a EN_ATENCION).
#
# v1 a propósito acotado (según lo hablado): listar + registrar llegada
# + tiempo de espera. Nada de verificación de EPS ni cobro de copago
# todavía -- eso queda para una fase futura, cuando el flujo básico esté
# probado.

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from blueprints.auth.decorators import login_required
from repositories import hc_citas_repo as citas_repo
from repositories import hc_motivos_cancelacion_repo as motivos_repo
from services.permisos_service import requiere_permiso

bp_hc_admisiones = Blueprint(
    "hc_admisiones",
    __name__,
    url_prefix="/hc/admisiones",
)

ESTADOS_ADMISION = ("PENDIENTE", "CONFIRMADA")

# Nombre reservado del motivo de cancelación usado para marcar
# inasistencias desde Admisiones. Se busca/crea automáticamente (ver
# motivos_repo.obtener_o_crear_por_nombre) para no depender de que un
# administrador lo cree primero a mano en Configuración. Al quedar
# guardado como un motivo de cancelación más, el reporte "Citas
# canceladas" (que ya agrupa por motivo) sirve automáticamente para
# medir ausentismo, sin tener que construir un reporte nuevo.
MOTIVO_INASISTENCIA_NOMBRE = "No se presentó (inasistencia)"


@bp_hc_admisiones.route("/")
@login_required
def index():
    # Sedes y profesionales para los filtros -- la vista arranca
    # mostrando TODO (todas las sedes, todos los profesionales) y el
    # usuario puede acotar con los filtros si quiere, no al revés.
    try:
        from repositories import hc_sedes_repo as sedes_repo
        sedes = sedes_repo.listar_select()
    except Exception:
        sedes = []

    try:
        from repositories import hc_profesionales_repo as prof_repo
        profesionales = [
            p for p in (prof_repo.listar() or [])
            if (p.get("estado") or "ACTIVO") == "ACTIVO"
        ]
    except Exception:
        profesionales = []

    return render_template(
        "hc/admisiones/index.html",
        sedes=sedes,
        profesionales=profesionales,
    )


@bp_hc_admisiones.route("/api/hoy")
@login_required
def api_hoy():
    fecha = request.args.get("fecha") or datetime.now().strftime("%Y-%m-%d")
    medico_id = request.args.get("medico_id") or None
    sede_id = request.args.get("sede_id") or None

    try:
        citas = citas_repo.listar_por_fecha(
            fecha,
            medico_id=medico_id,
            sede_id=sede_id,
        )
        # Solo lo que todavía no ha sido llamado a consulta -- PENDIENTE
        # y CONFIRMADA. Esto incluye tanto a los que aún no han llegado
        # como a los que ya registraron llegada y están en sala de
        # espera (hora_llegada set pero estado sin tocar). Las que ya
        # están EN_ATENCION/FINALIZADA/etc. ya fueron llamadas por el
        # profesional (o no aplican) y no tienen nada que hacer en esta
        # pantalla.
        pendientes = [c for c in citas if c.get("estado") in ESTADOS_ADMISION]

        return jsonify({"ok": True, "data": pendientes})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_hc_admisiones.route("/api/registrar-llegada", methods=["POST"])
@login_required
@requiere_permiso("admisiones", "edit")
def api_registrar_llegada():
    body = request.get_json(silent=True) or {}
    cita_id = body.get("cita_id")

    if not cita_id:
        return jsonify({"ok": False, "error": "cita_id es requerido"}), 400

    try:
        citas_repo.registrar_llegada(cita_id)
        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_hc_admisiones.route("/api/marcar-inasistencia", methods=["POST"])
@login_required
@requiere_permiso("admisiones", "edit")
def api_marcar_inasistencia():
    body = request.get_json(silent=True) or {}
    cita_id = body.get("cita_id")

    if not cita_id:
        return jsonify({"ok": False, "error": "cita_id es requerido"}), 400

    try:
        # Reutiliza a propósito el mismo mecanismo de CANCELADA + motivo
        # que ya usa "Cancelar cita" en la agenda (repo.cambiar_estado +
        # motivo_cancelacion_id): ese camino ya está probado, ya excluye
        # correctamente la cita de facturación, y ya la saca de esta
        # lista de Admisiones (que solo muestra PENDIENTE/CONFIRMADA).
        # La diferencia con una cancelación normal es el motivo (uno
        # reservado para inasistencia) y que NO se envía el correo de
        # "cita cancelada" al paciente -- no aplica para un no-show.
        motivo = motivos_repo.obtener_o_crear_por_nombre(MOTIVO_INASISTENCIA_NOMBRE)
        citas_repo.cambiar_estado(
            cita_id,
            "CANCELADA",
            extra={"motivo_cancelacion_id": motivo["id"]},
        )
        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
