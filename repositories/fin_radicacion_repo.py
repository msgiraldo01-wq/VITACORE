# =============================================
# VITACORE · Repositorio Radicación
# Archivo: repositories/fin_radicacion_repo.py
# =============================================

from services.supabase_service import get_supabase_admin
from datetime import date, datetime, timedelta
import uuid


def obtener_todas_radicaciones():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_radicaciones")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def obtener_radicacion_por_id(radicacion_id: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_radicaciones")
        .select("*")
        .eq("id", radicacion_id)
        .single()
        .execute()
    )
    return response.data


def obtener_radicacion_por_factura(numero_factura: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_radicaciones")
        .select("*")
        .eq("numero_factura", numero_factura)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def obtener_facturas_para_radicar():
    """Facturas en cartera que aún no han sido radicadas o están devueltas."""
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_facturas")
        .select("*")
        .in_("estado", ["pendiente", "en_gestion", "vencida"])
        .order("fecha_expedicion", desc=True)
        .execute()
    )
    facturas = response.data or []

    # Marcar cuáles ya tienen radicación activa
    for f in facturas:
        rad = (
            supabase.table("fin_radicaciones")
            .select("id, estado, numero_radicado, fecha_radicacion")
            .eq("numero_factura", f["numero_factura"])
            .not_.in_("estado", ["devuelta", "objetada"])
            .limit(1)
            .execute()
        ).data
        f["radicacion"] = rad[0] if rad else None

    return facturas


def crear_radicacion(data: dict, archivo=None) -> dict:
    supabase    = get_supabase_admin()
    soporte_url = ""

    if archivo and archivo.filename:
        extension     = archivo.filename.rsplit(".", 1)[-1] if "." in archivo.filename else "bin"
        nombre_unico  = f"radicaciones/{uuid.uuid4()}.{extension}"
        archivo_bytes = archivo.read()
        tipo_mime     = archivo.content_type or "application/octet-stream"

        supabase.storage.from_("soportes-cartera").upload(
            path=nombre_unico,
            file=archivo_bytes,
            file_options={"content-type": tipo_mime}
        )
        signed = supabase.storage.from_("soportes-cartera").create_signed_url(
            nombre_unico, 31536000
        )
        soporte_url = signed.get("signedURL") or signed.get("signed_url") or ""

    # Fecha vencimiento = fecha radicación + 30 días
    fecha_rad = data.get("fecha_radicacion", date.today().isoformat())
    try:
        fecha_rad_dt = datetime.strptime(str(fecha_rad)[:10], "%Y-%m-%d").date()
        fecha_venc   = (fecha_rad_dt + timedelta(days=30)).isoformat()
    except Exception:
        fecha_venc = None

    # Limpiar valor_factura (puede llegar como "$300.000" o "300000" o número)
    valor_raw = str(data.get("valor_factura", 0) or 0)
    valor_raw = valor_raw.replace("$", "").replace(".", "").replace(",", "").strip()
    try:
        valor_factura = float(valor_raw) if valor_raw else 0
    except Exception:
        valor_factura = 0

    # Limpiar factura_id — debe ser UUID o None
    factura_id_raw = data.get("factura_id") or None
    if factura_id_raw:
        factura_id_raw = str(factura_id_raw).strip()
        # Validar que tenga formato UUID (36 chars con guiones)
        if len(factura_id_raw) != 36:
            factura_id_raw = None

    registro = {
        "factura_id":        factura_id_raw,
        "numero_factura":    data.get("numero_factura"),
        "eps":               data.get("eps"),
        "nit_eps":           data.get("nit_eps") or None,
        "valor_factura":     valor_factura,
        "numero_radicado":   data.get("numero_radicado") or None,
        "fecha_radicacion":  fecha_rad,
        "fecha_vencimiento": fecha_venc,
        "canal":             data.get("canal", "presencial"),
        "estado":            "radicada",
        "soporte_url":       soporte_url or None,
        "registrado_por":    data.get("registrado_por", "Sistema"),
        "observaciones":     data.get("observaciones") or None,
    }

    res = supabase.table("fin_radicaciones").insert(registro).execute()

    # ── Actualizar estado en cartera ──
    supabase.table("fin_cartera_facturas").update({
        "estado":           "radicada",
        "fecha_radicacion": fecha_rad,
        "estado_factura":   "RADICADA",
        "updated_at":       date.today().isoformat(),
    }).eq("numero_factura", data.get("numero_factura")).execute()

    return res.data[0] if res.data else {}

def actualizar_estado_radicacion(radicacion_id: str, nuevo_estado: str,
                                  motivo: str = None, registrado_por: str = "Sistema"):
    supabase = get_supabase_admin()

    update = {
        "estado":     nuevo_estado,
        "updated_at": date.today().isoformat(),
    }
    if motivo:
        update["motivo_devolucion"] = motivo

    supabase.table("fin_radicaciones").update(update).eq("id", radicacion_id).execute()

    # Obtener número de factura para actualizar cartera
    rad = obtener_radicacion_por_id(radicacion_id)
    if rad:
        estado_cartera = {
            "radicada":     "radicada",
            "en_auditoria": "en_gestion",
            "devuelta":     "en_gestion",
            "pagada":       "pagada",
            "objetada":     "en_gestion",
        }.get(nuevo_estado, "en_gestion")

        supabase.table("fin_cartera_facturas").update({
            "estado":     estado_cartera,
            "updated_at": date.today().isoformat(),
        }).eq("numero_factura", rad["numero_factura"]).execute()

    return True


def obtener_kpis_radicacion():
    supabase     = get_supabase_admin()
    radicaciones = (
        supabase.table("fin_radicaciones")
        .select("estado, valor_factura")
        .execute()
    ).data or []

    total         = len(radicaciones)
    radicadas     = sum(1 for r in radicaciones if r.get("estado") == "radicada")
    pendientes    = sum(1 for r in radicaciones if r.get("estado") == "pendiente")
    devueltas     = sum(1 for r in radicaciones if r.get("estado") == "devuelta")
    en_auditoria  = sum(1 for r in radicaciones if r.get("estado") == "en_auditoria")
    valor_radicado = sum(float(r.get("valor_factura", 0) or 0) for r in radicaciones
                         if r.get("estado") in ["radicada", "en_auditoria", "pagada"])

    # Facturas pendientes de radicar
    pendientes_radicar = (
        supabase.table("fin_cartera_facturas")
        .select("id")
        .in_("estado", ["pendiente", "en_gestion", "vencida"])
        .execute()
    ).data or []

    return {
        "total":              total,
        "radicadas":          radicadas,
        "pendientes":         pendientes,
        "devueltas":          devueltas,
        "en_auditoria":       en_auditoria,
        "valor_radicado":     valor_radicado,
        "sin_radicar":        len(pendientes_radicar),
    }


def subir_soporte_radicacion(archivo_bytes: bytes, nombre_archivo: str, tipo_mime: str) -> str:
    supabase     = get_supabase_admin()
    extension    = nombre_archivo.rsplit(".", 1)[-1] if "." in nombre_archivo else "bin"
    nombre_unico = f"radicaciones/{uuid.uuid4()}.{extension}"

    supabase.storage.from_("soportes-cartera").upload(
        path=nombre_unico,
        file=archivo_bytes,
        file_options={"content-type": tipo_mime}
    )
    signed = supabase.storage.from_("soportes-cartera").create_signed_url(
        nombre_unico, 31536000
    )
    return signed.get("signedURL") or signed.get("signed_url") or ""