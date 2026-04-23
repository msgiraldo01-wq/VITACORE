from services.supabase_service import get_supabase_admin


def _sb():
    return get_supabase_admin()


def listar_por_fecha(fecha: str, medico_id: int = None, sede_id: int = None):
    q = (
        _sb()
        .table("hc_citas")
        .select("""
            id, fecha, hora, hora_fin, duracion_min, motivo,
            tipo_cita, estado, via_solicitud, medico_remitente,
            paciente_id, medico_id, especialidad_id, sede_id, cups_id, recurso_id,
            hc_pacientes!hc_citas_paciente_id_fkey(
                id, primer_nombre, segundo_nombre,
                primer_apellido, segundo_apellido,
                numero_documento
            ),
            hc_profesionales!hc_citas_medico_id_fkey(
                id, nombres, apellidos, especialidad_id
            ),
            hc_especialidades!hc_citas_especialidad_id_fkey(nombre),
            hc_sedes!hc_citas_sede_id_fkey(nombre),
            hc_cups!hc_citas_cups_id_fkey(id, codigo, descripcion),
            hc_recursos!hc_citas_recurso_id_fkey(id, nombre, tipo)
        """)
        .eq("fecha", fecha)
    )

    if medico_id:
        q = q.eq("medico_id", medico_id)
    if sede_id:
        q = q.eq("sede_id", sede_id)

    r = q.order("hora").execute()
    raw = r.data or []

    resultado = []
    for c in raw:
        pac  = c.get("hc_pacientes")    or {}
        med  = c.get("hc_profesionales") or {}   # ← CORREGIDO
        esp  = c.get("hc_especialidades") or {}
        sede = c.get("hc_sedes")         or {}
        cups = c.get("hc_cups")          or {}
        rec  = c.get("hc_recursos")      or {}

        nombre_pac = " ".join(filter(None, [
            pac.get("primer_nombre"), pac.get("segundo_nombre"),
            pac.get("primer_apellido"), pac.get("segundo_apellido")
        ]))

        # ← CORREGIDO: usa nombres + apellidos
        nombre_med = f"{med.get('nombres','')} {med.get('apellidos','')}".strip()
        iniciales  = "".join([w[0] for w in nombre_med.split()[:2]]).upper() or "?"

        # Normalizar hora a HH:MM
        hora_raw  = str(c.get("hora") or "")
        hora_norm = hora_raw[:5] if len(hora_raw) >= 5 else hora_raw

        # Calcular hora_slot (slot de 30 min al que pertenece)
        # ✅ REEMPLAZAR el bloque hora_slot
        try:
            hh, mm = hora_norm.split(":")
            mm_int  = int(mm)
         # Redondear al slot de 15 min más cercano hacia abajo
            slot_m  = (mm_int // 15) * 15
            hora_slot = f"{hh}:{str(slot_m).zfill(2)}"
        except Exception:
             hora_slot = hora_norm

        resultado.append({
            "id"                : c["id"],
            "fecha"             : str(c.get("fecha") or ""),
            "hora"              : hora_slot,    # ← slot para agrupar en timeline
            "hora_real"         : hora_norm,    # ← hora exacta para mostrar
            "hora_fin"          : str(c.get("hora_fin") or "")[:5],
            "duracion_min"      : c.get("duracion_min") or 30,
            "duracion"          : f"{c.get('duracion_min') or 30} min",
            "motivo"            : c.get("motivo") or "",
            "tipo_cita"         : c.get("tipo_cita") or "",
            "estado"            : (c.get("estado") or "pendiente").lower(),
            "via_solicitud"     : c.get("via_solicitud") or "",
            "medico_remitente"  : c.get("medico_remitente") or "",
            "paciente"          : nombre_pac,
            "paciente_documento": pac.get("numero_documento") or "",
            "paciente_id"       : c.get("paciente_id"),
            "medico"            : nombre_med,
            "medico_id"         : c.get("medico_id"),
            "medico_iniciales"  : iniciales,
            "especialidad"      : esp.get("nombre") or "",
            "especialidad_id"   : c.get("especialidad_id"),
            "sede"              : sede.get("nombre") or "",
            "sede_id"           : c.get("sede_id"),
            "cups_codigo"       : cups.get("codigo") or "",
            "cups_descripcion"  : cups.get("descripcion") or "",
            "cups_id"           : c.get("cups_id"),
            "recurso"           : rec.get("nombre") or "",
            "recurso_tipo"      : rec.get("tipo") or "",
            "recurso_id"        : c.get("recurso_id"),
        })

    return resultado


def existe_conflicto(medico_id: int, fecha: str, hora: str,
                     excluir_id: int = None) -> bool:
    q = (
        _sb()
        .table("hc_citas")
        .select("id")
        .eq("medico_id", medico_id)
        .eq("fecha", fecha)
        .eq("hora", hora)
        .neq("estado", "cancelada")
    )
    if excluir_id:
        q = q.neq("id", excluir_id)
    r = q.execute()
    return bool(r.data)


def crear(data: dict):
    payload = {
        "paciente_id"     : data.get("paciente_id"),
        "medico_id"       : data.get("medico_id"),
        "especialidad_id" : data.get("especialidad_id"),
        "sede_id"         : data.get("sede_id"),
        "tipo_cita"       : data.get("tipo_cita"),
        "fecha"           : data.get("fecha"),
        "hora"            : data.get("hora"),
        "hora_fin"        : data.get("hora_fin"),
        "duracion_min"    : data.get("duracion_min", 30),
        "motivo"          : data.get("motivo", ""),
        "estado"          : data.get("estado", "pendiente"),
        "cups_id"         : data.get("cups_id") or None,
        "recurso_id"      : data.get("recurso_id") or None,
        "medico_remitente": data.get("medico_remitente", ""),
        "via_solicitud"   : data.get("via_solicitud", "PRESENCIAL"),
    }
    r = _sb().table("hc_citas").insert(payload).execute()
    return r.data[0] if r.data else None


def cambiar_estado(cita_id: int, estado: str):
    r = (
        _sb()
        .table("hc_citas")
        .update({"estado": estado.lower()})
        .eq("id", cita_id)
        .execute()
    )
    return r.data[0] if r.data else None


def listar_horas_ocupadas(medico_id: int, fecha: str,
                          recurso_id: int = None) -> set:
    q = (
        _sb()
        .table("hc_citas")
        .select("hora, duracion_min")
        .eq("fecha", fecha)
        .neq("estado", "cancelada")
    )
    if medico_id:
        q = q.eq("medico_id", medico_id)

    r = q.execute()
    ocupadas = set()
    for c in (r.data or []):
        hora_str = str(c.get("hora") or "")[:5]
        ocupadas.add(hora_str)

    if recurso_id:
        r2 = (
            _sb()
            .table("hc_citas")
            .select("hora")
            .eq("fecha", fecha)
            .eq("recurso_id", recurso_id)
            .neq("estado", "cancelada")
            .execute()
        )
        for c in (r2.data or []):
            ocupadas.add(str(c.get("hora") or "")[:5])

    return ocupadas