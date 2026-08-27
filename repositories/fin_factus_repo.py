"""
Repositorio de soporte para la integración Factus — Vitacore
Tablas: fin_factus_doc_tipo_map, fin_factus_referencias,
        fin_factus_eventos_log
(ver migración SQL: db/migracion_factus.sql)
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


# =============================================================
# DATOS DEL ADQUIRIENTE (paciente / cliente) PARA FACTUS
# Consultas dedicadas — no tocan los repos existentes de pacientes/clientes
# para no afectar el resto de la aplicación.
# =============================================================

def obtener_paciente_para_dian(paciente_id: int):
    res = (
        _sb()
        .table("hc_pacientes")
        .select(
            "id, tipo_documento_id, numero_documento, primer_nombre, segundo_nombre, "
            "primer_apellido, segundo_apellido, direccion, email, telefono, celular, "
            "municipio_id, "
            "hc_tipos_documento(codigo), "
            "hc_municipios(codigo_dian, nombre)"
        )
        .eq("id", paciente_id)
        .single()
        .execute()
    )
    row = res.data
    if not row:
        return None
    tipo_doc = row.pop("hc_tipos_documento", None) or {}
    municipio = row.pop("hc_municipios", None) or {}
    row["tipo_documento"] = tipo_doc.get("codigo", "CC")
    row["municipio_dian_codigo"] = municipio.get("codigo_dian")
    row["municipio_nombre"] = municipio.get("nombre")
    return row


def obtener_cliente_para_dian(cliente_id: int):
    res = (
        _sb()
        .table("hc_clientes")
        .select(
            "id, nombre, nit, dv, tipo_identificacion, direccion, email, telefono, "
            "usa_paciente_como_adquiriente, municipio_id, "
            "hc_municipios(codigo_dian, nombre)"
        )
        .eq("id", cliente_id)
        .single()
        .execute()
    )
    row = res.data
    if not row:
        return None
    municipio = row.pop("hc_municipios", None) or {}
    row["municipio_dian_codigo"] = municipio.get("codigo_dian")
    row["municipio_nombre"] = municipio.get("nombre")
    return row


def obtener_cups_para_dian(codigos: list) -> dict:
    """Retorna { codigo_cups: {factus_tratamiento, factus_tributo_codigo, factus_tarifa, factus_unidad_medida, factus_standard_code} }"""
    codigos = [c for c in set(codigos) if c]
    if not codigos:
        return {}
    res = (
        _sb()
        .table("hc_cups")
        .select("codigo, factus_tratamiento, factus_tributo_codigo, factus_tarifa, factus_unidad_medida, factus_standard_code")
        .in_("codigo", codigos)
        .execute()
    )
    return {row["codigo"]: row for row in (res.data or [])}


# =============================================================
# MAPEO TIPO DE DOCUMENTO LOCAL → CÓDIGO FACTUS/DIAN
# =============================================================

def obtener_mapeo_tipos_documento() -> dict:
    """
    Retorna { 'CC': '13', 'NIT': '31', ... } a partir de la tabla
    fin_factus_doc_tipo_map. Si un código local no tiene mapeo (factus_code
    es NULL), no aparece en el dict — el llamador debe tratarlo como dato
    faltante y pedir que se configure antes de facturar.
    """
    res = _sb().table("fin_factus_doc_tipo_map").select("codigo_local, codigo_factus").execute()
    return {
        row["codigo_local"]: row["codigo_factus"]
        for row in (res.data or [])
        if row.get("codigo_factus")
    }


def actualizar_mapeo_tipo_documento(codigo_local: str, codigo_factus: str):
    res = (
        _sb()
        .table("fin_factus_doc_tipo_map")
        .update({"codigo_factus": codigo_factus})
        .eq("codigo_local", codigo_local)
        .execute()
    )
    return res.data


# =============================================================
# TABLAS DE REFERENCIA CACHEADAS (municipios, tributos, etc.)
# =============================================================

def guardar_referencias(tabla: str, items: list):
    """Reemplaza el caché local de una tabla de referencia de Factus."""
    sb = _sb()
    sb.table("fin_factus_referencias").delete().eq("tabla", tabla).execute()
    filas = [
        {
            "tabla": tabla,
            "codigo": str(item.get("code") or item.get("id") or item.get("codigo") or ""),
            "nombre": item.get("name") or item.get("nombre") or "",
            "extra": item,
        }
        for item in items
    ]
    if filas:
        sb.table("fin_factus_referencias").insert(filas).execute()
    return len(filas)


def buscar_referencias(tabla: str, texto: str = "", limite: int = 20):
    q = _sb().table("fin_factus_referencias").select("*").eq("tabla", tabla)
    if texto:
        q = q.or_(f"nombre.ilike.%{texto}%,codigo.ilike.%{texto}%")
    res = q.limit(limite).execute()
    return res.data or []


# =============================================================
# LOG DE EVENTOS / RESPUESTAS DIAN (auditoría)
# =============================================================

def registrar_evento(documento_tipo: str, documento_id: int, accion: str, payload_envio: dict, respuesta: dict, ok: bool):
    """
    documento_tipo: 'FACTURA' | 'NOTA_CREDITO' | 'NOTA_DEBITO'
    accion: 'CREAR_VALIDAR' | 'REINTENTO' | 'CONSULTA_EVENTOS' | 'EMAIL' | ...
    """
    _sb().table("fin_factus_eventos_log").insert({
        "documento_tipo": documento_tipo,
        "documento_id": documento_id,
        "accion": accion,
        "payload_envio": payload_envio,
        "respuesta": respuesta,
        "ok": ok,
    }).execute()


def listar_eventos(documento_tipo: str, documento_id: int):
    res = (
        _sb()
        .table("fin_factus_eventos_log")
        .select("*")
        .eq("documento_tipo", documento_tipo)
        .eq("documento_id", documento_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def listar_eventos_recientes(limite: int = 100, solo_errores: bool = False):
    """
    Trae el log de eventos Factus más reciente, SIN filtrar por un
    documento en particular — para el panel de diagnóstico
    (/facturacion/factus/eventos), que muestra de un vistazo qué se le
    mandó a Factus y qué respondió, en vez de tener que leerlo desde la
    consola del navegador cada vez.
    """
    q = _sb().table("fin_factus_eventos_log").select("*")
    if solo_errores:
        q = q.eq("ok", False)
    res = q.order("created_at", desc=True).limit(limite).execute()
    return res.data or []
