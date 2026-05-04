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

# Agregar esta función al final de repositories/hc_citas_repo.py

def obtener_detalle(cita_id: int, empresa_id: int = None):
    """
    Devuelve una cita completa con joins de paciente, médico, sede
    y sus procedimientos CUPS.
    """
    sb      = _supabase()
    empresa = empresa_id or _empresa_id()

    res = (
        sb.table(_table())
        .select("""
            *,
            paciente:hc_pacientes(
                id,
                numero_documento,
                tipo_documento:hc_tipos_documento(nombre),
                primer_nombre,
                segundo_nombre,
                primer_apellido,
                segundo_apellido,
                celular,
                email
            ),
            medico:hc_profesionales(
                id,
                nombre_completo,
                especialidad:hc_especialidades(nombre)
            ),
            sede:hc_sedes(
                id,
                nombre
            )
        """)
        .eq("id", cita_id)
        .eq("empresa_id", empresa)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    row = res.data[0]

    pac    = row.get("paciente") or {}
    medico = row.get("medico")   or {}
    sede   = row.get("sede")     or {}

    nombre_paciente = " ".join(filter(None, [
        pac.get("primer_nombre"),
        pac.get("segundo_nombre"),
        pac.get("primer_apellido"),
        pac.get("segundo_apellido"),
    ])) or "Sin nombre"

    # Procedimientos CUPS (join separado)
    from repositories import hc_cita_procedimientos_repo
    procedimientos_raw = hc_cita_procedimientos_repo.listar_por_cita(cita_id)
    procedimientos = []
    for p in procedimientos_raw:
        cups = p.get("hc_cups") or {}
        procedimientos.append({
            "id":           p["id"],
            "orden":        p.get("orden", 1),
            "cups_id":      p["cups_id"],
            "codigo":       cups.get("codigo", ""),
            "descripcion":  cups.get("descripcion", ""),
            "duracion_min": p.get("duracion_min", 20),
        })

    return {
        # Cita base
        "id":                 row.get("id"),
        "estado":             row.get("estado"),
        "fecha":              row.get("fecha"),
        "hora_inicio":        row.get("hora_inicio"),
        "hora_fin":           row.get("hora_fin"),
        "duracion":           row.get("duracion"),
        "tipo_atencion":      row.get("tipo_atencion"),
        "modalidad":          row.get("modalidad"),
        "finalidad_consulta": row.get("finalidad_consulta"),
        "motivo_consulta":    row.get("motivo_consulta"),
        "prioridad":          row.get("prioridad"),
        # Paciente
        "paciente_id":        pac.get("id"),
        "paciente_nombre":    nombre_paciente,
        "paciente_documento": f"{pac.get('tipo_documento_id','CC')} {pac.get('numero_documento','')}".strip(),
        "paciente_celular":   pac.get("celular", ""),
        "paciente_email":     pac.get("email", ""),
        # Médico
        "medico_id":          medico.get("id"),
        "medico_nombre":      medico.get("nombre_completo", ""),
        "medico_especialidad": (medico.get("especialidad") or {}).get("nombre", ""),
        # Sede
        "sede_id":            sede.get("id"),
        "sede_nombre":        sede.get("nombre", ""),
        # Procedimientos
        "procedimientos":     procedimientos,
    }


# Agregar al final de repositories/hc_citas_repo.py

def obtener_datos_pdf(cita_id: int, empresa_id: int = None):
    """
    Devuelve todo lo necesario para generar el PDF de una cita:
    detalle completo + edad del paciente + datos de sede.
    """
    from repositories import hc_pacientes_repo

    # Detalle base (ya tiene paciente, médico, procedimientos)
    detalle = obtener_detalle(cita_id, empresa_id)
    if not detalle:
        return None

    sb = _supabase()

    # Edad del paciente
    pac_res = (
        sb.table("hc_pacientes")
        .select("fecha_nacimiento")
        .eq("id", detalle["paciente_id"])
        .limit(1)
        .execute()
    )
    fecha_nac = (pac_res.data or [{}])[0].get("fecha_nacimiento")
    detalle["paciente_edad"] = hc_pacientes_repo.calcular_edad(fecha_nac) if fecha_nac else None

    # Datos completos de la sede
    sede_res = (
        sb.table("hc_sedes")
        .select("nombre, direccion, telefono, ciudad")
        .eq("id", detalle["sede_id"])
        .limit(1)
        .execute()
    )
    sede = (sede_res.data or [{}])[0]
    detalle["sede_direccion"] = sede.get("direccion", "")
    detalle["sede_telefono"]  = sede.get("telefono", "")
    detalle["sede_ciudad"]    = sede.get("ciudad", "")

    return detalle