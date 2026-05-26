# =============================================
# VITACORE · Repositorio Glosas
# Archivo: repositories/fin_glosas_repo.py
# =============================================

from services.supabase_service import get_supabase_admin
from datetime import date, datetime, timedelta
import uuid


def obtener_todas_glosas():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_glosas")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def obtener_glosa_por_numero(numero_glosa: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_glosas")
        .select("*")
        .eq("numero_glosa", numero_glosa)
        .single()
        .execute()
    )
    return response.data


def obtener_respuestas_por_glosa(numero_glosa: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_glosas_respuestas")
        .select("*")
        .eq("numero_glosa", numero_glosa)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def registrar_respuesta(data: dict, archivo=None):
    supabase    = get_supabase_admin()
    soporte_url = ""

    if archivo and archivo.filename:
        extension     = archivo.filename.rsplit(".", 1)[-1] if "." in archivo.filename else "bin"
        nombre_unico  = f"glosas/{uuid.uuid4()}.{extension}"
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

    respuesta = {
        "glosa_id":        data.get("glosa_id"),
        "numero_glosa":    data.get("numero_glosa"),
        "tipo_respuesta":  data.get("tipo_respuesta", "respuesta"),
        "descripcion":     data.get("descripcion"),
        "valor_propuesto": float(data.get("valor_propuesto", 0) or 0),
        "soporte_url":     soporte_url,
        "registrado_por":  data.get("registrado_por", "Sistema"),
    }
    supabase.table("fin_glosas_respuestas").insert(respuesta).execute()

    # Actualizar estado de la glosa
    nuevo_estado = data.get("nuevo_estado", "en_respuesta")
    supabase.table("fin_glosas").update({
        "estado":          nuevo_estado,
        "fecha_respuesta": date.today().isoformat(),
        "respondida_por":  data.get("registrado_por", "Sistema"),
        "updated_at":      date.today().isoformat(),
    }).eq("numero_glosa", data.get("numero_glosa")).execute()

    # ── Si la glosa se levanta, actualizar valor_glosas en cartera ──
    if nuevo_estado == "levantada":
        glosa = obtener_glosa_por_numero(data.get("numero_glosa"))
        if glosa:
            factura = (
                supabase.table("fin_cartera_facturas")
                .select("id, valor_glosas")
                .eq("numero_factura", glosa.get("numero_factura"))
                .execute()
            ).data
            if factura:
                f = factura[0]
                nuevo_glosas = max(0, float(f.get("valor_glosas", 0)) - float(glosa.get("valor_glosado", 0)))
                supabase.table("fin_cartera_facturas").update({
                    "valor_glosas": nuevo_glosas,
                    "updated_at":   date.today().isoformat(),
                }).eq("id", f["id"]).execute()

    return True


def obtener_kpis_glosas():
    supabase = get_supabase_admin()
    glosas   = (
        supabase.table("fin_glosas")
        .select("estado, valor_glosado, valor_levantado, dias_respuesta")
        .execute()
    ).data or []

    total         = len(glosas)
    valor_glosado = sum(g.get("valor_glosado", 0) or 0 for g in glosas)
    respondidas   = sum(1 for g in glosas if g.get("estado") in ["respondida", "levantada", "conciliada"])
    levantadas    = sum(1 for g in glosas if g.get("estado") == "levantada")
    recibidas     = sum(1 for g in glosas if g.get("estado") == "recibida")
    vencidas      = sum(1 for g in glosas if (g.get("dias_respuesta") or 0) > 15 and g.get("estado") == "recibida")

    return {
        "total":         total,
        "valor_glosado": valor_glosado,
        "respondidas":   respondidas,
        "levantadas":    levantadas,
        "recibidas":     recibidas,
        "vencidas":      vencidas,
    }


def obtener_glosas_para_excel():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_glosas")
        .select(
            "numero_glosa, numero_factura, eps, tipo_glosa, "
            "valor_glosado, valor_aceptado, valor_levantado, valor_ratificado, "
            "fecha_glosa, fecha_vencimiento, fecha_respuesta, "
            "dias_respuesta, estado, causal, respondida_por"
        )
        .order("dias_respuesta", desc=True)
        .execute()
    )
    return response.data or []


def actualizar_dias_mora_glosas():
    """Actualiza dias_respuesta para todas las glosas activas."""
    supabase = get_supabase_admin()
    hoy      = date.today()

    glosas = (
        supabase.table("fin_glosas")
        .select("id, fecha_glosa, estado")
        .not_.in_("estado", ["levantada", "ratificada", "conciliada"])
        .execute()
    ).data or []

    for g in glosas:
        fecha_glosa = g.get("fecha_glosa")
        if not fecha_glosa:
            continue
        try:
            fecha_dt = datetime.strptime(str(fecha_glosa)[:10], "%Y-%m-%d").date()
            dias     = (hoy - fecha_dt).days
            supabase.table("fin_glosas").update({
                "dias_respuesta": dias,
                "updated_at":     hoy.isoformat(),
            }).eq("id", g["id"]).execute()
        except Exception:
            continue


def crear_glosa(data: dict) -> str:
    """
    Crea una nueva glosa y actualiza el valor de glosas
    en la factura de cartera correspondiente.
    """
    supabase = get_supabase_admin()
    hoy      = date.today()

    # Generar número de glosa automático
    existing = (
        supabase.table("fin_glosas")
        .select("numero_glosa")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if existing:
        ultimo = existing[0]["numero_glosa"]
        try:
            num = int(ultimo.split("-")[-1]) + 1
        except Exception:
            num = 1
    else:
        num = 1

    numero_glosa = f"GL-{hoy.year}-{str(num).zfill(5)}"

    fecha_glosa_dt    = datetime.strptime(data["fecha_glosa"], "%Y-%m-%d").date()
    fecha_vencimiento = (fecha_glosa_dt + timedelta(days=21)).isoformat()
    dias_transcurridos = (hoy - fecha_glosa_dt).days

    glosa = {
        "numero_glosa":     numero_glosa,
        "numero_factura":   data.get("numero_factura"),
        "eps":              data.get("eps"),
        "tipo_glosa":       data.get("tipo_glosa"),
        "valor_glosado":    data.get("valor_glosado", 0),
        "valor_aceptado":   0,
        "valor_levantado":  0,
        "fecha_glosa":      data.get("fecha_glosa"),
        "fecha_vencimiento": fecha_vencimiento,
        "dias_respuesta":   dias_transcurridos,
        "estado":           "recibida",
        "causal":           data.get("causal"),
        "observaciones":    data.get("observaciones"),
    }

    supabase.table("fin_glosas").insert(glosa).execute()

    # ── Integración con Cartera: actualizar valor_glosas ──
    factura = (
        supabase.table("fin_cartera_facturas")
        .select("id, valor_glosas")
        .eq("numero_factura", data.get("numero_factura"))
        .execute()
    ).data

    if factura:
        f            = factura[0]
        nuevo_glosas = float(f.get("valor_glosas", 0)) + float(data.get("valor_glosado", 0))
        supabase.table("fin_cartera_facturas").update({
            "valor_glosas": nuevo_glosas,
            "updated_at":   hoy.isoformat(),
        }).eq("id", f["id"]).execute()

    return numero_glosa


def obtener_glosas_por_factura(numero_factura: str):
    """Retorna todas las glosas asociadas a una factura."""
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_glosas")
        .select("*")
        .eq("numero_factura", numero_factura)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []