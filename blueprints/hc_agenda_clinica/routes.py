# blueprints/hc_agenda_clinica/routes.py
#
# Agenda clínica: pantalla de trabajo para el personal asistencial.
# Muestra TODAS las citas del día (todos los profesionales y sedes, con
# filtros -- incluyendo búsqueda por número de documento del paciente),
# permite cambiar el estado de la atención (Confirmar / Iniciar
# atención / Finalizar) y lleva en un clic al formulario completo de la
# nota clínica (evolución) del paciente.
#
# A propósito NO duplica lógica que ya existe:
#   - Para listar, reutiliza citas_repo.listar_por_fecha (el mismo repo
#     que usa la agenda de citas y Admisiones).
#   - Para cambiar de estado, el frontend llama directamente al mismo
#     endpoint que ya usa la agenda de citas (/citas/api/estado, en
#     blueprints/citas/routes.py) -- así cualquier regla que ya exista
#     ahí (permiso citas:edit, validación de estados, correo de
#     confirmación al paciente) sigue aplicando sin reescribirla acá.
#   - Para la nota clínica, enlaza directo al wizard que ya existe en
#     /hc/evoluciones/nuevo/<paciente_id>.
#
# Esta pantalla en sí solo requiere permiso de "historia_clinica" para
# verse (ver services/permisos_service.py, RUTAS_MODULO) -- quien ya
# puede ver Historia clínica ve esta agenda sin configuración adicional.
# Los botones de cambiar estado dependen aparte del permiso citas:edit,
# igual que en la agenda de citas de siempre.

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from blueprints.auth.decorators import login_required
from repositories import hc_citas_repo as citas_repo

bp_hc_agenda_clinica = Blueprint(
    "hc_agenda_clinica",
    __name__,
    url_prefix="/hc/agenda-clinica",
)

# Estados con algo pendiente de ver/hacer en la clínica hoy. CANCELADA
# queda fuera a propósito -- no hay ninguna acción clínica que tomar
# sobre una cita cancelada.
ESTADOS_VISIBLES = ("PENDIENTE", "CONFIRMADA", "EN_ATENCION", "FINALIZADA", "FACTURADA")


@bp_hc_agenda_clinica.route("/")
@login_required
def index():
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
        "hc/agenda_clinica/index.html",
        sedes=sedes,
        profesionales=profesionales,
    )


@bp_hc_agenda_clinica.route("/api/dia")
@login_required
def api_dia():
    fecha = request.args.get("fecha") or datetime.now().strftime("%Y-%m-%d")
    medico_id = request.args.get("medico_id") or None
    sede_id = request.args.get("sede_id") or None

    try:
        citas = citas_repo.listar_por_fecha(fecha, medico_id=medico_id, sede_id=sede_id)
        visibles = [c for c in citas if c.get("estado") in ESTADOS_VISIBLES]
        return jsonify({"ok": True, "data": visibles})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
