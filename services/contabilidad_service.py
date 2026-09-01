"""
Servicio del núcleo contable — Vitacore
=======================================
Lógica de negocio del módulo financiero-contable. Orquesta el repositorio
y prepara/valida los datos antes de tocar la base. La validación DURA
(partida doble, cuentas, periodo) vive en la función RPC de Postgres; aquí
se hacen validaciones previas de forma amigable para el usuario y se
calculan los saldos de los libros.

Sigue el patrón de services/ del proyecto: funciones sueltas que importan
el repositorio correspondiente.
"""

from repositories import fin_contabilidad_repo as repo


# =============================================================
# COMPROBANTES
# =============================================================

def preparar_y_registrar_comprobante(form: dict, lineas: list, usuario: str):
    """
    Recibe los datos del formulario y las líneas del asiento, hace una
    validación previa amigable y llama al repositorio (RPC atómica).

    form: {
        "tipo_comprobante": "NC",
        "fecha": "2026-01-15",
        "descripcion": "...",
        "empresa_id": 1, "sede_id": 1 (opcional)
    }
    lineas: [
        {"cuenta_id": 5, "tercero_id": 1|None, "centro_costo_id": 1|None,
         "descripcion": "...", "debito": 100000, "credito": 0,
         "base_gravable": 0},
        ...
    ]

    Retorna (ok: bool, resultado: dict|str)
    """
    # --- Validaciones previas (mensajes claros antes de ir a la BD) ---
    if not form.get("tipo_comprobante"):
        return False, "Debe seleccionar el tipo de comprobante."
    if not form.get("fecha"):
        return False, "Debe indicar la fecha del comprobante."
    if not lineas or len(lineas) < 2:
        return False, "El comprobante debe tener al menos 2 líneas."

    total_debito = 0.0
    total_credito = 0.0
    for i, ln in enumerate(lineas, start=1):
        if not ln.get("cuenta_id"):
            return False, f"La línea {i} no tiene cuenta seleccionada."
        deb = float(ln.get("debito", 0) or 0)
        cre = float(ln.get("credito", 0) or 0)
        if deb > 0 and cre > 0:
            return False, f"La línea {i} tiene débito y crédito a la vez."
        if deb == 0 and cre == 0:
            return False, f"La línea {i} no tiene valor (débito o crédito)."
        total_debito += deb
        total_credito += cre

    if round(total_debito, 2) != round(total_credito, 2):
        return False, (
            f"El comprobante está descuadrado: débitos ${total_debito:,.2f} "
            f"≠ créditos ${total_credito:,.2f}."
        )

    # --- Normalizar líneas al formato que espera la RPC ---
    movimientos = []
    for ln in lineas:
        movimientos.append({
            "cuenta_id": int(ln["cuenta_id"]),
            "tercero_id": int(ln["tercero_id"]) if ln.get("tercero_id") else None,
            "centro_costo_id": int(ln["centro_costo_id"]) if ln.get("centro_costo_id") else None,
            "descripcion": ln.get("descripcion", ""),
            "debito": float(ln.get("debito", 0) or 0),
            "credito": float(ln.get("credito", 0) or 0),
            "base_gravable": float(ln.get("base_gravable", 0) or 0),
        })

    # --- Llamar a la RPC atómica ---
    resultado = repo.registrar_comprobante(
        empresa_id=int(form.get("empresa_id", 1)),
        sede_id=int(form["sede_id"]) if form.get("sede_id") else None,
        tipo_comprobante=form["tipo_comprobante"],
        fecha=form["fecha"],
        descripcion=form.get("descripcion", ""),
        movimientos=movimientos,
        usuario=usuario,
        origen="MANUAL",
    )

    if resultado and resultado.get("ok"):
        return True, resultado
    else:
        # La RPC devolvió un error de negocio controlado
        error = (resultado or {}).get("error", "Error desconocido al contabilizar.")
        return False, error


def anular(comprobante_id: int, usuario: str, motivo: str):
    if not motivo or not motivo.strip():
        return False, "Debe indicar el motivo de la anulación."
    resultado = repo.anular_comprobante(comprobante_id, usuario, motivo.strip())
    if resultado and resultado.get("ok"):
        return True, resultado
    return False, (resultado or {}).get("error", "No se pudo anular el comprobante.")


def detalle_comprobante(comprobante_id: int):
    """Encabezado + movimientos aplanados para la vista de detalle."""
    cab = repo.obtener_comprobante(comprobante_id)
    if not cab:
        return None, []
    movs = repo.obtener_movimientos(comprobante_id)

    # Aplanar relaciones embebidas para la plantilla
    for m in movs:
        cuenta = m.pop("fin_puc", None) or {}
        tercero = m.pop("fin_terceros", None) or {}
        cc = m.pop("fin_centros_costo", None) or {}
        m["cuenta_nombre"] = cuenta.get("nombre", "")
        m["tercero_nombre"] = tercero.get("razon_social", "")
        m["tercero_doc"] = tercero.get("numero_documento", "")
        m["centro_costo"] = cc.get("nombre", "")
    return cab, movs


# =============================================================
# LIBROS
# =============================================================

def obtener_libro_diario(empresa_id: int = 1, periodo: str = None):
    """Aplana los datos del diario para la plantilla."""
    filas = repo.libro_diario(empresa_id=empresa_id, periodo=periodo)
    salida = []
    for f in filas:
        comp = f.pop("fin_comprobantes", None) or {}
        cuenta = f.pop("fin_puc", None) or {}
        # El diario solo muestra comprobantes vigentes
        if comp.get("estado") == "ANULADO":
            continue
        salida.append({
            "numero": comp.get("numero", ""),
            "fecha": comp.get("fecha", ""),
            "tipo": comp.get("tipo_comprobante", ""),
            "cuenta_codigo": f.get("cuenta_codigo", ""),
            "cuenta_nombre": cuenta.get("nombre", ""),
            "descripcion": f.get("descripcion", ""),
            "debito": float(f.get("debito", 0) or 0),
            "credito": float(f.get("credito", 0) or 0),
        })
    # Orden por fecha y número
    salida.sort(key=lambda x: (str(x["fecha"]), x["numero"]))
    return salida


def obtener_libro_mayor(cuenta_id: int, empresa_id: int = 1, periodo: str = None):
    """
    Libro mayor de una cuenta con SALDO ACUMULADO calculado según la
    naturaleza de la cuenta (deudora suma débitos, acreedora suma créditos).
    """
    cuenta = repo.obtener_cuenta(cuenta_id)
    if not cuenta:
        return None, [], {}

    filas = repo.libro_mayor(cuenta_id, empresa_id=empresa_id, periodo=periodo)
    naturaleza = cuenta.get("naturaleza", "DEBITO")

    # Ordenar por fecha del comprobante
    def _fecha(f):
        comp = f.get("fin_comprobantes") or {}
        return (str(comp.get("fecha", "")), comp.get("numero", ""))
    filas.sort(key=_fecha)

    movimientos = []
    saldo = 0.0
    tot_deb = 0.0
    tot_cre = 0.0
    for f in filas:
        comp = f.get("fin_comprobantes") or {}
        if comp.get("estado") == "ANULADO":
            continue
        deb = float(f.get("debito", 0) or 0)
        cre = float(f.get("credito", 0) or 0)
        # Saldo según naturaleza
        if naturaleza == "DEBITO":
            saldo += deb - cre
        else:
            saldo += cre - deb
        tot_deb += deb
        tot_cre += cre
        movimientos.append({
            "numero": comp.get("numero", ""),
            "fecha": comp.get("fecha", ""),
            "descripcion": f.get("descripcion", ""),
            "debito": deb,
            "credito": cre,
            "saldo": saldo,
        })

    totales = {
        "total_debito": tot_deb,
        "total_credito": tot_cre,
        "saldo_final": saldo,
        "naturaleza": naturaleza,
    }
    return cuenta, movimientos, totales


# =============================================================
# CATÁLOGOS (para poblar formularios)
# =============================================================

def catalogos_para_formulario(empresa_id: int = 1):
    """Devuelve cuentas de movimiento, terceros, centros de costo y tipos
    de comprobante para armar el formulario de nuevo comprobante."""
    return {
        "cuentas": repo.listar_puc(empresa_id=empresa_id, solo_movimiento=True),
        "terceros": repo.listar_terceros(empresa_id=empresa_id),
        "centros_costo": repo.listar_centros_costo(empresa_id=empresa_id),
        "tipos_comprobante": repo.listar_consecutivos(empresa_id=empresa_id),
    }
