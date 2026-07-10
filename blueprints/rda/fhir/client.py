"""
Cliente del IHCE (Ministerio): autenticación OAuth2, envío y consulta de RDA.
Las credenciales se leen de variables de entorno (.env), no del código.
"""

import os
import requests

from . import constants as C


class IhceError(Exception):
    pass


def _cfg():
    """Lee la configuración del Ministerio desde variables de entorno."""
    return {
        "enabled": os.environ.get("IHCE_ENABLED", "0") == "1",
        "endpoint": os.environ.get("IHCE_ENDPOINT", "").rstrip("/"),
        "tenant_id": os.environ.get("IHCE_TENANT_ID", ""),
        "client_id": os.environ.get("IHCE_CLIENT_ID", ""),
        "client_secret": os.environ.get("IHCE_CLIENT_SECRET", ""),
        "scope": os.environ.get("IHCE_SCOPE", ""),
        "subscription_key": os.environ.get("IHCE_SUBSCRIPTION_KEY", ""),
        "timeout": int(os.environ.get("IHCE_TIMEOUT", "40")),
    }


def esta_habilitado():
    return _cfg()["enabled"]


# --- Caché simple de token (dura mientras el Ministerio lo mantenga válido) ---
_token_cache = {"valor": None, "expira": 0.0}


def obtener_token_actual():
    """Devuelve un token válido, reutilizándolo mientras no expire.
    Evita pedir un token nuevo en cada consulta (ahorra 1-2 s por búsqueda)."""
    import time
    cfg = _cfg()
    if not cfg["enabled"]:
        raise IhceError("Se requiere IHCE_ENABLED=1")
    ahora = time.time()
    if _token_cache["valor"] and ahora < _token_cache["expira"]:
        return _token_cache["valor"]
    token = _obtener_token(cfg)
    # margen de seguridad: se renueva 5 min antes de la expiración real (~1 h)
    _token_cache["valor"] = token
    _token_cache["expira"] = ahora + 55 * 60
    return token


def _obtener_token(cfg):
    url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": cfg["scope"],
    }
    try:
        r = requests.post(url, data=data, timeout=cfg["timeout"])
    except requests.RequestException as e:
        raise IhceError(f"Error de red al autenticar: {e}") from e
    if r.status_code != 200:
        raise IhceError(f"Error de autenticación ({r.status_code}): {r.text[:300]}")
    return r.json().get("access_token")


def _headers(cfg, token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": cfg["subscription_key"],
    }


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:600]}


def enviar_rda_consulta(bundle: dict) -> dict:
    """Transmite un Bundle de consulta externa al Ministerio."""
    cfg = _cfg()
    if not cfg["enabled"]:
        raise IhceError("La transmisión real requiere IHCE_ENABLED=1")

    token = _obtener_token(cfg)
    url = f"{cfg['endpoint']}/{C.OP_ENVIAR_CONSULTA}"
    try:
        r = requests.post(url, json=bundle, headers=_headers(cfg, token),
                          timeout=cfg["timeout"])
    except requests.RequestException as e:
        raise IhceError(f"Error de red al transmitir: {e}") from e

    return {
        "status": r.status_code,
        "ok": r.status_code == 200,
        "respuesta": _safe_json(r),
    }


def consultar_rda_paciente(*, tipo_doc, num_doc) -> dict:
    """Lista los RDA de encuentros clínicos de un paciente."""
    cfg = _cfg()
    if not cfg["enabled"]:
        raise IhceError("La consulta real requiere IHCE_ENABLED=1")

    token = _obtener_token(cfg)
    url = f"{cfg['endpoint']}/{C.OP_CONSULTAR_ENCUENTROS}"
    params = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "identifier", "part": [
                {"name": "type", "valueString": tipo_doc},
                {"name": "value", "valueString": str(num_doc)},
            ]},
        ],
    }
    try:
        r = requests.post(url, json=params, headers=_headers(cfg, token),
                          timeout=cfg["timeout"])
    except requests.RequestException as e:
        raise IhceError(f"Error de red al consultar: {e}") from e

    return {
        "status": r.status_code,
        "ok": r.status_code == 200,
        "respuesta": _safe_json(r),
    }


# =========================
# OPERACIONES DE CONSULTA (VISOR)
# =========================

def _post_operacion(operacion, payload, cfg=None, token=None):
    """POST a una operación FHIR del Ministerio. Reusa token si se pasa."""
    cfg = cfg or _cfg()
    if not cfg["enabled"]:
        raise IhceError("La consulta requiere IHCE_ENABLED=1")
    token = token or _obtener_token(cfg)
    url = f"{cfg['endpoint']}/{operacion}"
    try:
        r = requests.post(url, json=payload, headers=_headers(cfg, token),
                          timeout=cfg["timeout"])
    except requests.RequestException as e:
        raise IhceError(f"Error de red en {operacion}: {e}") from e
    if r.status_code != 200:
        raise IhceError(f"{operacion} devolvió HTTP {r.status_code}")
    return _safe_json(r)


def _get_recurso(tipo, rid, cfg=None, token=None):
    """GET de un recurso FHIR por tipo e id."""
    cfg = cfg or _cfg()
    token = token or _obtener_token(cfg)
    url = f"{cfg['endpoint']}/{tipo}/{rid}"
    try:
        r = requests.get(url, headers=_headers(cfg, token), timeout=cfg["timeout"])
    except requests.RequestException as e:
        raise IhceError(f"Error de red al leer {tipo}/{rid}: {e}") from e
    if r.status_code != 200:
        return None
    return _safe_json(r)


def consultar_rda_completo(tipo_doc, num_doc):
    """
    Consulta en paralelo los dos RDA del paciente:
      - $consultar-rda-paciente         (antecedentes manifestados)
      - $consultar-rda-encuentros-clinicos (atenciones)
    Devuelve dict con ambos resultados, sin lanzar si uno falla.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cfg = _cfg()
    if not cfg["enabled"]:
        raise IhceError("La consulta requiere IHCE_ENABLED=1")
    token = obtener_token_actual()  # token cacheado, uno para ambas

    payload = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "identifier", "part": [
                {"name": "type", "valueString": tipo_doc},
                {"name": "value", "valueString": str(num_doc)},
            ]},
        ],
    }

    ops = {
        "paciente": C.OP_CONSULTAR_PACIENTE,
        "encuentros": C.OP_CONSULTAR_ENCUENTROS,
    }
    out = {k: {"ok": False, "data": None, "error": None} for k in ops}

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut = {ex.submit(_post_operacion, op, payload, cfg, token): k
               for k, op in ops.items()}
        for f in as_completed(fut):
            k = fut[f]
            try:
                out[k] = {"ok": True, "data": f.result(), "error": None}
            except Exception as e:
                out[k] = {"ok": False, "data": None, "error": str(e)}
    return out, token


def obtener_recurso(tipo, rid, token=None):
    """Lee un recurso referenciado (Patient, Encounter, Condition, ...)."""
    return _get_recurso(tipo, rid, token=token)