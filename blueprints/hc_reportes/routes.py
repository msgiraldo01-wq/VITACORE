# blueprints/hc_reportes/routes.py
"""
Apartado "Reportes" de historia clínica / citas ("/hc/reportes").

Por ahora contiene el indicador de oportunidad de asignación de citas
de primera vez que pide la Resolución 256 de 2016. El permiso de
módulo ("reportes") y el enlace del menú ya existían de antes; solo
faltaba este blueprint.
"""

import csv
import io
from datetime import date

from flask import Blueprint, Response, render_template, request, session

from blueprints.auth.decorators import login_required
from repositories import hc_reportes_repo as repo

bp_hc_reportes = Blueprint("hc_reportes", __name__, url_prefix="/hc/reportes")


# Catálogo de reportes disponibles en este apartado -- la clave debe
# coincidir con el nombre de la función de vista, para que el índice
# arme el link con url_for('hc_reportes.' + clave) sin tocar nada más
# cuando se agregue un reporte nuevo.
REPORTES = {
    "oportunidad_citas": {
        "titulo": "Oportunidad de citas — Resolución 256",
        "ayuda": "Días entre la solicitud y la asignación de citas médicas de primera vez, por especialidad.",
        "icono": "fa-calendar-check",
    },
    "citas_canceladas": {
        "titulo": "Citas canceladas",
        "ayuda": "Conteo y porcentaje de citas canceladas por motivo y por especialidad.",
        "icono": "fa-ban",
    },
    "citas_reprogramadas": {
        "titulo": "Citas reprogramadas",
        "ayuda": "Conteo y porcentaje de citas reprogramadas por motivo y por especialidad.",
        "icono": "fa-calendar-days",
    },
}


def _rango_por_defecto():
    """Mes calendario actual, como rango por defecto del filtro."""
    hoy = date.today()
    desde = hoy.replace(day=1)
    return desde.isoformat(), hoy.isoformat()


@bp_hc_reportes.route("/")
@login_required
def index():
    return render_template("hc/reportes/index.html", reportes=REPORTES)


@bp_hc_reportes.route("/oportunidad-citas")
@login_required
def oportunidad_citas():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_oportunidad_citas(empresa_id, desde, hasta)

    return render_template(
        "hc/reportes/oportunidad_citas.html",
        data=data, desde=desde, hasta=hasta,
    )


@bp_hc_reportes.route("/oportunidad-citas/csv")
@login_required
def oportunidad_citas_csv():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_oportunidad_citas(empresa_id, desde, hasta)

    salida = io.StringIO()
    # delimiter ';' y BOM: Excel en español abre el archivo con las columnas separadas
    w = csv.writer(salida, delimiter=";")
    w.writerow(["ESPECIALIDAD", "CITAS DE PRIMERA VEZ", "PROMEDIO DIAS OPORTUNIDAD"])
    for f in data["filas"]:
        w.writerow([f["especialidad"], f["citas"], f["promedio_dias"]])
    w.writerow([])
    w.writerow(["TOTAL", data["total_citas"], data["promedio_general"]])

    contenido = "\ufeff" + salida.getvalue()
    nombre = f"oportunidad_citas_{desde}_a_{hasta}.csv"
    return Response(
        contenido, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


@bp_hc_reportes.route("/citas-canceladas")
@login_required
def citas_canceladas():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_citas_canceladas(empresa_id, desde, hasta)

    return render_template(
        "hc/reportes/citas_canceladas.html",
        data=data, desde=desde, hasta=hasta,
    )


@bp_hc_reportes.route("/citas-canceladas/csv")
@login_required
def citas_canceladas_csv():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_citas_canceladas(empresa_id, desde, hasta)

    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";")
    w.writerow(["TOTAL CANCELADAS", data["total_canceladas"]])
    w.writerow(["TOTAL CITAS DEL PERIODO", data["total_periodo"]])
    w.writerow(["TASA DE CANCELACION (%)", data["tasa_cancelacion"]])
    w.writerow([])
    w.writerow(["POR MOTIVO"])
    w.writerow(["MOTIVO", "CITAS", "PORCENTAJE"])
    for f in data["por_motivo"]:
        w.writerow([f["nombre"], f["citas"], f["porcentaje"]])
    w.writerow([])
    w.writerow(["POR ESPECIALIDAD"])
    w.writerow(["ESPECIALIDAD", "CITAS", "PORCENTAJE"])
    for f in data["por_especialidad"]:
        w.writerow([f["nombre"], f["citas"], f["porcentaje"]])

    contenido = "\ufeff" + salida.getvalue()
    nombre = f"citas_canceladas_{desde}_a_{hasta}.csv"
    return Response(
        contenido, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


@bp_hc_reportes.route("/citas-reprogramadas")
@login_required
def citas_reprogramadas():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_citas_reprogramadas(empresa_id, desde, hasta)

    return render_template(
        "hc/reportes/citas_reprogramadas.html",
        data=data, desde=desde, hasta=hasta,
    )


@bp_hc_reportes.route("/citas-reprogramadas/csv")
@login_required
def citas_reprogramadas_csv():
    empresa_id = session.get("empresa_id")
    desde_default, hasta_default = _rango_por_defecto()
    desde = request.args.get("desde") or desde_default
    hasta = request.args.get("hasta") or hasta_default

    data = repo.rep_citas_reprogramadas(empresa_id, desde, hasta)

    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";")
    w.writerow(["TOTAL REPROGRAMADAS", data["total_reprogramadas"]])
    w.writerow(["TOTAL CITAS DEL PERIODO", data["total_periodo"]])
    w.writerow(["TASA DE REPROGRAMACION (%)", data["tasa_reprogramacion"]])
    w.writerow(["PROMEDIO DE VECES REPROGRAMADA", data["promedio_veces"]])
    w.writerow([])
    w.writerow(["POR MOTIVO"])
    w.writerow(["MOTIVO", "CITAS", "PORCENTAJE"])
    for f in data["por_motivo"]:
        w.writerow([f["nombre"], f["citas"], f["porcentaje"]])
    w.writerow([])
    w.writerow(["POR ESPECIALIDAD"])
    w.writerow(["ESPECIALIDAD", "CITAS", "PORCENTAJE"])
    for f in data["por_especialidad"]:
        w.writerow([f["nombre"], f["citas"], f["porcentaje"]])

    contenido = "\ufeff" + salida.getvalue()
    nombre = f"citas_reprogramadas_{desde}_a_{hasta}.csv"
    return Response(
        contenido, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )
