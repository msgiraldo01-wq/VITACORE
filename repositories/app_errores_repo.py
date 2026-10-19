"""Lectura y gestión de los errores registrados (pantalla de Soporte).

La escritura no vive aquí: la hace services/error_service.py a través de
la función app_registrar_error de Postgres, que agrupa repeticiones.
"""

from datetime import datetime, timezone

from services.supabase_service import get_supabase_admin

TABLA = "app_errores"

ESTADOS = ("NUEVO", "REVISADO", "IGNORADO")

# Columnas de la lista: el traceback NO se trae aquí (son miles de
# caracteres por fila y la lista puede mostrar cientos).
_COLS_LISTA = ("id, codigo, tipo, mensaje, ruta, metodo, modulo, usuario, "
               "empresa_id, estado, veces, primera_vez, ultima_vez")


def _sb():
    return get_supabase_admin()


def listar(estado: str = "", busqueda: str = "", modulo: str = "", limite: int = 100):
    """Lista de errores, del más reciente al más viejo."""
    try:
        q = _sb().table(TABLA).select(_COLS_LISTA)

        if estado:
            q = q.eq("estado", estado.upper())
        if modulo:
            q = q.eq("modulo", modulo)
        if busqueda:
            texto = busqueda.strip()
            if texto.upper().startswith("VTC-"):
                q = q.eq("codigo", texto.upper())
            else:
                # el % lo interpreta PostgREST como comodín
                q = q.or_(f"mensaje.ilike.%{texto}%,ruta.ilike.%{texto}%,tipo.ilike.%{texto}%")

        r = q.order("ultima_vez", desc=True).limit(limite).execute()
        return r.data or []
    except Exception as e:
        print("[SOPORTE] error listando:", e)
        return []


def obtener(error_id: int):
    """Un error con su traceback completo."""
    try:
        r = (_sb().table(TABLA).select("*")
             .eq("id", error_id).limit(1).execute())
        return (r.data or [None])[0]
    except Exception as e:
        print("[SOPORTE] error obteniendo", error_id, ":", e)
        return None


def obtener_por_codigo(codigo: str):
    """Búsqueda por el código que dicta el usuario (VTC-7F3A91)."""
    try:
        r = (_sb().table(TABLA).select("*")
             .eq("codigo", (codigo or "").strip().upper()).limit(1).execute())
        return (r.data or [None])[0]
    except Exception as e:
        print("[SOPORTE] error buscando código:", e)
        return None


def cambiar_estado(error_id: int, estado: str, notas: str = None):
    """Marca un error como revisado o ignorado."""
    estado = (estado or "").upper()
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")

    datos = {"estado": estado}
    if notas is not None:
        datos["notas"] = notas

    r = _sb().table(TABLA).update(datos).eq("id", error_id).execute()
    return (r.data or [None])[0]


def resumen():
    """Contadores para las tarjetas del panel de Soporte."""
    try:
        r = _sb().table(TABLA).select("estado, veces, ultima_vez").execute()
        filas = r.data or []

        hoy = datetime.now(timezone.utc).date().isoformat()
        return {
            "distintos": len(filas),
            "nuevos": sum(1 for f in filas if f.get("estado") == "NUEVO"),
            "ocurrencias": sum(int(f.get("veces") or 1) for f in filas),
            "hoy": sum(1 for f in filas if (f.get("ultima_vez") or "")[:10] == hoy),
        }
    except Exception as e:
        print("[SOPORTE] error en resumen:", e)
        return {"distintos": 0, "nuevos": 0, "ocurrencias": 0, "hoy": 0}


def purgar(dias: int = 90):
    """Borra errores revisados o ignorados con más de N días sin repetirse."""
    from datetime import timedelta
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    r = (_sb().table(TABLA).delete()
         .in_("estado", ["REVISADO", "IGNORADO"])
         .lt("ultima_vez", limite).execute())
    return len(r.data or [])
