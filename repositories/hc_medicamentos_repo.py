from typing import Any
from services.supabase_service import get_supabase_admin
from flask import session


def _table():
    return "hc_medicamentos"


def _sb():
    return get_supabase_admin()


def _empresa_id():
    return session.get("empresa_id")
    


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo"),
        "principio_activo": row.get("principio_activo"),
        "forma_farmaceutica": row.get("forma_farmaceutica"),
        "concentracion": row.get("concentracion"),
        "estado": row.get("estado"),
        "via_administracion": row.get("via_administracion"),
        "nombre_comercial": row.get("nombre_comercial"),
        "laboratorio": row.get("laboratorio"),
        "registro_invima": row.get("registro_invima"),
        "cum": row.get("cum"),
    }


# ======================
# LISTAR
# ======================

def listar():

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    res = (
        _sb()
        .table(_table())
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("principio_activo")
        .execute()
    )

    return [_normalize(x) for x in res.data]


# ======================
# CREAR
# ======================

def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    data["empresa_id"] = empresa_id  

    res = (
        _sb()
        .table(_table())
        .insert(data)
        .execute()
    )

    return _normalize(res.data[0])


# ======================
# OBTENER
# ======================

def obtener(id: int):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    res = (
        _sb()
        .table(_table())
        .select("*")
        .eq("id", id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return _normalize(res.data[0])


# ======================
# ACTUALIZAR
# ======================

def actualizar(id: int, data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    res = (
        _sb()
        .table(_table())
        .update(data)
        .eq("id", id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .execute()
    )

    if not res.data:
        return None

    return _normalize(res.data[0])


# ======================
# BUSCAR
# ======================

def buscar(texto: str):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    res = (
        _sb()
        .table(_table())
        .select("*")
        .ilike("principio_activo", f"%{texto}%")
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .limit(10)
        .execute()
    )

    return [_normalize(x) for x in res.data]


# ======================
# CAMBIAR ESTADO
# ======================

def cambiar_estado(id: int, estado: str):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    res = (
        _sb()
        .table(_table())
        .update({"estado": estado})
        .eq("id", id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .execute()
    )

    if not res.data:
        return None

    return _normalize(res.data[0])