# =============================================
# VITACORE · Repositorio Documentos de Cartera
# Archivo: repositories/fin_cartera_documentos_repo.py
# =============================================

from services.supabase_service import get_supabase_admin
from datetime import date
import uuid


# Prefijos por tipo de documento
PREFIJOS = {
    "NC":  "NC",
    "ND":  "ND",
    "RC":  "RC",
    "DEV": "DEV",
    "ACL": "ACL",
    "CRU": "CRU",
}

# Etiquetas legibles
ETIQUETAS = {
    "NC":  "Nota crédito",
    "ND":  "Nota débito",
    "RC":  "Recibo de caja",
    "DEV": "Devolución",
    "ACL": "Aclaración",
    "CRU": "Cruce de cuentas",
}

# Efecto sobre el saldo (+/-)
EFECTO_SALDO = {
    "NC":  "resta",   # Reduce deuda del pagador
    "ND":  "suma",    # Aumenta deuda del pagador
    "RC":  "resta",   # Pago recibido reduce saldo
    "DEV": "suma",    # Devolución aumenta saldo
    "ACL": "neutro",  # No afecta saldo
    "CRU": "resta",   # Cruce reduce saldo
}


def obtener_documentos_por_factura(numero_factura: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_documentos")
        .select("*")
        .eq("numero_factura", numero_factura)
        .eq("estado", "activo")
        .order("fecha_documento", desc=True)
        .execute()
    )
    return response.data or []


def obtener_todos_documentos():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_documentos")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def obtener_documento_por_numero(numero_documento: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_documentos")
        .select("*")
        .eq("numero_documento", numero_documento)
        .single()
        .execute()
    )
    return response.data


def generar_numero_documento(tipo: str) -> str:
    """Genera número consecutivo automático por tipo."""
    supabase  = get_supabase_admin()
    prefijo   = PREFIJOS.get(tipo, tipo)
    anio      = date.today().year

    existing = (
        supabase.table("fin_cartera_documentos")
        .select("numero_documento")
        .eq("tipo_documento", tipo)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if existing:
        ultimo = existing[0]["numero_documento"]
        try:
            num = int(ultimo.split("-")[-1]) + 1
        except:
            num = 1
    else:
        num = 1

    return f"{prefijo}-{anio}-{str(num).zfill(5)}"


def crear_documento(data: dict, archivo=None) -> str:
    """
    Crea un documento de cartera y actualiza el saldo
    de la factura según el tipo.
    """
    supabase = get_supabase_admin()
    hoy      = date.today()
    tipo     = data.get("tipo_documento")

    soporte_url = ""
    if archivo and archivo.filename:
        extension    = archivo.filename.rsplit(".", 1)[-1] if "." in archivo.filename else "bin"
        nombre_unico = f"documentos-cartera/{uuid.uuid4()}.{extension}"
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

    numero_documento = generar_numero_documento(tipo)

    documento = {
        "numero_documento":   numero_documento,
        "tipo_documento":     tipo,
        "numero_factura":     data.get("numero_factura"),
        "factura_id":         data.get("factura_id"),
        "eps":                data.get("eps"),
        "valor":              float(data.get("valor", 0)),
        "fecha_documento":    data.get("fecha_documento"),
        "descripcion":        data.get("descripcion"),
        "referencia_externa": data.get("referencia_externa"),
        "afecta_saldo":       data.get("afecta_saldo", True),
        "soporte_url":        soporte_url,
        "registrado_por":     data.get("registrado_por", "Sistema"),
        "estado":             "activo",
    }

    supabase.table("fin_cartera_documentos").insert(documento).execute()

    # ── Actualizar saldo en fin_cartera_facturas ──
    if data.get("afecta_saldo", True):
        _aplicar_efecto_saldo(
            supabase,
            data.get("factura_id"),
            tipo,
            float(data.get("valor", 0)),
            hoy
        )

    return numero_documento


def _aplicar_efecto_saldo(supabase, factura_id: str, tipo: str, valor: float, hoy):
    """Aplica el efecto del documento sobre el saldo de la factura."""
    from repositories.fin_cartera_repo import obtener_factura_por_numero

    factura = (
        supabase.table("fin_cartera_facturas")
        .select("*")
        .eq("id", factura_id)
        .single()
        .execute()
    ).data

    if not factura:
        return

    efecto = EFECTO_SALDO.get(tipo, "neutro")

    update_data = {"updated_at": hoy.isoformat()}

    if tipo == "NC":
        # Nota crédito: aumenta notas_credito → reduce saldo
        nuevo = float(factura.get("notas_credito", 0)) + valor
        update_data["notas_credito"] = nuevo

    elif tipo == "ND":
        # Nota débito: aumenta el valor de la factura
        nuevo = float(factura.get("valor_factura", 0)) + valor
        update_data["valor_factura"] = nuevo

    elif tipo == "RC":
        # Recibo de caja: aumenta valor pagado
        nuevo = float(factura.get("valor_pagado", 0)) + valor
        update_data["valor_pagado"] = nuevo
        update_data["ultimo_pago"]  = hoy.isoformat()

    elif tipo == "DEV":
        # Devolución: reduce valor pagado
        nuevo = max(0, float(factura.get("valor_pagado", 0)) - valor)
        update_data["valor_pagado"] = nuevo

    elif tipo == "CRU":
        # Cruce: aumenta notas_credito
        nuevo = float(factura.get("notas_credito", 0)) + valor
        update_data["notas_credito"] = nuevo

    # Verificar si quedó saldada
    saldo = (
        float(factura.get("valor_factura",  0))
        - float(update_data.get("valor_pagado",   factura.get("valor_pagado",   0)))
        - float(factura.get("valor_glosas",  0))
        - float(update_data.get("notas_credito",  factura.get("notas_credito",  0)))
    )
    if saldo <= 0:
        update_data["estado"] = "pagada"

    supabase.table("fin_cartera_facturas").update(update_data).eq("id", factura_id).execute()


def anular_documento(numero_documento: str, usuario: str) -> bool:
    """Anula un documento (no lo elimina, lo marca como anulado)."""
    supabase = get_supabase_admin()
    supabase.table("fin_cartera_documentos").update({
        "estado":     "anulado",
        "updated_at": date.today().isoformat(),
    }).eq("numero_documento", numero_documento).execute()
    return True


def obtener_kpis_documentos():
    supabase  = get_supabase_admin()
    docs      = (
        supabase.table("fin_cartera_documentos")
        .select("tipo_documento, valor, estado")
        .eq("estado", "activo")
        .execute()
    ).data or []

    return {
        "total":       len(docs),
        "total_nc":    sum(d["valor"] for d in docs if d["tipo_documento"] == "NC"),
        "total_nd":    sum(d["valor"] for d in docs if d["tipo_documento"] == "ND"),
        "total_rc":    sum(d["valor"] for d in docs if d["tipo_documento"] == "RC"),
        "total_dev":   sum(d["valor"] for d in docs if d["tipo_documento"] == "DEV"),
        "count_nc":    sum(1 for d in docs if d["tipo_documento"] == "NC"),
        "count_nd":    sum(1 for d in docs if d["tipo_documento"] == "ND"),
        "count_rc":    sum(1 for d in docs if d["tipo_documento"] == "RC"),
        "count_dev":   sum(1 for d in docs if d["tipo_documento"] == "DEV"),
        "count_acl":   sum(1 for d in docs if d["tipo_documento"] == "ACL"),
        "count_cru":   sum(1 for d in docs if d["tipo_documento"] == "CRU"),
    }