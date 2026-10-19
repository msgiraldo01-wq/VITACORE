"""
Datos de auditoría de quien ejecuta una acción.

Esto vivía dentro de blueprints/citas/routes.py y solo lo usaban las
citas. La nota clínica necesita lo mismo —y con más razón, porque la
Resolución 1995 de 1999 exige poder atribuir cada registro a alguien—,
así que se saca aquí para que las dos usen la misma lógica y no se
tengan que mantener dos versiones que con el tiempo divergen.
"""

import ipaddress

from flask import has_request_context, request, session


def clasificar_ips(req=None):
    """
    Devuelve (ip_privada, ip_publica) de quien hace la petición.

    Se separan a propósito: detrás de un proxy o de la red de la clínica
    llegan las dos, y saber desde qué equipo interno se registró una
    evolución es tan útil como saber desde qué conexión salió.
    """
    req = req or (request if has_request_context() else None)
    if req is None:
        return None, None

    candidatas = []
    reenviadas = req.headers.get("X-Forwarded-For", "")
    if reenviadas:
        candidatas.extend(p.strip() for p in reenviadas.split(",") if p.strip())
    real = req.headers.get("X-Real-IP")
    if real:
        candidatas.append(real.strip())
    if req.remote_addr:
        candidatas.append(req.remote_addr)

    ip_privada = None
    ip_publica = None
    for ip_str in candidatas:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip_obj.is_private or ip_obj.is_loopback:
            ip_privada = ip_privada or ip_str
        else:
            ip_publica = ip_publica or ip_str

    return ip_privada, ip_publica


def usuario_actual():
    """(username, id) del usuario de la sesión, o (None, None) fuera de ella."""
    try:
        if not has_request_context():
            return None, None
        u = session.get("user") or {}
        return (u.get("username") or None,
                str(u.get("id")) if u.get("id") is not None else None)
    except Exception:
        return None, None


def datos_de_creacion():
    """
    Bloque listo para guardar junto a un registro nuevo:
    quién lo creó y desde dónde. La fecha la pone la base.
    """
    usuario, usuario_id = usuario_actual()
    ip_privada, ip_publica = clasificar_ips()
    return {
        "usuario_creacion": usuario,
        "usuario_creacion_id": usuario_id,
        "ip_privada": ip_privada,
        "ip_publica": ip_publica,
    }
