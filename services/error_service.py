"""
Registro central de errores de la aplicación.

Qué hace cuando algo falla:
  1. Genera un código corto (VTC-7F3A91) que el usuario ve en pantalla y
     le dicta a quien da soporte.
  2. Escribe el error completo en el archivo de log (siempre, pase lo que
     pase: es la red de seguridad si la base no responde).
  3. Lo guarda en la tabla app_errores para que se pueda consultar desde
     la pantalla de Soporte, agrupando las repeticiones del mismo error
     en una sola fila con un contador.

Reglas que se respetan aquí:

  - Registrar un error NUNCA puede provocar otro. Todo va dentro de un
    try/except que, en el peor caso, se queda solo con el log en archivo.
  - NO se guarda el cuerpo del request. En esta aplicación por ahí viajan
    nombres, cédulas y diagnósticos de pacientes, y una tabla de errores
    no es lugar para datos clínicos. Se guardan ruta, método y usuario,
    que es lo que de verdad sirve para reproducir el problema.
  - Al usuario se le muestra el código, nunca el mensaje técnico.
"""

import hashlib
import logging
import os
import traceback
import uuid
from logging.handlers import RotatingFileHandler

_logger = logging.getLogger("vitacore")


# =========================
# LOGGING A ARCHIVO
# =========================

def configurar_logging(app=None, carpeta="logs", nivel=logging.INFO):
    """
    Deja el logger 'vitacore' escribiendo en logs/vitacore.log, rotando
    cada 2 MB y guardando 10 archivos (unos cuantos meses de operación
    normal). Se llama una sola vez, al arrancar la aplicación.
    """
    if _logger.handlers:            # ya configurado (recarga de Flask)
        return _logger

    _logger.setLevel(nivel)
    formato = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Consola: para desarrollo
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    _logger.addHandler(consola)

    # Archivo: para producción. Si no se puede escribir (permisos, disco),
    # la aplicación sigue con la consola en vez de no arrancar.
    try:
        os.makedirs(carpeta, exist_ok=True)
        archivo = RotatingFileHandler(
            os.path.join(carpeta, "vitacore.log"),
            maxBytes=2 * 1024 * 1024, backupCount=10, encoding="utf-8",
        )
        archivo.setFormatter(formato)
        _logger.addHandler(archivo)
    except Exception as e:
        _logger.warning("No se pudo abrir el archivo de log: %s", e)

    if app is not None:
        app.logger.handlers = _logger.handlers
        app.logger.setLevel(nivel)

    return _logger


def log():
    return _logger


# =========================
# REGISTRO DE UN ERROR
# =========================

def _codigo_nuevo() -> str:
    return "VTC-" + uuid.uuid4().hex[:6].upper()


def _huella(exc, ruta: str) -> str:
    """
    Identifica un error de forma estable para poder agrupar repeticiones:
    tipo de excepción + ruta + el último punto del traceback que está en
    código del proyecto (no dentro de una librería).
    """
    ultimo = ""
    try:
        for marco in reversed(traceback.extract_tb(exc.__traceback__) or []):
            ruta_archivo = (marco.filename or "").replace("\\", "/")
            if "site-packages" in ruta_archivo or "/lib/" in ruta_archivo:
                continue
            ultimo = f"{os.path.basename(ruta_archivo)}:{marco.lineno}"
            break
    except Exception:
        pass

    semilla = f"{type(exc).__name__}|{ruta}|{ultimo}"
    return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:20]


def _contexto():
    """Datos del request y de la sesión, si los hay. Fuera de un request
    (por ejemplo un script) devuelve el diccionario vacío."""
    datos = {"ruta": "", "metodo": "", "ip": "", "user_agent": "",
             "usuario": "", "usuario_id": "", "empresa_id": None, "modulo": ""}
    try:
        from flask import request, session, has_request_context
        if not has_request_context():
            return datos

        datos["ruta"] = request.path
        datos["metodo"] = request.method
        datos["user_agent"] = (request.headers.get("User-Agent") or "")[:400]

        # IP real detrás de un proxy inverso (nginx, Cloudflare)
        reenviada = request.headers.get("X-Forwarded-For", "")
        datos["ip"] = (reenviada.split(",")[0].strip() if reenviada
                       else (request.remote_addr or ""))

        usuario = session.get("user") or {}
        datos["usuario"] = usuario.get("username") or ""
        datos["usuario_id"] = str(usuario.get("id") or "")
        datos["empresa_id"] = session.get("empresa_id")

        try:
            from services import permisos_service
            datos["modulo"] = permisos_service.resolver_modulo_code(request.path) or ""
        except Exception:
            pass
    except Exception:
        pass
    return datos


def registrar(exc: BaseException, nota: str = "") -> str:
    """
    Registra un error y devuelve el código para mostrarle al usuario.

    Pensado para usarse tanto desde los manejadores globales como dentro
    de un `except` puntual:

        except Exception as e:
            codigo = error_service.registrar(e)
            return jsonify({"ok": False, "codigo": codigo}), 500
    """
    codigo = _codigo_nuevo()

    ctx = _contexto()
    tipo = type(exc).__name__
    mensaje = str(exc)[:1000]
    traza = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:8000]

    # 1) El log SIEMPRE, antes de tocar la base: si Supabase está caído,
    #    este es el único rastro que queda.
    _logger.error(
        "[%s] %s %s · %s: %s · usuario=%s empresa=%s%s\n%s",
        codigo, ctx["metodo"], ctx["ruta"], tipo, mensaje,
        ctx["usuario"] or "anónimo", ctx["empresa_id"],
        f" · {nota}" if nota else "", traza,
    )

    # 2) La base, para la pantalla de Soporte. Si falla, no pasa nada más
    #    que perder esa fila: el error ya quedó en el archivo.
    try:
        from services.supabase_service import get_supabase_admin
        resultado = get_supabase_admin().rpc("app_registrar_error", {
            "p_codigo": codigo,
            "p_huella": _huella(exc, ctx["ruta"]),
            "p_empresa_id": ctx["empresa_id"],
            "p_usuario": ctx["usuario"],
            "p_usuario_id": ctx["usuario_id"],
            "p_ruta": ctx["ruta"],
            "p_metodo": ctx["metodo"],
            "p_modulo": ctx["modulo"],
            "p_tipo": tipo,
            "p_mensaje": f"{mensaje} · {nota}" if nota else mensaje,
            "p_traceback": traza,
            "p_ip": ctx["ip"],
            "p_user_agent": ctx["user_agent"],
        }).execute()

        # Si el error ya existía, la función devuelve el código ORIGINAL:
        # así el usuario dicta el mismo código que ya está en el panel.
        if resultado and getattr(resultado, "data", None):
            previo = resultado.data
            if isinstance(previo, str) and previo.startswith("VTC-"):
                codigo = previo
    except Exception as e:
        _logger.warning("[%s] no se pudo guardar el error en la base: %s", codigo, e)

    return codigo
