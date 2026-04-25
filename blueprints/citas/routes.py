from flask import render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta

from flask import Blueprint

from repositories import (
    hc_sedes_repo       as repo_sedes,
    hc_especialidades_repo as repo_esp,
    hc_profesionales_repo  as repo_prof,
    hc_recursos_repo       as repo_recursos,
    hc_citas_repo          as repo_citas,
)

# Importa CUPS solo si existe, si no lo tienes aún lo manejamos abajo
try:
    from repositories import hc_cups_repo as repo_cups
    _TIENE_CUPS = True
except ImportError:
    _TIENE_CUPS = False

from services.agenda_service import generar_slots


bp_citas = Blueprint(
    "citas",
    __name__,
    url_prefix="/citas",
    template_folder="templates",
    static_folder="static"
)


# ══════════════════════════════════════════════════════════
#  AGENDA PRINCIPAL
# ══════════════════════════════════════════════════════════

@bp_citas.route("/")
def agenda():

    fecha_str = request.args.get("fecha")

    if not fecha_str:
        fecha_str = datetime.today().strftime("%Y-%m-%d")

    # Citas del día desde BD
    try:
        citas_raw = repo_citas.listar_por_fecha(fecha_str)
    except Exception:
        citas_raw = []

    # Normalizar para la plantilla
    citas = []
    for c in citas_raw:
        hora_real = c.get("hora_real") or c.get("hora") or ""
        hora_slot = (hora_real[:5] if hora_real else "")  # "HH:MM"

        # Iniciales del médico
        medico = c.get("medico") or c.get("profesional_nombre") or "Sin asignar"
        partes = medico.strip().split()
        iniciales = ""
        if len(partes) >= 2:
            iniciales = partes[0][0].upper() + partes[-1][0].upper()
        elif partes:
            iniciales = partes[0][:2].upper()

        citas.append({
            "id"                 : c.get("id"),
            "hora"               : hora_slot,
            "hora_real"          : hora_real[:5] if hora_real else "",
            "paciente"           : c.get("paciente_nombre") or c.get("paciente") or "—",
            "paciente_documento" : c.get("paciente_documento") or "",
            "servicio"           : c.get("especialidad") or c.get("servicio") or "—",
            "especialidad"       : c.get("especialidad") or "",
            "estado"             : (c.get("estado") or "pendiente").lower(),
            "medico"             : medico,
            "medico_id"          : c.get("medico_id") or c.get("profesional_id") or "",
            "medico_iniciales"   : iniciales,
            "sede"               : c.get("sede") or "",
            "sede_id"            : c.get("sede_id") or "",
            "tipo_cita"          : c.get("tipo_cita") or "",
            "motivo"             : c.get("motivo") or "",
            "duracion"           : f"{c.get('duracion_min', 30)} min",
            "fecha"              : c.get("fecha") or fecha_str,
        })

    # Datos para filtros y selects del modal
    try:
        sedes   = repo_sedes.listar()
    except Exception:
        sedes   = []

    try:
        medicos = [
            {"id": p["id"], "nombre": p["nombre_completo"]}
            for p in repo_prof.listar()
            if p.get("estado") == "ACTIVO"
        ]
    except Exception:
        medicos = []

    return render_template(
        "citas/agenda.html",
        citas      = citas,
        sedes      = sedes,
        medicos    = medicos,
        fecha_hoy  = fecha_str,
    )


# ══════════════════════════════════════════════════════════
#  API — CASCADA DEL MODAL
# ══════════════════════════════════════════════════════════

@bp_citas.route("/api/especialidades")
def api_especialidades():
    """Todas las especialidades activas."""
    try:
        from repositories import hc_especialidades_repo as repo_esp
        data = repo_esp.listar()
        return jsonify([
            {"id": e["id"], "nombre": e["nombre"]}
            for e in data
            if e.get("estado") in ("ACTIVO", "ACTIVA", None, "")
        ])
    except Exception as ex:
        return jsonify([])


@bp_citas.route("/api/medicos")
def api_medicos():
    """Médicos filtrados por especialidad."""
    especialidad_id = request.args.get("especialidad_id")

    try:
        todos = repo_prof.listar()
        resultado = []
        for p in todos:
            if p.get("estado") != "ACTIVO":
                continue
            if especialidad_id and str(p.get("especialidad_id")) != str(especialidad_id):
                continue
            resultado.append({
                "id"    : p["id"],
                "nombre": p["nombre_completo"],
            })
        return jsonify(resultado)
    except Exception:
        return jsonify([])


@bp_citas.route("/api/recursos")
def api_recursos():
    """Recursos filtrados por sede."""
    sede_id = request.args.get("sede_id")

    try:
        todos = repo_recursos.listar()
        resultado = []
        for r in todos:
            if r.get("estado") not in ("ACTIVO", "activo", None):
                continue
            if sede_id and str(r.get("sede_id")) != str(sede_id):
                continue
            resultado.append({
                "id"    : r["id"],
                "nombre": r.get("nombre") or r.get("codigo") or f"Recurso {r['id']}",
            })
        return jsonify(resultado)
    except Exception:
        return jsonify([])


@bp_citas.route("/api/cups-profesional")
def api_cups_profesional():
    """CUPS asociados a un médico. Si no tienes el repo aún, devuelve []."""
    medico_id = request.args.get("medico_id")

    if not _TIENE_CUPS or not medico_id:
        return jsonify([])

    try:
        data = repo_cups.listar_por_medico(int(medico_id))
        return jsonify([
            {
                "id"          : c["id"],
                "codigo"      : c.get("codigo", ""),
                "descripcion" : c.get("descripcion") or c.get("nombre", ""),
                "duracion_min": c.get("duracion_min", 30),
            }
            for c in data
        ])
    except Exception:
        return jsonify([])


@bp_citas.route("/api/slots-v2")
def api_slots_v2():
    """Slots de disponibilidad con estado libre/ocupado."""
    fecha      = request.args.get("fecha")
    medico_id  = request.args.get("medico_id")
    recurso_id = request.args.get("recurso_id")
    duracion   = int(request.args.get("duracion", 30))

    if not fecha or not medico_id:
        return jsonify([])

    # 1. Generar todos los slots de la agenda
    slots_libres = generar_slots(
        fecha,
        profesional_id = medico_id,
        recurso_id     = recurso_id,
    )

    if not slots_libres:
        return jsonify([])

    # 2. Citas ya agendadas ese día para ese médico
    try:
        citas_dia = repo_citas.listar_por_fecha_medico(fecha, int(medico_id))
        horas_ocupadas = {
            c.get("hora", "")[:5]
            for c in citas_dia
            if c.get("estado", "").lower() not in ("cancelada", "cancelado")
        }
    except Exception:
        horas_ocupadas = set()

    # 3. Marcar disponibilidad
    resultado = []
    for s in slots_libres:
        hora = s["hora"][:5]
        resultado.append({
            "hora"       : hora,
            "disponible" : hora not in horas_ocupadas,
        })

    return jsonify(resultado)


# ══════════════════════════════════════════════════════════
#  CREAR CITA
# ══════════════════════════════════════════════════════════

@bp_citas.route("/crear/", methods=["POST"])
def crear_cita():
    try:
        data = request.get_json(force=True)

        requeridos = ["paciente_id", "medico_id", "sede_id", "fecha", "hora"]
        for campo in requeridos:
            if not data.get(campo):
                return jsonify({"ok": False, "error": f"Falta el campo: {campo}"})

        resultado = repo_citas.crear(data)

        if resultado:
            return jsonify({"ok": True, "id": resultado.get("id")})
        else:
            return jsonify({"ok": False, "error": "No se pudo guardar la cita"})

    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)})


# ══════════════════════════════════════════════════════════
#  ACCIONES RÁPIDAS (confirmar / cancelar)
# ══════════════════════════════════════════════════════════

@bp_citas.route("/<int:cita_id>/confirmar/", methods=["POST"])
def confirmar_cita(cita_id):
    try:
        repo_citas.cambiar_estado(cita_id, "confirmada")
        return jsonify({"ok": True})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)})


@bp_citas.route("/<int:cita_id>/cancelar/", methods=["POST"])
def cancelar_cita(cita_id):
    try:
        repo_citas.cambiar_estado(cita_id, "cancelada")
        return jsonify({"ok": True})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)})


# ══════════════════════════════════════════════════════════
#  SLOTS (ruta original, se mantiene para compatibilidad)
# ══════════════════════════════════════════════════════════

@bp_citas.route("/slots")
def obtener_slots():
    fecha      = request.args.get("fecha")
    if not fecha:
        return jsonify([])
    profesional_id = request.args.get("profesional_id")
    recurso_id     = request.args.get("recurso_id")
    slots = generar_slots(fecha, profesional_id=profesional_id, recurso_id=recurso_id)
    return jsonify(slots)


# ══════════════════════════════════════════════════════════
#  IMPRESIÓN
# ══════════════════════════════════════════════════════════

@bp_citas.route("/imprimir/")
def imprimir_cita():
    datos = {k: request.args.get(k, "—") for k in [
        "id","paciente","documento","fecha","hora",
        "duracion","medico","especialidad","sede",
        "tipo","motivo","estado"
    ]}
    return render_template("citas/imprimir.html", **datos)




