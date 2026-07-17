"""
Generador del PDF de epicrisis para el DocumentReference del RDA.

No inventa contenido clínico: cada sección usa el texto que el médico
escribió en la evolución (hc_evoluciones). Si un campo opcional viene
vacío, se marca explícitamente como "No registrado" en vez de omitirse
en silencio -- así el PDF nunca sugiere que un dato existió cuando no.
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _texto(valor, default="No registrado"):
    v = (valor or "").strip() if isinstance(valor, str) else valor
    return v if v else default


def _estilos():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="EpiTitulo", fontSize=14, spaceAfter=6,
        textColor=colors.HexColor("#1a3c5e"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="EpiSeccion", fontSize=11, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor("#1a3c5e"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="EpiCuerpo", fontSize=9.5, leading=13, alignment=TA_JUSTIFY,
    ))
    styles.add(ParagraphStyle(
        name="EpiPie", fontSize=7.5, textColor=colors.grey,
    ))
    return styles


def generar_epicrisis_pdf(evo, pac, medico, empresa) -> bytes:
    """Genera el PDF de epicrisis a partir de los datos ya cargados de la
    evolución, el paciente, el médico y la empresa (IPS). Devuelve los
    bytes del PDF, listos para codificar en base64 y adjuntar al RDA.

    Parámetros: los mismos dicts que ya construyes en rda_service.py
    (evo = repo_evo.obtener(evolucion_id), pac = _paciente_full(...),
    medico = repo_prof.obtener(...), empresa = _empresa_activa(...)).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    styles = _estilos()
    story = []

    # --- Encabezado institucional ---
    nombre_ips = empresa.get("nombre_comercial") or empresa.get("razon_social") or "IPS"
    story.append(Paragraph(nombre_ips, styles["EpiTitulo"]))
    story.append(Paragraph(
        f"NIT {empresa.get('nit', '')} &middot; "
        f"C&oacute;digo de habilitaci&oacute;n {empresa.get('codigo_habilitacion', '')}",
        styles["EpiCuerpo"],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph("EPICRISIS &middot; RESUMEN DE ATENCI&Oacute;N", styles["EpiTitulo"]))
    story.append(Spacer(1, 6))

    # --- Datos del paciente / atención ---
    fecha_str = str(evo.get("fecha") or "")[:16].replace("T", " ")
    paciente_nombre = " ".join(filter(None, [
        pac.get("primer_nombre"), pac.get("segundo_nombre"),
        pac.get("primer_apellido"), pac.get("segundo_apellido"),
    ])) or "No registrado"
    medico_nombre = f"{medico.get('nombres', '')} {medico.get('apellidos', '')}".strip() or "No registrado"

    tabla_datos = [
        ["Paciente:", paciente_nombre, "Documento:", str(pac.get("numero_documento", ""))],
        ["Fecha de atenci\u00f3n:", fecha_str, "Tipo de atenci\u00f3n:", _texto(evo.get("tipo_atencion"))],
        ["M\u00e9dico tratante:", medico_nombre, "Documento m\u00e9dico:", str(medico.get("numero_documento", ""))],
    ]
    t = Table(tabla_datos, colWidths=[3.2 * cm, 5.3 * cm, 3.2 * cm, 5.3 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # --- Secciones clínicas (contenido real de la evolución, sin inventar nada) ---
    secciones = [
        ("Motivo de consulta", evo.get("motivo_consulta")),
        ("Antecedentes", evo.get("antecedentes")),
        ("Enfermedad actual", evo.get("enfermedad_actual")),
        ("Examen f\u00edsico", evo.get("examen_fisico")),
        ("Examen por sistemas", evo.get("examen_sistemas")),
        ("Resultados paracl\u00ednicos", evo.get("resultados_paraclinicos")),
    ]
    for titulo, contenido in secciones:
        story.append(Paragraph(titulo, styles["EpiSeccion"]))
        story.append(Paragraph(_texto(contenido), styles["EpiCuerpo"]))

    # --- Diagnóstico ---
    story.append(Paragraph("Diagn\u00f3stico", styles["EpiSeccion"]))
    dx_cod = evo.get("cie10_codigo") or ""
    dx_nom = evo.get("cie10_nombre") or ""
    dx_principal = f"{dx_cod} - {dx_nom}".strip(" -") or "No registrado"
    story.append(Paragraph(f"Principal: {dx_principal}", styles["EpiCuerpo"]))
    if evo.get("impresion_diagnostica"):
        story.append(Paragraph(
            f"Impresi\u00f3n diagn\u00f3stica: {evo['impresion_diagnostica']}", styles["EpiCuerpo"]))
    if evo.get("diagnosticos_secundarios"):
        story.append(Paragraph(
            f"Diagn\u00f3sticos secundarios: {evo['diagnosticos_secundarios']}", styles["EpiCuerpo"]))

    # --- Plan y recomendaciones ---
    story.append(Paragraph("Plan de manejo", styles["EpiSeccion"]))
    story.append(Paragraph(_texto(evo.get("plan")), styles["EpiCuerpo"]))

    story.append(Paragraph("Recomendaciones", styles["EpiSeccion"]))
    story.append(Paragraph(_texto(evo.get("recomendaciones")), styles["EpiCuerpo"]))

    # --- Destino y seguimiento ---
    destino = _texto(evo.get("destino_paciente"), default="No especificado")
    control_fecha = evo.get("proximo_control_fecha")
    if control_fecha:
        control_str = f"{control_fecha} ({evo.get('proximo_control_tipo') or 'sin tipo especificado'})"
    else:
        control_str = "No programado"
    story.append(Paragraph("Destino y seguimiento", styles["EpiSeccion"]))
    story.append(Paragraph(f"Destino del paciente: {destino}", styles["EpiCuerpo"]))
    story.append(Paragraph(f"Pr\u00f3ximo control: {control_str}", styles["EpiCuerpo"]))

    # --- Pie de página ---
    story.append(Spacer(1, 16))
    generado = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(
        f"Documento generado electr\u00f3nicamente por VitaCore el {generado}. "
        "Forma parte del Resumen Digital de Atenci\u00f3n (RDA) transmitido conforme "
        "a la Resoluci\u00f3n 1888 de 2025.",
        styles["EpiPie"],
    ))

    doc.build(story)
    return buffer.getvalue()