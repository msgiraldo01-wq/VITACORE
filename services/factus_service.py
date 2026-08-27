"""
Cliente de la API Factus V2 (facturación electrónica DIAN) — Vitacore
======================================================================

Este módulo encapsula toda la comunicación HTTP con Factus: autenticación
OAuth2, creación/validación de facturas y notas, consulta, descarga de
PDF/XML y tablas de referencia.

IMPORTANTE — estado de verificación de cada endpoint
------------------------------------------------------
Cada entrada de ENDPOINTS trae una etiqueta:

  (CONFIRMADO)  → Verificado contra la documentación oficial de Factus
                  (developers.factus.com.co) el 2026-08-26.
  (VERIFICAR)   → Sigue el mismo patrón de la API pero su path exacto no
                  pudo confirmarse en la documentación pública al momento
                  de escribir esto. Antes de usarlo en producción, revisa
                  la colección Postman oficial:
                  https://developers.factus.com.co/coleccion
                  y ajusta la constante correspondiente si difiere.

Nada de esto requiere tocar el resto de la aplicación: si Factus cambia
un path, se corrige aquí, en un solo lugar.
"""

import base64
import threading
import time
from typing import Optional

import requests
from flask import current_app

BASE_URLS = {
    "sandbox": "https://api-sandbox.factus.com.co",
    # (VERIFICAR) El host de producción no se confirmó explícitamente en la
    # documentación pública consultada; se asume el mismo patrón que el de
    # sandbox. Confírmalo con soporte de Factus antes de salir a producción.
    "production": "https://api.factus.com.co",
}

ENDPOINTS = {
    "token": "/oauth/token",                                         # (CONFIRMADO)
    "acquirer": "/v2/dian/acquirer",                                  # (CONFIRMADO)
    "numbering_ranges": "/v2/numbering-ranges",                       # (CONFIRMADO 2026-08-26 — probado en sandbox real)
    "bills_validate": "/v2/bills/validate",                           # (VERIFICAR — mismo patrón que credit-notes/validate, confirmado)
    "bill_detail": "/v2/bills/{number}",                              # (CONFIRMADO)
    "bills_list": "/v2/bills",                                        # (VERIFICAR)
    "bill_xml": "/v2/bills/{number}/download-xml",                    # (CONFIRMADO)
    "bill_xml_attached": "/v2/bills/{number}/download-xml-attached-document",  # (VERIFICAR)
    "bill_pdf": "/v2/bills/{number}/download-pdf",                    # (VERIFICAR)
    "bill_events": "/v2/bills/{number}/radian/events",                # (CONFIRMADO, solo lectura)
    # (CORREGIDO 2026-08-27 — developers.factus.com.co/facturas/enviar-correo/
    # confirma la ruta real: Factus devolvía 404 "No se encontró la ruta o
    # recurso solicitado" con "/email", la ruta correcta es "/send-email".
    # El body {"email": ...} es OBLIGATORIO para Factus -- no hay envío al
    # correo "registrado" por defecto si se omite.)
    "bill_email": "/v2/bills/{number}/send-email",                    # (CONFIRMADO)
    # (CONFIRMADO 2026-08-27 — developers.factus.com.co/facturas/eliminar/)
    # Borra una factura NO VALIDADA (is_validated=false) por su
    # reference_code. Es la solución oficial documentada para el error 409
    # "Se encontró una factura pendiente por enviar a la DIAN": ese error
    # significa que el rango de numeración tiene una factura sin validar
    # atascada, y Factus no deja crear otra hasta que esa se borre (o
    # termine de validarse). Solo aplica mientras siga pendiente.
    "bill_delete_pending": "/v2/bills/destroy/reference/{reference_code}",
    "credit_notes_validate": "/v2/credit-notes/validate",             # (CONFIRMADO)
    "credit_note_detail": "/v2/credit-notes/{number}",                # (VERIFICAR)
    "credit_note_pdf": "/v2/credit-notes/{number}/download-pdf",      # (VERIFICAR)
    "credit_note_xml": "/v2/credit-notes/{number}/download-xml",      # (VERIFICAR)
    "debit_notes_validate": "/v2/debit-notes/validate",               # (VERIFICAR — mismo patrón)
    "debit_note_detail": "/v2/debit-notes/{number}",                  # (VERIFICAR)
    # (NO EXISTE — confirmado 2026-08-26) Se probó en sandbox real y Factus
    # devuelve su propio 404 ("No se encontró la ruta o recurso
    # solicitado"); además la colección Postman oficial de Factus v2 (Auth,
    # Facturas, Notas crédito, Notas débito, Documentos soporte) no incluye
    # ninguna tabla de referencia. Factus v2 NO expone tablas de referencia
    # (municipios, etc.) vía API. Para municipios se usa ahora el portal de
    # datos abiertos DANE (ver api_factus_sincronizar_municipios en
    # blueprints/bp_financiero/facturacion/routes.py). Se deja esta entrada
    # y obtener_tabla_referencia() sin usar, por si Factus llega a publicar
    # esto más adelante — no depender de esto sin volver a verificar.
    "reference_table": "/v2/common/{tabla}",
}


class FactusAPIError(Exception):
    """Error de negocio devuelto por Factus (validación DIAN, HTTP, etc.)."""

    def __init__(self, message: str, status_code: int = None, errors=None, raw=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors or {}
        self.raw = raw

    def to_dict(self):
        return {
            "message": self.message,
            "status_code": self.status_code,
            "errors": self.errors,
        }


# Caché de token en memoria por proceso. Si la app corre con varios workers
# (gunicorn -w N), cada worker mantendrá su propio token — es válido pero
# implica hasta N logins simultáneos la primera vez. Si esto se vuelve un
# problema de escala, mover este caché a Redis o a una tabla de BD.
_token_cache = {"access_token": None, "refresh_token": None, "expires_at": 0}
_token_lock = threading.Lock()


def _config():
    return current_app.config


def _base_url() -> str:
    env = (_config().get("FACTUS_ENV") or "sandbox").lower()
    return BASE_URLS.get(env, BASE_URLS["sandbox"])


def _habilitado() -> bool:
    return bool(_config().get("FACTUS_HABILITADO", True))


def _login() -> dict:
    """Autentica con grant_type=password y guarda el token en caché."""
    url = _base_url() + ENDPOINTS["token"]
    data = {
        "grant_type": "password",
        "client_id": _config().get("FACTUS_CLIENT_ID", ""),
        "client_secret": _config().get("FACTUS_CLIENT_SECRET", ""),
        "username": _config().get("FACTUS_USERNAME", ""),
        "password": _config().get("FACTUS_PASSWORD", ""),
    }
    resp = requests.post(url, data=data, headers={"Accept": "application/json"}, timeout=20)
    if resp.status_code >= 400:
        raise FactusAPIError(
            f"No fue posible autenticar con Factus ({resp.status_code}). "
            "Revisa FACTUS_CLIENT_ID / FACTUS_CLIENT_SECRET / FACTUS_USERNAME / FACTUS_PASSWORD en el .env.",
            status_code=resp.status_code,
            raw=_safe_json(resp),
        )
    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["refresh_token"] = payload.get("refresh_token")
    # Margen de seguridad de 30s antes de que expire.
    _token_cache["expires_at"] = time.time() + float(payload.get("expires_in", 600)) - 30
    return payload


def _get_token() -> str:
    if not _habilitado():
        raise FactusAPIError("La integración con Factus está deshabilitada (FACTUS_HABILITADO=false).")

    with _token_lock:
        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["access_token"]
        _login()
        return _token_cache["access_token"]


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text[:2000]}


def _request(method: str, path: str, json_body: dict = None, params: dict = None, retry_on_401: bool = True):
    token = _get_token()
    url = _base_url() + path
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = requests.request(method, url, json=json_body, params=params, headers=headers, timeout=30)

    if resp.status_code == 401 and retry_on_401:
        # Token posiblemente expirado a destiempo — forzar relogin una vez.
        with _token_lock:
            _token_cache["access_token"] = None
        return _request(method, path, json_body=json_body, params=params, retry_on_401=False)

    body = _safe_json(resp)

    if resp.status_code >= 400:
        errores = body.get("errors") or body.get("data") or {}
        mensaje = body.get("message") or "Factus rechazó la solicitud."
        raise FactusAPIError(mensaje, status_code=resp.status_code, errors=errores, raw=body)

    return body


# =============================================================
# FACTURAS
# =============================================================

def crear_y_validar_factura(payload: dict) -> dict:
    """
    Crea y valida una factura electrónica de venta ante la DIAN.
    payload debe construirse con factus_mapper.construir_payload_factura().
    Devuelve el JSON completo de la respuesta de Factus.
    """
    return _request("POST", ENDPOINTS["bills_validate"], json_body=payload)


def obtener_factura(numero: str) -> dict:
    path = ENDPOINTS["bill_detail"].format(number=numero)
    return _request("GET", path)


def listar_facturas(params: dict = None) -> list:
    data = _request("GET", ENDPOINTS["bills_list"], params=params)
    return _desenvolver_lista(data)


def descargar_xml(numero: str) -> bytes:
    path = ENDPOINTS["bill_xml"].format(number=numero)
    data = _request("GET", path)
    b64 = (data.get("data") or {}).get("xml_base_64_encoded") or data.get("xml_base_64_encoded")
    if not b64:
        raise FactusAPIError("Factus no devolvió el XML esperado.", raw=data)
    return base64.b64decode(b64)


def descargar_pdf(numero: str) -> bytes:
    path = ENDPOINTS["bill_pdf"].format(number=numero)
    data = _request("GET", path)
    b64 = (
        (data.get("data") or {}).get("pdf_base_64_encoded")
        or data.get("pdf_base_64_encoded")
    )
    if not b64:
        raise FactusAPIError("Factus no devolvió el PDF esperado.", raw=data)
    return base64.b64decode(b64)


def obtener_eventos_factura(numero: str) -> list:
    path = ENDPOINTS["bill_events"].format(number=numero)
    data = _request("GET", path)
    return data.get("data") or []


def eliminar_factura_pendiente(reference_code: str) -> dict:
    """
    Elimina en Factus una factura NO VALIDADA (is_validated=false)
    identificada por su reference_code. Uso: cuando crear_y_validar_factura
    devuelve 409 "Se encontró una factura pendiente por enviar a la DIAN",
    hay que borrar esa factura atascada con esto ANTES de poder reintentar
    con el mismo reference_code (o cualquier otro, ya que el bloqueo es a
    nivel del rango de numeración completo, no solo de la referencia).
    Si Factus ya validó la factura, este endpoint no aplica.
    """
    path = ENDPOINTS["bill_delete_pending"].format(reference_code=reference_code)
    return _request("DELETE", path)


def reenviar_email_factura(numero: str, email: str) -> dict:
    """
    Reenvía por correo una factura ya validada. Factus exige el campo
    "email" en el body (no hay un "correo registrado" por defecto que use
    si se omite) -- el caller es responsable de resolver a qué correo
    enviarla (el del adquiriente guardado, o uno indicado manualmente)
    ANTES de llamar a esta función.
    """
    path = ENDPOINTS["bill_email"].format(number=numero)
    return _request("POST", path, json_body={"email": email})


# =============================================================
# NOTAS CRÉDITO / DÉBITO
# =============================================================

def crear_y_validar_nota_credito(payload: dict) -> dict:
    return _request("POST", ENDPOINTS["credit_notes_validate"], json_body=payload)


def crear_y_validar_nota_debito(payload: dict) -> dict:
    return _request("POST", ENDPOINTS["debit_notes_validate"], json_body=payload)


def obtener_nota_credito(numero: str) -> dict:
    path = ENDPOINTS["credit_note_detail"].format(number=numero)
    return _request("GET", path)


# =============================================================
# NUMERACIÓN / ADQUIRIENTE / TABLAS DE REFERENCIA
# =============================================================

def _desenvolver_lista(data: dict) -> list:
    """
    Factus envuelve las listas paginadas dos veces:
    { "data": { "data": [...filas...], "pagination": {...} } }
    Esta función soporta esa forma y, por si acaso, también una forma
    plana { "data": [...] } sin el nivel extra de paginación.
    """
    interno = data.get("data")
    if isinstance(interno, dict):
        return interno.get("data") or []
    if isinstance(interno, list):
        return interno
    return []


def obtener_rangos_numeracion() -> list:
    data = _request("GET", ENDPOINTS["numbering_ranges"])
    return _desenvolver_lista(data)


def consultar_adquiriente(identification_document_code: str, identification_number: str) -> dict:
    """Autocompleta nombre/email de un adquiriente consultando a la DIAN vía Factus."""
    params = {
        "identification_document_code": identification_document_code,
        "identification_number": identification_number,
    }
    data = _request("GET", ENDPOINTS["acquirer"], params=params)
    return data.get("data") or {}


def obtener_tabla_referencia(tabla: str) -> list:
    """
    tabla: p.ej. 'municipalities', 'document-types', 'measurement-units'.
    (VERIFICAR) Confirma el nombre exacto del recurso contra la colección
    Postman antes de depender de esto en producción.
    """
    path = ENDPOINTS["reference_table"].format(tabla=tabla)
    data = _request("GET", path)
    return _desenvolver_lista(data)


def test_conexion() -> dict:
    """Prueba mínima de conectividad: login + una consulta simple."""
    _get_token()
    try:
        rangos = obtener_rangos_numeracion()
        return {"ok": True, "rangos_numeracion": rangos}
    except FactusAPIError as e:
        return {"ok": True, "login": True, "rangos_numeracion_error": e.to_dict()}
