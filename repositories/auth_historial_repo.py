"""
Historial de accesos (auditoría de inicios de sesión).

`registrar_intento` se llama desde blueprints/auth/routes.py en CADA
rama del login (éxito y cada tipo de fallo). Es defensivo a propósito
-- nunca debe lanzar, ni bloquear ni retrasar el login real -- porque
una falla guardando auditoría no puede convertirse en una falla de
acceso al sistema. Mismo criterio que _correos_activos() en
services/email_service.py.
"""

from datetime import datetime, timezone, timedelta

from services.supabase_service import get_supabase_admin


MOTIVOS_LABELS = {
    "ok": "Acceso exitoso",
    "usuario_no_existe": "Usuario no existe",
    "cuenta_inactiva": "Cuenta inactiva",
    "sin_correo_configurado": "Sin correo configurado",
    "credenciales_invalidas": "Contraseña incorrecta",
    "error_interno": "Error interno del sistema",
}

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# creado_en se guarda en UTC (timestamptz default now() en Supabase) --
# se muestra siempre convertido a hora de Colombia. Colombia no tiene
# horario de verano, así que un offset fijo -05:00 es correcto todo el
# año; se intenta primero con zoneinfo (IANA "America/Bogota") por si
# algún día cambia, y si no hay base de datos de zonas horarias
# disponible (puede pasar en Windows sin el paquete "tzdata") se cae
# de forma segura al offset fijo.
try:
    from zoneinfo import ZoneInfo
    _TZ_COLOMBIA = ZoneInfo("America/Bogota")
except Exception:
    _TZ_COLOMBIA = timezone(timedelta(hours=-5))


def _formatear_fecha(valor) -> str:
    """'2026-08-31T00:36:10.123456+00:00' (UTC, como se guarda) ->
    '30 ago 2026, 19:36' (hora de Colombia, UTC-5). Nunca lanza --
    ante cualquier formato inesperado devuelve el valor original tal
    cual, para no romper la tabla por un dato raro."""
    if not valor:
        return "—"
    try:
        texto = valor.replace("Z", "+00:00") if isinstance(valor, str) else valor
        dt = datetime.fromisoformat(texto) if isinstance(texto, str) else texto
        if dt.tzinfo is None:
            # Por si algún registro llega sin offset explícito -- se
            # asume UTC, que es como Supabase/Postgres lo guarda.
            dt = dt.replace(tzinfo=timezone.utc)
        dt_col = dt.astimezone(_TZ_COLOMBIA)
        return f"{dt_col.day} {_MESES[dt_col.month - 1]} {dt_col.year}, {dt_col.strftime('%H:%M')}"
    except Exception:
        return str(valor)


def _enriquecer_fila(fila: dict) -> dict:
    """Agrega al registro crudo de Supabase una etiqueta de motivo legible
    y la fecha ya formateada, para no repetir esa lógica en cada template."""
    motivo = fila.get("motivo") or ""
    fila["motivo_label"] = MOTIVOS_LABELS.get(motivo) or (motivo.replace("_", " ").capitalize() or "—")
    fila["creado_en_fmt"] = _formatear_fecha(fila.get("creado_en"))
    return fila


def registrar_intento(
    username: str,
    exito: bool,
    motivo: str,
    user_id: str = None,
    ip_address: str = None,
    pais: str = None,
    ciudad: str = None,
    dispositivo: str = None,
    user_agent: str = None,
):
    try:
        supabase = get_supabase_admin()

        payload = {
            "username": (username or "").strip().lower(),
            "exito": bool(exito),
            "motivo": motivo,
            "user_id": user_id,
            "ip_address": ip_address,
            "pais": pais,
            "ciudad": ciudad,
            "dispositivo": dispositivo,
            "user_agent": user_agent,
        }

        supabase.table("auth_historial_accesos").insert(payload).execute()

    except Exception as e:
        # Nunca debe romper el login: si la tabla no existe todavía
        # (script SQL no ejecutado) o falla la escritura, solo se
        # registra en consola y el flujo de login sigue normal.
        print(f"[auth_historial_repo] No se pudo registrar el intento de acceso de '{username}': {e}")


def listar_historial_usuario(user_id: str, limit: int = 20):
    if not user_id:
        return []

    try:
        supabase = get_supabase_admin()
        res = (
            supabase
            .table("auth_historial_accesos")
            .select("id, exito, motivo, ip_address, pais, ciudad, dispositivo, creado_en")
            .eq("user_id", user_id)
            .order("creado_en", desc=True)
            .limit(limit)
            .execute()
        )
        return [_enriquecer_fila(f) for f in (res.data or [])]
    except Exception as e:
        print(f"[auth_historial_repo] No se pudo leer el historial del usuario {user_id}: {e}")
        return []


def listar_historial_todos(limit: int = 100):
    try:
        supabase = get_supabase_admin()
        res = (
            supabase
            .table("auth_historial_accesos")
            .select("""
                id,
                username,
                exito,
                motivo,
                ip_address,
                pais,
                ciudad,
                dispositivo,
                creado_en,
                profiles:user_id (
                    full_name
                )
            """)
            .order("creado_en", desc=True)
            .limit(limit)
            .execute()
        )
        return [_enriquecer_fila(f) for f in (res.data or [])]
    except Exception as e:
        print(f"[auth_historial_repo] No se pudo leer el historial general de accesos: {e}")
        return []
