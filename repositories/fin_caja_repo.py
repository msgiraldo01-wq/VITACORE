"""
Repositorio del módulo de caja — Vitacore
Tablas: fin_cajas, fin_caja_movimientos, fin_caja_conteos,
        fin_caja_conteo_historial
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


# =============================================================
# CAJA — APERTURA / CONSULTA / CIERRE
# =============================================================

def obtener_caja_abierta(usuario_id: int):
    """Retorna la caja abierta del usuario o None."""
    res = (
        _sb()
        .table("fin_cajas")
        .select("*, hc_sedes(nombre)")
        .eq("usuario_id", usuario_id)
        .eq("estado", "ABIERTA")
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def abrir_caja(data: dict):
    """
    Abre una nueva caja.
    data: { empresa_id, sede_id, usuario_id, usuario_nombre, valor_base }
    """
    # Obtener siguiente nro_cuadre global
    nro_res = _sb().rpc("fin_siguiente_nro_cuadre", {"p_sede_id": data.get("sede_id", 1)}).execute()
    nro_cuadre = nro_res.data if isinstance(nro_res.data, int) else 1

    caja_data = {
        "empresa_id": data.get("empresa_id", 1),
        "sede_id": data["sede_id"],
        "usuario_id": data["usuario_id"],
        "usuario_nombre": data["usuario_nombre"],
        "nro_cuadre": nro_cuadre,
        "valor_base": float(data.get("valor_base", 0)),
        "estado": "ABIERTA",
    }

    res = _sb().table("fin_cajas").insert(caja_data).execute()
    caja = res.data[0] if res.data else None

    # Crear registro de conteo vacío
    if caja:
        _sb().table("fin_caja_conteos").insert({"caja_id": caja["id"]}).execute()

    return caja


def obtener_caja(caja_id: int):
    """Obtiene una caja por ID con datos de sede."""
    res = (
        _sb()
        .table("fin_cajas")
        .select("*, hc_sedes(nombre)")
        .eq("id", caja_id)
        .single()
        .execute()
    )
    return res.data


def cerrar_caja(caja_id: int, data: dict):
    """
    Cierra una caja con los datos del conteo y notas.
    Calcula total_en_caja, total_sistema y diferencia.
    """
    # Calcular total sistema (suma de movimientos)
    movimientos = listar_movimientos(caja_id)
    total_sistema = sum(float(m.get("valor", 0)) for m in movimientos)

    # Calcular totales del conteo
    denominaciones = {
        100000: int(data.get("den_100000_cant", 0)),
        50000: int(data.get("den_50000_cant", 0)),
        20000: int(data.get("den_20000_cant", 0)),
        10000: int(data.get("den_10000_cant", 0)),
        5000: int(data.get("den_5000_cant", 0)),
        2000: int(data.get("den_2000_cant", 0)),
        1000: int(data.get("den_1000_cant", 0)),
        500: int(data.get("den_500_cant", 0)),
        200: int(data.get("den_200_cant", 0)),
        100: int(data.get("den_100_cant", 0)),
        50: int(data.get("den_50_cant", 0)),
    }
    total_efectivo = sum(den * cant for den, cant in denominaciones.items())

    # Documentos
    doc_fields = [
        "cheques", "datafono", "transferencias", "consignaciones",
        "facturas", "vales", "retenciones", "otros"
    ]
    total_documentos = 0
    doc_update = {}
    for field in doc_fields:
        cant = int(data.get(f"doc_{field}_cant", 0))
        valor = float(data.get(f"doc_{field}_valor", 0))
        doc_update[f"doc_{field}_cant"] = cant
        doc_update[f"doc_{field}_valor"] = valor
        total_documentos += valor

    total_en_caja = total_efectivo + total_documentos
    diferencia = total_en_caja - total_sistema

    # Actualizar caja
    update_data = {
        "estado": "CERRADA",
        "fecha_cierre": "now()",
        "hora_cierre": "now()",
        "total_efectivo": total_efectivo,
        "total_documentos": total_documentos,
        "total_en_caja": total_en_caja,
        "total_sistema": total_sistema,
        "diferencia": diferencia,
        "nota_antes_cierre": data.get("nota_antes_cierre", ""),
        "nota_despues_cierre": data.get("nota_despues_cierre", ""),
        # Denominaciones
        "den_100000_cant": denominaciones[100000],
        "den_50000_cant": denominaciones[50000],
        "den_20000_cant": denominaciones[20000],
        "den_10000_cant": denominaciones[10000],
        "den_5000_cant": denominaciones[5000],
        "den_2000_cant": denominaciones[2000],
        "den_1000_cant": denominaciones[1000],
        "den_500_cant": denominaciones[500],
        "den_200_cant": denominaciones[200],
        "den_100_cant": denominaciones[100],
        "den_50_cant": denominaciones[50],
        "updated_at": "now()",
    }
    update_data.update(doc_update)

    res = (
        _sb()
        .table("fin_cajas")
        .update(update_data)
        .eq("id", caja_id)
        .execute()
    )
    return res.data[0] if res.data else None


def listar_cajas(empresa_id: int = 1, sede_id: int = None, usuario_id=None, limit: int = 50):
    """Lista las últimas cajas, opcionalmente filtradas por usuario."""
    q = (
        _sb()
        .table("fin_cajas")
        .select("*, hc_sedes(nombre)")
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if sede_id:
        q = q.eq("sede_id", sede_id)
    if usuario_id:
        q = q.eq("usuario_id", str(usuario_id))
    res = q.execute()
    return res.data or []


# =============================================================
# MOVIMIENTOS
# =============================================================

def registrar_movimiento(data: dict):
    """
    Registra un movimiento de ingreso en la caja.
    data: { caja_id, factura_id, tipo, medio_pago, valor,
            descripcion, paciente_id, paciente_nombre, numero_factura }
    """
    res = _sb().table("fin_caja_movimientos").insert(data).execute()
    return res.data[0] if res.data else None


def listar_movimientos(caja_id: int):
    """Lista todos los movimientos de una caja."""
    res = (
        _sb()
        .table("fin_caja_movimientos")
        .select("*")
        .eq("caja_id", caja_id)
        .order("created_at", desc=False)
        .execute()
    )
    return res.data or []


def resumen_movimientos(caja_id: int):
    """Resumen agrupado por tipo y medio de pago."""
    movimientos = listar_movimientos(caja_id)

    por_tipo = {}
    por_medio = {}
    total = 0

    for m in movimientos:
        valor = float(m.get("valor", 0))
        tipo = m.get("tipo", "OTRO")
        medio = m.get("medio_pago", "OTRO")

        por_tipo[tipo] = por_tipo.get(tipo, 0) + valor
        por_medio[medio] = por_medio.get(medio, 0) + valor
        total += valor

    return {
        "total": total,
        "cantidad": len(movimientos),
        "por_tipo": por_tipo,
        "por_medio": por_medio,
    }


# =============================================================
# CONTEO EN TIEMPO REAL
# =============================================================

def obtener_conteo(caja_id: int):
    """Obtiene el conteo actual de la caja."""
    res = (
        _sb()
        .table("fin_caja_conteos")
        .select("*")
        .eq("caja_id", caja_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def actualizar_conteo(caja_id: int, campo: str, valor_nuevo, usuario_id: int, usuario_nombre: str):
    """
    Actualiza un campo del conteo y registra en historial.
    campo: ej 'den_100000', 'doc_datafono_cant', 'doc_datafono_valor'
    """
    # Obtener valor anterior
    conteo = obtener_conteo(caja_id)
    if not conteo:
        return None

    valor_anterior = conteo.get(campo, 0)

    # Solo registrar si cambió
    if float(valor_anterior or 0) == float(valor_nuevo or 0):
        return conteo

    # Actualizar conteo
    _sb().table("fin_caja_conteos").update({
        campo: valor_nuevo,
        "updated_at": "now()",
    }).eq("caja_id", caja_id).execute()

    # Registrar en historial
    _sb().table("fin_caja_conteo_historial").insert({
        "caja_id": caja_id,
        "campo": campo,
        "valor_anterior": float(valor_anterior or 0),
        "valor_nuevo": float(valor_nuevo or 0),
        "usuario_id": usuario_id,
        "usuario_nombre": usuario_nombre,
    }).execute()

    return obtener_conteo(caja_id)


def guardar_conteo_completo(caja_id: int, data: dict, usuario_id, usuario_nombre: str):
    """
    Guarda todo el conteo de golpe y registra cambios en historial.
    Optimizado: máximo 3 queries (leer, actualizar, insertar historial).
    """
    conteo_actual = obtener_conteo(caja_id)
    if not conteo_actual:
        # Si no existe, crear el registro
        _sb().table("fin_caja_conteos").insert({"caja_id": caja_id}).execute()
        conteo_actual = obtener_conteo(caja_id)
        if not conteo_actual:
            return None

    cambios = []
    update = {}

    for campo, valor_nuevo in data.items():
        if campo in ("id", "caja_id", "updated_at"):
            continue
        valor_anterior = conteo_actual.get(campo, 0)
        update[campo] = valor_nuevo

        if float(valor_anterior or 0) != float(valor_nuevo or 0):
            cambios.append({
                "caja_id": caja_id,
                "campo": campo,
                "valor_anterior": float(valor_anterior or 0),
                "valor_nuevo": float(valor_nuevo or 0),
                "usuario_id": str(usuario_id),
                "usuario_nombre": usuario_nombre,
            })

    # Solo hacer queries si hay algo que actualizar
    if update:
        _sb().table("fin_caja_conteos").update(update).eq("caja_id", caja_id).execute()

    if cambios:
        _sb().table("fin_caja_conteo_historial").insert(cambios).execute()

    return {"ok": True}


def listar_conteo_historial(caja_id: int):
    """Lista el historial de cambios del conteo."""
    res = (
        _sb()
        .table("fin_caja_conteo_historial")
        .select("*")
        .eq("caja_id", caja_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    return res.data or []


# =============================================================
# REGISTRAR MOVIMIENTO DESDE FACTURACIÓN
# (Se llama automáticamente al facturar)
# =============================================================

def registrar_cobro_factura(caja_id: int, factura: dict, medio_pago: str = "EFECTIVO"):
    """
    Registra los cobros de una factura en la caja.
    Genera movimientos separados para copago, cuota moderadora, etc.
    """
    movimientos = []
    numero = factura.get("numero_factura", "")
    factura_id = factura.get("id")
    paciente_id = factura.get("paciente_id")

    # Nombre del paciente
    pac = factura.get("hc_pacientes", {}) or {}
    pac_nombre = " ".join(filter(None, [
        pac.get("primer_nombre"), pac.get("primer_apellido")
    ]))

    # Copago
    copago = float(factura.get("copago", 0) or 0)
    if copago > 0:
        movimientos.append({
            "caja_id": caja_id,
            "factura_id": factura_id,
            "tipo": "COPAGO",
            "medio_pago": medio_pago,
            "valor": copago,
            "descripcion": f"Copago factura {numero}",
            "paciente_id": paciente_id,
            "paciente_nombre": pac_nombre,
            "numero_factura": numero,
        })

    # Cuota moderadora
    cuota_mod = float(factura.get("cuota_moderadora", 0) or 0)
    if cuota_mod > 0:
        movimientos.append({
            "caja_id": caja_id,
            "factura_id": factura_id,
            "tipo": "CUOTA_MODERADORA",
            "medio_pago": medio_pago,
            "valor": cuota_mod,
            "descripcion": f"Cuota moderadora factura {numero}",
            "paciente_id": paciente_id,
            "paciente_nombre": pac_nombre,
            "numero_factura": numero,
        })

    # Cuota recuperación
    cuota_rec = float(factura.get("cuota_recuperacion", 0) or 0)
    if cuota_rec > 0:
        movimientos.append({
            "caja_id": caja_id,
            "factura_id": factura_id,
            "tipo": "CUOTA_RECUPERACION",
            "medio_pago": medio_pago,
            "valor": cuota_rec,
            "descripcion": f"Cuota recuperación factura {numero}",
            "paciente_id": paciente_id,
            "paciente_nombre": pac_nombre,
            "numero_factura": numero,
        })

    # Total de la factura (pago particular = total - copago - cuotas)
    total = float(factura.get("total", 0) or 0)
    total_cuotas = copago + cuota_mod + cuota_rec
    particular = total - total_cuotas

    if particular > 0:
        movimientos.append({
            "caja_id": caja_id,
            "factura_id": factura_id,
            "tipo": "PARTICULAR",
            "medio_pago": medio_pago,
            "valor": particular,
            "descripcion": f"Pago factura {numero}",
            "paciente_id": paciente_id,
            "paciente_nombre": pac_nombre,
            "numero_factura": numero,
        })

    # Insertar movimientos
    if movimientos:
        _sb().table("fin_caja_movimientos").insert(movimientos).execute()

    return movimientos