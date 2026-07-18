# ============================================================================
# VITACORE HMS — Servicio de Inventario (Fase 1)
# Reglas de negocio. Toda entrada/salida de stock del sistema pasa por aquí:
# dispensación (Fase 3), traslados y compras (Fase 2) llamarán a este servicio,
# NUNCA al repositorio directo. Un solo punto de verdad = kardex confiable.
# ============================================================================
from datetime import date

from repositories import inventario_repository as repo


class InventarioError(Exception):
    """Error de negocio legible para mostrar al usuario."""


# ------------------------------- PRODUCTOS ---------------------------------

TIPOS_PRODUCTO = ("MEDICAMENTO", "DISPOSITIVO", "INSUMO")

FORMAS_FARMACEUTICAS = (
    "TABLETA", "CÁPSULA", "JARABE", "SUSPENSIÓN", "SOLUCIÓN ORAL",
    "SOLUCIÓN INYECTABLE", "POLVO PARA RECONSTITUIR", "CREMA", "UNGÜENTO",
    "GEL", "GOTAS", "AEROSOL / INHALADOR", "SUPOSITORIO", "ÓVULO", "PARCHE", "OTRA",
)

VIAS_ADMINISTRACION = (
    "ORAL", "INTRAVENOSA", "INTRAMUSCULAR", "SUBCUTÁNEA", "TÓPICA",
    "OFTÁLMICA", "ÓTICA", "NASAL", "INHALATORIA", "RECTAL", "VAGINAL", "SUBLINGUAL", "OTRA",
)

UNIDADES_MEDIDA = ("UNIDAD", "TABLETA", "CÁPSULA", "AMPOLLA", "VIAL",
                   "FRASCO", "TUBO", "SOBRE", "CAJA", "PAR", "ROLLO", "ML", "G")


def guardar_producto(empresa_id: str, usuario_id: str, form: dict, producto_id: str | None = None):
    """Valida y crea/actualiza un producto del maestro."""
    tipo = form.get("tipo", "").strip()
    nombre = form.get("nombre", "").strip()

    if tipo not in TIPOS_PRODUCTO:
        raise InventarioError("Debe seleccionar un tipo de producto válido.")
    if not nombre:
        raise InventarioError("El nombre del producto es obligatorio.")

    es_medicamento = tipo == "MEDICAMENTO"
    if es_medicamento and not form.get("principio_activo_id"):
        raise InventarioError("Todo medicamento debe tener principio activo. "
                              "Créalo primero en 'Principios activos' si no existe.")
    if es_medicamento and not form.get("registro_invima", "").strip():
        raise InventarioError("El registro INVIMA es obligatorio para medicamentos.")

    es_control = form.get("es_control_especial") == "on"
    if es_control and not es_medicamento:
        raise InventarioError("Solo un medicamento puede marcarse como control especial.")

    requiere_frio = form.get("requiere_cadena_frio") == "on"
    t_min = _num(form.get("temperatura_min"))
    t_max = _num(form.get("temperatura_max"))
    if requiere_frio and (t_min is None or t_max is None):
        raise InventarioError("Si requiere cadena de frío debe indicar temperatura mínima y máxima.")
    if t_min is not None and t_max is not None and t_min >= t_max:
        raise InventarioError("La temperatura mínima debe ser menor que la máxima.")

    stock_min = _num(form.get("stock_minimo")) or 0
    stock_max = _num(form.get("stock_maximo"))
    if stock_max is not None and stock_max < stock_min:
        raise InventarioError("El stock máximo no puede ser menor que el mínimo.")

    datos = {
        "empresa_id": empresa_id,
        "tipo": tipo,
        "nombre": nombre.upper(),
        "descripcion": form.get("descripcion", "").strip() or None,
        "principio_activo_id": form.get("principio_activo_id") or None,
        "concentracion": form.get("concentracion", "").strip() or None,
        "forma_farmaceutica": form.get("forma_farmaceutica") or None,
        "via_administracion": form.get("via_administracion") or None,
        "cum": form.get("cum", "").strip() or None,
        "ium": form.get("ium", "").strip() or None,
        "registro_invima": form.get("registro_invima", "").strip() or None,
        "laboratorio": form.get("laboratorio", "").strip().upper() or None,
        "es_control_especial": es_control,
        "tipo_control": form.get("tipo_control") if es_control else None,
        "clasificacion_riesgo": form.get("clasificacion_riesgo") or None if tipo == "DISPOSITIVO" else None,
        "unidad_medida": form.get("unidad_medida") or "UNIDAD",
        "requiere_cadena_frio": requiere_frio,
        "temperatura_min": t_min if requiere_frio else None,
        "temperatura_max": t_max if requiere_frio else None,
        "requiere_lote": form.get("requiere_lote", "on") == "on",
        "stock_minimo": stock_min,
        "stock_maximo": stock_max,
        "codigo_cups_cargo": form.get("codigo_cups_cargo", "").strip() or None,
        "hc_medicamento_id": form.get("hc_medicamento_id") or None,
        "estado": form.get("estado", "ACTIVO"),
    }

    if producto_id:
        return repo.actualizar_producto(producto_id, datos)

    datos["codigo_interno"] = repo.siguiente_codigo_interno(empresa_id, tipo)
    datos["created_by"] = usuario_id
    return repo.crear_producto(datos)


# ----------------------------- ENTRADAS / SALIDAS ---------------------------

TIPOS_ENTRADA_MANUAL = ("ENTRADA_INICIAL", "ENTRADA_AJUSTE", "ENTRADA_DEVOLUCION")
TIPOS_SALIDA_MANUAL = ("SALIDA_AJUSTE", "SALIDA_VENCIMIENTO", "SALIDA_AVERIA", "SALIDA_CONSUMO")


def registrar_entrada_manual(empresa_id: str, usuario_id: str, form: dict) -> dict:
    tipo = form.get("tipo", "ENTRADA_INICIAL")
    if tipo not in TIPOS_ENTRADA_MANUAL:
        raise InventarioError("Tipo de entrada no permitido desde este formulario.")

    producto = repo.obtener_producto(form.get("producto_id", ""))
    if not producto:
        raise InventarioError("Debe seleccionar un producto del catálogo.")

    numero_lote = form.get("numero_lote", "").strip().upper()
    fecha_venc = form.get("fecha_vencimiento") or None
    if producto["requiere_lote"]:
        if not numero_lote:
            raise InventarioError("Este producto exige número de lote.")
        if not fecha_venc:
            raise InventarioError("Este producto exige fecha de vencimiento.")

    cantidad = _num(form.get("cantidad"))
    costo = _num(form.get("costo_unitario"))
    if not cantidad or cantidad <= 0:
        raise InventarioError("La cantidad debe ser mayor a cero.")
    if costo is None or costo < 0:
        raise InventarioError("El costo unitario es obligatorio (puede ser 0 para donaciones).")

    try:
        return repo.registrar_entrada(
            p_empresa_id=empresa_id,
            p_bodega_id=form["bodega_id"],
            p_producto_id=producto["id"],
            p_numero_lote=numero_lote or None,
            p_fecha_vencimiento=fecha_venc,
            p_cantidad=cantidad,
            p_costo_unitario=costo,
            p_tipo=tipo,
            p_usuario_id=usuario_id,
            p_observaciones=form.get("observaciones", "").strip() or None,
        )
    except Exception as e:  # errores raise exception de la función SQL
        raise InventarioError(_mensaje_bd(e)) from e


def registrar_salida_manual(empresa_id: str, usuario_id: str, form: dict) -> dict:
    tipo = form.get("tipo", "SALIDA_AJUSTE")
    if tipo not in TIPOS_SALIDA_MANUAL:
        raise InventarioError("Tipo de salida no permitido desde este formulario.")

    cantidad = _num(form.get("cantidad"))
    if not cantidad or cantidad <= 0:
        raise InventarioError("La cantidad debe ser mayor a cero.")

    observaciones = form.get("observaciones", "").strip()
    if tipo in ("SALIDA_AJUSTE", "SALIDA_AVERIA") and not observaciones:
        raise InventarioError("Los ajustes y averías exigen una justificación en observaciones.")

    try:
        return repo.registrar_salida(
            p_empresa_id=empresa_id,
            p_bodega_id=form["bodega_id"],
            p_producto_id=form["producto_id"],
            p_cantidad=cantidad,
            p_tipo=tipo,
            p_lote_id=form.get("lote_id") or None,
            p_usuario_id=usuario_id,
            p_observaciones=observaciones or None,
            p_permitir_vencidos=tipo == "SALIDA_VENCIMIENTO",
        )
    except Exception as e:
        raise InventarioError(_mensaje_bd(e)) from e


# --------------------------------- BODEGAS ----------------------------------

TIPOS_BODEGA = ("PRINCIPAL", "FARMACIA", "SATELITE", "CARRO_PARO")


def guardar_bodega(empresa_id: str, usuario_id: str, form: dict, bodega_id: str | None = None):
    nombre = form.get("nombre", "").strip()
    tipo = form.get("tipo", "")
    if not nombre:
        raise InventarioError("El nombre de la bodega es obligatorio.")
    if tipo not in TIPOS_BODEGA:
        raise InventarioError("Debe seleccionar un tipo de bodega válido.")

    datos = {
        "empresa_id": empresa_id,
        "nombre": nombre.upper(),
        "tipo": tipo,
        "ubicacion": form.get("ubicacion", "").strip() or None,
        "permite_dispensacion": form.get("permite_dispensacion") == "on",
        "estado": form.get("estado", "ACTIVA"),
    }
    if bodega_id:
        return repo.actualizar_bodega(bodega_id, datos)
    datos["created_by"] = usuario_id
    return repo.crear_bodega(datos)


# --------------------------------- HELPERS ----------------------------------

def _num(valor):
    try:
        return float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _mensaje_bd(e: Exception) -> str:
    """Extrae el mensaje legible de un error de la función de PostgreSQL."""
    texto = str(e)
    if "Stock insuficiente" in texto:
        inicio = texto.find("Stock insuficiente")
        return texto[inicio:].split('"')[0].split("'")[0].strip()
    if "lote ya vencido" in texto:
        return "No se puede ingresar un lote con fecha de vencimiento pasada."
    return "No fue posible registrar el movimiento. Verifica los datos e intenta de nuevo."