import re
import unicodedata
from typing import Any
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_municipios"


def _sb():
    return get_supabase_admin()


def normalizar_texto(texto: str) -> str:
    """Normaliza un nombre para comparar sin importar tildes, mayúsculas,
    puntuación o espacios extra (ej. 'Bogotá, D.C.' -> 'BOGOTA DC')."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^A-Za-z0-9]+", " ", t)
    return t.strip().upper()


# ========================
# SINCRONIZACIÓN CON DANE/DIAN (código_dian)
# ========================

def listar_todos_para_sync():
    """id, nombre, departamento_id y codigo_dian de TODOS los municipios
    (sin filtrar por estado), para el proceso de sincronización con la
    tabla oficial DANE/DIVIPOLA."""
    res = (
        _sb()
        .table(_table())
        .select("id, nombre, departamento_id, codigo_dian")
        .execute()
    )
    return res.data or []


def actualizar_codigo_dian(item_id: int, codigo_dian: str, cliente=None):
    """
    cliente: cliente de Supabase ya creado, opcional. Pásalo cuando esto se
    llame desde un hilo de un ThreadPoolExecutor (por ejemplo, al
    paralelizar muchas actualizaciones) — _sb() usa current_app.config, y
    Flask no tiene el contexto de la app disponible en hilos que no sean
    el que atendió el request ("Working outside of application context").
    Crea el cliente en el hilo principal (donde sí hay contexto) y pásalo.
    """
    sb = cliente or _sb()
    sb.table(_table()).update({"codigo_dian": codigo_dian}).eq("id", item_id).execute()


def insertar_muchos(filas: list):
    """filas: [{departamento_id, nombre, codigo, codigo_dian}, ...]"""
    if not filas:
        return []
    res = _sb().table(_table()).insert(filas).execute()
    return res.data or []


def buscar_con_codigo_dian(texto: str = "", limite: int = 20):
    """Busca municipios que YA tienen codigo_dian asignado (listos para
    facturación electrónica), para el buscador del modal 'completar datos
    DIAN'. Devuelve el id real de hc_municipios (el que exige la FK de
    hc_clientes.municipio_id / hc_pacientes.municipio_id)."""
    q = (
        _sb()
        .table(_table())
        .select("id, nombre, codigo_dian, hc_departamentos(nombre)")
        .not_.is_("codigo_dian", "null")
    )
    if texto:
        q = q.ilike("nombre", f"%{texto}%")
    res = q.order("nombre").limit(limite).execute()

    filas = []
    for row in (res.data or []):
        dep = row.get("hc_departamentos") or {}
        filas.append({
            "id": row.get("id"),
            "nombre": row.get("nombre") or "",
            "departamento": dep.get("nombre") or "",
            "codigo_dian": row.get("codigo_dian"),
        })
    return filas


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    dep = row.get("hc_departamentos") or {}

    return {
        "id": row.get("id"),
        "departamento_id": row.get("departamento_id"),
        "departamento": dep.get("nombre"),
        "departamento_nombre": dep.get("nombre"),

        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",

        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
    }


# ========================
# LISTAR
# ========================

def listar():

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .order("nombre")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ========================
# LISTAR POR DEPARTAMENTO
# ========================

def listar_por_departamento(dep_id):

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .eq("departamento_id", dep_id)
        .order("nombre")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ========================
# OBTENER
# ========================

def obtener(item_id: int):

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    data = res.data or []

    return _normalize(data[0]) if data else None


# ========================
# CREAR
# ========================

def crear(data: dict):

    payload = {
        "departamento_id": data.get("departamento_id"),
        "codigo": (data.get("codigo") or "").strip(),
        "nombre": (data.get("nombre") or "").strip(),
        "estado": "ACTIVO",
    }

    res = _sb().table(_table()).insert(payload).execute()

    return _normalize(res.data[0]) if res.data else None


# ========================
# ACTUALIZAR
# ========================

def actualizar(item_id: int, data: dict):

    payload = {
        "departamento_id": data.get("departamento_id"),
        "codigo": (data.get("codigo") or "").strip(),
        "nombre": (data.get("nombre") or "").strip(),
    }

    res = (
        _sb()
        .table(_table())
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    rows = res.data or []

    return _normalize(rows[0]) if rows else obtener(item_id)


# ========================
# TOGGLE ESTADO
# ========================

def cambiar_estado(item_id: int, nuevo_estado: str):

    res = (
        _sb()
        .table(_table())
        .update({"estado": nuevo_estado})
        .eq("id", item_id)
        .execute()
    )

    rows = res.data or []

    return _normalize(rows[0]) if rows else obtener(item_id)