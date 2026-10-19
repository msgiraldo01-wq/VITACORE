"""
Módulos contratados por empresa.

Hay dos capas de acceso en Vitacore y conviene no confundirlas:

  1. COMERCIAL — qué módulos contrató esta IPS (este archivo).
  2. PERMISOS  — qué puede hacer este rol dentro de lo contratado
     (services/permisos_service.py).

Un usuario ve un módulo solo si pasan las dos. Lo comercial manda:
si la IPS no contrató Farmacia, no hay rol que la haga aparecer.

Decisiones que vale la pena conocer antes de tocar esto:

  - FALLA ABIERTO. Si la tabla no existe todavía (la migración no se
    ha corrido) o la consulta falla, se asume que la empresa tiene
    todo contratado. Es deliberado: un error de infraestructura no
    puede dejar a una clínica sin sistema a medio turno.
  - Una empresa SIN NINGUNA fila también cuenta como "todo
    contratado". Así una IPS recién creada nace funcionando y el
    vendedor apaga después lo que no entró en el contrato.
  - Hay módulos que no se pueden apagar nunca (MODULOS_NUCLEO), para
    que nadie deje a un cliente sin la pantalla de configuración.
"""

from flask import g, session

from services.supabase_service import get_supabase_admin
from services.cache_service import cacheado, invalidar


# Último catálogo de menú leído con éxito. Sobrevive entre peticiones
# dentro del mismo proceso y solo se usa como respaldo si Supabase falla.
_CATALOGO_MENU = None

# Sin estos no queda sistema utilizable: no se pueden desactivar.
MODULOS_NUCLEO = {"configuracion", "dashboard_clinico"}

# Pantallas que cuelgan de un módulo pero no son módulos aparte: comparten
# su permiso y su contratación. Aparecen en el menú debajo de su padre.
SUBITEMS = {
    "historia_clinica": [
        {"name": "Agenda clínica", "endpoint": "/hc/agenda-clinica",
         "icon": "fa-stethoscope"},
    ],
    "rda": [
        {"name": "Visor RDA", "endpoint": "/rda/visor",
         "icon": "fa-magnifying-glass-chart"},
    ],
}


def _sb():
    return get_supabase_admin()


# =========================
# LECTURA (cacheada por request)
# =========================

def contratados(empresa_id=None) -> set:
    """
    Códigos de los módulos que la empresa tiene activos.

    Devuelve None cuando no hay restricción aplicable (empresa sin
    filas, tabla inexistente o error). Quien consulte debe tratar
    None como "todo permitido", que es lo que hace `tiene()`.
    """
    empresa_id = empresa_id or session.get("empresa_id")
    if not empresa_id:
        return None

    cache = getattr(g, "_modulos_empresa", None)
    if cache is not None and cache.get("empresa_id") == empresa_id:
        return cache["codigos"]

    codigos = _leer_contratados(empresa_id)
    g._modulos_empresa = {"empresa_id": empresa_id, "codigos": codigos}
    return codigos



# Las dos consultas de abajo las paga CADA pantalla de la aplicación solo
# para dibujar el menú y saber qué está contratado. Son los datos que menos
# cambian del sistema, así que se guardan unos minutos: la escritura de
# cambiar() los invalida, y el catálogo de módulos solo cambia con una
# migración.

@cacheado(300)
def _leer_contratados(empresa_id):
    """Códigos activos de la empresa, o None si no hay restricción."""
    try:
        res = (
            _sb()
            .table("empresas_modulos")
            .select("activo, modulos!inner(code)")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        filas = res.data or []
        if not filas:                   # sin filas => sin restricción
            return None
        return {
            (f.get("modulos") or {}).get("code")
            for f in filas
            if f.get("activo") and (f.get("modulos") or {}).get("code")
        }
    except Exception as e:
        # La migración todavía no corrió, o Supabase no respondió.
        # Se deja pasar: ver la nota sobre fallar abierto, arriba.
        print(f"[MODULOS] no se pudo leer empresas_modulos: {e}")
        return None


@cacheado(300)
def _leer_catalogo_menu():
    res = (
        _sb().table("modulos")
        .select("code, name, endpoint, icon, section, sort_order")
        .eq("is_active", True)
        .eq("visible_in_sidebar", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []


def tiene(modulo_code: str, empresa_id=None) -> bool:
    """¿La empresa tiene contratado este módulo?"""
    if not modulo_code:
        return True
    if modulo_code in MODULOS_NUCLEO:
        return True

    codigos = contratados(empresa_id)
    if codigos is None:
        return True
    return modulo_code in codigos


# =========================
# ADMINISTRACIÓN
# =========================

@cacheado(300)
def _catalogo():
    """Todos los módulos del sistema, con su id."""
    res = (
        _sb().table("modulos")
        .select("id, code, name, section, sort_order, is_active")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []


@cacheado(300)
def _leer_dependencias_crudas():
    res = (
        _sb().table("modulos_dependencias")
        .select("motivo, modulo:modulos!modulos_dependencias_modulo_id_fkey(code), "
                "requiere:modulos!modulos_dependencias_requiere_id_fkey(code)")
        .execute()
    )
    return res.data or []


def dependencias() -> dict:
    """{code: [(code_requerido, motivo), ...]} — qué necesita cada módulo."""
    cache = getattr(g, "_modulos_deps", None)
    if cache is not None:
        return cache

    mapa = {}
    try:
        for fila in _leer_dependencias_crudas():
            code = (fila.get("modulo") or {}).get("code")
            req = (fila.get("requiere") or {}).get("code")
            if code and req:
                mapa.setdefault(code, []).append((req, fila.get("motivo") or ""))
    except Exception as e:
        print(f"[MODULOS] no se pudieron leer las dependencias: {e}")

    g._modulos_deps = mapa
    return mapa


def dependientes(code: str) -> list:
    """Módulos que necesitan a `code` para funcionar (la relación al revés)."""
    salida = []
    for modulo, requisitos in dependencias().items():
        for req, motivo in requisitos:
            if req == code:
                salida.append((modulo, motivo))
    return salida


def estado_empresa(empresa_id: int) -> list:
    """
    Catálogo completo con el estado de cada módulo para esa empresa,
    listo para pintar la pantalla de administración.
    """
    catalogo = _catalogo()
    activos = contratados(empresa_id)
    deps = dependencias()

    # nombre legible por código, para los mensajes
    nombres = {m["code"]: m["name"] for m in catalogo}

    salida = []
    for m in catalogo:
        code = m["code"]
        activo = True if activos is None else (code in activos)
        requiere = [
            {"code": r, "name": nombres.get(r, r), "motivo": motivo,
             "activo": True if activos is None else (r in activos)}
            for r, motivo in deps.get(code, [])
        ]
        usado_por = [
            {"code": d, "name": nombres.get(d, d), "motivo": motivo,
             "activo": True if activos is None else (d in activos)}
            for d, motivo in dependientes(code)
        ]
        salida.append({
            "id": m["id"],
            "code": code,
            "name": m["name"],
            "section": m.get("section") or "Otros",
            "activo": activo,
            "nucleo": code in MODULOS_NUCLEO,
            "requiere": requiere,
            "usado_por": usado_por,
        })
    return salida


class ModuloError(Exception):
    """Un cambio que no se puede hacer, con una explicación para el usuario."""

    def __init__(self, mensaje, bloqueantes=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.bloqueantes = bloqueantes or []


def cambiar(empresa_id: int, code: str, activar: bool, usuario: str = ""):
    """
    Enciende o apaga un módulo para una empresa, validando dependencias.

    Al APAGAR: se niega si hay módulos encendidos que lo necesitan, y
    dice cuáles son. Es la regla que evita dejar Admisiones rota a las
    siete de la mañana porque alguien apagó Citas.

    Al ENCENDER: se niega si le falta algo que necesita, y dice qué.
    """
    catalogo = {m["code"]: m for m in _catalogo()}
    if code not in catalogo:
        raise ModuloError(f"El módulo '{code}' no existe.")

    if not activar and code in MODULOS_NUCLEO:
        raise ModuloError(
            f"{catalogo[code]['name']} no se puede desactivar: sin él la empresa "
            "se queda sin acceso a la administración del sistema."
        )

    activos = contratados(empresa_id)
    activos = set(catalogo.keys()) if activos is None else set(activos)

    if not activar:
        bloqueantes = [
            {"code": d, "name": catalogo.get(d, {}).get("name", d), "motivo": motivo}
            for d, motivo in dependientes(code) if d in activos
        ]
        if bloqueantes:
            raise ModuloError(
                f"No se puede apagar {catalogo[code]['name']}: estos módulos "
                "dejarían de funcionar.", bloqueantes)
    else:
        faltantes = [
            {"code": r, "name": catalogo.get(r, {}).get("name", r), "motivo": motivo}
            for r, motivo in dependencias().get(code, []) if r not in activos
        ]
        if faltantes:
            raise ModuloError(
                f"{catalogo[code]['name']} necesita otros módulos que la empresa "
                "no tiene activos.", faltantes)

    _sb().table("empresas_modulos").upsert({
        "empresa_id": empresa_id,
        "modulo_id": catalogo[code]["id"],
        "activo": activar,
        "activado_por": usuario or "sistema",
    }, on_conflict="empresa_id,modulo_id").execute()

    # tras escribir, lo guardado queda viejo: el request en curso y la
    # caché compartida entre peticiones
    invalidar("modulos_service")
    if hasattr(g, "_modulos_empresa"):
        del g._modulos_empresa
    if hasattr(g, "_menu_modulos"):
        del g._menu_modulos

    return True


# =========================
# MENÚ
# =========================



def _icono_de(icono):
    """
    La columna `modulos.icon` guarda el nombre de Font Awesome con su
    prefijo ("fa-book"), pero alguna fila se cargó sin él ("book") y el
    menú terminaba pintando <i class="fa-solid book">, que no dibuja nada.
    """
    icono = (icono or "").strip()
    if not icono:
        return "fa-circle"
    return icono if icono.startswith("fa-") else f"fa-{icono}"


def _url_de(endpoint):
    """
    La columna `modulos.endpoint` guarda una URL ("/hc/pacientes"), pero
    alguna fila se cargó con el nombre interno de Flask ("contabilidad.index").
    Con el menú escrito a mano eso daba igual; leyéndolo de la tabla, pintaba
    un enlace relativo que no lleva a ninguna parte.

    Se aceptan las dos formas y se descarta la fila que no resuelva, en vez
    de dejar un enlace roto en el menú.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return None
    if endpoint.startswith("/"):
        return endpoint
    try:
        from flask import url_for
        return url_for(endpoint)
    except Exception as e:
        print(f"[MODULOS] endpoint '{endpoint}' no resuelve, se omite del menú: {e}")
        return None


def menu_visible(puede_ver) -> list:
    """
    Items del menú lateral: los módulos contratados por la empresa que
    además el rol puede ver, agrupados por sección y en el orden que
    define la tabla `modulos`.

    `puede_ver` se recibe como parámetro (y no se importa) para no
    crear un ciclo con permisos_service, que a su vez usa este módulo.
    """
    cache = getattr(g, "_menu_modulos", None)
    if cache is not None:
        return cache

    global _CATALOGO_MENU
    try:
        filas = _leer_catalogo_menu()
        if filas:
            _CATALOGO_MENU = filas
    except Exception as e:
        # Un corte momentáneo con Supabase no puede dejar al usuario sin
        # menú: se reusa el último catálogo bueno que vio este proceso.
        # El filtro por contratación y permisos se aplica igual, así que
        # el respaldo no muestra de más.
        print(f"[MODULOS] no se pudo leer el catálogo del menú: {e}")
        filas = _CATALOGO_MENU or []

    # OJO: la clave se llama "enlaces" y no "items" porque en Jinja
    # `seccion.items` resuelve al método items() del diccionario.
    secciones = []
    indice = {}
    for m in filas:
        code = m.get("code")
        if not tiene(code) or not puede_ver(code):
            continue
        seccion = m.get("section") or "Otros"
        if seccion not in indice:
            indice[seccion] = {"nombre": seccion, "enlaces": []}
            secciones.append(indice[seccion])
        destino = _url_de(m.get("endpoint"))
        if not destino:
            continue                    # fila mal configurada: no se pinta
        indice[seccion]["enlaces"].append({
            "code": code,
            "name": m.get("name") or code,
            "endpoint": destino,
            "icon": _icono_de(m.get("icon")),
        })
        for sub in SUBITEMS.get(code, []):
            indice[seccion]["enlaces"].append({**sub, "code": code})

    secciones = [s for s in secciones if s["enlaces"]]
    g._menu_modulos = secciones
    return secciones
