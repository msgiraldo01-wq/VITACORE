"""
Traduce documentos del día a día en asientos contables.

Hasta ahora la contabilidad de Vitacore era una libreta digital al lado
de un sistema que ya sabía todo lo que había que anotar en ella: había
27 facturas emitidas y cero comprobantes. Este módulo cierra esa brecha.

CÓMO FUNCIONA, y por qué así:

  1. Se propone, no se contabiliza. El asiento va a
     fin_comprobantes_propuestos y espera al contador. Crear el
     comprobante de verdad consume un número de consecutivo, y un
     borrador que nunca se apruebe dejaría un hueco en la numeración
     contable -- que en Colombia no puede tenerlos.

  2. Al aprobar se llama a fin_registrar_comprobante, la función de
     Postgres que ya existía. Ella valida partida doble, cuentas,
     terceros, centros de costo y periodo, de forma atómica. Aquí no se
     reimplementa ninguna de esas reglas.

  3. Las cuentas salen de fin_cuentas_por_concepto, no del código:
     cada IPS tiene su plan de cuentas.

  4. Nada de esto puede tumbar una factura. Si la contabilización
     falla, la factura sigue emitida y la propuesta queda marcada con
     el motivo.
"""

from datetime import date

from services.supabase_service import get_supabase_admin
from repositories import fin_contabilidad_repo as repo_cont


# Un CUPS 89xxxx es consulta; el resto, procedimiento. Es la división
# que usan las cuentas 415505 y 415510 del PUC.
PREFIJO_CONSULTA = "89"

ORIGEN_FACTURA = "fin_facturas"


def _sb():
    return get_supabase_admin()


# =============================================================
# PARAMETRIZACIÓN
# =============================================================

def cuentas(empresa_id: int) -> dict:
    """
    {concepto: {"cuenta_id":…, "centro_costo_id":…}} para esta empresa.

    Sin caché a propósito: esto se consulta una vez por lote, no por
    línea, y una parametrización contable recién corregida tiene que
    aplicarse en el siguiente intento, no en el siguiente minuto.
    """
    r = (_sb().table("fin_cuentas_por_concepto")
         .select("concepto,cuenta_id,centro_costo_id")
         .eq("empresa_id", empresa_id)
         .execute())
    return {f["concepto"]: f for f in (r.data or [])}


# =============================================================
# TERCEROS
# =============================================================

def tercero_de_cliente(cliente_id, empresa_id: int):
    """
    El tercero contable de un cliente, creándolo si hace falta.

    Las cuentas de cartera e ingresos tienen exige_tercero en el PUC, y
    fin_terceros está vacía. Sin esto habría que teclear cada EPS a
    mano antes de poder contabilizar la primera factura.

    Devuelve (tercero_id, error).
    """
    if not cliente_id:
        return None, "La factura no tiene cliente."

    c = (_sb().table("hc_clientes").select("*")
         .eq("id", cliente_id).limit(1).execute()).data
    if not c:
        return None, f"El cliente {cliente_id} no existe."
    cli = c[0]

    nit = str(cli.get("nit") or "").strip()
    if not nit:
        return None, f"El cliente {cli.get('nombre')} no tiene NIT."

    ya = (_sb().table("fin_terceros").select("id")
          .eq("empresa_id", empresa_id)
          .eq("numero_documento", nit)
          .limit(1).execute()).data
    if ya:
        return ya[0]["id"], None

    nuevo = repo_cont.crear_tercero({
        "empresa_id": empresa_id,
        "tipo_documento": "NIT",
        "numero_documento": nit,
        "dv": cli.get("dv"),
        "tipo_persona": "JURIDICA",
        "razon_social": cli.get("nombre") or f"Cliente {cliente_id}",
        "es_cliente": True,
        "es_entidad_salud": True,
        "email": cli.get("email"),
        "telefono": cli.get("telefono"),
        "created_by": "contabilizacion",
    })
    if not nuevo:
        return None, f"No se pudo crear el tercero del cliente {nit}."
    return nuevo["id"], None


# =============================================================
# ARMAR EL ASIENTO DE UNA FACTURA
# =============================================================

def _numero_visible(fac) -> str:
    """
    El número tal como lo ve la EPS.

    `numero_factura` ya trae el prefijo incorporado ("FV2"), así que
    concatenarlo con `prefijo` producía "FVFV2" en la descripción del
    asiento. Se antepone solo cuando falta.
    """
    numero = str(fac.get("numero_factura") or "").strip()
    if not numero:
        return f"#{fac.get('id')}"

    # El número ya trae su propia letra: unas veces la del prefijo
    # ("FV2") y otras una distinta, porque las del set de pruebas de la
    # DIAN empiezan por SETP aunque el prefijo siga diciendo FV. Solo
    # se antepone el prefijo cuando el número es puramente numérico.
    if numero.isdigit():
        prefijo = str(fac.get("prefijo") or "").strip()
        return (prefijo + numero) if prefijo else numero
    return numero


def _concepto_de_cups(codigo_cups) -> str:
    cups = str(codigo_cups or "").strip()
    return "INGRESO_CONSULTA" if cups.startswith(PREFIJO_CONSULTA) else "INGRESO_PROCEDIMIENTO"


def asiento_de_factura(factura_id, empresa_id: int, param: dict = None):
    """
    Las líneas del asiento de una factura, sin escribir nada.

    Débito a cartera por el total; crédito a ingresos por cada línea,
    separando consulta de procedimiento; crédito a IVA si lo hay (los
    servicios de salud suelen ir excluidos, así que casi nunca).

    Devuelve (datos, error).
    """
    param = param if param is not None else cuentas(empresa_id)

    f = (_sb().table("fin_facturas").select("*")
         .eq("id", factura_id).limit(1).execute()).data
    if not f:
        return None, f"La factura {factura_id} no existe."
    fac = f[0]

    if (fac.get("estado") or "").upper() == "ANULADA":
        return None, "La factura está anulada; su asiento sería una reversión, no una causación."

    det = (_sb().table("fin_factura_detalle").select("*")
           .eq("factura_id", factura_id).execute()).data or []
    if not det:
        return None, "La factura no tiene detalle: no hay nada que contabilizar."

    falta = [c for c in ("CLIENTES", "INGRESO_CONSULTA", "INGRESO_PROCEDIMIENTO")
             if c not in param]
    if falta:
        return None, "Sin parametrizar: " + ", ".join(falta)

    tercero_id, err = tercero_de_cliente(fac.get("cliente_id"), empresa_id)
    if err:
        return None, err

    lineas = []

    # --- Débito: lo que la EPS nos debe ---
    total = round(float(fac.get("total") or 0), 2)
    if total <= 0:
        return None, "La factura tiene total cero."

    cta_cli = param["CLIENTES"]
    lineas.append({
        "cuenta_id": cta_cli["cuenta_id"],
        "tercero_id": tercero_id,
        "centro_costo_id": cta_cli.get("centro_costo_id"),
        "descripcion": f"Factura {_numero_visible(fac)}",
        "debito": total, "credito": 0, "base_gravable": 0,
    })

    # --- Crédito: los ingresos, agrupados por tipo de servicio ---
    # Agrupados y no línea a línea: diez ecografías en una factura son
    # un solo renglón de ingresos, no diez. El detalle clínico ya vive
    # en fin_factura_detalle.
    por_concepto = {}
    for d in det:
        concepto = _concepto_de_cups(d.get("codigo_cups"))
        por_concepto[concepto] = por_concepto.get(concepto, 0) + float(d.get("valor_total") or 0)

    for concepto, valor in sorted(por_concepto.items()):
        valor = round(valor, 2)
        if valor <= 0:
            continue                      # líneas de prueba en cero
        cta = param[concepto]
        lineas.append({
            "cuenta_id": cta["cuenta_id"],
            "tercero_id": tercero_id,
            "centro_costo_id": cta.get("centro_costo_id"),
            "descripcion": ("Consulta" if concepto == "INGRESO_CONSULTA" else "Procedimientos"),
            "debito": 0, "credito": valor, "base_gravable": 0,
        })

    # --- Crédito: IVA, cuando lo hay ---
    iva = round(float(fac.get("iva_valor") or 0), 2)
    if iva > 0:
        if "IVA_GENERADO" not in param:
            return None, "La factura tiene IVA y falta parametrizar IVA_GENERADO."
        cta_iva = param["IVA_GENERADO"]
        lineas.append({
            "cuenta_id": cta_iva["cuenta_id"],
            "tercero_id": tercero_id,
            "centro_costo_id": cta_iva.get("centro_costo_id"),
            "descripcion": "IVA generado",
            "debito": 0, "credito": iva,
            "base_gravable": round(float(fac.get("subtotal") or 0), 2),
        })

    deb = round(sum(l["debito"] for l in lineas), 2)
    cre = round(sum(l["credito"] for l in lineas), 2)
    if deb != cre:
        # La función de Postgres lo rechazaría igual, pero es mejor no
        # llegar a proponer un asiento que ya sabemos que está mal.
        return None, f"El asiento no cuadra: débito {deb} contra crédito {cre}."

    return {
        "empresa_id": empresa_id,
        "sede_id": fac.get("sede_id"),
        "origen_tabla": ORIGEN_FACTURA,
        "origen_id": str(factura_id),
        "tipo_comprobante": "CAU",
        "fecha": (fac.get("fecha_expedicion") or date.today().isoformat())[:10],
        "descripcion": f"Causación factura {_numero_visible(fac)}",
        "lineas": lineas,
        "total_debito": deb,
        "total_credito": cre,
    }, None


# =============================================================
# PROPONER
# =============================================================

def proponer_factura(factura_id, empresa_id: int, usuario: str, param: dict = None):
    """
    Deja el asiento esperando al contador. No toca los libros.

    Idempotente: si ya hay una propuesta viva para esa factura, la
    devuelve en vez de crear otra. La base lo garantiza además con un
    índice único, porque dos peticiones simultáneas pasarían las dos
    comprobaciones del código.
    """
    ya = (_sb().table("fin_comprobantes_propuestos").select("*")
          .eq("empresa_id", empresa_id)
          .eq("origen_tabla", ORIGEN_FACTURA)
          .eq("origen_id", str(factura_id))
          .neq("estado", "DESCARTADO")
          .limit(1).execute()).data
    if ya:
        return {"ok": True, "repetida": True, "propuesta": ya[0]}

    datos, err = asiento_de_factura(factura_id, empresa_id, param)
    if err:
        return {"ok": False, "error": err}

    datos["estado"] = "PROPUESTO"
    datos["created_by"] = usuario
    try:
        r = _sb().table("fin_comprobantes_propuestos").insert(datos).execute()
        return {"ok": True, "propuesta": (r.data or [None])[0]}
    except Exception as e:
        # El índice único salta si otra petición ganó la carrera: eso no
        # es un error, es la protección haciendo su trabajo.
        if "fin_propuestos_origen_uk" in str(e):
            return {"ok": True, "repetida": True}
        return {"ok": False, "error": str(e)}


def proponer_lote(empresa_id: int, usuario: str, limite: int = 500):
    """
    Propone el asiento de las facturas emitidas que aún no lo tengan.

    Se consultan de una vez las facturas y los orígenes ya propuestos, y
    solo se arman las que faltan. Preguntar factura por factura si ya
    tenía propuesta costaba un viaje a la base por cada una -- unos
    220 ms cada viaje -- y esto se llama al abrir la pantalla.
    """
    facturas = (_sb().table("fin_facturas").select("id")
                .eq("empresa_id", empresa_id)
                .eq("estado", "EMITIDA")
                .order("id")
                .limit(limite).execute()).data or []

    ya = (_sb().table("fin_comprobantes_propuestos").select("origen_id")
          .eq("empresa_id", empresa_id)
          .eq("origen_tabla", ORIGEN_FACTURA)
          .neq("estado", "DESCARTADO")
          .execute()).data or []
    hechas = {str(x["origen_id"]) for x in ya}

    faltan = [f for f in facturas if str(f["id"]) not in hechas]
    resumen = {"propuestas": 0, "repetidas": len(facturas) - len(faltan),
               "fallidas": 0, "errores": []}
    if not faltan:
        return resumen

    param = cuentas(empresa_id)
    for f in faltan:
        r = proponer_factura(f["id"], empresa_id, usuario, param)
        if not r.get("ok"):
            resumen["fallidas"] += 1
            resumen["errores"].append({"factura_id": f["id"], "error": r.get("error")})
        elif r.get("repetida"):
            resumen["repetidas"] += 1
        else:
            resumen["propuestas"] += 1
    return resumen


# =============================================================
# APROBAR Y DESCARTAR
# =============================================================

def aprobar(propuesta_id: int, usuario: str):
    """
    Lleva la propuesta a los libros.

    Aquí es donde se consume el consecutivo y donde la función de
    Postgres aplica todas sus validaciones. Si rechaza, la propuesta
    queda FALLIDA con el motivo, para corregir la parametrización y
    reintentar sin tener que volver a armar el asiento.
    """
    p = (_sb().table("fin_comprobantes_propuestos").select("*")
         .eq("id", propuesta_id).limit(1).execute()).data
    if not p:
        return {"ok": False, "error": "La propuesta no existe."}
    prop = p[0]

    if prop["estado"] == "APROBADO":
        return {"ok": True, "repetida": True, "comprobante_id": prop.get("comprobante_id")}
    if prop["estado"] == "DESCARTADO":
        return {"ok": False, "error": "La propuesta está descartada."}

    res = repo_cont.registrar_comprobante(
        empresa_id=prop["empresa_id"],
        sede_id=prop.get("sede_id"),
        tipo_comprobante=prop["tipo_comprobante"],
        fecha=prop["fecha"],
        descripcion=prop.get("descripcion") or "",
        movimientos=prop["lineas"],
        usuario=usuario,
        origen="AUTOMATICO",
        origen_tabla=prop["origen_tabla"],
        origen_id=prop["origen_id"],
    ) or {}

    if not res.get("ok"):
        motivo = res.get("error") or "La función contable lo rechazó sin decir por qué."
        _sb().table("fin_comprobantes_propuestos").update({
            "estado": "FALLIDO", "error": motivo,
            "resuelto_en": "now()", "resuelto_por": usuario,
        }).eq("id", propuesta_id).execute()
        return {"ok": False, "error": motivo}

    _sb().table("fin_comprobantes_propuestos").update({
        "estado": "APROBADO", "error": None,
        "comprobante_id": res.get("comprobante_id"),
        "resuelto_en": "now()", "resuelto_por": usuario,
    }).eq("id", propuesta_id).execute()

    return {"ok": True, "comprobante_id": res.get("comprobante_id"),
            "numero": res.get("numero")}


def descartar(propuesta_id: int, usuario: str, motivo: str = None):
    """El contador no quiere ese asiento. No se borra: queda el rastro."""
    _sb().table("fin_comprobantes_propuestos").update({
        "estado": "DESCARTADO",
        "error": motivo,
        "resuelto_en": "now()", "resuelto_por": usuario,
    }).eq("id", propuesta_id).execute()
    return {"ok": True}


def pendientes(empresa_id: int, limite: int = 200):
    """Lo que espera al contador, lo fallido primero: eso hay que arreglarlo."""
    r = (_sb().table("fin_comprobantes_propuestos").select("*")
         .eq("empresa_id", empresa_id)
         .in_("estado", ["PROPUESTO", "FALLIDO"])
         .order("estado")
         .order("fecha", desc=True)
         .limit(limite).execute())
    return r.data or []
