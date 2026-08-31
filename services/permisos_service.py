"""
Servicio central de permisos por módulo.

Reemplaza los dos mecanismos que convivían sin estar bien conectados
(la matriz por módulo en `roles_modulos`, que ya tenía checkboxes
Ver/Crear/Editar/Eliminar pero no controlaba nada real; y la matriz
por ruta técnica en `roles_rutas`, que sí se intentaba usar pero
dependía de un `role_id` que el login nunca guardaba en sesión).

Ahora hay un solo mapa de permisos por rol (`roles_modulos`), y este
módulo es el único punto que:
  1) Resuelve a qué "módulo" de negocio pertenece la URL que se está
     pidiendo (RUTAS_MODULO, por prefijo de URL -- no por nombre
     interno de blueprint, para que sea fácil de leer y mantener).
  2) Carga la matriz de permisos del rol activo UNA vez por request
     (cacheada en flask.g) y expone helpers simples para el gate
     central en app.py y para el sidebar en los templates.

SUPER_ADMIN (guardado como texto en profiles.role, fuera del sistema
de roles/role_id) siempre tiene acceso total -- igual que ya hacía
hc_empresa/routes.py para el selector de empresas.
"""

from functools import wraps

from flask import session, g, request, jsonify

from services.supabase_service import get_supabase_admin


# Prefijos de URL -> code del módulo en la tabla `modulos`.
# Se evalúan del más específico al más genérico (por longitud de
# prefijo), así que no importa el orden en que se escriban aquí.
RUTAS_MODULO = {
    "/hc/pacientes": "pacientes",
    "/hc/admisiones": "admisiones",
    # Historia clínica está repartida en varios blueprints con prefijos
    # de URL distintos ("/hc/historia-clinica" es solo la pantalla de
    # entrada con el buscador; el contenido real -- línea de tiempo,
    # evoluciones/notas clínicas, signos vitales -- vive en "/hc/historia",
    # "/hc/evoluciones" y "/hc/signos"). Antes de esto esos tres últimos
    # caían en el "/hc/" genérico de más abajo (dashboard_clinico), o sea
    # que el checkbox "Historia clínica" de Roles y permisos no controlaba
    # lo más sensible del sistema. Todos apuntan al mismo código.
    "/hc/historia-clinica": "historia_clinica",
    "/hc/historia": "historia_clinica",
    "/hc/evoluciones": "historia_clinica",
    "/hc/signos": "historia_clinica",
    # Agenda clínica (vista de trabajo: lista del día + cambiar estado +
    # acceso directo a la nota) es otra puerta de entrada al mismo
    # módulo -- quien ya puede ver Historia clínica la ve sin necesidad
    # de que un administrador configure nada aparte.
    "/hc/agenda-clinica": "historia_clinica",
    # Catálogo maestro de medicamentos (crear/editar el formulario del
    # medicamento en sí) -- es dato administrativo, no historia clínica
    # de un paciente, así que tiene su propio módulo.
    "/hc/medicamentos": "medicamentos",
    "/hc/reportes": "reportes",
    # Clientes, contratos y manuales tarifarios viven -- por razones
    # técnicas/históricas -- dentro del blueprint de Configuración
    # ("/hc/configuracion/clientes", "/hc/configuracion/contratos",
    # "/hc/configuracion/manuales-tarifarios"), pero conceptualmente son
    # el módulo de Contratos, no catálogos de Configuración. Sin estos
    # prefijos más específicos caían en "/hc/configuracion" de abajo
    # (el checkbox "Configuración"), igual que le pasaba antes a Historia
    # clínica. El usuario decidió agruparlos todos bajo un solo módulo
    # "Contratos" en Roles y permisos.
    "/hc/configuracion/clientes": "contratos",
    "/hc/configuracion/contratos": "contratos",
    "/hc/configuracion/manuales-tarifarios": "contratos",
    "/hc/configuracion": "configuracion",
    "/hc/": "dashboard_clinico",

    "/citas": "citas",
    "/rda": "rda",
    "/inventario": "farmacia",

    "/financiero/dashboard": "dashboard_financiero",
    "/financiero/contratos": "contratos",
    # Facturación se parte en 3: el día a día (crear/ver facturas), la
    # configuración de consecutivos/resoluciones, y el panel técnico de
    # diagnóstico Factus -- son prefijos más específicos que "/facturacion",
    # así que ganan sobre el genérico automáticamente (se elige el más largo).
    "/facturacion/configuracion": "facturacion_config",
    "/facturacion/api/consecutivos": "facturacion_config",
    "/facturacion/factus/eventos": "facturacion_diagnostico",
    "/facturacion/api/factus": "facturacion_diagnostico",
    "/facturacion": "facturacion",
    "/financiero/radicacion": "radicacion",
    "/financiero/glosas": "glosas",
    "/financiero/cartera": "cartera",
    "/financiero/conciliaciones": "conciliaciones",
    "/financiero/tesoreria": "tesoreria",
    "/financiero/configuracion": "config_financiera",

    "/caja": "caja",
}

# Prefijos que nunca requieren permiso de módulo (login, estáticos,
# selector de empresa de SUPER_ADMIN, endpoints internos de sync).
RUTAS_EXENTAS = ("/auth", "/static", "/empresa", "/admin", "/ping")


def resolver_modulo_code(path: str):
    """Devuelve el modulo_code que corresponde a una URL, o None si
    esa URL no requiere permiso (pública o no mapeada todavía)."""
    if path == "/" or path.startswith(RUTAS_EXENTAS):
        return None

    mejor_prefijo = ""
    modulo_code = None
    for prefijo, code in RUTAS_MODULO.items():
        if path.startswith(prefijo) and len(prefijo) > len(mejor_prefijo):
            mejor_prefijo = prefijo
            modulo_code = code
    return modulo_code


def es_super_admin() -> bool:
    return (session.get("rol") or "").strip().upper() == "SUPER_ADMIN"


def _matriz_rol(role_id: int) -> dict:
    """Matriz {modulo_code: {can_view, can_create, can_edit, can_delete}}
    del rol dado, cacheada una vez por request en flask.g."""
    cache = getattr(g, "_matriz_permisos_cache", None)
    if cache is not None and cache.get("role_id") == role_id:
        return cache["matriz"]

    supabase = get_supabase_admin()
    matriz = {}

    if role_id:
        res = (
            supabase
            .table("roles_modulos")
            .select("can_view, can_create, can_edit, can_delete, modulos!inner(code)")
            .eq("role_id", role_id)
            .execute()
        )
        for fila in (res.data or []):
            modulo = fila.get("modulos") or {}
            code = modulo.get("code")
            if code:
                matriz[code] = {
                    "can_view": bool(fila.get("can_view")),
                    "can_create": bool(fila.get("can_create")),
                    "can_edit": bool(fila.get("can_edit")),
                    "can_delete": bool(fila.get("can_delete")),
                }

    g._matriz_permisos_cache = {"role_id": role_id, "matriz": matriz}
    return matriz


def puede(modulo_code: str, accion: str = "view") -> bool:
    """¿El usuario de la sesión actual puede `accion` sobre `modulo_code`?
    accion en {"view", "create", "edit", "delete"}."""
    if not modulo_code:
        return True

    if es_super_admin():
        return True

    user = session.get("user") or {}
    role_id = user.get("role_id")
    if not role_id:
        return False

    permiso = _matriz_rol(role_id).get(modulo_code)
    if not permiso:
        return False

    return bool(permiso.get(f"can_{accion}", False))


def puede_ver(modulo_code: str) -> bool:
    """Atajo para los templates (sidebar): ¿se ve este módulo en el menú?"""
    return puede(modulo_code, "view")


def requiere_permiso(modulo_code: str, accion: str):
    """
    Decorador para exigir Crear/Editar/Eliminar (no solo "Ver", que ya
    cubre el gate central de app.py) en una vista puntual. Se usa en las
    rutas que de verdad modifican datos -- crear una factura, anular,
    eliminar un pendiente, etc.

    Uso:
        @bp_facturacion.route("/api/nota", methods=["POST"])
        @login_required
        @requiere_permiso("facturacion", "create")
        def api_crear_nota():
            ...
    """
    def decorador(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not puede(modulo_code, accion):
                mensaje = f"No tienes permiso para {accion} en este módulo."
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
                    return jsonify({"error": mensaje}), 403
                from flask import render_template
                return render_template("/hc/acceso_denegado.html"), 403
            return view_func(*args, **kwargs)
        return wrapped
    return decorador


def denegado(modulo_code: str, accion: str):
    """Versión "inline" de `requiere_permiso`, para usar DENTRO del cuerpo
    de una vista en vez de como decorador -- necesaria cuando una misma
    función atiende más de una acción según los datos del request (p. ej.
    una sola ruta que sirve de alta O edición según si llega un id, o una
    ruta con un único `if request.method == "POST":` donde solo esa rama
    modifica datos y la vista GET debe seguir siendo visible con "view").

    Devuelve None si el usuario sí tiene el permiso (seguir normal), o la
    respuesta 403 lista para retornar (`return denegado(...)`) si no lo
    tiene. Misma semántica que `requiere_permiso`: JSON para AJAX/API,
    página de acceso denegado en el resto de los casos.
    """
    if puede(modulo_code, accion):
        return None
    mensaje = f"No tienes permiso para {accion} en este módulo."
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
        return jsonify({"error": mensaje}), 403
    from flask import render_template
    return render_template("/hc/acceso_denegado.html"), 403
