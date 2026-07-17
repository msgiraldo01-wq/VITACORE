# ============================================================================
# VITACORE HMS — Blueprint de Inventario/Farmacia (Fase 1)
# ============================================================================
from functools import wraps

from flask import Blueprint, redirect, session, url_for

inventario_bp = Blueprint(
    "inventario",
    __name__,
    url_prefix="/inventario",
    template_folder="../../templates",
)


def contexto_empresa(f):
    """Exige empresa seleccionada (modelo multiempresa) e inyecta empresa/usuario.

    Coincide con la convención del proyecto: la empresa activa vive en
    session["empresa_id"] (igual que en repositories de pacientes) y el
    usuario autenticado es un dict en session["user"].

    Nota de diseño: aquí pasamos empresa_id explícito a servicio/repositorio
    (en vez de leer session adentro del repo) porque las funciones SQL del
    kardex lo reciben como parámetro y así el servicio queda testeable sin
    contexto Flask. El resultado para la seguridad es el mismo: toda consulta
    filtra por empresa.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        empresa_id = session.get("empresa_id")
        user = session.get("user") or {}
        usuario_id = user.get("id")  # ⚠️ si tu dict de usuario usa otra llave (p.ej. 'user_id' o 'uuid'), cámbiala aquí
        if not empresa_id:
            # Endpoint real del proyecto (confirmado por Flask): bp_hc_empresa.seleccionar_empresa
            try:
                return redirect(url_for("bp_hc_empresa.seleccionar_empresa"))
            except Exception:
                return redirect("/empresa/seleccionar")
        return f(empresa_id=empresa_id, usuario_id=usuario_id, *args, **kwargs)
    return wrapper


# Importar las rutas al final para que se registren sobre el blueprint
from . import routes_bodegas, routes_compras, routes_condiciones, routes_movimientos, routes_productos, routes_traslados  # noqa: E402,F401
