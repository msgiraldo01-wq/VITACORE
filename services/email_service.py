# services/email_service.py
"""
Correos al paciente para los 4 momentos de una cita: creación,
confirmación, cancelación y reprogramación. Se envían vía Resend
(https://resend.com) usando su API HTTP directa (con `requests`, ya es
dependencia del proyecto) -- no hace falta instalar su SDK.

Reglas de este módulo, deliberadas:

- Nunca lanza una excepción hacia quien lo llama. Si Resend no está
  configurado, si el paciente no tiene correo registrado, o si la
  petición a Resend falla, se registra en consola (para poder revisar
  el log del servidor) y la función devuelve False -- pero la cita ya
  se creó/canceló/reprogramó igual. El correo es un extra, nunca debe
  poder tumbar ni revertir la acción real sobre la cita.
- Solo se manda correo cuando el paciente tiene un email registrado.
- Las plantillas viven en templates/emails/ y se renderizan con el
  motor de Jinja de Flask (render_template), igual que el resto de la
  app -- así el HTML del correo puede reutilizar los mismos filtros y
  convenciones.
"""

import requests
from flask import current_app, render_template

import repositories.hc_parametros_repo as repo_parametros

RESEND_API_URL = "https://api.resend.com/emails"


def _configurado() -> bool:
    return bool(current_app.config.get("RESEND_API_KEY")) and bool(current_app.config.get("EMAIL_FROM"))


def _correos_activos() -> bool:
    """Interruptor general: Configuración → Parámetros generales → Envío de
    correos a pacientes. Se guarda en hc_parametros_sistema (clave
    'correos_activos'). Si el parámetro no existe todavía en la base de
    datos, o si falla la consulta, se asume activo -- este interruptor
    es para que el usuario pueda apagar el envío a propósito, nunca para
    que un problema leyéndolo apague los correos por accidente."""
    try:
        valor = repo_parametros.obtener("correos_activos", "true")
        return (valor or "true").strip().lower() == "true"
    except Exception as e:
        print(f"[email_service] No se pudo leer el parámetro 'correos_activos' (se asume activo): {e}")
        return True


def _enviar(destinatario: str, asunto: str, html: str) -> bool:
    if not _correos_activos():
        print(f"[email_service] Envío de correos desactivado desde Configuración → Parámetros "
              f"-- correo a {destinatario} NO enviado ({asunto!r}).")
        return False

    if not destinatario:
        print(f"[email_service] Paciente sin correo registrado -- correo NO enviado ({asunto!r}).")
        return False

    if not _configurado():
        print(f"[email_service] Resend no está configurado (falta RESEND_API_KEY o EMAIL_FROM) "
              f"-- correo a {destinatario} NO enviado ({asunto!r}).")
        return False

    try:
        resp = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {current_app.config['RESEND_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "from": current_app.config["EMAIL_FROM"],
                "to": [destinatario],
                "subject": asunto,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            print(f"[email_service] Resend respondió {resp.status_code} enviando a {destinatario}: {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"[email_service] Error de conexión enviando correo a {destinatario}: {e}")
        return False


def _url_publica_cita(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/citas/publico/{token}"


def enviar_cita_creada(cita: dict, base_url: str) -> bool:
    """Al crear la cita: resumen + enlace para confirmar o cancelar."""
    try:
        html = render_template(
            "emails/cita_creada.html",
            cita=cita,
            url_cita=_url_publica_cita(base_url, cita.get("token_confirmacion") or ""),
        )
        return _enviar(cita.get("paciente_email"), "Tu cita quedó agendada — Vitacore", html)
    except Exception as e:
        print(f"[email_service] Error preparando correo de cita creada: {e}")
        return False


def enviar_cita_confirmada(cita: dict) -> bool:
    """Cuando el personal de la clínica confirma la cita manualmente (por ejemplo, el paciente llamó)."""
    try:
        html = render_template("emails/cita_confirmada.html", cita=cita)
        return _enviar(cita.get("paciente_email"), "Tu cita fue confirmada — Vitacore", html)
    except Exception as e:
        print(f"[email_service] Error preparando correo de cita confirmada: {e}")
        return False


def enviar_cita_cancelada(cita: dict) -> bool:
    """Cuando el personal de la clínica cancela la cita (la autogestión del paciente no manda este correo:
    ya vio el resultado directamente en la página pública)."""
    try:
        html = render_template("emails/cita_cancelada.html", cita=cita)
        return _enviar(cita.get("paciente_email"), "Tu cita fue cancelada — Vitacore", html)
    except Exception as e:
        print(f"[email_service] Error preparando correo de cita cancelada: {e}")
        return False


def enviar_cita_reprogramada(cita: dict, base_url: str) -> bool:
    """Al reprogramar: fecha/hora anterior tachada, la nueva, y el mismo tipo de enlace para reconfirmar."""
    try:
        html = render_template(
            "emails/cita_reprogramada.html",
            cita=cita,
            url_cita=_url_publica_cita(base_url, cita.get("token_confirmacion") or ""),
        )
        return _enviar(cita.get("paciente_email"), "Tu cita fue reprogramada — Vitacore", html)
    except Exception as e:
        print(f"[email_service] Error preparando correo de cita reprogramada: {e}")
        return False
