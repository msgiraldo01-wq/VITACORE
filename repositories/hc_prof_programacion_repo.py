"""
Repositorio: hc_prof_programacion_repo.py
Maneja horario semanal recurrente y bloqueos de profesionales.
ACTUALIZADO: Soporta bloqueos parciales (por horas).
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


# ══════════════════════════════════════════════════════════════
#  PROGRAMACIÓN SEMANAL
# ══════════════════════════════════════════════════════════════

def listar_por_profesional(profesional_id: int) -> list:
    res = (
        _sb()
        .table("hc_prof_programacion")
        .select("*")
        .eq("profesional_id", profesional_id)
        .eq("estado", "ACTIVO")
        .order("dia_semana")
        .order("hora_inicio")
        .execute()
    )
    return res.data or []


def agregar_bloque(profesional_id: int, dia_semana: int, hora_inicio: str, hora_fin: str) -> dict:
    existentes = (
        _sb()
        .table("hc_prof_programacion")
        .select("id, hora_inicio, hora_fin")
        .eq("profesional_id", profesional_id)
        .eq("dia_semana", dia_semana)
        .eq("estado", "ACTIVO")
        .execute()
    ).data or []

    for bloque in existentes:
        if hora_inicio < bloque["hora_fin"] and hora_fin > bloque["hora_inicio"]:
            raise ValueError(
                f"Se solapa con el bloque {bloque['hora_inicio'][:5]} - {bloque['hora_fin'][:5]}"
            )

    res = (
        _sb()
        .table("hc_prof_programacion")
        .insert({
            "profesional_id": profesional_id,
            "dia_semana": dia_semana,
            "hora_inicio": hora_inicio,
            "hora_fin": hora_fin,
        })
        .execute()
    )
    return res.data[0] if res.data else {}


def eliminar_bloque(bloque_id: int):
    _sb().table("hc_prof_programacion").delete().eq("id", bloque_id).execute()


def obtener_bloques_dia(profesional_id: int, dia_semana: int) -> list:
    res = (
        _sb()
        .table("hc_prof_programacion")
        .select("hora_inicio, hora_fin")
        .eq("profesional_id", profesional_id)
        .eq("dia_semana", dia_semana)
        .eq("estado", "ACTIVO")
        .order("hora_inicio")
        .execute()
    )
    return res.data or []


# ══════════════════════════════════════════════════════════════
#  BLOQUEOS (con soporte de horas parciales)
# ══════════════════════════════════════════════════════════════

def listar_bloqueos(profesional_id: int) -> list:
    res = (
        _sb()
        .table("hc_prof_bloqueos")
        .select("*")
        .eq("profesional_id", profesional_id)
        .eq("estado", "ACTIVO")
        .order("fecha_inicio", desc=True)
        .execute()
    )
    return res.data or []


def agregar_bloqueo(
    profesional_id: int,
    fecha_inicio: str,
    fecha_fin: str,
    motivo: str = None,
    hora_inicio: str = None,
    hora_fin: str = None,
) -> dict:
    payload = {
        "profesional_id": profesional_id,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "motivo": motivo,
    }
    # Solo incluir horas si ambas están presentes
    if hora_inicio and hora_fin:
        payload["hora_inicio"] = hora_inicio
        payload["hora_fin"] = hora_fin

    res = (
        _sb()
        .table("hc_prof_bloqueos")
        .insert(payload)
        .execute()
    )
    return res.data[0] if res.data else {}


def eliminar_bloqueo(bloqueo_id: int):
    _sb().table("hc_prof_bloqueos").delete().eq("id", bloqueo_id).execute()


def obtener_bloqueos_fecha(profesional_id: int, fecha: str) -> list:
    """
    Retorna todos los bloqueos activos que cubren una fecha específica.
    Cada bloqueo puede ser:
      - Día completo: hora_inicio=null, hora_fin=null
      - Parcial: hora_inicio y hora_fin con valores
    """
    res = (
        _sb()
        .table("hc_prof_bloqueos")
        .select("id, fecha_inicio, fecha_fin, hora_inicio, hora_fin, motivo")
        .eq("profesional_id", profesional_id)
        .eq("estado", "ACTIVO")
        .lte("fecha_inicio", fecha)
        .gte("fecha_fin", fecha)
        .execute()
    )
    return res.data or []


def tiene_bloqueo_total(profesional_id: int, fecha: str) -> bool:
    """Retorna True si hay un bloqueo de DÍA COMPLETO para esa fecha."""
    bloqueos = obtener_bloqueos_fecha(profesional_id, fecha)
    return any(b.get("hora_inicio") is None for b in bloqueos)


# ══════════════════════════════════════════════════════════════
#  DISPONIBILIDAD (usado por el módulo de citas)
# ══════════════════════════════════════════════════════════════

def obtener_disponibilidad(profesional_id: int, fecha: str) -> list:
    """
    Retorna los rangos horarios disponibles para un profesional en una fecha.
    1. Consulta el día de la semana → bloques de programación
    2. Verifica bloqueos (totales y parciales) → recorta los rangos
    Retorna: [{"hora_inicio": "07:00", "hora_fin": "12:00"}, ...]
    """
    from datetime import date

    partes = fecha.split("-")
    fecha_obj = date(int(partes[0]), int(partes[1]), int(partes[2]))
    dia_semana = fecha_obj.weekday()

    # Verificar bloqueo total (día completo)
    bloqueos = obtener_bloqueos_fecha(profesional_id, fecha)

    # Si hay bloqueo de día completo → 0 disponibilidad
    if any(b.get("hora_inicio") is None for b in bloqueos):
        return []

    # Obtener bloques de programación del día de la semana
    bloques = obtener_bloques_dia(profesional_id, dia_semana)
    if not bloques:
        return []

    # Convertir bloques a rangos en minutos
    rangos = []
    for b in bloques:
        r_ini = _time_to_min(b["hora_inicio"])
        r_fin = _time_to_min(b["hora_fin"])
        rangos.append([r_ini, r_fin])

    # Restar bloqueos parciales
    bloqueos_parciales = [
        b for b in bloqueos
        if b.get("hora_inicio") is not None
    ]

    for bp in bloqueos_parciales:
        bp_ini = _time_to_min(bp["hora_inicio"])
        bp_fin = _time_to_min(bp["hora_fin"])
        rangos = _restar_rango(rangos, bp_ini, bp_fin)

    return [
        {
            "hora_inicio": _min_to_time(r[0]),
            "hora_fin": _min_to_time(r[1]),
        }
        for r in rangos
        if r[1] > r[0]
    ]


def obtener_alertas_fecha(profesional_id: int, fecha: str) -> list:
    """
    Retorna alertas para mostrar en la agenda:
    - Bloqueos parciales (con hora) → para mostrar en el timeline
    - Bloqueos totales → para mostrar banner
    """
    bloqueos = obtener_bloqueos_fecha(profesional_id, fecha)
    alertas = []

    for b in bloqueos:
        if b.get("hora_inicio") is None:
            alertas.append({
                "tipo": "bloqueo_total",
                "motivo": b.get("motivo") or "Día bloqueado",
                "hora_inicio": None,
                "hora_fin": None,
            })
        else:
            alertas.append({
                "tipo": "bloqueo_parcial",
                "motivo": b.get("motivo") or "Horario bloqueado",
                "hora_inicio": b["hora_inicio"][:5] if b["hora_inicio"] else None,
                "hora_fin": b["hora_fin"][:5] if b["hora_fin"] else None,
            })

    return alertas


# ══════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _time_to_min(t: str) -> int:
    """Convierte "HH:MM" o "HH:MM:SS" a minutos desde medianoche."""
    parts = str(t).strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _min_to_time(m: int) -> str:
    """Convierte minutos desde medianoche a "HH:MM"."""
    return f"{m // 60:02d}:{m % 60:02d}"


def _restar_rango(rangos: list, bp_ini: int, bp_fin: int) -> list:
    """
    Resta un rango de bloqueo [bp_ini, bp_fin) de una lista de rangos.
    Ej: rangos=[[420, 720]] y bloqueo=[600, 840]
        → resultado=[[420, 600]]  (7:00-10:00 queda, 10:00-12:00 se bloquea)
    """
    resultado = []
    for r_ini, r_fin in rangos:
        # Sin solapamiento
        if bp_fin <= r_ini or bp_ini >= r_fin:
            resultado.append([r_ini, r_fin])
            continue

        # Parte antes del bloqueo
        if r_ini < bp_ini:
            resultado.append([r_ini, bp_ini])

        # Parte después del bloqueo
        if r_fin > bp_fin:
            resultado.append([bp_fin, r_fin])

    return resultado

def buscar_siguiente_disponible(profesional_id: int, fecha_desde: str, duracion_min: int = 20) -> dict:
    """
    Busca el próximo slot disponible desde una fecha.
    Retorna {"fecha": "2026-05-19", "hora": "09:00"} o None si no hay en 90 días.
    """
    from datetime import date, timedelta

    partes = fecha_desde.split("-")
    fecha = date(int(partes[0]), int(partes[1]), int(partes[2]))
    hoy = date.today()

    for i in range(90):
        fecha_actual = fecha + timedelta(days=i)
        fecha_str = fecha_actual.isoformat()

        # Obtener rangos disponibles (ya resta bloqueos)
        rangos = obtener_disponibilidad(profesional_id, fecha_str)
        if not rangos:
            continue

        # Obtener citas del día
        citas = (
            _sb()
            .table("hc_citas")
            .select("hora_inicio, duracion, estado")
            .eq("medico_id", profesional_id)
            .eq("fecha", fecha_str)
            .neq("estado", "CANCELADA")
            .execute()
        ).data or []

        # Hora mínima si es hoy
        min_minutos = 0
        if fecha_actual == hoy:
            from datetime import datetime
            ahora = datetime.now()
            min_minutos = ((ahora.hour * 60 + ahora.minute + 5) // 5) * 5

        # Buscar primer slot libre
        for rango in rangos:
            r_ini = _time_to_min(rango["hora_inicio"])
            r_fin = _time_to_min(rango["hora_fin"])

            slot = max(r_ini, min_minutos)
            while slot + duracion_min <= r_fin:
                fin_slot = slot + duracion_min
                ocupado = False
                for c in citas:
                    c_ini = _time_to_min(c["hora_inicio"])
                    c_fin = c_ini + (c.get("duracion") or 20)
                    if slot < c_fin and fin_slot > c_ini:
                        ocupado = True
                        break

                if not ocupado:
                    return {
                        "fecha": fecha_str,
                        "hora": _min_to_time(slot),
                    }
                slot += 5

    return None