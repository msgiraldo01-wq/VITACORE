"""
Cuánto dura una sesión y cuándo hay que cerrarla.

Vitacore no tenía nada de esto: la cookie se emitía sin fecha de
expiración, así que la sesión vivía lo que viviera el navegador. Un
equipo del consultorio con la pantalla abierta seguía dentro al día
siguiente.

La solución estándar de Flask -- marcar la sesión como permanente y
poner PERMANENT_SESSION_LIFETIME -- aquí NO sirve. Cada pantalla
abierta llama a /ping cada 30 segundos para vigilar la conexión
(templates/hc/base.html), y Flask renueva la cookie en cada petición.
La sesión se renovaría sola para siempre con nadie delante.

Por eso la inactividad se mide contra peticiones que sí representan a
una persona, con una lista explícita de rutas que no cuentan.
"""

import os

from services import cache_service


# Último recurso, si la empresa no tiene política y .env tampoco dice nada.
INACTIVIDAD_POR_DEFECTO = 30   # minutos
JORNADA_POR_DEFECTO = 12       # horas

# Rutas cuyo tráfico NO es actividad de una persona. El ping es el
# motivo de que esta lista exista; las demás están porque pedir un CSS
# o salirse tampoco dice que haya alguien trabajando.
#
# "/auth/" cubre login y logout, que viven bajo ese prefijo: entrar o
# salir no es trabajar, y si el guardia interceptara el logout nadie
# podría cerrar una sesión ya caducada.
RUTAS_EXENTAS = ("/ping", "/static/", "/auth/", "/favicon")


def _entero(valor, minimo, maximo):
    """Un número de configuración dentro de su rango, o None si no vale."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo else None


@cache_service.cacheado(60)
def _de_la_empresa(empresa_id):
    """
    La política que tenga configurada la empresa.

    Cacheada un minuto porque esto se consulta en CADA petición: sin
    caché sería un viaje a la base por cada clic de cada usuario. Un
    minuto es poco para quien cambia la política y mucho para el coste.
    """
    if not empresa_id:
        return {}
    try:
        from services.supabase_service import get_supabase_admin
        r = (get_supabase_admin()
             .table("hc_empresas")
             .select("sesion_inactividad_min,sesion_jornada_horas")
             .eq("id", empresa_id)
             .limit(1)
             .execute())
        return (r.data or [{}])[0] or {}
    except Exception:
        # La migración puede no estar corrida todavía, o la base puede
        # estar teniendo un mal momento. Ninguna de las dos cosas puede
        # dejar a la gente sin poder trabajar: se cae a los valores por
        # defecto, que son los más estrictos que conocemos.
        return {}


def politica(empresa_id=None):
    """
    Minutos de inactividad y horas de jornada que aplican ahora.

    Tres escalones: lo de la empresa, lo de .env, y lo del código.
    """
    de_empresa = _de_la_empresa(empresa_id)

    inactividad = (
        _entero(de_empresa.get("sesion_inactividad_min"), 5, 480)
        or _entero(os.getenv("SESION_INACTIVIDAD_MIN"), 5, 480)
        or INACTIVIDAD_POR_DEFECTO
    )
    jornada = (
        _entero(de_empresa.get("sesion_jornada_horas"), 1, 24)
        or _entero(os.getenv("SESION_JORNADA_HORAS"), 1, 24)
        or JORNADA_POR_DEFECTO
    )
    return {"inactividad_min": inactividad, "jornada_horas": jornada}


def es_exenta(ruta):
    """¿Esta ruta cuenta como alguien trabajando?"""
    return any(ruta.startswith(p) for p in RUTAS_EXENTAS)


def motivo_de_cierre(ultima_actividad, inicio_sesion, ahora, pol):
    """
    Por qué hay que cerrar esta sesión, o None si no hay que cerrarla.

    Devuelve "inactividad" o "jornada" para poder decirle a la persona
    cuál de los dos límites la sacó, en vez del clásico "su sesión ha
    expirado" que no explica nada.

    Una marca ausente o ilegible se trata como sesión a cerrar: una
    sesión cuyo origen no se puede demostrar no es una sesión válida.
    """
    if not ultima_actividad or not inicio_sesion:
        return "inactividad"

    try:
        if ahora - float(ultima_actividad) > pol["inactividad_min"] * 60:
            return "inactividad"
        if ahora - float(inicio_sesion) > pol["jornada_horas"] * 3600:
            return "jornada"
    except (TypeError, ValueError):
        return "inactividad"

    return None


def invalidar_politica():
    """Tras guardar la empresa, para que el cambio no espere al minuto."""
    # El prefijo es el espacio que arma cache_service: módulo.función.
    cache_service.invalidar("sesion_service")
