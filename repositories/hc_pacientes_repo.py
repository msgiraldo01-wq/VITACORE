from typing import Any
from datetime import date, datetime
from services.supabase_service import get_supabase_admin
from flask import session


def _table_name() -> str:
    return "hc_pacientes"

def _empresa_id():
    return session.get("empresa_id")


def _sb():
    return get_supabase_admin()


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row.get("id"),
        "tipo_documento_id": row.get("tipo_documento_id"),
        "numero_documento": row.get("numero_documento") or "",

        "primer_nombre": row.get("primer_nombre") or "",
        "segundo_nombre": row.get("segundo_nombre") or "",
        "primer_apellido": row.get("primer_apellido") or "",
        "segundo_apellido": row.get("segundo_apellido") or "",

        "fecha_nacimiento": row.get("fecha_nacimiento"),
        "pais_id": row.get("pais_id"),
        "departamento_id": row.get("departamento_id"),
        "municipio_id": row.get("municipio_id"),
        "sexo": row.get("sexo") or "",
        "estado_civil": row.get("estado_civil") or "",
        "edad": calcular_edad(row.get("fecha_nacimiento")),
        
        # Contacto
        "telefono": row.get("telefono") or "",
        "celular": row.get("celular") or "",
        "email": row.get("email") or "",
        "direccion": row.get("direccion") or "",
        
        # EPS
        "eps_id": row.get("eps_id"),
        "eps_nombre": row.get("eps_nombre") or "",
        "regimen_afiliacion": row.get("regimen_afiliacion") or "",
        "aseguradora": row.get("aseguradora") or "",
        
        # Datos adicionales Res. 1888
        "ocupacion": row.get("ocupacion") or "",
        "zona": row.get("zona") or "",
        "grupo_poblacional": row.get("grupo_poblacional") or "",
        "nivel_educativo": row.get("nivel_educativo") or "",
        
        # Datos relacionados
        "hc_tipos_documento": row.get("hc_tipos_documento"),
        "hc_municipios": row.get("hc_municipios"),
        "hc_eps": row.get("hc_eps"),
        
        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ================================
# LISTAR PACIENTES
# ================================

def listar(completo: bool = True):
    """
    Lista pacientes por empresa.
    """

    empresa_id = _empresa_id()

    # 🔒 Seguridad: sin empresa no hay datos
    if not empresa_id:
        return []

    select_query = """
        *,
        hc_tipos_documento(nombre),
        hc_eps(id, nombre, codigo)
    """
    
    if completo:
        select_query = """
            *,
            hc_tipos_documento(nombre),
            hc_municipios(*),
            hc_eps(id, nombre, codigo)
        """

    response = (
        _sb()
        .table(_table_name())
        .select(select_query)
        .eq("empresa_id", empresa_id)  # 🔥 FILTRO CLAVE
        .order("primer_apellido")
        .order("primer_nombre")
        .execute()
    )

    pacientes = response.data or []

    if not completo:
        return [_normalize_row(x) for x in pacientes]

    # =========================
    # MUNICIPIOS + DEPARTAMENTO
    # =========================
    municipios_response = (
        _sb()
        .table("hc_municipios")
        .select("*, hc_departamentos(nombre)")
        .execute()
    )

    municipios_dict = {}
    for m in (municipios_response.data or []):
        dept_nombre = ""

        if m.get("hc_departamentos"):
            dept_nombre = m["hc_departamentos"].get("nombre", "")
        elif m.get("departamento_nombre"):
            dept_nombre = m["departamento_nombre"]

        municipios_dict[m["id"]] = {
            "id": m["id"],
            "nombre": m.get("nombre", ""),
            "departamento_nombre": dept_nombre
        }

    # 🔄 Enriquecer pacientes
    for p in pacientes:
        mun_id = p.get("municipio_id")

        if mun_id and mun_id in municipios_dict:
            p["hc_municipios"] = municipios_dict[mun_id]
        else:
            p["hc_municipios"] = None

    return [_normalize_row(x) for x in pacientes]
# ================================
# OBTENER PACIENTE
# ================================

def obtener(item_id: int):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    response = (
        _sb()
        .table(_table_name())
        .select("""
            *,
            hc_eps:eps_id(id, nombre, codigo, nit),
            hc_municipios:municipio_id(
                id,
                nombre,
                hc_departamentos:departamento_id(nombre)
            )
        """)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )

    data = response.data or []

    print(data)  # 👈 deja esto para verificar

    return _normalize_row(data[0]) if data else None

# ================================
# BUSCAR PACIENTE POR DOCUMENTO
# ================================

def buscar_por_documento(numero_documento: str):

    numero_documento = (numero_documento or "").strip()
    empresa_id = _empresa_id()

    if not numero_documento or not empresa_id:
        return None

    response = (
        _sb()
        .table(_table_name())
        .select("*, hc_eps(id, nombre, codigo)")
        .eq("numero_documento", numero_documento)
        .eq("empresa_id", empresa_id)  # 🔥 FIX
        .limit(1)
        .execute()
    )

    data = response.data or []

    return _normalize_row(data[0]) if data else None


# ================================
# CREAR PACIENTE
# ================================

def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None


    payload = {

        "empresa_id": empresa_id,

        "tipo_documento_id": data.get("tipo_documento_id"),
        "numero_documento": (data.get("numero_documento") or "").strip(),

        "primer_nombre": (data.get("primer_nombre") or "").strip(),
        "segundo_nombre": (data.get("segundo_nombre") or "").strip(),
        "primer_apellido": (data.get("primer_apellido") or "").strip(),
        "segundo_apellido": (data.get("segundo_apellido") or "").strip(),

        "fecha_nacimiento": data.get("fecha_nacimiento"),
        "pais_id": data.get("pais_id"),
        "departamento_id": data.get("departamento_id"),
        "municipio_id": data.get("municipio_id"),
        "sexo": (data.get("sexo") or "").strip(),
        "estado_civil": (data.get("estado_civil") or "").strip(),
        
        "telefono": (data.get("telefono") or "").strip(),
        "celular": (data.get("celular") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),
        
        # EPS
        "eps_id": data.get("eps_id"),
        "eps_nombre": (data.get("eps_nombre") or "").strip(),
        "regimen_afiliacion": (data.get("regimen_afiliacion") or "").strip(),
        "aseguradora": (data.get("aseguradora") or "").strip(),
        
        # Datos adicionales Res. 1888
        "ocupacion": (data.get("ocupacion") or "").strip(),
        "zona": (data.get("zona") or "").strip(),
        "grupo_poblacional": (data.get("grupo_poblacional") or "").strip(),
        "nivel_educativo": (data.get("nivel_educativo") or "").strip(),
        
        "estado": "ACTIVO",
    }

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else None


# ================================
# ACTUALIZAR PACIENTE
# ================================

def actualizar(item_id: int, data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None  # 🔒 seguridad

    payload = {
        "tipo_documento_id": data.get("tipo_documento_id"),
        "numero_documento": (data.get("numero_documento") or "").strip(),

        "primer_nombre": (data.get("primer_nombre") or "").strip(),
        "segundo_nombre": (data.get("segundo_nombre") or "").strip(),
        "primer_apellido": (data.get("primer_apellido") or "").strip(),
        "segundo_apellido": (data.get("segundo_apellido") or "").strip(),

        "fecha_nacimiento": data.get("fecha_nacimiento"),
        "pais_id": data.get("pais_id"),
        "departamento_id": data.get("departamento_id"),
        "municipio_id": data.get("municipio_id"),
        "sexo": (data.get("sexo") or "").strip(),
        "estado_civil": (data.get("estado_civil") or "").strip(),

        "telefono": (data.get("telefono") or "").strip(),
        "celular": (data.get("celular") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),

        # EPS
        "eps_id": data.get("eps_id"),
        "eps_nombre": (data.get("eps_nombre") or "").strip(),
        "regimen_afiliacion": (data.get("regimen_afiliacion") or "").strip(),
        "aseguradora": (data.get("aseguradora") or "").strip(),

        # Res. 1888
        "ocupacion": (data.get("ocupacion") or "").strip(),
        "zona": (data.get("zona") or "").strip(),
        "grupo_poblacional": (data.get("grupo_poblacional") or "").strip(),
        "nivel_educativo": (data.get("nivel_educativo") or "").strip(),
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 SEGURIDAD
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)

# ================================
# CAMBIAR ESTADO
# ================================

def cambiar_estado(item_id: int, nuevo_estado: str):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None  # 🔒 seguridad

    payload = {
        "estado": (nuevo_estado or "").strip().upper()
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)


def nombre_completo(p: dict):

    return " ".join(filter(None, [
        p.get("primer_nombre"),
        p.get("segundo_nombre"),
        p.get("primer_apellido"),
        p.get("segundo_apellido"),
    ]))


# =========================
# BUSCAR
# =========================

def buscar(q: str = "", limite: int = 15):

    q = (q or "").strip()
    empresa_id = _empresa_id()

    if not q or not empresa_id:
        return []

    response = (
        _sb()
        .table(_table_name())
        .select("id, numero_documento, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido")
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .or_(
            f"numero_documento.ilike.%{q}%," 
            f"primer_nombre.ilike.%{q}%," 
            f"primer_apellido.ilike.%{q}%," 
            f"segundo_apellido.ilike.%{q}%"
        )
        .eq("estado", "ACTIVO")
        .order("primer_apellido")
        .limit(limite)
        .execute()
    )

    return response.data or []

def calcular_edad(fecha):
    if not fecha:
        return None

    # Si viene como string (Supabase)
    if isinstance(fecha, str):
        fecha = datetime.strptime(fecha, "%Y-%m-%d").date()

    return (date.today() - fecha).days // 365