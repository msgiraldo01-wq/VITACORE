from flask import render_template, request, jsonify
from datetime import date
from collections import Counter
from flask import Blueprint

import repositories.hc_citas_repo          as repo_citas
import repositories.hc_sedes_repo          as repo_sedes
import repositories.hc_especialidades_repo as repo_especialidades
import repositories.hc_medicos_repo        as repo_medicos
import repositories.hc_recursos_repo as repo_recursos
from services.supabase_service import get_supabase_admin

bp_citas = Blueprint(
    "citas",
    __name__,
    url_prefix="/citas",
    template_folder="templates",
    static_folder="static"
)


def _normalizar_hora(hora_str: str) -> str:
    """
    Convierte cualquier formato de hora a HH:MM.
    Ejemplos: '06:15:00' → '06:15' | '06:15' → '06:15'
    """
    if not hora_str:
        return "00:00"
    partes = str(hora_str).strip().split(":")
    return f"{partes[0].zfill(2)}:{partes[1].zfill(2)}"


# ✅ REEMPLAZAR
def _hora_slot(hora_hhmm: str) -> str:
    """
    Devuelve el slot de 15 min al que pertenece una hora HH:MM.
    06:00 → 06:00 | 06:07 → 06:00 | 06:16 → 06:15 | 06:31 → 06:30
    """
    h, m = hora_hhmm.split(":")
    slot_m = (int(m) // 15) * 15
    return f"{h}:{str(slot_m).zfill(2)}"


@bp_citas.route("/")
def agenda():
    fecha_str = request.args.get("fecha", date.today().isoformat())
    medico_id = request.args.get("medico_id", type=int)
    sede_id   = request.args.get("sede_id",   type=int)

    citas_raw = repo_citas.listar_por_fecha(fecha_str, medico_id, sede_id)

    # Normalizar hora y agregar hora_slot en cada cita
    citas = []
    for c in citas_raw:
        hora_normalizada = _normalizar_hora(c.get("hora") or c.get("hora_real") or "")
        c["hora_real"]   = hora_normalizada          # hora exacta para mostrar en la tarjeta
        c["hora_slot"]   = _hora_slot(hora_normalizada)  # slot de 30 min para agrupar en la grilla
        citas.append(c)

    # DEBUG temporal
    conteo = Counter(c["hora_slot"] for c in citas)
    print(f"=== {len(citas)} citas — slots: {dict(conteo)} ===")

    medicos = repo_medicos.listar()
    sedes   = repo_sedes.listar()

    return render_template(
        "citas/agenda.html",
        citas     = citas,
        medicos   = medicos,
        sedes     = sedes,
        fecha_hoy = fecha_str,
    )


@bp_citas.route("/api/sedes")
def api_sedes():
    return jsonify(repo_sedes.listar_select())


@bp_citas.route("/api/especialidades")
def api_especialidades():
    return jsonify(repo_especialidades.listar_select())


# ✅ REEMPLAZAR la función api_medicos completa
@bp_citas.route("/api/medicos")
def api_medicos():
    especialidad_id = request.args.get("especialidad_id", type=int)

    q = get_supabase_admin()\
        .table("hc_profesionales")\
        .select("id, nombres, apellidos, especialidad_id")\
        .eq("estado", "ACTIVO")\
        .order("apellidos")

    if especialidad_id:
        q = q.eq("especialidad_id", especialidad_id)

    r = q.execute()
    return jsonify([
        {
            "id"    : p["id"],
            "nombre": f"{p.get('nombres','')} {p.get('apellidos','')}".strip()
        }
        for p in (r.data or [])
    ])


@bp_citas.route("/crear/", methods=["POST"])
def crear_cita():
    body = request.get_json(silent=True) or {}

    requeridos = ["paciente_id", "medico_id", "especialidad_id",
                  "sede_id", "tipo_cita", "fecha", "hora"]
    for campo in requeridos:
        if not body.get(campo):
            return jsonify({"ok": False, "error": f"Campo requerido: {campo}"}), 400

    conflicto = repo_citas.existe_conflicto(
        medico_id = body["medico_id"],
        fecha     = body["fecha"],
        hora      = body["hora"],
    )
    if conflicto:
        return jsonify({
            "ok"   : False,
            "error": "El profesional ya tiene una cita en ese horario."
        }), 409

    cita = repo_citas.crear(body)
    if not cita:
        return jsonify({"ok": False, "error": "Error al guardar la cita"}), 500

    return jsonify({"ok": True, "cita": cita}), 201


@bp_citas.route("/<int:cita_id>/confirmar/", methods=["POST"])
def confirmar_cita(cita_id):
    cita = repo_citas.cambiar_estado(cita_id, "CONFIRMADA")
    if not cita:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    return jsonify({"ok": True, "cita": cita})


@bp_citas.route("/<int:cita_id>/cancelar/", methods=["POST"])
def cancelar_cita(cita_id):
    cita = repo_citas.cambiar_estado(cita_id, "CANCELADA")
    if not cita:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    return jsonify({"ok": True, "cita": cita})


@bp_citas.route("/api/slots")
def obtener_slots():
    fecha     = request.args.get("fecha")
    medico_id = request.args.get("medico_id", type=int)

    if not fecha or not medico_id:
        return jsonify([])

    citas_dia = repo_citas.listar_por_fecha(fecha, medico_id=medico_id)

    horas_ocupadas = set()
    for c in citas_dia:
        if c.get("estado") not in ("cancelada",):
            horas_ocupadas.add(_normalizar_hora(c.get("hora") or c.get("hora_real") or ""))

    slots = []
    for h in range(6, 20):
        for m in (0, 15, 30, 45):
            hora_str = f"{h:02d}:{m:02d}"
            slots.append({
                "hora"      : hora_str,
                "disponible": hora_str not in horas_ocupadas,
            })

    return jsonify(slots)

@bp_citas.route('/imprimir/')
def imprimir_cita():
    """
    Renderiza la plantilla de impresión de cita.
    Los datos llegan como query params en la URL y se inyectan con JS.
    No se necesita consultar la BD porque los datos vienen del modal.
    """
    return render_template('citas/imprimir_cita.html')

# ── API recursos por sede ─────────────────────────────────
@bp_citas.route("/api/recursos")
def api_recursos():
    sede_id = request.args.get("sede_id", type=int)
    return jsonify(repo_recursos.listar_select(sede_id=sede_id))


# ── API CUPS por profesional (con duración) ───────────────
@bp_citas.route("/api/cups-profesional")
def api_cups_profesional():
    medico_id = request.args.get("medico_id", type=int)
    if not medico_id:
        return jsonify([])
    r = get_supabase_admin()\
        .table("hc_prof_procedimientos")\
        .select("id, duracion_min, hc_cups(id, codigo, descripcion)")\
        .eq("profesional_id", medico_id)\
        .execute()
    resultado = []
    for p in (r.data or []):
        cups = p.get("hc_cups") or {}
        resultado.append({
            "id"          : cups.get("id"),
            "codigo"      : cups.get("codigo") or "",
            "descripcion" : cups.get("descripcion") or "",
            "duracion_min": p.get("duracion_min") or 30,
        })
    return jsonify(resultado)


# ── API slots con duración dinámica ──────────────────────
@bp_citas.route("/api/slots-v2")
def obtener_slots_v2():
    fecha        = request.args.get("fecha")
    medico_id    = request.args.get("medico_id",  type=int)
    recurso_id   = request.args.get("recurso_id", type=int)
    duracion_min = request.args.get("duracion",   type=int, default=15)

    if not fecha or not medico_id:
        return jsonify([])

    ocupadas = repo_citas.listar_horas_ocupadas(
        medico_id  = medico_id,
        fecha      = fecha,
        recurso_id = recurso_id,
    )

    slots = []
    for h in range(6, 20):
        for m in (0, 15, 30, 45):
            hora_str = f"{h:02d}:{m:02d}"
            slots.append({
                "hora"      : hora_str,
                "disponible": hora_str not in ocupadas,
            })

    return jsonify(slots)