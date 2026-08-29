# repositories/hc_parametros_repo.py
"""
Parámetros generales del sistema: valores de configuración sueltos que
no ameritan su propia tabla ni pantalla dedicada (a diferencia de una
maestra como Festivos, que sí es una lista de varios registros). Se
guardan como pares clave/valor en hc_parametros_sistema.

El primer parámetro real es "horas_limite_confirmacion_cita": cuántas
horas antes de la cita deja de funcionar el enlace de confirmar/cancelar
que se manda por correo al paciente.
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


def _table():
    return "hc_parametros_sistema"


def listar() -> list:
    """Todos los parámetros, para la página de administración."""
    res = (
        _sb()
        .table(_table())
        .select("*")
        .order("clave")
        .execute()
    )
    return res.data or []


def obtener(clave: str, default=None):
    """Valor de un parámetro puntual (siempre texto; quien lo use lo convierte)."""
    res = (
        _sb()
        .table(_table())
        .select("valor")
        .eq("clave", clave)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0].get("valor")
    return default


def establecer(clave: str, valor: str):
    _sb().table(_table()).update({"valor": str(valor)}).eq("clave", clave).execute()
