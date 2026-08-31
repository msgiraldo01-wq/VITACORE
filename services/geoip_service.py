"""
Geolocalización aproximada por IP + identificación amigable del
dispositivo/navegador, para el historial de accesos (auditoría).

Todo esto es "mejor esfuerzo": nunca debe romper el login. Si la
librería no está instalada, si la IP es privada/LAN (como pasa hoy con
Vitacore accedido por IP local, p. ej. 192.168.101.83), o si algo falla,
simplemente se devuelve None/una etiqueta genérica -- nunca una excepción.

Geolocalización offline con `geoip2fast` (pip install geoip2fast):
no requiere API key ni conexión a internet en cada consulta, trae una
base de datos de países incluida en el propio paquete. El nivel de
detalle es país (+ ciudad solo si se instala manualmente la base de
datos de ciudades, que no viene por defecto) -- suficiente para lo que
se pidió ("IP + ciudad/país aproximado").
"""

import re

_geoip = None
_geoip_intentado = False


def _get_geoip():
    """Instancia perezosa y única de GeoIP2Fast. Si el paquete no está
    instalado (pip install geoip2fast pendiente) o falla al cargar, se
    deja en None para siempre y el resto del sistema sigue funcionando
    sin geolocalización -- ya no se vuelve a intentar en cada request."""
    global _geoip, _geoip_intentado

    if _geoip_intentado:
        return _geoip

    _geoip_intentado = True
    try:
        from geoip2fast import GeoIP2Fast
        _geoip = GeoIP2Fast()
    except Exception as e:
        print(f"[geoip_service] geoip2fast no disponible (falta 'pip install geoip2fast'): {e}")
        _geoip = None

    return _geoip


def localizar_ip(ip_address: str):
    """Devuelve (pais, ciudad) aproximados según la IP, o (None, None)
    si no se pudo determinar (IP privada/LAN, IP vacía, librería no
    instalada, o cualquier error de lookup)."""
    if not ip_address:
        return None, None

    geoip = _get_geoip()
    if not geoip:
        return None, None

    try:
        resultado = geoip.lookup(ip_address)

        if getattr(resultado, "is_private", False):
            return None, None

        pais = getattr(resultado, "country_name", None) or None

        ciudad = None
        city_obj = getattr(resultado, "city", None)
        if city_obj is not None:
            nombre_ciudad = getattr(city_obj, "name", None)
            if nombre_ciudad:
                ciudad = nombre_ciudad

        return pais, ciudad

    except Exception as e:
        print(f"[geoip_service] No se pudo geolocalizar la IP {ip_address}: {e}")
        return None, None


def obtener_ip_cliente(request) -> str:
    """IP real del cliente, considerando que en producción Vitacore
    puede estar detrás de un proxy/balanceador (X-Forwarded-For trae
    la IP original primero en la lista)."""
    forwardeada = request.headers.get("X-Forwarded-For", "")
    if forwardeada:
        return forwardeada.split(",")[0].strip()
    return request.remote_addr or ""


# ------------------------------------------------------------------
# Identificación amigable del dispositivo/navegador a partir del
# User-Agent. Es deliberadamente simple (regex, sin dependencias
# nuevas) -- no pretende ser un parser exhaustivo, solo dar contexto
# legible en el historial ("Windows · Chrome", "Android · Chrome
# móvil", "iPhone · Safari"), no una huella técnica precisa.
# ------------------------------------------------------------------

def _detectar_so(ua: str) -> str:
    if re.search(r"windows", ua, re.I):
        return "Windows"
    if re.search(r"android", ua, re.I):
        return "Android"
    if re.search(r"iphone|ipad|ipod", ua, re.I):
        return "iOS"
    if re.search(r"mac os x|macintosh", ua, re.I):
        return "macOS"
    if re.search(r"linux", ua, re.I):
        return "Linux"
    return "Sistema desconocido"


def _detectar_navegador(ua: str) -> str:
    # Orden importa: Edge/Opera incluyen "Chrome" en su UA, y Chrome
    # incluye "Safari" en el suyo -- hay que descartar los más
    # específicos primero.
    if re.search(r"edg/", ua, re.I):
        return "Edge"
    if re.search(r"opr/|opera", ua, re.I):
        return "Opera"
    if re.search(r"chrome/", ua, re.I):
        return "Chrome"
    if re.search(r"firefox/", ua, re.I):
        return "Firefox"
    if re.search(r"safari/", ua, re.I):
        return "Safari"
    return "Navegador desconocido"


def parsear_user_agent(user_agent: str) -> str:
    """Devuelve una descripción corta y legible del dispositivo, p.ej.
    'Windows · Chrome' o 'Android · Chrome móvil'. Nunca lanza -- ante
    cualquier user-agent vacío o raro devuelve una etiqueta genérica."""
    if not user_agent:
        return "Dispositivo desconocido"

    try:
        so = _detectar_so(user_agent)
        navegador = _detectar_navegador(user_agent)
        es_movil = bool(re.search(r"mobile|android(?!.*tablet)", user_agent, re.I))

        etiqueta = f"{so} · {navegador}"
        if es_movil:
            etiqueta += " móvil"

        return etiqueta
    except Exception:
        return "Dispositivo desconocido"
