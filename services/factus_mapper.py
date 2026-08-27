"""
Mapeador Vitacore → Factus — Vitacore
======================================

Construye los payloads que exige la API de Factus (adquiriente, ítems,
factura, nota crédito) a partir de los datos que Vitacore ya tiene
(paciente, cliente, contrato, detalle de factura) y detecta qué datos
obligatorios para la DIAN todavía faltan, para poder pedirlos en el
formulario de facturación ANTES de intentar emitir.

Reglas de negocio aplicadas (definidas junto con el usuario):
  - El "adquiriente" de la factura electrónica es el CLIENTE contratante
    (EPS/aseguradora/empresa) en la mayoría de los casos, salvo que el
    registro de hc_clientes tenga usa_paciente_como_adquiriente = true,
    en cuyo caso el adquiriente es el PACIENTE (pago particular).
  - El tratamiento de IVA de cada ítem depende del CUPS/producto
    facturado (columna hc_cups.factus_tratamiento).
"""

import re

from repositories import fin_factus_repo

# Código DIAN "estándar adoptado por el contribuyente" (tabla 13.2.5.7),
# usado cuando el ítem no tiene código UNSPSC.
# CORREGIDO (2026-08-27): era "4" — Factus lo rechazó en una prueba real
# con "El campo código estándar es inválido". El ejemplo oficial de Factus
# ("factura estándar a consumidor final") usa "999" para productos/
# servicios sin un estándar reconocido (UNSPSC, GTIN, etc.), así que ese es
# el valor correcto para procedimientos CUPS. Ver también el UPDATE en
# db/migracion_factus.sql para corregir hc_cups.factus_standard_code, que
# había quedado sembrado con el valor viejo.
FACTUS_STANDARD_CODE_ADOPTADO = "999"
# Unidad de medida DIAN por defecto: "94" = Unidad (ver ejemplo oficial del
# SDK de Factus). Ajustable por CUPS vía hc_cups.factus_unidad_medida.
FACTUS_UNIDAD_MEDIDA_DEFAULT = "94"

LEGAL_ORG_JURIDICA = "1"
LEGAL_ORG_NATURAL = "2"


class DatosFaltantesError(Exception):
    """Se levanta cuando faltan datos obligatorios DIAN del adquiriente."""

    def __init__(self, entidad: str, entidad_id, campos_faltantes: list):
        self.entidad = entidad  # 'PACIENTE' | 'CLIENTE'
        self.entidad_id = entidad_id
        self.campos_faltantes = campos_faltantes
        super().__init__(
            f"Faltan datos DIAN de {entidad} #{entidad_id}: {', '.join(campos_faltantes)}"
        )


def _limpiar_texto(valor) -> str:
    """
    CORREGIDO (2026-08-27): se detectó un rechazo "ZE02, Rechazo: Valor de
    la Firma inválido" en una prueba real, y el payload mostraba una
    dirección con un salto de línea crudo metido adentro
    (ej. "Mz 18 Casa 5...\r\nRisaralda" — típico de un campo de dirección
    en la BD que junta calle + ciudad con un enter). Factus arma y firma
    el XML UBL a partir de estos campos; un \\r\\n crudo dentro de un
    valor de texto puede hacer que la normalización de espacios en blanco
    que aplica el firmante y la que aplica el verificador de la DIAN no
    coincidan, invalidando la firma sin que ningún campo individual se vea
    "mal" a simple vista. Se limpia TODO texto libre que vaya a Factus
    (dirección, nombres, observaciones, descripciones de ítems) para evitar
    esto: se colapsan saltos de línea / tabs / espacios múltiples a un solo
    espacio y se recorta.
    """
    if valor is None:
        return ""
    texto = str(valor)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _codigo_documento_factus(codigo_local: str) -> str:
    mapeo = fin_factus_repo.obtener_mapeo_tipos_documento()
    codigo = mapeo.get((codigo_local or "").upper())
    if not codigo:
        raise DatosFaltantesError(
            "CONFIGURACION",
            codigo_local,
            [f"mapeo_tipo_documento_{codigo_local or 'desconocido'}"],
        )
    return codigo


def determinar_adquiriente(cliente: dict, paciente: dict) -> str:
    """Devuelve 'PACIENTE' o 'CLIENTE' según la regla de negocio configurada."""
    if cliente and cliente.get("usa_paciente_como_adquiriente"):
        return "PACIENTE"
    return "CLIENTE"


def construir_adquiriente_desde_cliente(cliente: dict) -> dict:
    if not cliente:
        raise DatosFaltantesError("CLIENTE", None, ["cliente_no_encontrado"])
    faltan = []
    if not cliente.get("nit"):
        faltan.append("nit")
    if not cliente.get("nombre"):
        faltan.append("nombre")
    if not cliente.get("direccion"):
        faltan.append("direccion")
    if not cliente.get("email"):
        faltan.append("email")
    if not cliente.get("municipio_dian_codigo"):
        faltan.append("municipio_dian_codigo")
    if faltan:
        raise DatosFaltantesError("CLIENTE", cliente.get("id"), faltan)

    tipo_doc_local = cliente.get("tipo_identificacion") or "NIT"
    # CORREGIDO (2026-08-27): un cliente con NIT es persona jurídica ante la
    # DIAN — Factus exige la razón social en "company" (no en "names") para
    # legal_organization_code = 1, y rechazó la factura de prueba con
    # "El campo razón social debe ser una cadena de caracteres" porque
    # "company" nunca se enviaba. Si el cliente tiene un tipo de
    # identificación de persona natural (CC/CE/TI/PA — p. ej. un cliente
    # "Particular" sin NIT), se trata como natural en su lugar.
    es_juridica = tipo_doc_local.upper() == "NIT"
    payload = {
        "identification_document_code": _codigo_documento_factus(tipo_doc_local),
        "identification": str(cliente["nit"]).replace("-", "").strip(),
        "dv": str(cliente.get("dv") or "").strip() or None,
        "address": _limpiar_texto(cliente["direccion"]),
        "email": _limpiar_texto(cliente["email"]),
        "phone": _limpiar_texto(cliente.get("telefono") or ""),
        "legal_organization_code": LEGAL_ORG_JURIDICA if es_juridica else LEGAL_ORG_NATURAL,
        "municipality_code": cliente["municipio_dian_codigo"],
    }
    if es_juridica:
        payload["company"] = _limpiar_texto(cliente["nombre"])
        payload["names"] = ""
    else:
        payload["names"] = _limpiar_texto(cliente["nombre"])
        payload["company"] = ""
    return payload


def construir_adquiriente_desde_paciente(paciente: dict) -> dict:
    if not paciente:
        raise DatosFaltantesError("PACIENTE", None, ["paciente_no_encontrado"])
    faltan = []
    nombre = " ".join(filter(None, [
        paciente.get("primer_nombre"), paciente.get("segundo_nombre"),
        paciente.get("primer_apellido"), paciente.get("segundo_apellido"),
    ])).strip()

    if not paciente.get("numero_documento"):
        faltan.append("numero_documento")
    if not nombre:
        faltan.append("nombre")
    if not paciente.get("direccion"):
        faltan.append("direccion")
    if not paciente.get("email"):
        faltan.append("email")
    if not paciente.get("municipio_dian_codigo"):
        faltan.append("municipio_dian_codigo")
    if faltan:
        raise DatosFaltantesError("PACIENTE", paciente.get("id"), faltan)

    tipo_doc_local = paciente.get("tipo_documento") or "CC"
    return {
        "identification_document_code": _codigo_documento_factus(tipo_doc_local),
        "identification": str(paciente["numero_documento"]).strip(),
        "dv": None,
        "names": _limpiar_texto(nombre),
        # "company" no aplica para persona natural, pero Factus exige que
        # el campo sea una cadena si viene en el payload — se manda vacío
        # en vez de omitirlo, igual que en construir_adquiriente_desde_cliente.
        "company": "",
        "address": _limpiar_texto(paciente["direccion"]),
        "email": _limpiar_texto(paciente["email"]),
        "phone": _limpiar_texto(paciente.get("telefono") or paciente.get("celular") or ""),
        "legal_organization_code": LEGAL_ORG_NATURAL,
        "municipality_code": paciente["municipio_dian_codigo"],
    }


def construir_adquiriente(cliente: dict, paciente: dict):
    """
    Devuelve (adquiriente_tipo, payload_customer).
    Lanza DatosFaltantesError si faltan datos obligatorios.
    """
    tipo = determinar_adquiriente(cliente, paciente)
    if tipo == "PACIENTE":
        return tipo, construir_adquiriente_desde_paciente(paciente)
    return tipo, construir_adquiriente_desde_cliente(cliente)


def _impuestos_item(cups: dict) -> list:
    """
    cups: fila de hc_cups (o del ítem libre) con factus_tratamiento /
    factus_tributo_codigo / factus_tarifa.

    CORREGIDO (2026-08-27): un arreglo vacío [] hacía que Factus rechazara
    la factura de prueba con "El campo items.0.taxes es obligatorio." —
    Factus exige SIEMPRE al menos un objeto de impuesto por ítem, y marca
    los excluidos/exentos con "is_excluded": true (en vez de omitir el
    impuesto). Ver developers.factus.com.co/facturas/descripcion-de-campos.

    (VERIFICAR) La documentación de Factus no distingue explícitamente
    "excluido" de "exento" — ambos se describen con el mismo parámetro
    is_excluded. Aquí se tratan igual (is_excluded=true); si Factus llega a
    exigir un tratamiento distinto para EXENTO (p. ej. tarifa 0% pero
    is_excluded=false porque sí causa IVA), ajústalo en esta función.
    """
    tratamiento = (cups or {}).get("factus_tratamiento") or "EXCLUIDO"
    if tratamiento == "GRAVADO":
        codigo = (cups or {}).get("factus_tributo_codigo") or "01"
        tarifa = (cups or {}).get("factus_tarifa") or 0
        return [{"code": codigo, "rate": str(tarifa), "is_excluded": False}]
    # EXCLUIDO / EXENTO: sigue exigiendo un objeto de impuesto, marcado
    # como excluido, con tarifa 0.
    return [{"code": "01", "rate": "0.00", "is_excluded": True}]


def construir_item(detalle_item: dict, cups: dict = None) -> dict:
    cantidad = float(detalle_item.get("cantidad", 1) or 1)
    valor_unitario = float(detalle_item.get("valor_unitario", 0) or 0)

    return {
        "code_reference": detalle_item.get("codigo_cups") or "SERV",
        "name": _limpiar_texto(detalle_item.get("descripcion") or "Servicio de salud"),
        "quantity": cantidad,
        "discount_rate": 0,
        "price": valor_unitario,
        "unit_measure_code": (cups or {}).get("factus_unidad_medida") or FACTUS_UNIDAD_MEDIDA_DEFAULT,
        "standard_code": (cups or {}).get("factus_standard_code") or FACTUS_STANDARD_CODE_ADOPTADO,
        "taxes": _impuestos_item(cups),
    }


def construir_payload_factura(
    reference_code: str,
    observaciones: str,
    total: float,
    detalle: list,
    numbering_range_id: int,
    adquiriente_tipo: str,
    customer_payload: dict,
    cups_por_codigo: dict = None,
) -> dict:
    cups_por_codigo = cups_por_codigo or {}
    items = [
        construir_item(d, cups_por_codigo.get(d.get("codigo_cups")))
        for d in detalle
    ]

    payment_form = "1"  # (VERIFICAR tabla Factus) 1 = Contado (patrón común DIAN)
    payment_method_code = "10"  # (VERIFICAR tabla Factus) 10 = Efectivo (patrón común DIAN)

    return {
        "numbering_range_id": numbering_range_id,
        "reference_code": reference_code,
        "observation": _limpiar_texto(observaciones or ""),
        "payment_form": payment_form,
        "payment_details": [
            {
                "payment_form": payment_form,
                "payment_method_code": payment_method_code,
                "amount": str(total or 0),
            }
        ],
        "customer": customer_payload,
        "items": items,
        # Envío automático por correo (2026-08-27): apenas Factus valida la
        # factura ante la DIAN, la envía sola al correo del adquiriente
        # (customer.email, que ya es un dato obligatorio -- ver los
        # DatosFaltantesError de construir_adquiriente_desde_*). Si el
        # correo estaba mal y se corrige después, existe además el botón
        # "Reenviar por correo" (api/factura/<id>/email) para reenviarla.
        "send_email": True,
        # Campo interno propio (no lo envía Factus, sirve para trazabilidad
        # si se guarda el payload completo en fin_factus_eventos_log).
        "_adquiriente_tipo": adquiriente_tipo,
    }


def construir_payload_nota_credito(
    factura_dian_number: str,
    motivo_codigo: str,
    detalle: list,
    valor_total: float,
    concepto: str,
    numbering_range_id: int,
    customer_payload: dict,
    cups_por_codigo: dict = None,
) -> dict:
    """
    CORREGIDO (2026-08-27): la primera prueba real contra Factus rechazó
    esta nota con "El campo customer es obligatorio", "El campo id rango de
    numeración es obligatorio" y "El campo detalles de pago es obligatorio"
    -- una nota crédito/débito electrónica no es solo una referencia al
    número de factura: exige el MISMO adquiriente (customer) y el mismo
    rango de numeración (numbering_range_id) que se usó al validar la
    factura original, además de payment_details, igual que una factura.
    """
    cups_por_codigo = cups_por_codigo or {}
    items = [
        construir_item(d, cups_por_codigo.get(d.get("codigo_cups")))
        for d in detalle
    ] or [{
        "code_reference": "AJUSTE",
        "name": _limpiar_texto(concepto or "Ajuste"),
        "quantity": 1,
        "discount_rate": 0,
        "price": valor_total,
        "unit_measure_code": FACTUS_UNIDAD_MEDIDA_DEFAULT,
        "standard_code": FACTUS_STANDARD_CODE_ADOPTADO,
        "taxes": [{"code": "01", "rate": "0.00", "is_excluded": True}],
    }]

    payment_form = "1"  # (VERIFICAR tabla Factus) 1 = Contado (patrón común DIAN)
    payment_method_code = "10"  # (VERIFICAR tabla Factus) 10 = Efectivo (patrón común DIAN)

    return {
        "numbering_range_id": numbering_range_id,
        "reference_code": f"VITACORE-NC-{factura_dian_number}-{motivo_codigo}",
        "correction_concept_code": motivo_codigo,
        "bill_number": factura_dian_number,
        "observation": _limpiar_texto(concepto or ""),
        "payment_form": payment_form,
        "payment_details": [
            {
                "payment_form": payment_form,
                "payment_method_code": payment_method_code,
                "amount": str(valor_total or 0),
            }
        ],
        "customer": customer_payload,
        "items": items,
    }
