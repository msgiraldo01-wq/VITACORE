from typing import Any, Optional
from datetime import datetime, timezone
from services.supabase_service import get_supabase_admin


def _table_name():
    return "rda_envios"


def _sb():
    return get_supabase_admin()


# =========================
# NORMALIZAR
# =========================

def _normalize(row: Optional[dict]) -> Optional[dict]:
    """Normaliza un registro de envío RDA para el panel."""
    if not row:
        return None

    return {
        "id": row.get("id"),
        "evolucion_id": row.get("evolucion_id"),
        "paciente_id": row.get("paciente_id"),

        # Datos visibles en el panel
        "paciente_doc": row.get("paciente_doc") or "",
        "paciente_nombre": row.get("paciente_nombre") or "",
        "dx_codigo": row.get("dx_codigo") or "",

        # Estado
        "estado": row.get("estado") or "pendiente",
        "http_status": row.get("http_status"),
        "motivo": row.get("motivo") or "",

        # Acuse del Ministerio
        "composition_id": row.get("composition_id") or "",
        "intentos": row.get("intentos") or 1,

        # Metadata
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# =========================
# CREAR ENVIO
# =========================

def crear(data: dict) -> Optional[dict]:
    """Registra un nuevo intento de envío del RDA."""
    try:
        insert_data = {
            "evolucion_id": data.get("evolucion_id"),
            "paciente_id": data.get("paciente_id"),
            "paciente_doc": data.get("paciente_doc"),
            "paciente_nombre": data.get("paciente_nombre"),
            "dx_codigo": data.get("dx_codigo"),
            "estado": data.get("estado", "pendiente"),
            "http_status": data.get("http_status"),
            "motivo": data.get("motivo"),
            "composition_id": data.get("composition_id"),
            "bundle_json": data.get("bundle_json"),
            "acuse_json": data.get("acuse_json"),
            "intentos": data.get("intentos", 1),
        }

        r = (
            _sb()
            .table(_table_name())
            .insert(insert_data)
            .execute()
        )

        if not r or not hasattr(r, "data") or not r.data:
            return None

        return _normalize(r.data[0])

    except Exception as e:
        print(f"Error creando envío RDA: {e}")
        raise


# =========================
# ACTUALIZAR ESTADO
# =========================

def actualizar_estado(envio_id: int, data: dict) -> Optional[dict]:
    """Actualiza el resultado de un envío tras transmitir (o reintentar)."""
    if not envio_id:
        return None

    try:
        update_data = {
            "estado": data.get("estado"),
            "http_status": data.get("http_status"),
            "motivo": data.get("motivo"),
            "composition_id": data.get("composition_id"),
            "acuse_json": data.get("acuse_json"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if data.get("bundle_json") is not None:
            update_data["bundle_json"] = data.get("bundle_json")
        if data.get("intentos") is not None:
            update_data["intentos"] = data.get("intentos")

        # limpiar claves None para no sobreescribir con vacío
        update_data = {k: v for k, v in update_data.items() if v is not None}

        r = (
            _sb()
            .table(_table_name())
            .update(update_data)
            .eq("id", envio_id)
            .execute()
        )

        if not r or not hasattr(r, "data") or not r.data:
            return None

        return _normalize(r.data[0])

    except Exception as e:
        print(f"Error actualizando envío RDA {envio_id}: {e}")
        return None


# =========================
# OBTENER ENVIO
# =========================

def obtener(envio_id: int) -> Optional[dict]:
    """Obtiene un envío por su id (incluye bundle y acuse completos)."""
    if not envio_id:
        return None

    try:
        r = (
            _sb()
            .table(_table_name())
            .select("*")
            .eq("id", envio_id)
            .limit(1)
            .execute()
        )

        if not r or not hasattr(r, "data") or not r.data:
            return None

        row = r.data[0]
        base = _normalize(row)
        # el detalle sí expone los JSON completos
        base["bundle_json"] = row.get("bundle_json")
        base["acuse_json"] = row.get("acuse_json")
        return base

    except Exception as e:
        print(f"Error obteniendo envío RDA {envio_id}: {e}")
        return None


# =========================
# LISTAR ENVIOS (PANEL)
# =========================

def listar(estado: str = "", limite: int = 200) -> list:
    """Lista los envíos para el panel, opcionalmente filtrando por estado."""
    try:
        q = (
            _sb()
            .table(_table_name())
            .select("*")
            .order("created_at", desc=True)
            .limit(limite)
        )
        if estado:
            q = q.eq("estado", estado)

        r = q.execute()

        if not r or not hasattr(r, "data") or not r.data:
            return []

        return [_normalize(row) for row in r.data if row]

    except Exception as e:
        print(f"Error listando envíos RDA: {e}")
        return []


# =========================
# RESUMEN (TARJETAS DEL PANEL)
# =========================

def resumen() -> dict:
    """Cuenta los envíos por estado para las tarjetas del panel."""
    try:
        r = (
            _sb()
            .table(_table_name())
            .select("estado, http_status")
            .execute()
        )
        filas = (r.data or []) if r and hasattr(r, "data") else []

        total = len(filas)
        aceptados = sum(1 for f in filas if f.get("estado") == "aceptado")
        rechazados = sum(1 for f in filas if f.get("estado") in ("rechazado", "error"))
        pendientes = sum(1 for f in filas if f.get("estado") in ("pendiente", "excepcion_identidad"))
        duplicados = sum(1 for f in filas if f.get("http_status") == 409)

        return {
            "total": total,
            "aceptados": aceptados,
            "rechazados": rechazados,
            "pendientes": pendientes,
            "duplicados": duplicados,
        }

    except Exception as e:
        print(f"Error en resumen de envíos RDA: {e}")
        return {"total": 0, "aceptados": 0, "rechazados": 0, "pendientes": 0, "duplicados": 0}