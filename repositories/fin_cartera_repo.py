# =============================================
# VITACORE · Repositorio Cartera
# Archivo: repositories/fin_cartera_repo.py
# =============================================

from services.supabase_service import get_supabase_admin
from datetime import date, datetime
import uuid


def obtener_todas_facturas():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_facturas")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def obtener_factura_por_numero(numero_factura: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_facturas")
        .select("*")
        .eq("numero_factura", numero_factura)
        .single()
        .execute()
    )
    return response.data


def obtener_pagos_por_factura(numero_factura: str):
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_pagos")
        .select("*")
        .eq("numero_factura", numero_factura)
        .order("fecha_pago", desc=True)
        .execute()
    )
    return response.data or []


def sincronizar_factura_a_cartera(factura: dict) -> bool:
    """
    Sincroniza una factura emitida desde fin_facturas
    hacia fin_cartera_facturas.
    Llamar después de emitir una factura.
    """
    supabase = get_supabase_admin()

    # Obtener nombre EPS desde hc_clientes
    eps_nombre = ""
    nit_eps    = ""
    if factura.get("cliente_id"):
        cli = (
            supabase.table("hc_clientes")
            .select("nombre, nit")
            .eq("id", factura["cliente_id"])
            .single()
            .execute()
        ).data
        if cli:
            eps_nombre = cli.get("nombre", "")
            nit_eps    = cli.get("nit", "")

    # Calcular fecha vencimiento (30 días desde expedición por defecto)
    from datetime import timedelta
    fecha_exp = factura.get("fecha_expedicion")
    if fecha_exp:
        if isinstance(fecha_exp, str):
            fecha_exp_dt = datetime.fromisoformat(fecha_exp[:10]).date()
        else:
            fecha_exp_dt = fecha_exp
        fecha_venc = (fecha_exp_dt + timedelta(days=30)).isoformat()
        fecha_exp_str = fecha_exp_dt.isoformat()
    else:
        fecha_venc    = None
        fecha_exp_str = None

    registro = {
        "factura_id":       factura.get("id"),
        "numero_factura":   factura.get("numero_factura"),
        "prefijo":          factura.get("prefijo"),
        "eps":              eps_nombre,
        "nit_eps":          nit_eps,
        "cliente_id":       factura.get("cliente_id"),
        "contrato_id":      factura.get("contrato_id"),
        "paciente_id":      factura.get("paciente_id"),
        "valor_factura":    float(factura.get("total", 0) or 0),
        "valor_pagado":     0,
        "valor_glosas":     0,
        "notas_credito":    0,
        "copago":           float(factura.get("copago", 0) or 0),
        "cuota_moderadora": float(factura.get("cuota_moderadora", 0) or 0),
        "fecha_expedicion": fecha_exp_str,
        "fecha_vencimiento": fecha_venc,
        "fecha_radicacion": fecha_exp_str,
        "dias_mora":        0,
        "estado":           "pendiente",
        "estado_factura":   factura.get("estado"),
        "estado_dian":      factura.get("estado_dian"),
        "updated_at":       date.today().isoformat(),
    }

    # Upsert por factura_id
    supabase.table("fin_cartera_facturas").upsert(
        registro,
        on_conflict="factura_id"
    ).execute()

    return True


def subir_soporte_storage(archivo_bytes: bytes, nombre_archivo: str, tipo_mime: str) -> str:
    supabase   = get_supabase_admin()
    extension  = nombre_archivo.rsplit(".", 1)[-1] if "." in nombre_archivo else "bin"
    nombre_unico = f"pagos/{uuid.uuid4()}.{extension}"

    supabase.storage.from_("soportes-cartera").upload(
        path=nombre_unico,
        file=archivo_bytes,
        file_options={"content-type": tipo_mime}
    )
    signed = supabase.storage.from_("soportes-cartera").create_signed_url(
        nombre_unico, 31536000
    )
    return signed.get("signedURL") or signed.get("signed_url") or ""


def registrar_pago(data: dict, archivo=None):
    supabase    = get_supabase_admin()
    soporte_url = ""

    if archivo and archivo.filename:
        archivo_bytes = archivo.read()
        tipo_mime     = archivo.content_type or "application/octet-stream"
        soporte_url   = subir_soporte_storage(
            archivo_bytes, archivo.filename, tipo_mime
        )

    pago = {
        "factura_id":          data.get("factura_id"),
        "numero_factura":      data.get("numero_factura"),
        "valor_pago":          float(data.get("valor_pago", 0)),
        "fecha_pago":          data.get("fecha_pago"),
        "banco":               data.get("banco"),
        "tipo_pago":           data.get("tipo_pago", "Transferencia"),
        "referencia_bancaria": data.get("referencia_bancaria"),
        "observacion":         data.get("observacion"),
        "registrado_por":      data.get("registrado_por", "Sistema"),
        "soporte_url":         soporte_url,
    }

    supabase.table("fin_cartera_pagos").insert(pago).execute()

    # Actualizar valor pagado en cartera
    factura = obtener_factura_por_numero(data.get("numero_factura"))
    if factura:
        nuevo_valor_pagado = float(factura.get("valor_pagado", 0)) + float(data.get("valor_pago", 0))
        saldo = (
            float(factura.get("valor_factura", 0))
            - nuevo_valor_pagado
            - float(factura.get("valor_glosas", 0))
        )
        nuevo_estado = "pagada" if saldo <= 0 else factura.get("estado", "en_gestion")

        supabase.table("fin_cartera_facturas").update({
            "valor_pagado": nuevo_valor_pagado,
            "ultimo_pago":  data.get("fecha_pago"),
            "estado":       nuevo_estado,
            "updated_at":   date.today().isoformat(),
        }).eq("numero_factura", data.get("numero_factura")).execute()

    return True


def actualizar_dias_mora():
    supabase = get_supabase_admin()
    hoy      = date.today()

    facturas = (
        supabase.table("fin_cartera_facturas")
        .select("id, fecha_vencimiento, estado")
        .neq("estado", "pagada")
        .neq("estado", "anulada")
        .execute()
    ).data or []

    for f in facturas:
        fecha_venc = f.get("fecha_vencimiento")
        if not fecha_venc:
            continue

        fecha_venc_dt = datetime.strptime(fecha_venc, "%Y-%m-%d").date()
        dias = max(0, (hoy - fecha_venc_dt).days)

        if dias == 0:
            nuevo_estado = "pendiente"
        elif dias <= 90:
            nuevo_estado = "en_gestion"
        else:
            nuevo_estado = "vencida"

        supabase.table("fin_cartera_facturas").update({
            "dias_mora":  dias,
            "estado":     nuevo_estado,
            "updated_at": hoy.isoformat(),
        }).eq("id", f["id"]).execute()


def obtener_kpis_cartera():
    supabase = get_supabase_admin()
    facturas = (
        supabase.table("fin_cartera_facturas")
        .select("valor_factura, valor_pagado, valor_glosas, estado, dias_mora, saldo_pendiente")
        .execute()
    ).data or []

    total        = sum(f.get("valor_factura",   0) for f in facturas)
    total_pagado = sum(f.get("valor_pagado",    0) for f in facturas)
    vencida      = sum(f.get("saldo_pendiente", 0) for f in facturas if f.get("estado") == "vencida")
    corriente    = sum(f.get("saldo_pendiente", 0) for f in facturas if (f.get("dias_mora") or 0) <= 30)

    return {
        "cartera_total":     total,
        "cartera_corriente": corriente,
        "cartera_vencida":   vencida,
        "recaudo_total":     total_pagado,
    }


def obtener_facturas_para_excel():
    supabase = get_supabase_admin()
    response = (
        supabase.table("fin_cartera_facturas")
        .select("numero_factura, eps, nit_eps, valor_factura, valor_pagado, valor_glosas, saldo_pendiente, dias_mora, estado, fecha_radicacion, fecha_vencimiento, ultimo_pago, responsable")
        .order("dias_mora", desc=True)
        .execute()
    )
    return response.data or []