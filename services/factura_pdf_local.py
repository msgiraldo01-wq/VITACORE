"""
PDF local de respaldo para facturas — Vitacore
================================================

Antes de esta integración, la ruta /api/factura/<id>/pdf importaba
`services.fin_factura_pdf`, un módulo que no existía en el proyecto (bug
preexistente: la descarga de PDF estaba rota). Este módulo lo reemplaza.

Este PDF es un RESPALDO INTERNO — se usa solo cuando la factura todavía
no tiene CUFE de la DIAN (por ejemplo, con Factus deshabilitado en un
ambiente de pruebas). Una factura ya validada por la DIAN debe
descargarse siempre con el PDF oficial de Factus (que trae CUFE, QR y
representación gráfica válida), servido por la misma ruta cuando
corresponda — ver blueprints/bp_financiero/facturacion/routes.py.
"""

from services.pdf_service import PDFService


def _fmt_moneda(valor) -> str:
    try:
        return f"${float(valor or 0):,.0f}".replace(",", ".")
    except Exception:
        return "$0"


def generar_factura_pdf_local(factura: dict, detalle: list, empresa: dict) -> bytes:
    pac = factura.get("hc_pacientes", {}) or {}
    cli = factura.get("hc_clientes", {}) or {}
    sede = factura.get("hc_sedes", {}) or {}

    nombre_paciente = " ".join(filter(None, [
        pac.get("primer_nombre"), pac.get("primer_apellido"),
    ])) or "—"

    filas_html = "".join(
        f"<tr>"
        f"<td>{d.get('codigo_cups', '')}</td>"
        f"<td>{d.get('descripcion', '')}</td>"
        f"<td style='text-align:right'>{d.get('cantidad', 1)}</td>"
        f"<td style='text-align:right'>{_fmt_moneda(d.get('valor_unitario'))}</td>"
        f"<td style='text-align:right'>{_fmt_moneda(d.get('valor_total'))}</td>"
        f"</tr>"
        for d in detalle
    )

    aviso_dian = ""
    if factura.get("factus_estado") not in ("VALIDADA",):
        aviso_dian = (
            "<div style='margin:14px 0;padding:10px 14px;background:#fff3cd;"
            "border:1px solid #ffe08a;border-radius:6px;font-size:12px;color:#7a5b00;'>"
            "⚠ Documento interno — aún no validado electrónicamente ante la DIAN. "
            "No constituye una factura electrónica de venta."
            "</div>"
        )

    html = f"""
    <html><head><meta charset="utf-8"><style>
      body {{ font-family: Arial, sans-serif; font-size: 13px; color:#222; }}
      h1 {{ font-size: 18px; margin-bottom:0; }}
      table {{ width:100%; border-collapse: collapse; margin-top:14px; }}
      th, td {{ border:1px solid #ccc; padding:6px 8px; font-size:12px; }}
      th {{ background:#f2f2f2; text-align:left; }}
      .totales td {{ border:none; }}
    </style></head>
    <body>
      <h1>{empresa.get('nombre', '')}</h1>
      <div>{empresa.get('nit', '')}</div>
      <div>{empresa.get('direccion', '')} {empresa.get('ciudad', '')}</div>
      {aviso_dian}
      <h2>Factura {factura.get('numero_factura', '')}</h2>
      <div><b>Paciente:</b> {nombre_paciente} — {pac.get('numero_documento', '')}</div>
      <div><b>Cliente:</b> {cli.get('nombre', '')} — NIT {cli.get('nit', '')}</div>
      <div><b>Sede:</b> {sede.get('nombre', '')}</div>
      <table>
        <thead><tr><th>CUPS</th><th>Descripción</th><th>Cant.</th><th>Vlr. unit.</th><th>Vlr. total</th></tr></thead>
        <tbody>{filas_html}</tbody>
      </table>
      <table class="totales" style="width:300px; margin-left:auto;">
        <tr><td>Subtotal</td><td style="text-align:right">{_fmt_moneda(factura.get('subtotal'))}</td></tr>
        <tr><td>Descuento</td><td style="text-align:right">{_fmt_moneda(factura.get('descuento'))}</td></tr>
        <tr><td><b>Total</b></td><td style="text-align:right"><b>{_fmt_moneda(factura.get('total'))}</b></td></tr>
      </table>
    </body></html>
    """

    return PDFService.sync_html_to_pdf(html)
