from services.supabase_service import get_supabase_public

TABLE      = "hc_manuales_tarifarios"
TABLE_PROC = "hc_mt_procedimientos"
TABLE_ITEM = "hc_mt_items"


def _sb():
    return get_supabase_public()


# ── MANUALES ───────────────────────────────────────────────────────

def listar():
    res = (
        _sb()
        .table(TABLE)
        .select("*, base:manual_base_id(id,nombre)")
        .order("nombre")
        .execute()
    )
    data = res.data or []
    for m in data:
        base = m.pop("base", None)
        m["manual_base_nombre"] = base["nombre"] if base else None
    return data


def listar_activos():
    res = (
        _sb()
        .table(TABLE)
        .select("id, nombre, codigo")
        .eq("estado", "ACTIVO")
        .order("nombre")
        .execute()
    )
    return res.data or []


def obtener(manual_id):
    res = (
        _sb()
        .table(TABLE)
        .select("*, base:manual_base_id(id,nombre)")
        .eq("id", manual_id)
        .single()
        .execute()
    )
    data = res.data
    if data:
        base = data.pop("base", None)
        data["manual_base_nombre"] = base["nombre"] if base else None
    return data


def crear(data: dict):
    res = _sb().table(TABLE).insert(data).execute()
    return res.data


def actualizar(manual_id, data: dict):
    res = _sb().table(TABLE).update(data).eq("id", manual_id).execute()
    return res.data


def cambiar_estado(manual_id, nuevo_estado: str):
    _sb().table(TABLE).update({"estado": nuevo_estado}).eq("id", manual_id).execute()


def existe_codigo(codigo: str, exclude_id=None):
    q = _sb().table(TABLE).select("id").eq("codigo", codigo.strip().upper())
    if exclude_id:
        q = q.neq("id", exclude_id)
    res = q.execute()
    return bool(res.data)


# ── HERENCIA DE PROCEDIMIENTOS ─────────────────────────────────────

def heredar_procedimientos_de_base(manual_id: int, manual_base_id: int, pct_base: float):
    """
    Copia los procedimientos del manual base al manual actual
    aplicando el porcentaje indicado sobre los valores financieros.

    Ejemplos:
      pct_base = 100  → misma tarifa (factor 1.0, sin cambio)
      pct_base = 110  → +10% sobre tarifa base (factor 1.1)
      pct_base =  90  → -10% sobre tarifa base (factor 0.9)

    Regla de duplicados (por cod_proc):
      - Si el manual actual YA tiene un procedimiento con ese cod_proc
        → se respeta el propio, NO se sobreescribe.
      - Si NO lo tiene → se inserta desde el base con valores ajustados.

    Retorna el número de procedimientos insertados.
    """
    if not manual_base_id or pct_base is None:
        return 0

    factor = float(pct_base) / 100.0

    # 1. Traer todos los procedimientos del manual base
    res_base = (
        _sb()
        .table(TABLE_PROC)
        .select("*")
        .eq("manual_id", manual_base_id)
        .execute()
    )
    procs_base = res_base.data or []

    if not procs_base:
        return 0

    # 2. Traer cod_proc ya existentes en el manual actual
    res_propios = (
        _sb()
        .table(TABLE_PROC)
        .select("cod_proc")
        .eq("manual_id", manual_id)
        .execute()
    )
    codigos_propios = {
        r["cod_proc"]
        for r in (res_propios.data or [])
        if r.get("cod_proc")
    }

    # 3. Construir lista a insertar (solo los que no existen)
    def _ajustar(v):
        try:
            return round(float(v or 0) * factor, 2)
        except (TypeError, ValueError):
            return 0.0

    a_insertar = []
    for p in procs_base:
        cod = (p.get("cod_proc") or "").strip()
        if cod in codigos_propios:
            continue  # el propio gana

        a_insertar.append({
            "manual_id":             manual_id,
            "cod_proc":              cod,
            "nombre_procedimiento":  p.get("nombre_procedimiento"),
            "cod_cups":              p.get("cod_cups"),
            "cod_factura":           p.get("cod_factura"),
            "grupo":                 p.get("grupo"),
            "via_ingreso":           p.get("via_ingreso"),
            "ambito_atencion":       p.get("ambito_atencion"),
            "finalidad":             p.get("finalidad"),
            "valor_paquete":         _ajustar(p.get("valor_paquete")),
            "valor_procedimiento":   _ajustar(p.get("valor_procedimiento")),
            "valor_suministro":      _ajustar(p.get("valor_suministro")),
        })

    if not a_insertar:
        return 0

    # 4. Insertar en lotes de 500
    LOTE  = 500
    total = 0
    for i in range(0, len(a_insertar), LOTE):
        _sb().table(TABLE_PROC).insert(a_insertar[i:i + LOTE]).execute()
        total += len(a_insertar[i:i + LOTE])

    return total


# ── PROCEDIMIENTOS ─────────────────────────────────────────────────

def listar_procedimientos(manual_id):
    res = (
        _sb()
        .table(TABLE_PROC)
        .select("*, hc_cups(codigo, descripcion)")
        .eq("manual_id", manual_id)
        .order("cod_proc")
        .execute()
    )
    data = res.data or []
    for p in data:
        cups = p.pop("hc_cups", None)
        p["cups_codigo"]      = cups["codigo"]      if cups else None
        p["cups_descripcion"] = cups["descripcion"] if cups else None
    return data


def agregar_procedimiento(data: dict):
    res = _sb().table(TABLE_PROC).insert(data).execute()
    return res.data


def actualizar_procedimiento(proc_id, data: dict):
    res = _sb().table(TABLE_PROC).update(data).eq("id", proc_id).execute()
    return res.data


def eliminar_procedimiento(proc_id):
    _sb().table(TABLE_PROC).delete().eq("id", proc_id).execute()


def importar_procedimientos(manual_id, registros: list):
    """Inserta en lote. Ignora duplicados por cod_proc."""
    if not registros:
        return 0

    def _safe(v):
        return str(v).strip() if v is not None else ""

    payload = []
    for r in registros:
        payload.append({
            "manual_id":             manual_id,
            "cod_proc":              _safe(r.get("cod_proc")),
            "nombre_procedimiento":  _safe(r.get("nombre_procedimiento")),
            "valor_paquete":         _num(r.get("valor_paquete")),
            "valor_procedimiento":   _num(r.get("valor_procedimiento")),
            "valor_suministro":      _num(r.get("valor_suministro")),
            "cod_factura":           _safe(r.get("cod_factura")) or None,
            "cod_cups":              _safe(r.get("cod_cups")) or None,
            "grupo":                 _safe(r.get("grupo")) or None,
            "via_ingreso":           _enum(r.get("via_ingreso"),
                                          ["AMBULATORIO", "HOSPITALARIO", "URGENCIAS"]),
            "ambito_atencion":       _enum(r.get("ambito_atencion"),
                                          ["CONSULTA_EXTERNA", "HOSPITALIZACION",
                                           "URGENCIAS", "CIRUGIA_AMBULATORIA"]),
            "finalidad":             _enum(r.get("finalidad"),
                                          ["DIAGNOSTICO", "TERAPEUTICO",
                                           "PROTECCION_ESPECIFICA", "REHABILITACION",
                                           "DETECCION_ALTERACION"]),
        })

    LOTE  = 500
    total = 0
    for i in range(0, len(payload), LOTE):
        _sb().table(TABLE_PROC).insert(payload[i:i + LOTE]).execute()
        total += len(payload[i:i + LOTE])
    return total


# ── ÍTEMS ──────────────────────────────────────────────────────────

def listar_items(manual_id):
    res = (
        _sb()
        .table(TABLE_ITEM)
        .select("*, hc_medicamentos(nombre, codigo)")
        .eq("manual_id", manual_id)
        .order("cod_item")
        .execute()
    )
    data = res.data or []
    for i in data:
        med = i.pop("hc_medicamentos", None)
        i["med_nombre"] = med["nombre"] if med else None
        i["med_codigo"] = med["codigo"] if med else None
    return data


def agregar_item(data: dict):
    res = _sb().table(TABLE_ITEM).insert(data).execute()
    return res.data


def actualizar_item(item_id, data: dict):
    res = _sb().table(TABLE_ITEM).update(data).eq("id", item_id).execute()
    return res.data


def eliminar_item(item_id):
    _sb().table(TABLE_ITEM).delete().eq("id", item_id).execute()


def importar_items(manual_id, registros: list):
    if not registros:
        return 0

    def _safe(v):
        return str(v).strip() if v is not None else ""

    payload = []
    for r in registros:
        payload.append({
            "manual_id":      manual_id,
            "cod_item":       _safe(r.get("cod_item")),
            "nombre":         _safe(r.get("nombre")),
            "valor_unitario": _num(r.get("valor_unitario")),
        })

    LOTE  = 500
    total = 0
    for i in range(0, len(payload), LOTE):
        _sb().table(TABLE_ITEM).insert(payload[i:i + LOTE]).execute()
        total += len(payload[i:i + LOTE])
    return total


# ── HELPERS ────────────────────────────────────────────────────────

def _num(v):
    try:
        return float(str(v).replace(",", ".").strip()) if v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _enum(v, allowed):
    if not v:
        return None
    val = str(v).strip().upper()
    return val if val in allowed else None