# repositories/hc_citas_repo.py

from flask import current_app, session
from datetime import datetime


def _table():
    return current_app.config.get("SUPABASE_TABLE_HC_CITAS", "hc_citas")


def _supabase():
    from services.supabase_service import get_supabase_admin
    return get_supabase_admin()


def _empresa_id(fallback=None):
    """Obtener empresa_id de sesión o de fallback (para APIs sin sesión)."""
    return session.get("empresa_id") or fallback


def _normalize(row):
    if not row:
        return {}
    return {
        "id": row.get("id"),
        "empresa_id": row.get("empresa_id"),
        "paciente_id": row.get("paciente_id"),
        "medico_id": row.get("medico_id"),
        "sede_id": row.get("sede_id"),
        "consultorio_id": row.get("consultorio_id"),
        "fecha": row.get("fecha"),
        "hora_inicio": row.get("hora_inicio"),
        "hora_fin": row.get("hora_fin"),
        "duracion": row.get("duracion"),
        "tipo_atencion": row.get("tipo_atencion"),
        "modalidad": row.get("modalidad"),
        "finalidad_consulta": row.get("finalidad_consulta"),
        "eps_id": row.get("eps_id"),
        "regimen": row.get("regimen"),
        "tipo_usuario": row.get("tipo_usuario"),
        "motivo_consulta": row.get("motivo_consulta"),
        "cie10_codigo": row.get("cie10_codigo"),
        "prioridad": row.get("prioridad"),
        "estado": row.get("estado"),
        "hora_llegada": row.get("hora_llegada"),
        "hora_inicio_real": row.get("hora_inicio_real"),
        "hora_fin_real": row.get("hora_fin_real"),
        "evolucion_id": row.get("evolucion_id"),
        "usuario_creacion": row.get("usuario_creacion"),
        "fecha_creacion": row.get("fecha_creacion"),
    }


# --------------------------------------------------
# CRUD
# --------------------------------------------------

def listar(fecha=None, medico_id=None):
    sb = _supabase()
    empresa = _empresa_id()

    if not empresa:
        raise ValueError("empresa_id es requerido (no hay sesión activa)")

    query = (
        sb.table(_table())
        .select("*")
        .eq("empresa_id", empresa)
        .order("hora_inicio", desc=False)
    )

    if fecha:
        query = query.eq("fecha", fecha)
    if medico_id:
        query = query.eq("medico_id", medico_id)

    res = query.execute()
    return [_normalize(r) for r in (res.data or [])]


def obtener(cita_id):
    sb = _supabase()
    empresa = _empresa_id()

    res = (
        sb.table(_table())
        .select("*")
        .eq("id", cita_id)
        .eq("empresa_id", empresa)
        .limit(1)
        .execute()
    )

    return _normalize(res.data[0]) if res.data else None


def crear(data):
    sb = _supabase()

    # Priorizar sesión, sino el body
    empresa = _empresa_id() or data.get("empresa_id")

    if not empresa:
        raise ValueError("empresa_id es requerido")

    payload = {
        **data,
        "empresa_id": int(empresa),
        "fecha_creacion": datetime.now().isoformat(),
    }

    res = sb.table(_table()).insert(payload).execute()

    return _normalize(res.data[0]) if res.data else None


def actualizar(cita_id, data):
    sb = _supabase()
    empresa = _empresa_id() or data.get("empresa_id")

    if not empresa:
        raise ValueError("empresa_id es requerido para actualizar")

    payload = {
        **data,
        "fecha_modificacion": datetime.now().isoformat(),
    }

    res = (
        sb.table(_table())
        .update(payload)
        .eq("id", cita_id)
        .eq("empresa_id", empresa)
        .execute()
    )

    return res.data


def cambiar_estado(cita_id, nuevo_estado):
    sb = _supabase()
    empresa = _empresa_id()

    if not empresa:
        # Para cambio de estado sin sesión, obtener la cita primero
        cita = obtener(cita_id)
        if not cita:
            raise ValueError("Cita no encontrada")
        empresa = cita.get("empresa_id")

    payload = {
        "estado": nuevo_estado,
        "fecha_modificacion": datetime.now().isoformat(),
    }

    if nuevo_estado == "EN_ATENCION":
        payload["hora_inicio_real"] = datetime.now().time().isoformat()

    if nuevo_estado == "FINALIZADA":
        payload["hora_fin_real"] = datetime.now().time().isoformat()

    res = (
        sb.table(_table())
        .update(payload)
        .eq("id", cita_id)
        .eq("empresa_id", empresa)
        .execute()
    )

    return res.data


# --------------------------------------------------
# AGENDA (con joins)
# --------------------------------------------------

def listar_por_fecha(fecha, medico_id=None, sede_id=None, empresa_id=None):
    sb = _supabase()

    # 🔥 PRIORIDAD: parámetro → sesión
    empresa = empresa_id or _empresa_id()

    if not empresa:
        raise ValueError("empresa_id es requerido (no hay sesión activa)")

    try:
        empresa = int(empresa)
    except:
        raise ValueError("empresa_id inválido")

    query = (
        sb.table(_table())
        .select("""
            *,
            paciente:hc_pacientes(
                id,
                numero_documento,
                primer_nombre,
                segundo_nombre,
                primer_apellido,
                segundo_apellido
            ),
            medico:hc_profesionales(
                id,
                nombre_completo
            )
        """)
        .eq("empresa_id", empresa)
        .eq("fecha", fecha)
        .order("hora_inicio", desc=False)
    )

    if medico_id:
        query = query.eq("medico_id", medico_id)

    if sede_id:
        query = query.eq("sede_id", sede_id)

    res = query.execute()

    return [_normalize_agenda(r) for r in (res.data or [])]


def _normalize_agenda(row):
    base = _normalize(row)

    paciente = row.get("paciente") or {}
    medico = row.get("medico") or {}

    nombre_paciente = " ".join(filter(None, [
        paciente.get("primer_nombre"),
        paciente.get("segundo_nombre"),
        paciente.get("primer_apellido"),
        paciente.get("segundo_apellido"),
    ]))

    base.update({
        "paciente_nombre": nombre_paciente or "Sin nombre",
        "paciente_documento": paciente.get("numero_documento"),
        "medico_nombre": medico.get("nombre_completo") or "Sin médico",
    })

    return base