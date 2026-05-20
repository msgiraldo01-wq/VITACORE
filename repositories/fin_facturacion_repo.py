"""
Repositorio del módulo de facturación — Vitacore
Tablas: fin_consecutivos_facturacion, fin_prefacturas,
        fin_prefactura_items, fin_facturas, fin_factura_detalle,
        fin_notas_credito_debito
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


# =============================================================
# BUSCAR CITAS FACTURABLES POR CÉDULA
# Estados: CONFIRMADA, EN_ATENCION, FINALIZADA (no facturadas)
# =============================================================

def buscar_citas_facturables(numero_documento: str):
    """
    Busca paciente por número de documento y retorna sus citas
    facturables (CONFIRMADA, EN_ATENCION, FINALIZADA).
    """
    # 1. Buscar paciente
    pac = (
        _sb()
        .table("hc_pacientes")
        .select("id, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, numero_documento, tipo_documento_id")
        .eq("numero_documento", numero_documento.strip())
        .limit(1)
        .execute()
    )
    if not pac.data:
        return None, []

    paciente = pac.data[0]

    # 2. Buscar citas facturables de ese paciente
    citas = (
        _sb()
        .table("hc_citas")
        .select(
            "id, fecha, hora_inicio, hora_fin, duracion, estado, "
            "tipo_atencion, modalidad, motivo_consulta, valor_tarifa, "
            "causa_externa, via_ingreso, ambito_atencion, numero_autorizacion, "
            "medico_id, sede_id, cliente_id, contrato_id, "
            "hc_profesionales(nombre_completo), "
            "hc_sedes(nombre), "
            "hc_clientes(nombre, nit), "
            "hc_contratos(nro_contrato, manual_tarifario, tipo_contrato)"
        )
        .eq("paciente_id", paciente["id"])
        .in_("estado", ["CONFIRMADA", "EN_ATENCION", "FINALIZADA"])
        .order("fecha", desc=True)
        .order("hora_inicio", desc=True)
        .execute()
    )

    return paciente, citas.data or []


def obtener_procedimientos_cita(cita_id: int):
    """Retorna los procedimientos CUPS asociados a una cita."""
    res = (
        _sb()
        .table("hc_cita_procedimientos")
        .select("id, cups_id, duracion_min, orden, hc_cups(codigo, descripcion)")
        .eq("cita_id", cita_id)
        .order("orden")
        .execute()
    )
    return res.data or []


# =============================================================
# CONSECUTIVOS DE FACTURACIÓN
# =============================================================

def obtener_consecutivo_activo(empresa_id: int = 1, sede_id: int = None):
    """Obtiene el consecutivo activo para la sede."""
    q = (
        _sb()
        .table("fin_consecutivos_facturacion")
        .select("*")
        .eq("empresa_id", empresa_id)
        .eq("estado", "ACTIVO")
    )
    if sede_id:
        q = q.eq("sede_id", sede_id)
    else:
        q = q.eq("es_principal", True)

    res = q.limit(1).execute()
    return res.data[0] if res.data else None


def incrementar_consecutivo(consecutivo_id: int):
    """Incrementa el consecutivo y retorna el nuevo número."""
    # Leer actual
    res = (
        _sb()
        .table("fin_consecutivos_facturacion")
        .select("consecutivo_actual, rango_hasta, prefijo")
        .eq("id", consecutivo_id)
        .single()
        .execute()
    )
    actual = res.data
    nuevo = actual["consecutivo_actual"] + 1

    # Validar rango si existe
    if actual.get("rango_hasta") and nuevo > actual["rango_hasta"]:
        # Marcar como agotado
        _sb().table("fin_consecutivos_facturacion").update(
            {"estado": "AGOTADO"}
        ).eq("id", consecutivo_id).execute()
        return None, "Consecutivo agotado"

    # Actualizar
    _sb().table("fin_consecutivos_facturacion").update(
        {"consecutivo_actual": nuevo, "updated_at": "now()"}
    ).eq("id", consecutivo_id).execute()

    numero_factura = f"{actual['prefijo']}{nuevo}"
    return numero_factura, None


def crear_consecutivo(data: dict):
    res = _sb().table("fin_consecutivos_facturacion").insert(data).execute()
    return res.data


def listar_consecutivos(empresa_id: int = 1):
    res = (
        _sb()
        .table("fin_consecutivos_facturacion")
        .select("*, hc_sedes(nombre)")
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


# =============================================================
# PREFACTURAS (CUENTAS MÉDICAS)
# =============================================================

def crear_prefactura(data: dict):
    res = _sb().table("fin_prefacturas").insert(data).execute()
    return res.data[0] if res.data else None


def agregar_items_prefactura(items: list):
    res = _sb().table("fin_prefactura_items").insert(items).execute()
    return res.data or []


def obtener_prefactura(prefactura_id: int):
    res = (
        _sb()
        .table("fin_prefacturas")
        .select(
            "*, hc_pacientes(primer_nombre, primer_apellido, numero_documento), "
            "hc_clientes(nombre, nit), "
            "hc_contratos(nro_contrato, manual_tarifario)"
        )
        .eq("id", prefactura_id)
        .single()
        .execute()
    )
    return res.data


def obtener_items_prefactura(prefactura_id: int):
    res = (
        _sb()
        .table("fin_prefactura_items")
        .select("*, hc_citas(fecha, hora_inicio, estado)")
        .eq("prefactura_id", prefactura_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def listar_prefacturas(empresa_id: int = 1, estado: str = None):
    q = (
        _sb()
        .table("fin_prefacturas")
        .select(
            "*, hc_pacientes(primer_nombre, primer_apellido, numero_documento), "
            "hc_clientes(nombre)"
        )
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .limit(50)
    )
    if estado:
        q = q.eq("estado", estado)
    res = q.execute()
    return res.data or []


def actualizar_prefactura(prefactura_id: int, data: dict):
    res = (
        _sb()
        .table("fin_prefacturas")
        .update(data)
        .eq("id", prefactura_id)
        .execute()
    )
    return res.data


def cerrar_prefactura(prefactura_id: int):
    return actualizar_prefactura(prefactura_id, {"estado": "CERRADA"})


# =============================================================
# FACTURAS
# =============================================================

def crear_factura(data: dict):
    res = _sb().table("fin_facturas").insert(data).execute()
    return res.data[0] if res.data else None


def agregar_detalle_factura(items: list):
    res = _sb().table("fin_factura_detalle").insert(items).execute()
    return res.data or []


def obtener_factura(factura_id: int):
    res = (
        _sb()
        .table("fin_facturas")
        .select(
            "*, hc_pacientes(primer_nombre, segundo_nombre, primer_apellido, "
            "segundo_apellido, numero_documento, tipo_documento_id, "
            "fecha_nacimiento, sexo), "
            "hc_clientes(nombre, nit, codigo), "
            "hc_contratos(nro_contrato, manual_tarifario, tipo_contrato), "
            "hc_sedes(nombre, codigo, direccion), "
            "fin_consecutivos_facturacion(prefijo, resolucion_dian)"
        )
        .eq("id", factura_id)
        .single()
        .execute()
    )
    return res.data


def obtener_detalle_factura(factura_id: int):
    res = (
        _sb()
        .table("fin_factura_detalle")
        .select("*")
        .eq("factura_id", factura_id)
        .order("id")
        .execute()
    )
    return res.data or []


def listar_facturas(empresa_id: int = 1, estado: str = None,
                    cliente_id: int = None, fecha_desde: str = None,
                    fecha_hasta: str = None, limit: int = 50):
    q = (
        _sb()
        .table("fin_facturas")
        .select(
            "id, numero_factura, fecha_expedicion, total, estado, "
            "copago, cuota_moderadora, estado_dian, "
            "hc_pacientes(primer_nombre, primer_apellido, numero_documento), "
            "hc_clientes(nombre, nit)"
        )
        .eq("empresa_id", empresa_id)
        .order("fecha_expedicion", desc=True)
        .limit(limit)
    )
    if estado:
        q = q.eq("estado", estado)
    if cliente_id:
        q = q.eq("cliente_id", cliente_id)
    if fecha_desde:
        q = q.gte("fecha_expedicion", fecha_desde)
    if fecha_hasta:
        q = q.lte("fecha_expedicion", fecha_hasta)

    res = q.execute()
    return res.data or []


def actualizar_factura(factura_id: int, data: dict):
    res = (
        _sb()
        .table("fin_facturas")
        .update(data)
        .eq("id", factura_id)
        .execute()
    )
    return res.data


def anular_factura(factura_id: int, motivo: str = None):
    data = {"estado": "ANULADA"}
    if motivo:
        data["observaciones"] = motivo
    return actualizar_factura(factura_id, data)


# =============================================================
# MARCAR CITAS COMO FACTURADAS
# =============================================================

def marcar_citas_facturadas(cita_ids: list):
    """Cambia el estado de las citas a FACTURADA."""
    for cita_id in cita_ids:
        _sb().table("hc_citas").update(
            {"estado": "FACTURADA"}
        ).eq("id", cita_id).execute()


# =============================================================
# NOTAS CRÉDITO / DÉBITO
# =============================================================

def crear_nota(data: dict):
    res = _sb().table("fin_notas_credito_debito").insert(data).execute()
    return res.data[0] if res.data else None


def listar_notas_factura(factura_id: int):
    res = (
        _sb()
        .table("fin_notas_credito_debito")
        .select("*")
        .eq("factura_id", factura_id)
        .order("fecha_expedicion", desc=True)
        .execute()
    )
    return res.data or []


def obtener_nota(nota_id: int):
    res = (
        _sb()
        .table("fin_notas_credito_debito")
        .select("*, fin_facturas(numero_factura, total)")
        .eq("id", nota_id)
        .single()
        .execute()
    )
    return res.data


# =============================================================
# CONSULTAR TARIFA DE UN CUPS EN EL MANUAL DEL CONTRATO
# (reutiliza lógica existente del módulo de citas)
# =============================================================

def obtener_tarifa_cups(contrato_id: int, cups_id: int):
    """
    Busca la tarifa de un procedimiento CUPS en el manual
    tarifario asociado al contrato.
    """
    # 1. Obtener nombre del manual del contrato
    contrato = (
        _sb()
        .table("hc_contratos")
        .select("manual_tarifario")
        .eq("id", contrato_id)
        .single()
        .execute()
    )
    if not contrato.data or not contrato.data.get("manual_tarifario"):
        return None

    nombre_manual = contrato.data["manual_tarifario"]

    # 2. Buscar el manual
    manual = (
        _sb()
        .table("hc_manuales_tarifarios")
        .select("id")
        .eq("nombre", nombre_manual)
        .limit(1)
        .execute()
    )
    if not manual.data:
        return None

    manual_id = manual.data[0]["id"]

    # 3. Buscar tarifa del procedimiento
    tarifa = (
        _sb()
        .table("hc_mt_procedimientos")
        .select("valor_paquete, valor_procedimiento, valor_suministro")
        .eq("manual_id", manual_id)
        .eq("cups_id", cups_id)
        .limit(1)
        .execute()
    )
    if not tarifa.data:
        return None

    t = tarifa.data[0]
    t["valor_total"] = (
        float(t.get("valor_paquete") or 0) +
        float(t.get("valor_procedimiento") or 0) +
        float(t.get("valor_suministro") or 0)
    )
    return t


# =============================================================
# DASHBOARD / ESTADÍSTICAS
# =============================================================

def resumen_facturacion(empresa_id: int = 1):
    """Resumen básico para el dashboard de facturación."""
    facturas = (
        _sb()
        .table("fin_facturas")
        .select("estado, total")
        .eq("empresa_id", empresa_id)
        .execute()
    )
    data = facturas.data or []

    resumen = {
        "total_facturas": len(data),
        "emitidas": 0,
        "radicadas": 0,
        "pagadas": 0,
        "anuladas": 0,
        "valor_emitidas": 0,
        "valor_radicadas": 0,
        "valor_pagadas": 0,
    }

    for f in data:
        estado = f.get("estado", "")
        total = float(f.get("total", 0) or 0)
        if estado == "EMITIDA":
            resumen["emitidas"] += 1
            resumen["valor_emitidas"] += total
        elif estado == "RADICADA":
            resumen["radicadas"] += 1
            resumen["valor_radicadas"] += total
        elif estado == "PAGADA":
            resumen["pagadas"] += 1
            resumen["valor_pagadas"] += total
        elif estado == "ANULADA":
            resumen["anuladas"] += 1

    return resumen


# =============================================================
# FACTURACIÓN LIBRE (SIN CITA)
# =============================================================

def buscar_paciente_por_cedula(numero_documento: str):
    """Busca un paciente solo por cédula, sin filtrar citas."""
    res = (
        _sb()
        .table("hc_pacientes")
        .select(
            "id, primer_nombre, segundo_nombre, primer_apellido, "
            "segundo_apellido, numero_documento, tipo_documento_id, "
            "fecha_nacimiento, sexo"
        )
        .eq("numero_documento", numero_documento.strip())
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def crear_prefactura_libre(data: dict, items: list):
    """
    Crea una prefactura con ítems manuales (sin cita).
    Los ítems llevan cita_id = None.
    """
    prefactura = crear_prefactura(data)
    if not prefactura:
        return None, []

    for item in items:
        item["prefactura_id"] = prefactura["id"]
        item["cita_id"] = None
        item["cita_procedimiento_id"] = None

    items_creados = agregar_items_prefactura(items)
    return prefactura, items_creados


def buscar_cups_por_texto(query: str, limite: int = 15):
    """Busca procedimientos CUPS por código o descripción."""
    res = (
        _sb()
        .table("hc_cups")
        .select("id, codigo, descripcion")
        .or_(f"codigo.ilike.%{query}%,descripcion.ilike.%{query}%")
        .order("codigo")
        .limit(limite)
        .execute()
    )
    return res.data or []