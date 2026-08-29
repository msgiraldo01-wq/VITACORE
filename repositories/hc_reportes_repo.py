# repositories/hc_reportes_repo.py
"""
Reportes gerenciales/regulatorios de historia clínica y citas.

Por ahora solo contiene el indicador de oportunidad de asignación de
citas de primera vez (Resolución 0256 de 2016, Ministerio de Salud),
pero queda como el lugar natural para futuros reportes de este mismo
apartado ("/hc/reportes").
"""

from datetime import datetime


def _sb():
    from services.supabase_service import get_supabase_admin
    return get_supabase_admin()


def rep_oportunidad_citas(empresa_id: int, desde: str, hasta: str) -> dict:
    """
    Indicador de oportunidad en la asignación de citas médicas de
    primera vez (Resolución 256/2016): días calendario que transcurren
    entre el primer contacto (fecha de solicitud) y la fecha en que
    quedó asignada la cita.

    - Solo cuenta citas marcadas como "Primera vez" (campo tipo_consulta,
      agregado para este indicador -- las citas creadas antes de eso no
      tienen este dato y no entran al cálculo).
    - Cuando no se registró una fecha de solicitud explícita (caso normal:
      la cita se agendó en el mismo momento en que se pidió), se usa la
      fecha de creación del registro como equivalente.
    - No se cuentan las citas canceladas: no representan un ciclo de
      atención cumplido, aunque sí se les haya asignado una fecha.
    - Se agrupa por especialidad del médico, tal como lo pide la
      resolución para el reporte mensual.
    """
    sb = _sb()

    res = (
        sb.table("hc_citas")
        .select("""
            id, fecha, fecha_solicitud, fecha_creacion, estado, tipo_consulta,
            medico:hc_profesionales(
                id,
                nombre_completo,
                especialidad:hc_especialidades(id, nombre)
            )
        """)
        .eq("empresa_id", empresa_id)
        .eq("tipo_consulta", "PRIMERA_VEZ")
        .neq("estado", "CANCELADA")
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )
    filas = res.data or []

    por_especialidad = {}
    total_citas = 0
    total_dias = 0
    excluidas = 0  # sin dato de fecha usable, o inconsistentes

    for row in filas:
        medico = row.get("medico") or {}
        especialidad = (medico.get("especialidad") or {}).get("nombre") or "Sin especialidad"

        fecha_cita = row.get("fecha")
        base = row.get("fecha_solicitud") or (row.get("fecha_creacion") or "")[:10]

        dias = None
        if fecha_cita and base:
            try:
                d_cita = datetime.strptime(fecha_cita, "%Y-%m-%d").date()
                d_base = datetime.strptime(base[:10], "%Y-%m-%d").date()
                dias = (d_cita - d_base).days
            except ValueError:
                dias = None

        if dias is None or dias < 0:
            excluidas += 1
            continue

        grupo = por_especialidad.setdefault(especialidad, {
            "especialidad": especialidad, "citas": 0, "suma_dias": 0,
        })
        grupo["citas"] += 1
        grupo["suma_dias"] += dias
        total_citas += 1
        total_dias += dias

    filas_reporte = []
    for g in sorted(por_especialidad.values(), key=lambda x: x["especialidad"]):
        filas_reporte.append({
            "especialidad": g["especialidad"],
            "citas": g["citas"],
            "promedio_dias": round(g["suma_dias"] / g["citas"], 1) if g["citas"] else 0,
        })

    return {
        "filas": filas_reporte,
        "total_citas": total_citas,
        "promedio_general": round(total_dias / total_citas, 1) if total_citas else 0,
        "excluidas": excluidas,
    }


def rep_citas_canceladas(empresa_id: int, desde: str, hasta: str) -> dict:
    """
    Reporte de citas canceladas en un período: conteo y porcentaje por
    motivo de cancelación y por especialidad del médico, más la tasa de
    cancelación sobre el total de citas agendadas en el mismo período
    (de cualquier estado).

    El período filtra por la fecha de la cita (la misma fecha que usa
    "Oportunidad de citas"), no por la fecha en que se canceló.
    """
    sb = _sb()

    res_canceladas = (
        sb.table("hc_citas")
        .select("""
            id, fecha, motivo_cancelacion_id,
            motivo:hc_motivos_cancelacion(id, nombre),
            medico:hc_profesionales(
                id,
                nombre_completo,
                especialidad:hc_especialidades(id, nombre)
            )
        """)
        .eq("empresa_id", empresa_id)
        .eq("estado", "CANCELADA")
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )
    canceladas = res_canceladas.data or []
    total_canceladas = len(canceladas)

    # Total de citas agendadas en el período (cualquier estado), para la tasa.
    res_total = (
        sb.table("hc_citas")
        .select("id", count="exact")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )
    total_periodo = res_total.count or 0

    por_motivo = {}
    por_especialidad = {}
    sin_motivo = 0

    for row in canceladas:
        motivo = (row.get("motivo") or {}).get("nombre") or None
        if not motivo:
            sin_motivo += 1
            motivo = "Sin motivo registrado"

        medico = row.get("medico") or {}
        especialidad = (medico.get("especialidad") or {}).get("nombre") or "Sin especialidad"

        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
        por_especialidad[especialidad] = por_especialidad.get(especialidad, 0) + 1

    def _armar_filas(conteo: dict) -> list:
        filas = []
        for clave, citas in conteo.items():
            filas.append({
                "nombre": clave,
                "citas": citas,
                "porcentaje": round(citas / total_canceladas * 100, 1) if total_canceladas else 0,
            })
        return sorted(filas, key=lambda f: f["citas"], reverse=True)

    return {
        "total_canceladas": total_canceladas,
        "total_periodo": total_periodo,
        "tasa_cancelacion": round(total_canceladas / total_periodo * 100, 1) if total_periodo else 0,
        "por_motivo": _armar_filas(por_motivo),
        "por_especialidad": _armar_filas(por_especialidad),
        "sin_motivo": sin_motivo,
    }


def rep_citas_reprogramadas(empresa_id: int, desde: str, hasta: str) -> dict:
    """
    Reporte de citas reprogramadas en un período: conteo y porcentaje por
    motivo de reprogramación y por especialidad del médico, más cuántas
    veces en promedio se reprograma una cita que ya fue tocada al menos
    una vez.

    A diferencia de "Citas canceladas" (que filtra por la fecha de la
    cita), aquí el período filtra por fecha_reprogramacion -- el momento
    en que se hizo el cambio de horario -- porque lo que interesa medir
    es cuántas reprogramaciones ocurrieron en ese rango de tiempo, no
    cuántas citas cuya fecha *actual* cae en ese rango han sido tocadas
    alguna vez (esa fecha ya cambió, así que filtrar por ella no tendría
    sentido para este reporte).
    """
    sb = _sb()

    res_reprogramadas = (
        sb.table("hc_citas")
        .select("""
            id, fecha, fecha_reprogramacion, veces_reprogramada, motivo_reprogramacion_id,
            motivo:hc_motivos_reprogramacion(id, nombre),
            medico:hc_profesionales(
                id,
                nombre_completo,
                especialidad:hc_especialidades(id, nombre)
            )
        """)
        .eq("empresa_id", empresa_id)
        .not_.is_("fecha_reprogramacion", "null")
        .gte("fecha_reprogramacion", desde)
        .lte("fecha_reprogramacion", f"{hasta} 23:59:59")
        .execute()
    )
    reprogramadas = res_reprogramadas.data or []
    total_reprogramadas = len(reprogramadas)

    # Total de citas agendadas en el período (por fecha de la cita), para
    # dar una idea de proporción -- no es una "tasa" tan exacta como en
    # cancelaciones porque compara conteos con criterios de fecha distintos
    # (reprogramaciones por fecha del evento vs. citas por fecha de la cita),
    # pero sigue siendo útil como referencia de volumen.
    res_total = (
        sb.table("hc_citas")
        .select("id", count="exact")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )
    total_periodo = res_total.count or 0

    por_motivo = {}
    por_especialidad = {}
    sin_motivo = 0
    suma_veces = 0

    for row in reprogramadas:
        motivo = (row.get("motivo") or {}).get("nombre") or None
        if not motivo:
            sin_motivo += 1
            motivo = "Sin motivo registrado"

        medico = row.get("medico") or {}
        especialidad = (medico.get("especialidad") or {}).get("nombre") or "Sin especialidad"

        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
        por_especialidad[especialidad] = por_especialidad.get(especialidad, 0) + 1
        suma_veces += row.get("veces_reprogramada") or 1

    def _armar_filas(conteo: dict) -> list:
        filas = []
        for clave, citas in conteo.items():
            filas.append({
                "nombre": clave,
                "citas": citas,
                "porcentaje": round(citas / total_reprogramadas * 100, 1) if total_reprogramadas else 0,
            })
        return sorted(filas, key=lambda f: f["citas"], reverse=True)

    return {
        "total_reprogramadas": total_reprogramadas,
        "total_periodo": total_periodo,
        "tasa_reprogramacion": round(total_reprogramadas / total_periodo * 100, 1) if total_periodo else 0,
        "promedio_veces": round(suma_veces / total_reprogramadas, 1) if total_reprogramadas else 0,
        "por_motivo": _armar_filas(por_motivo),
        "por_especialidad": _armar_filas(por_especialidad),
        "sin_motivo": sin_motivo,
    }
