# ============================================================================
# VITACORE HMS — Repositorio de Inventario (Fase 1)
# Única capa que habla con Supabase. Las rutas NUNCA consultan la BD directo.
# Sigue la convención del proyecto (ver repositories de pacientes):
# cliente admin desde services.supabase_service.
# ============================================================================
from services.supabase_service import get_supabase_admin


def _client():
    return get_supabase_admin()


# ============================ PRINCIPIOS ACTIVOS ============================

def listar_principios(empresa_id: str):
    return (_client().table("farm_principios_activos")
            .select("*").eq("empresa_id", empresa_id)
            .order("nombre").execute().data)


def crear_principio(empresa_id: str, nombre: str, codigo_atc: str, usuario_id: str):
    return (_client().table("farm_principios_activos").insert({
        "empresa_id": empresa_id,
        "nombre": nombre.strip().upper(),
        "codigo_atc": (codigo_atc or "").strip().upper() or None,
        "created_by": usuario_id,
    }).execute().data)


def cambiar_estado_principio(principio_id: str, estado: str):
    return (_client().table("farm_principios_activos")
            .update({"estado": estado}).eq("id", principio_id).execute().data)


# ================================ PRODUCTOS =================================

def listar_productos(empresa_id: str, busqueda: str = "", tipo: str = ""):
    q = (_client().table("inv_productos")
         .select("*, farm_principios_activos(nombre)")
         .eq("empresa_id", empresa_id))
    if tipo:
        q = q.eq("tipo", tipo)
    if busqueda:
        q = q.or_(f"nombre.ilike.%{busqueda}%,cum.ilike.%{busqueda}%,codigo_interno.ilike.%{busqueda}%")
    return q.order("nombre").limit(300).execute().data


def obtener_producto(producto_id: str):
    res = (_client().table("inv_productos")
           .select("*").eq("id", producto_id).limit(1).execute().data)
    return res[0] if res else None


def siguiente_codigo_interno(empresa_id: str, tipo: str) -> str:
    """Genera consecutivo simple por tipo: MED-0001, DIS-0001, INS-0001."""
    prefijo = {"MEDICAMENTO": "MED", "DISPOSITIVO": "DIS", "INSUMO": "INS"}[tipo]
    res = (_client().table("inv_productos")
           .select("codigo_interno").eq("empresa_id", empresa_id)
           .like("codigo_interno", f"{prefijo}-%")
           .order("codigo_interno", desc=True).limit(1).execute().data)
    ultimo = int(res[0]["codigo_interno"].split("-")[1]) if res else 0
    return f"{prefijo}-{ultimo + 1:04d}"


def crear_producto(datos: dict):
    return _client().table("inv_productos").insert(datos).execute().data


def actualizar_producto(producto_id: str, datos: dict):
    return (_client().table("inv_productos")
            .update(datos).eq("id", producto_id).execute().data)


def buscar_cum(termino: str):
    """Busca en el catálogo oficial INVIMA para autocompletar el formulario."""
    return (_client().table("farm_cum_catalogo")
            .select("*")
            .or_(f"producto.ilike.%{termino}%,cum.ilike.%{termino}%,principio_activo.ilike.%{termino}%")
            .limit(15).execute().data)


# ================================= BODEGAS ==================================

def listar_bodegas(empresa_id: str, solo_activas: bool = False):
    q = (_client().table("inv_bodegas")
         .select("*").eq("empresa_id", empresa_id))
    if solo_activas:
        q = q.eq("estado", "ACTIVA")
    return q.order("nombre").execute().data


def crear_bodega(datos: dict):
    return _client().table("inv_bodegas").insert(datos).execute().data


def actualizar_bodega(bodega_id: str, datos: dict):
    return (_client().table("inv_bodegas")
            .update(datos).eq("id", bodega_id).execute().data)


# ======================== EXISTENCIAS / KARDEX / RPC ========================

def registrar_entrada(**kwargs):
    """Llama la función fn_inv_registrar_entrada (transacción atómica en BD)."""
    return _client().rpc("fn_inv_registrar_entrada", kwargs).execute().data


def registrar_salida(**kwargs):
    """Llama la función fn_inv_registrar_salida (FEFO, transacción atómica)."""
    return _client().rpc("fn_inv_registrar_salida", kwargs).execute().data


def existencias(empresa_id: str, bodega_id: str = "", producto_id: str = ""):
    q = (_client().table("v_inv_semaforo_vencimientos")
         .select("*").eq("empresa_id", empresa_id))
    if bodega_id:
        q = q.eq("bodega_id", bodega_id)
    if producto_id:
        q = q.eq("producto_id", producto_id)
    return q.order("producto").order("fecha_vencimiento").execute().data


def kardex(empresa_id: str, producto_id: str, bodega_id: str = "", limite: int = 200):
    q = (_client().table("inv_movimientos")
         .select("*, inv_bodegas(nombre), inv_lotes(numero_lote, fecha_vencimiento)")
         .eq("empresa_id", empresa_id).eq("producto_id", producto_id))
    if bodega_id:
        q = q.eq("bodega_id", bodega_id)
    return q.order("fecha", desc=True).limit(limite).execute().data


def ultimos_movimientos(empresa_id: str, limite: int = 10):
    return (_client().table("inv_movimientos")
            .select("*, inv_productos(nombre, concentracion), inv_bodegas(nombre)")
            .eq("empresa_id", empresa_id)
            .order("fecha", desc=True).limit(limite).execute().data)


def dashboard(empresa_id: str):
    return _client().rpc("fn_inv_dashboard", {"p_empresa_id": empresa_id}).execute().data


def movimientos_filtrados(empresa_id, desde="", hasta="", tipo="", bodega_id="", limite=300):
    """Diario general de movimientos con filtros (para la pantalla Movimientos)."""
    q = (_client().table("inv_movimientos")
         .select("*, inv_productos(codigo_interno, nombre, concentracion),"
                 " inv_bodegas(nombre), inv_lotes(numero_lote)")
         .eq("empresa_id", empresa_id))
    if desde:
        q = q.gte("fecha", desde)
    if hasta:
        q = q.lte("fecha", hasta + "T23:59:59")
    if tipo:
        q = q.eq("tipo", tipo)
    if bodega_id:
        q = q.eq("bodega_id", bodega_id)
    return q.order("fecha", desc=True).limit(limite).execute().data


# ============================ TRASLADOS / CONDICIONES ============================

def crear_traslado(datos: dict, items: list):
    t = _client().table("inv_traslados").insert(datos).execute().data[0]
    for it in items:
        it["traslado_id"] = t["id"]
    _client().table("inv_traslado_items").insert(items).execute()
    return t


def listar_traslados(empresa_id):
    return (_client().table("inv_traslados")
            .select("*, origen:bodega_origen_id(nombre), destino:bodega_destino_id(nombre)")
            .eq("empresa_id", empresa_id).order("created_at", desc=True).limit(200).execute().data)


def obtener_traslado(empresa_id, traslado_id):
    t = (_client().table("inv_traslados")
         .select("*, origen:bodega_origen_id(nombre), destino:bodega_destino_id(nombre)")
         .eq("empresa_id", empresa_id).eq("id", traslado_id).limit(1).execute().data)
    if not t:
        return None, []
    items = (_client().table("inv_traslado_items")
             .select("*, inv_productos(codigo_interno, nombre, concentracion)")
             .eq("traslado_id", traslado_id).execute().data)
    return t[0], items


def despachar_traslado(empresa_id, traslado_id, usuario):
    return _client().rpc("fn_inv_despachar_traslado", {
        "p_empresa_id": empresa_id, "p_traslado_id": traslado_id, "p_usuario": usuario}).execute().data


def recibir_traslado(empresa_id, traslado_id, usuario):
    return _client().rpc("fn_inv_recibir_traslado", {
        "p_empresa_id": empresa_id, "p_traslado_id": traslado_id, "p_usuario": usuario}).execute().data


def registrar_condicion(datos: dict):
    return _client().table("inv_registros_condiciones").insert(datos).execute().data


def listar_condiciones(empresa_id, bodega_id="", limite=200):
    q = (_client().table("inv_registros_condiciones")
         .select("*, inv_bodegas(nombre)").eq("empresa_id", empresa_id))
    if bodega_id:
        q = q.eq("bodega_id", bodega_id)
    return q.order("fecha_hora", desc=True).limit(limite).execute().data


# ================================ FASE 2: COMPRAS ================================

def listar_proveedores(empresa_id, solo_activos=False):
    q = _client().table("inv_proveedores").select("*").eq("empresa_id", empresa_id)
    if solo_activos:
        q = q.eq("estado", "ACTIVO")
    return q.order("razon_social").execute().data


def crear_proveedor(datos: dict):
    return _client().table("inv_proveedores").insert(datos).execute().data


def actualizar_proveedor(proveedor_id, datos: dict):
    return (_client().table("inv_proveedores")
            .update(datos).eq("id", proveedor_id).execute().data)


def listar_ordenes(empresa_id):
    return (_client().table("inv_ordenes_compra")
            .select("*, inv_proveedores(razon_social), inv_bodegas(nombre)")
            .eq("empresa_id", empresa_id)
            .order("created_at", desc=True).limit(200).execute().data)


def crear_orden(datos: dict, items: list):
    oc = _client().table("inv_ordenes_compra").insert(datos).execute().data[0]
    for it in items:
        it["orden_id"] = oc["id"]
    _client().table("inv_orden_compra_items").insert(items).execute()
    return oc


def obtener_orden(empresa_id, orden_id):
    oc = (_client().table("inv_ordenes_compra")
          .select("*, inv_proveedores(razon_social, numero_documento), inv_bodegas(nombre)")
          .eq("empresa_id", empresa_id).eq("id", orden_id).limit(1).execute().data)
    if not oc:
        return None, [], []
    items = (_client().table("inv_orden_compra_items")
             .select("*, inv_productos(codigo_interno, nombre, concentracion, requiere_lote)")
             .eq("orden_id", orden_id).execute().data)
    recepciones = (_client().table("inv_recepciones")
                   .select("*").eq("orden_id", orden_id)
                   .order("created_at", desc=True).execute().data)
    return oc[0], items, recepciones


def cambiar_estado_orden(empresa_id, orden_id, estado, usuario=None):
    datos = {"estado": estado}
    if estado == "APROBADA":
        datos["aprobado_por"] = usuario
    return (_client().table("inv_ordenes_compra").update(datos)
            .eq("empresa_id", empresa_id).eq("id", orden_id).execute().data)


def registrar_recepcion(empresa_id, cabecera: dict, items: list):
    return _client().rpc("fn_inv_registrar_recepcion", {
        "p_empresa_id": empresa_id, "p_cabecera": cabecera, "p_items": items,
    }).execute().data


# ============================ FASE 2B: SOLICITUDES ============================

def productos_bajo_minimo(empresa_id):
    return (_client().table("v_inv_bajo_minimo").select("*")
            .eq("empresa_id", empresa_id).order("nombre").execute().data)


def crear_solicitud(datos: dict, items: list):
    s = _client().table("inv_solicitudes_compra").insert(datos).execute().data[0]
    for it in items:
        it["solicitud_id"] = s["id"]
    _client().table("inv_solicitud_items").insert(items).execute()
    return s


def listar_solicitudes(empresa_id):
    return (_client().table("inv_solicitudes_compra")
            .select("*, inv_bodegas(nombre)")
            .eq("empresa_id", empresa_id)
            .order("created_at", desc=True).limit(200).execute().data)


def obtener_solicitud(empresa_id, solicitud_id):
    s = (_client().table("inv_solicitudes_compra")
         .select("*, inv_bodegas(nombre)")
         .eq("empresa_id", empresa_id).eq("id", solicitud_id).limit(1).execute().data)
    if not s:
        return None, []
    items = (_client().table("inv_solicitud_items")
             .select("*, inv_productos(codigo_interno, nombre, concentracion)")
             .eq("solicitud_id", solicitud_id).execute().data)
    return s[0], items


def resolver_solicitud(solicitud_id, datos: dict):
    return (_client().table("inv_solicitudes_compra")
            .update(datos).eq("id", solicitud_id).execute().data)


def ultimo_precio_compra(empresa_id, producto_id):
    """Último costo de ENTRADA_COMPRA; si no hay, el costo promedio; si no, 0."""
    m = (_client().table("inv_movimientos").select("costo_unitario")
         .eq("empresa_id", empresa_id).eq("producto_id", producto_id)
         .eq("tipo", "ENTRADA_COMPRA")
         .order("fecha", desc=True).limit(1).execute().data)
    if m:
        return float(m[0]["costo_unitario"])
    e = (_client().table("inv_existencias").select("costo_promedio")
         .eq("empresa_id", empresa_id).eq("producto_id", producto_id)
         .limit(1).execute().data)
    return float(e[0]["costo_promedio"]) if e else 0.0


# ============================ FASE 3: DISPENSACIÓN ============================

def cola_formulas(empresa_id):
    """Fórmulas médicas (hc_evolucion_medicamentos) que aún no tienen dispensación.

    Trae paciente y médico vía hc_evoluciones. Excluye evoluciones ya dispensadas.
    """
    # Evoluciones que ya tienen dispensación en este módulo
    disp = (_client().table("farm_dispensaciones").select("evolucion_id")
            .eq("empresa_id", empresa_id).execute().data)
    ya = {d["evolucion_id"] for d in disp if d.get("evolucion_id")}
    # Evoluciones de la empresa con sus datos de paciente/médico
    evos = (_client().table("hc_evoluciones")
            .select("id, paciente_id, medico_id, fecha, estado")
            .eq("empresa_id", empresa_id).order("fecha", desc=True)
            .limit(300).execute().data)
    evo_ids = [e["id"] for e in evos if e["id"] not in ya]
    if not evo_ids:
        return []
    meds = (_client().table("hc_evolucion_medicamentos")
            .select("*").in_("evolucion_id", evo_ids).execute().data)
    # Agrupar medicamentos por evolución
    porevo = {}
    for m in meds:
        porevo.setdefault(m["evolucion_id"], []).append(m)
    cola = []
    for e in evos:
        if e["id"] in ya or e["id"] not in porevo:
            continue
        e["medicamentos"] = porevo[e["id"]]
        cola.append(e)
    return cola


def formula_de_evolucion(evolucion_id):
    evo = (_client().table("hc_evoluciones")
           .select("id, paciente_id, medico_id, fecha")
           .eq("id", evolucion_id).limit(1).execute().data)
    meds = (_client().table("hc_evolucion_medicamentos")
            .select("*").eq("evolucion_id", evolucion_id).execute().data)
    return (evo[0] if evo else None), meds


def crear_dispensacion(datos: dict, items: list):
    d = _client().table("farm_dispensaciones").insert(datos).execute().data[0]
    for it in items:
        it["dispensacion_id"] = d["id"]
    _client().table("farm_dispensacion_items").insert(items).execute()
    return d


def listar_dispensaciones(empresa_id):
    return (_client().table("farm_dispensaciones")
            .select("*").eq("empresa_id", empresa_id)
            .order("created_at", desc=True).limit(200).execute().data)


def obtener_dispensacion(empresa_id, disp_id):
    d = (_client().table("farm_dispensaciones").select("*")
         .eq("empresa_id", empresa_id).eq("id", disp_id).limit(1).execute().data)
    if not d:
        return None, []
    items = (_client().table("farm_dispensacion_items")
             .select("*, inv_productos(codigo_interno, nombre, concentracion)")
             .eq("dispensacion_id", disp_id).execute().data)
    return d[0], items


def actualizar_dispensacion(disp_id, datos):
    return (_client().table("farm_dispensaciones")
            .update(datos).eq("id", disp_id).execute().data)


def actualizar_disp_item(item_id, datos):
    return (_client().table("farm_dispensacion_items")
            .update(datos).eq("id", item_id).execute().data)


def dispensar(empresa_id, disp_id, usuario, items):
    return _client().rpc("fn_farm_dispensar", {
        "p_empresa_id": empresa_id, "p_dispensacion_id": disp_id,
        "p_usuario": usuario, "p_items": items}).execute().data


def buscar_paciente_nombre(paciente_id):
    """Nombre del paciente para mostrar (tolera esquemas distintos)."""
    try:
        p = (_client().table("hc_pacientes")
             .select("primer_nombre, primer_apellido, numero_documento")
             .eq("id", paciente_id).limit(1).execute().data)
        if p:
            x = p[0]
            return (f"{x.get('primer_nombre','')} {x.get('primer_apellido','')}".strip()
                    + f" ({x.get('numero_documento','')})")
    except Exception:
        pass
    return f"Paciente #{paciente_id}"