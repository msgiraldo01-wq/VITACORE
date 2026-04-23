from datetime import datetime, timedelta
from repositories import hc_agendas_repo

from flask import Blueprint

bp_citas = Blueprint(
    "citas",
    __name__,
    url_prefix="/citas",
    template_folder="templates",
    static_folder="static"
)


def generar_slots(fecha: str, profesional_id=None, recurso_id=None):

    if not fecha:
        return []

    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
    dia_semana = fecha_dt.isoweekday()  # 1-7

    agendas = hc_agendas_repo.listar()

    agendas_filtradas = []

    for a in agendas:

        # 🔹 estado
        if a.get("estado") != "ACTIVO":
            continue

        # 🔹 día (forzar int)
        if int(a.get("dia_semana", 0)) != int(dia_semana):
            continue

        # 🔹 FILTRO FLEXIBLE (PRO)
        if profesional_id:
            if str(a.get("profesional_id")) != str(profesional_id):
                continue

        if recurso_id:
            if str(a.get("recurso_id")) != str(recurso_id):
                continue

        agendas_filtradas.append(a)

    slots = []

    for a in agendas_filtradas:

        try:
            inicio_time = datetime.strptime(a["hora_inicio"], "%H:%M:%S").time()
            fin_time = datetime.strptime(a["hora_fin"], "%H:%M:%S").time()
        except Exception:
            continue

        inicio = datetime.combine(fecha_dt, inicio_time)
        fin = datetime.combine(fecha_dt, fin_time)

        # 🔴 VALIDACIÓN CRÍTICA
        if inicio >= fin:
            continue

        duracion = int(a.get("duracion_min", 20))

        actual = inicio

        while actual < fin:

            slots.append({
                "hora": actual.strftime("%H:%M"),
                "datetime": actual.isoformat()
            })

            actual += timedelta(minutes=duracion)

    return slots