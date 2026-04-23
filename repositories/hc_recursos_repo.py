from typing import Any
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_recursos"


def _sb():
    return get_supabase_admin()


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    sede = row.get("hc_sedes") or {}
    consultorio = row.get("hc_consultorios") or {}

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "tipo": row.get("tipo") or "",
        "descripcion": row.get("descripcion") or "",
        "estado": row.get("estado") or "ACTIVO",

        # 🔥 NUEVO
        "sede_nombre": sede.get("nombre"),
        "consultorio_nombre": consultorio.get("nombre"),
    }


# ========================
# LISTAR (CON JOIN)
# ========================

def listar():

    res = (
        _sb()
        .table(_table())
        .select("""
            *,
            hc_sedes(nombre),
            hc_consultorios(nombre)
        """)
        .order("nombre")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ========================
# OBTENER
# ========================

def obtener(id: int):

    res = (
        _sb()
        .table(_table())
        .select("*")
        .eq("id", id)
        .limit(1)
        .execute()
    )

    data = (res.data or [None])[0]
    return _normalize(data)


# ========================
# CREAR
# ========================

def crear(data: dict):

    return (
        _sb()
        .table(_table())
        .insert(data)
        .execute()
    )


# ========================
# ACTUALIZAR
# ========================

def actualizar(id: int, data: dict):

    return (
        _sb()
        .table(_table())
        .update(data)
        .eq("id", id)
        .execute()
    )


# ========================
# TOGGLE
# ========================

def toggle(id: int):

    recurso = obtener(id)

    nuevo_estado = "INACTIVO" if recurso["estado"] == "ACTIVO" else "ACTIVO"

    return actualizar(id, {"estado": nuevo_estado})

# ========================
# LISTAR SELECT (para modal de citas)
# ========================

def listar_select(sede_id: int = None, tipo: str = None):

    q = (
        _sb()
        .table(_table())
        .select("id, nombre, tipo, sede_id")
        .eq("estado", "ACTIVO")
        .order("nombre")
    )

    if sede_id:
        q = q.eq("sede_id", sede_id)

    if tipo:
        q = q.eq("tipo", tipo)

    r = q.execute()

    return [
        {
            "id"    : item["id"],
            "nombre": item["nombre"],
            "tipo"  : item.get("tipo") or "",
        }
        for item in (r.data or [])
    ]


def listar_por_sede(sede_id: int):
    return listar_select(sede_id=sede_id)