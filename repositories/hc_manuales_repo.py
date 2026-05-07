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
    """Para el select de manual base."""
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
        """Convierte None o cualquier valor a string limpio."""
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
                                          ["AMBULATORIO","HOSPITALARIO","URGENCIAS"]),
            "ambito_atencion":       _enum(r.get("ambito_atencion"),
                                          ["CONSULTA_EXTERNA","HOSPITALIZACION",
                                           "URGENCIAS","CIRUGIA_AMBULATORIA"]),
            "finalidad":             _enum(r.get("finalidad"),
                                          ["DIAGNOSTICO","TERAPEUTICO",
                                           "PROTECCION_ESPECIFICA","REHABILITACION",
                                           "DETECCION_ALTERACION"]),
        })
    _sb().table(TABLE_PROC).insert(payload).execute()
    return len(payload)


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
    _sb().table(TABLE_ITEM).insert(payload).execute()
    return len(payload)


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