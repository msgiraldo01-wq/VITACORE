"""
Repositorio: hc_prof_programacion_repo.py
Maneja horario semanal recurrente y bloqueos de profesionales.
ACTUALIZADO: Soporta bloqueos parciales (por horas).
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


def _trabaja_festivos(profesional_id: int) -> bool:
    """Consulta directa y mínima (1 sola columna) a hc_profesionales."""
    res = (
        _sb()
        .table("hc_profesionales")
        .select("trabaja_festivos")
        .eq("id", profesional_id)
        .limit(1)
        .execute()
    )
    return bool((res.data or [{}])[0].get("trabaja_festivos"))


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


def actualizar_bloqueo(
    bloqueo_id: int,
    fecha_inicio: str,
    fecha_fin: str,
    motivo: str = None,
    hora_inicio: str = None,
    hora_fin: str = None,
) -> dict:
    """
    Actualiza un bloqueo existente. A diferencia de agregar_bloqueo, aquí sí
    se envían hora_inicio/hora_fin explícitamente aunque sean None -- así,
    si el usuario cambia un bloqueo "por horas" a "día completo" (o al
    revés), el update realmente limpia/establece esos campos en vez de
    dejar el valor anterior.
    """
    payload = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "motivo": motivo,
        "hora_inicio": hora_inicio if (hora_inicio and hora_fin) else None,
        "hora_fin": hora_fin if (hora_inicio and hora_fin) else None,
    }

    res = (
        _sb()
        .table("hc_prof_bloqueos")
        .update(payload)
        .eq("id", bloqueo_id)
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

    # Festivo y el profesional no trabaja festivos → sin disponibilidad,
    # igual que un bloqueo de día completo.
    from repositories import hc_festivos_repo
    if hc_festivos_repo.es_festivo(fecha) and not _trabaja_festivos(profesional_id):
        return []

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

    # Festivo: si el profesional no atiende festivos, se muestra como
    # bloqueo total (mismo banner rojo que ya existe en la agenda, sin
    # tocar el frontend). Si sí atiende, se muestra un aviso informativo
    # aparte, sin bloquear nada.
    from repositories import hc_festivos_repo
    nombre_festivo = hc_festivos_repo.es_festivo(fecha)
    if nombre_festivo:
        if _trabaja_festivos(profesional_id):
            alertas.append({
                "tipo": "festivo_informativo",
                "motivo": f"Festivo: {nombre_festivo} — el profesional sí atiende.",
                "hora_inicio": None,
                "hora_fin": None,
            })
        else:
            alertas.append({
                "tipo": "bloqueo_total",
                "motivo": f"Festivo: {nombre_festivo} (el profesional no atiende festivos)",
                "hora_inicio": None,
                "hora_fin": None,
            })

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
    Busca el próximo slot disponible desde una fecha, dentro de una ventana
    de 90 días. Retorna {"fecha": "2026-05-19", "hora": "09:00"} o None si no
    hay disponibilidad en ese rango.

    NOTA DE RENDIMIENTO (antes vs. ahora):
    La versión anterior recorría los 90 días uno por uno y, por cada día,
    volvía a consultar Supabase para la programación semanal y los bloqueos
    (2 consultas fijas) más las citas del día si había horario (1 consulta
    más) -- hasta ~240 consultas secuenciales en el peor caso (médico sin
    cupo cercano), que es la causa real de la demora reportada al elegir
    médico en "Nueva cita". La programación semanal y los bloqueos casi
    nunca cambian de un día a otro dentro de la ventana, así que aquí se
    traen UNA sola vez cada uno (programación semanal completa, bloqueos de
    toda la ventana, citas de toda la ventana) y el resto -- rangos por día,
    resta de bloqueos, búsqueda de slot libre -- se calcula en memoria,
    sin más ida y vuelta a la base de datos. El resultado (mismo `fecha`+
    `hora`) es idéntico al de la versión anterior; solo cambia cuántas
    consultas se hacen para llegar a él.
    """
    from datetime import date, datetime, timedelta

    partes = fecha_desde.split("-")
    fecha_inicio_busqueda = date(int(partes[0]), int(partes[1]), int(partes[2]))
    fecha_fin_busqueda = fecha_inicio_busqueda + timedelta(days=89)
    hoy = date.today()

    # 0) Festivos de toda la ventana (1 consulta) + si el profesional
    #    trabaja festivos (1 consulta mínima, 1 sola columna).
    from repositories import hc_festivos_repo
    festivos_ventana = hc_festivos_repo.listar_rango(
        fecha_inicio_busqueda.isoformat(), fecha_fin_busqueda.isoformat()
    )
    trabaja_festivos = _trabaja_festivos(profesional_id)

    # 1) Programación semanal completa del profesional (1 consulta, en vez de
    #    una por cada uno de los 90 días -- solo hay 7 patrones distintos).
    bloques_por_dia = {}
    for b in listar_por_profesional(profesional_id):
        bloques_por_dia.setdefault(b["dia_semana"], []).append(b)

    # 2) Bloqueos que se solapan con la ventana completa (1 consulta).
    bloqueos_ventana = (
        _sb()
        .table("hc_prof_bloqueos")
        .select("fecha_inicio, fecha_fin, hora_inicio, hora_fin")
        .eq("profesional_id", profesional_id)
        .eq("estado", "ACTIVO")
        .lte("fecha_inicio", fecha_fin_busqueda.isoformat())
        .gte("fecha_fin", fecha_inicio_busqueda.isoformat())
        .execute()
    ).data or []

    # 3) Citas del profesional en toda la ventana (1 consulta), agrupadas
    #    por fecha para acceso directo dentro del loop.
    citas_ventana = (
        _sb()
        .table("hc_citas")
        .select("fecha, hora_inicio, duracion, estado")
        .eq("medico_id", profesional_id)
        .gte("fecha", fecha_inicio_busqueda.isoformat())
        .lte("fecha", fecha_fin_busqueda.isoformat())
        .neq("estado", "CANCELADA")
        .execute()
    ).data or []

    citas_por_dia = {}
    for c in citas_ventana:
        citas_por_dia.setdefault(c["fecha"], []).append(c)

    for i in range(90):
        fecha_actual = fecha_inicio_busqueda + timedelta(days=i)
        fecha_str = fecha_actual.isoformat()

        # Festivo y el profesional no trabaja festivos → se salta el día,
        # igual que un bloqueo de día completo.
        if fecha_str in festivos_ventana and not trabaja_festivos:
            continue

        # Bloqueos activos que cubren este día específico (mismo filtro que
        # obtener_bloqueos_fecha, aplicado en memoria).
        bloqueos_dia = [
            b for b in bloqueos_ventana
            if b["fecha_inicio"] <= fecha_str <= b["fecha_fin"]
        ]

        # Bloqueo de día completo (hora_inicio None) → sin disponibilidad.
        if any(b.get("hora_inicio") is None for b in bloqueos_dia):
            continue

        bloques = bloques_por_dia.get(fecha_actual.weekday(), [])
        if not bloques:
            continue

        rangos = [
            [_time_to_min(b["hora_inicio"]), _time_to_min(b["hora_fin"])]
            for b in bloques
        ]

        for bp in bloqueos_dia:
            if bp.get("hora_inicio") is None:
                continue
            rangos = _restar_rango(
                rangos, _time_to_min(bp["hora_inicio"]), _time_to_min(bp["hora_fin"])
            )

        rangos = [r for r in rangos if r[1] > r[0]]
        if not rangos:
            continue

        citas = citas_por_dia.get(fecha_str, [])

        # Hora mínima si es hoy
        min_minutos = 0
        if fecha_actual == hoy:
            ahora = datetime.now()
            min_minutos = ((ahora.hour * 60 + ahora.minute + 5) // 5) * 5

        # Buscar primer slot libre
        for r_ini, r_fin in rangos:
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