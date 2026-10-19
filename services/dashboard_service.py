"""
Datos del Dashboard clínico (/hc/).

Criterios de diseño, en orden de importancia:

1. UNA consulta por tarjeta. Nada de "una consulta para el conteo de hoy,
   otra para el de la semana y otra para los pacientes distintos": se trae
   el rango una sola vez y se cuenta en Python, que es gratis comparado
   con otro viaje a Supabase.
2. Solo las columnas que se pintan. Ningún `select("*")` aquí: el dashboard
   es la pantalla que más gente abre y la que más veces se recarga.
3. Solo se consulta lo que el usuario puede ver. Si un rol no tiene
   Farmacia, esa consulta no se hace -- no se hace y se esconde después.
4. Caché en memoria de 60 segundos por empresa y juego de permisos. Abrir
   el dashboard tres veces seguidas (o tenerlo en dos pestañas) no golpea
   la base tres veces.

Cada bloque va en su propio try: si una tarjeta falla, el resto de la
pantalla se pinta igual y esa queda marcada con error.
"""

import time
from datetime import date, datetime, timedelta, timezone

from services.supabase_service import get_supabase_admin


# La clínica opera en Colombia: "hoy" es hoy en Bogotá, no en el reloj
# del servidor (en producción suele estar en UTC, 5 horas adelante, así
# que después de las 7 p.m. "hoy" se convertiría en mañana).
try:
    from zoneinfo import ZoneInfo
    _TZ_CO = ZoneInfo("America/Bogota")
except Exception:
    _TZ_CO = timezone(timedelta(hours=-5))


_CACHE = {}
_TTL_SEGUNDOS = 60

DIAS_GRAFICO = 14

# Citas que todavía tienen algo pendiente en la clínica hoy.
_ESTADOS_ACTIVOS = ("PENDIENTE", "CONFIRMADA", "EN_ATENCION")
# Las que esperan ser admitidas (mismo criterio que el módulo de Admisiones).
_ESTADOS_ADMISION = ("PENDIENTE", "CONFIRMADA")


def hoy_co() -> date:
    return datetime.now(_TZ_CO).date()


_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_larga(iso: str) -> str:
    """'2026-04-13' -> '13 de abril' (con año si no es el actual)."""
    try:
        a, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    except Exception:
        return iso or ""
    texto = f"{d} de {_MESES[m - 1]}"
    return texto if a == hoy_co().year else f"{texto} de {a}"


def _nombre_paciente(pac: dict) -> str:
    if not pac:
        return "Paciente"
    partes = [pac.get("primer_nombre"), pac.get("primer_apellido")]
    return " ".join(p for p in partes if p) or "Paciente"


# =========================
# TARJETAS
# =========================

def _agenda_hoy(sb, empresa_id):
    """Citas de hoy: conteo por estado, pendientes de admisión y las
    próximas de la jornada. Una sola consulta para las tres cosas."""
    hoy = hoy_co().isoformat()
    r = (
        sb.table("hc_citas")
        .select("estado, hora_inicio, "
                "paciente:hc_pacientes(primer_nombre, primer_apellido), "
                "medico:hc_profesionales(nombre_completo)")
        .eq("empresa_id", empresa_id)
        .eq("fecha", hoy)
        .order("hora_inicio")
        .execute()
    )
    filas = r.data or []

    por_estado = {}
    for f in filas:
        estado = (f.get("estado") or "SIN_ESTADO").upper()
        por_estado[estado] = por_estado.get(estado, 0) + 1

    proximas = []
    for f in filas:
        if (f.get("estado") or "").upper() not in _ESTADOS_ACTIVOS:
            continue
        proximas.append({
            "hora": (f.get("hora_inicio") or "")[:5],
            "paciente": _nombre_paciente(f.get("paciente")),
            "medico": (f.get("medico") or {}).get("nombre_completo") or "",
            "estado": (f.get("estado") or "").upper(),
        })
        if len(proximas) == 5:
            break

    # Estado vacío con contexto: en vez de un 0 gigante, se dice cuándo fue
    # la última jornada con citas. Esta consulta SOLO corre si hoy no hay
    # nada, así que en un día normal de clínica cuesta cero.
    ultima = None
    if not filas:
        r2 = (
            sb.table("hc_citas").select("fecha")
            .eq("empresa_id", empresa_id)
            .lt("fecha", hoy)
            .order("fecha", desc=True)
            .limit(60)
            .execute()
        )
        fechas = [f.get("fecha") for f in (r2.data or []) if f.get("fecha")]
        if fechas:
            dia = fechas[0]
            ultima = {
                "fecha": dia,
                "etiqueta": _fecha_larga(dia),
                # cuenta dentro de las 60 traídas; si ese día tuvo más, se
                # queda corto, pero es un dato de contexto, no un indicador.
                "citas": sum(1 for f in fechas if f == dia),
            }

    return {
        "total": len(filas),
        "por_estado": por_estado,
        "atendidas": por_estado.get("FINALIZADA", 0) + por_estado.get("FACTURADA", 0),
        "en_atencion": por_estado.get("EN_ATENCION", 0),
        "pendientes_admision": sum(por_estado.get(e, 0) for e in _ESTADOS_ADMISION),
        "proximas": proximas,
        "fecha": hoy,
        "ultima_jornada": ultima,
    }


def _actividad_clinica(sb, empresa_id):
    """Evoluciones de las últimas dos semanas. De esta única consulta salen
    el conteo de hoy, el de la semana, los pacientes distintos atendidos y
    la serie diaria del gráfico."""
    hoy = hoy_co()
    desde = hoy - timedelta(days=DIAS_GRAFICO - 1)
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    r = (
        sb.table("hc_evoluciones")
        .select("fecha, paciente_id")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde.isoformat())
        .execute()
    )
    filas = r.data or []

    por_dia = {(desde + timedelta(days=i)).isoformat(): 0 for i in range(DIAS_GRAFICO)}
    hoy_iso = hoy.isoformat()
    semana_iso = inicio_semana.isoformat()
    total_hoy = 0
    total_semana = 0
    pacientes = set()

    for f in filas:
        dia = (f.get("fecha") or "")[:10]
        if dia in por_dia:
            por_dia[dia] += 1
        if dia == hoy_iso:
            total_hoy += 1
        if dia >= semana_iso:
            total_semana += 1
            if f.get("paciente_id"):
                pacientes.add(f["paciente_id"])

    serie = [{"dia": d, "total": por_dia[d]} for d in sorted(por_dia)]

    # Igual que la agenda: si no hubo actividad esta semana, se busca la
    # última nota registrada para dar contexto. Solo en ese caso.
    ultima_nota = None
    if total_semana == 0:
        r2 = (
            sb.table("hc_evoluciones").select("fecha")
            .eq("empresa_id", empresa_id)
            .order("fecha", desc=True)
            .limit(1)
            .execute()
        )
        if r2.data:
            dia = (r2.data[0].get("fecha") or "")[:10]
            if dia:
                ultima_nota = {"fecha": dia, "etiqueta": _fecha_larga(dia)}

    return {
        "hoy": total_hoy,
        "semana": total_semana,
        "pacientes_semana": len(pacientes),
        "serie": serie,
        "maximo": max((p["total"] for p in serie), default=0),
        "ultima_nota": ultima_nota,
    }


def _ultimas_evoluciones(sb, empresa_id, limite=5):
    """Las últimas notas clínicas, para entrar directo a la historia."""
    r = (
        sb.table("hc_evoluciones")
        .select("id, paciente_id, fecha, cie10_codigo, cie10_nombre, "
                "paciente:hc_pacientes(primer_nombre, primer_apellido), "
                "medico:hc_profesionales(nombre_completo)")
        .eq("empresa_id", empresa_id)
        .order("fecha", desc=True)
        .limit(limite)
        .execute()
    )
    salida = []
    for f in (r.data or []):
        salida.append({
            "id": f.get("id"),
            "paciente_id": f.get("paciente_id"),
            "paciente": _nombre_paciente(f.get("paciente")),
            "medico": (f.get("medico") or {}).get("nombre_completo") or "",
            "fecha": (f.get("fecha") or "")[:16].replace("T", " "),
            "dx": " · ".join(x for x in [f.get("cie10_codigo"), f.get("cie10_nombre")] if x),
        })
    return salida


def _rda(sb, empresa_id):
    """Estado de las transmisiones al Ministerio."""
    r = sb.table("rda_envios").select("estado").execute()
    filas = r.data or []
    aceptados = sum(1 for f in filas if f.get("estado") == "aceptado")
    rechazados = sum(1 for f in filas if f.get("estado") in ("rechazado", "error"))
    pendientes = sum(1 for f in filas
                     if f.get("estado") in ("pendiente", "excepcion_identidad"))
    return {
        "total": len(filas),
        "aceptados": aceptados,
        "rechazados": rechazados,
        "pendientes": pendientes,
    }


def _farmacia(sb, empresa_id):
    """Resumen de inventario. Lo calcula Postgres (fn_inv_dashboard), así
    que es una sola llamada y no trae filas de producto."""
    # Se llama la misma funcion de Postgres que usa inventario_repository,
    # pero con el cliente compartido (el repositorio crearia uno nuevo y
    # eso son ~700 ms mas solo por el handshake).
    datos = sb.rpc("fn_inv_dashboard", {"p_empresa_id": empresa_id}).execute().data
    if isinstance(datos, list):
        datos = datos[0] if datos else {}
    return datos or {}


# =========================
# PENDIENTES DEL DÍA
# =========================

def _plural(n, singular, plural=None):
    return singular if n == 1 else (plural or singular + "s")


def _construir_pendientes(datos: dict) -> list:
    """
    Traduce los datos ya consultados a una lista de cosas por hacer.

    No consulta nada: trabaja sobre lo que las tarjetas ya trajeron, así
    que esta sección sale gratis. Si la lista queda vacía, la pantalla
    muestra "todo al día" -- que es información, a diferencia de un 0.

    Niveles: critico (algo ya se dañó o se perdió), atencion (se va a
    dañar si nadie hace nada) e info (trabajo normal de la jornada).
    """
    pendientes = []

    rda = datos.get("rda") or {}
    if rda.get("rechazados"):
        n = rda["rechazados"]
        pendientes.append({
            "nivel": "critico", "icono": "fa-circle-exclamation",
            "texto": f"{n} {_plural(n, 'envío')} al Ministerio {_plural(n, 'rechazado')}",
            "detalle": "No quedaron registrados en el RDA.",
            "enlace": "/rda/?estado=rechazado", "cta": "Reintentar",
        })

    farmacia = datos.get("farmacia") or {}
    # Nota: la función de Postgres devuelve 'rojo' y 'vencidos' para lo
    # mismo (lote vencido), así que aquí solo se usa 'vencidos' y no se
    # listan dos veces.
    if farmacia.get("vencidos"):
        n = farmacia["vencidos"]
        pendientes.append({
            "nivel": "critico", "icono": "fa-triangle-exclamation",
            "texto": f"{n} {_plural(n, 'lote')} {_plural(n, 'vencido')} en bodega",
            "detalle": "Hay que darlos de baja.",
            "enlace": "/inventario/reportes/vencimientos?semaforo=rojo", "cta": "Ver",
        })
    if farmacia.get("amarillo"):
        n = farmacia["amarillo"]
        pendientes.append({
            "nivel": "atencion", "icono": "fa-hourglass-half",
            "texto": f"{n} {_plural(n, 'lote')} {_plural(n, 'próximo', 'próximos')} a vencer",
            "detalle": "Conviene rotarlos antes de perderlos.",
            "enlace": "/inventario/reportes/vencimientos?semaforo=amarillo", "cta": "Ver",
        })
    if farmacia.get("bajo_minimo"):
        n = farmacia["bajo_minimo"]
        pendientes.append({
            "nivel": "atencion", "icono": "fa-box-open",
            "texto": f"{n} {_plural(n, 'producto')} bajo el stock mínimo",
            "detalle": "Revisar antes de que se agoten.",
            "enlace": "/inventario/dashboard", "cta": "Ver",
        })

    if rda.get("pendientes"):
        n = rda["pendientes"]
        pendientes.append({
            "nivel": "atencion", "icono": "fa-cloud-arrow-up",
            "texto": f"{n} RDA sin transmitir al Ministerio",
            "detalle": "Quedaron en cola o con excepción de identidad.",
            "enlace": "/rda/", "cta": "Revisar",
        })

    agenda = datos.get("agenda") or {}
    if agenda.get("pendientes_admision"):
        n = agenda["pendientes_admision"]
        pendientes.append({
            "nivel": "info", "icono": "fa-door-open",
            "texto": f"{n} {_plural(n, 'paciente')} por admitir hoy",
            "detalle": "Citas de hoy que aún no registran llegada.",
            "enlace": "/hc/admisiones", "cta": "Admitir",
        })
    if agenda.get("en_atencion"):
        n = agenda["en_atencion"]
        pendientes.append({
            "nivel": "info", "icono": "fa-stethoscope",
            "texto": f"{n} {_plural(n, 'consulta')} en curso",
            "detalle": "Esperan que se cierre la nota clínica.",
            "enlace": "/hc/agenda-clinica", "cta": "Ver agenda",
        })

    orden = {"critico": 0, "atencion": 1, "info": 2}
    pendientes.sort(key=lambda p: orden.get(p["nivel"], 9))
    return pendientes


# =========================
# ORQUESTADOR
# =========================

_TARJETAS = {
    "agenda": _agenda_hoy,
    "actividad": _actividad_clinica,
    "ultimas": _ultimas_evoluciones,
    "rda": _rda,
    "farmacia": _farmacia,
}


def resumen(empresa_id, permisos: dict) -> dict:
    """
    Arma el dashboard con las tarjetas que `permisos` habilite.

    permisos: {"agenda": bool, "actividad": bool, "ultimas": bool,
               "rda": bool, "farmacia": bool}
    """
    habilitadas = tuple(sorted(k for k, v in permisos.items() if v))
    clave = (empresa_id, habilitadas, hoy_co().isoformat())

    guardado = _CACHE.get(clave)
    if guardado and (time.time() - guardado["t"]) < _TTL_SEGUNDOS:
        return {**guardado["datos"], "cacheado": True}

    # Un solo cliente para todas las tarjetas. Crear uno por consulta
    # (que es lo que hace el resto del proyecto) cuesta ~700 ms extra en
    # cada una por el handshake; reutilizarlo baja cada consulta de ~850 ms
    # a ~140 ms, medido contra esta misma base.
    sb = get_supabase_admin()

    datos = {"consultas": 0, "errores": []}
    for nombre in habilitadas:
        funcion = _TARJETAS.get(nombre)
        if not funcion:
            continue
        try:
            datos[nombre] = funcion(sb, empresa_id)
            datos["consultas"] += 1
        except Exception as e:
            print(f"[DASHBOARD] falló la tarjeta '{nombre}': {e}")
            datos[nombre] = None
            datos["errores"].append(nombre)

    # Los pendientes salen de lo ya consultado: ninguna consulta extra.
    datos["pendientes"] = _construir_pendientes(datos)
    datos["generado"] = datetime.now(_TZ_CO).strftime("%H:%M:%S")
    _CACHE[clave] = {"t": time.time(), "datos": datos}
    return {**datos, "cacheado": False}


def invalidar_cache():
    """Para pruebas o para forzar un refresco tras un cambio de datos."""
    _CACHE.clear()
