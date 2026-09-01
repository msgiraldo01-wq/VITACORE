# =============================================
# VITACORE · Repositorio Contabilidad (núcleo)
# Archivo: repositories/fin_contabilidad_repo.py
# ---------------------------------------------
# Capa de acceso a datos del núcleo contable.
# Sigue el mismo patrón que fin_cartera_repo / fin_facturacion_repo:
# funciones sueltas, cliente Supabase, retorno de .data.
#
# Tablas: fin_puc, fin_terceros, fin_centros_costo,
#         fin_comprobantes, fin_movimientos, fin_periodos,
#         fin_consecutivos_contables
# RPC:    fin_registrar_comprobante, fin_anular_comprobante
# =============================================

from services.supabase_service import get_supabase_admin


def _sb():
    return get_supabase_admin()


# =============================================================
# PLAN ÚNICO DE CUENTAS (PUC)
# =============================================================

def listar_puc(empresa_id: int = 1, solo_movimiento: bool = False):
    """Retorna el PUC ordenado por código. Si solo_movimiento=True,
    devuelve únicamente las cuentas que admiten asientos."""
    q = (
        _sb()
        .table("fin_puc")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("codigo")
    )
    if solo_movimiento:
        q = q.eq("tipo", "MOVIMIENTO").eq("estado", "ACTIVA").eq("bloqueada", False)
    res = q.execute()
    return res.data or []


def obtener_cuenta(cuenta_id: int):
    res = (
        _sb()
        .table("fin_puc")
        .select("*")
        .eq("id", cuenta_id)
        .single()
        .execute()
    )
    return res.data


def buscar_cuentas(query: str, empresa_id: int = 1, limite: int = 20):
    """Busca cuentas de MOVIMIENTO por código o nombre (para el buscador
    del formulario de comprobantes)."""
    res = (
        _sb()
        .table("fin_puc")
        .select("id, codigo, nombre, naturaleza, exige_tercero, exige_centro_costo, exige_base")
        .eq("empresa_id", empresa_id)
        .eq("tipo", "MOVIMIENTO")
        .eq("estado", "ACTIVA")
        .or_(f"codigo.ilike.%{query}%,nombre.ilike.%{query}%")
        .order("codigo")
        .limit(limite)
        .execute()
    )
    return res.data or []


def crear_cuenta(data: dict):
    res = _sb().table("fin_puc").insert(data).execute()
    return res.data[0] if res.data else None


def actualizar_cuenta(cuenta_id: int, data: dict):
    res = _sb().table("fin_puc").update(data).eq("id", cuenta_id).execute()
    return res.data


# =============================================================
# TERCEROS
# =============================================================

def listar_terceros(empresa_id: int = 1, limite: int = 200):
    res = (
        _sb()
        .table("fin_terceros")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("razon_social")
        .limit(limite)
        .execute()
    )
    return res.data or []


def buscar_terceros(query: str, empresa_id: int = 1, limite: int = 20):
    res = (
        _sb()
        .table("fin_terceros")
        .select("id, tipo_documento, numero_documento, razon_social")
        .eq("empresa_id", empresa_id)
        .eq("estado", "ACTIVO")
        .or_(f"numero_documento.ilike.%{query}%,razon_social.ilike.%{query}%")
        .order("razon_social")
        .limit(limite)
        .execute()
    )
    return res.data or []


def obtener_tercero(tercero_id: int):
    res = (
        _sb()
        .table("fin_terceros")
        .select("*")
        .eq("id", tercero_id)
        .single()
        .execute()
    )
    return res.data


def crear_tercero(data: dict):
    res = _sb().table("fin_terceros").insert(data).execute()
    return res.data[0] if res.data else None


def actualizar_tercero(tercero_id: int, data: dict):
    res = _sb().table("fin_terceros").update(data).eq("id", tercero_id).execute()
    return res.data


# =============================================================
# CENTROS DE COSTO
# =============================================================

def listar_centros_costo(empresa_id: int = 1):
    res = (
        _sb()
        .table("fin_centros_costo")
        .select("*")
        .eq("empresa_id", empresa_id)
        .eq("estado", "ACTIVO")
        .order("codigo")
        .execute()
    )
    return res.data or []


def crear_centro_costo(data: dict):
    res = _sb().table("fin_centros_costo").insert(data).execute()
    return res.data[0] if res.data else None


# =============================================================
# COMPROBANTES · MOTOR DE PARTIDA DOBLE (vía RPC transaccional)
# =============================================================

def registrar_comprobante(
    empresa_id: int,
    sede_id,
    tipo_comprobante: str,
    fecha: str,
    descripcion: str,
    movimientos: list,
    usuario: str,
    origen: str = "MANUAL",
    origen_tabla: str = None,
    origen_id: str = None,
):
    """
    Registra un comprobante contable de forma ATÓMICA llamando a la función
    RPC fin_registrar_comprobante en Postgres. Toda la validación de partida
    doble, cuentas, periodo y reglas de captura ocurre del lado del servidor.

    movimientos: lista de dicts con las líneas del asiento, p.ej.:
        [
          {"cuenta_id": 5, "tercero_id": 1, "centro_costo_id": 1,
           "descripcion": "...", "debito": 119000, "credito": 0,
           "base_gravable": 0},
          ...
        ]

    Retorna el dict que devuelve la RPC:
        {"ok": True, "comprobante_id": ..., "numero": "CI-000001", ...}
      o {"ok": False, "error": "..."}
    """
    params = {
        "p_empresa_id": empresa_id,
        "p_sede_id": sede_id,
        "p_tipo_comprobante": tipo_comprobante,
        "p_fecha": fecha,
        "p_descripcion": descripcion,
        "p_origen": origen,
        "p_origen_tabla": origen_tabla,
        "p_origen_id": origen_id,
        "p_usuario": usuario,
        "p_movimientos": movimientos,
    }
    res = _sb().rpc("fin_registrar_comprobante", params).execute()
    return res.data


def anular_comprobante(comprobante_id: int, usuario: str, motivo: str):
    """Anula un comprobante (no lo borra) vía RPC."""
    params = {
        "p_comprobante_id": comprobante_id,
        "p_usuario": usuario,
        "p_motivo": motivo,
    }
    res = _sb().rpc("fin_anular_comprobante", params).execute()
    return res.data


def listar_comprobantes(empresa_id: int = 1, periodo: str = None,
                        tipo: str = None, limite: int = 100):
    q = (
        _sb()
        .table("fin_comprobantes")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("fecha", desc=True)
        .order("id", desc=True)
        .limit(limite)
    )
    if periodo:
        q = q.eq("periodo", periodo)
    if tipo:
        q = q.eq("tipo_comprobante", tipo)
    res = q.execute()
    return res.data or []


def obtener_comprobante(comprobante_id: int):
    res = (
        _sb()
        .table("fin_comprobantes")
        .select("*")
        .eq("id", comprobante_id)
        .single()
        .execute()
    )
    return res.data


def obtener_movimientos(comprobante_id: int):
    """Movimientos de un comprobante, con datos de cuenta y tercero
    embebidos para mostrarlos en el detalle."""
    res = (
        _sb()
        .table("fin_movimientos")
        .select(
            "*, fin_puc(codigo, nombre), "
            "fin_terceros(numero_documento, razon_social), "
            "fin_centros_costo(codigo, nombre)"
        )
        .eq("comprobante_id", comprobante_id)
        .order("id")
        .execute()
    )
    return res.data or []


# =============================================================
# LIBROS · DIARIO Y MAYOR
# =============================================================

def libro_diario(empresa_id: int = 1, periodo: str = None, limite: int = 500):
    """
    Libro diario: movimientos ordenados por fecha del comprobante.
    Trae el comprobante embebido para conocer número y fecha.
    """
    q = (
        _sb()
        .table("fin_movimientos")
        .select(
            "id, cuenta_codigo, debito, credito, descripcion, "
            "fin_puc(nombre), "
            "fin_comprobantes!inner(numero, fecha, periodo, tipo_comprobante, estado)"
        )
        .eq("empresa_id", empresa_id)
        .limit(limite)
    )
    if periodo:
        q = q.eq("fin_comprobantes.periodo", periodo)
    res = q.execute()
    return res.data or []


def libro_mayor(cuenta_id: int, empresa_id: int = 1, periodo: str = None):
    """
    Libro mayor de una cuenta: todos sus movimientos con el comprobante
    asociado. El saldo acumulado se calcula en el service.
    """
    q = (
        _sb()
        .table("fin_movimientos")
        .select(
            "id, debito, credito, descripcion, "
            "fin_comprobantes!inner(numero, fecha, periodo, estado)"
        )
        .eq("empresa_id", empresa_id)
        .eq("cuenta_id", cuenta_id)
    )
    if periodo:
        q = q.eq("fin_comprobantes.periodo", periodo)
    res = q.execute()
    return res.data or []


# =============================================================
# PERIODOS
# =============================================================

def listar_periodos(empresa_id: int = 1):
    res = (
        _sb()
        .table("fin_periodos")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("periodo", desc=True)
        .execute()
    )
    return res.data or []


def cambiar_estado_periodo(empresa_id: int, periodo: str, estado: str, usuario: str):
    """Abre o cierra un periodo. Al cerrar, guarda quién y cuándo."""
    data = {"estado": estado}
    if estado == "CERRADO":
        data["cerrado_por"] = usuario
        data["cerrado_at"] = "now()"
    # upsert: si el periodo no existía, lo crea
    res = (
        _sb()
        .table("fin_periodos")
        .upsert(
            {"empresa_id": empresa_id, "periodo": periodo, **data},
            on_conflict="empresa_id,periodo",
        )
        .execute()
    )
    return res.data


# =============================================================
# CONSECUTIVOS
# =============================================================

def listar_consecutivos(empresa_id: int = 1):
    res = (
        _sb()
        .table("fin_consecutivos_contables")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("tipo_comprobante")
        .execute()
    )
    return res.data or []
