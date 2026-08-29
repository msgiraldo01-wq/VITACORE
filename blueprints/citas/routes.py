# blueprints/citas/routes.py

from flask import Blueprint, jsonify, request, render_template, session, send_file
from blueprints.auth.decorators import login_required
from services.permisos_service import requiere_permiso
from repositories import hc_citas_repo as repo
from datetime import datetime, timedelta
from services.pdf_service import PDFService, AssetHelper
from services import email_service
from postgrest.exceptions import APIError
import ipaddress
import os
import io


bp_citas = Blueprint("citas", __name__, url_prefix="/citas")


# --------------------------------------------------
# TRAZABILIDAD: IP privada / pública de quien crea la cita
# --------------------------------------------------

def _clasificar_ips(req) -> tuple[str | None, str | None]:
    """
    Un servidor no puede ver, en una sola petición, tanto la IP privada
    real de alguien detrás de un router NAT como su IP pública: solo ve
    la que le llega según la topología de red.
      - Si el navegador entra directo al servidor dentro de la misma red
        local (típico de una IPS que corre VITACORE en su propia red),
        lo que llega es la IP privada.
      - Si hay un proxy/balanceador de por medio (despliegue expuesto a
        internet), la IP pública real del cliente normalmente viaja en
        el header X-Forwarded-For, y remote_addr es la del proxy.
    Aquí se toman todas las IPs que el servidor sí puede ver (cadena de
    X-Forwarded-For + remote_addr) y se clasifica cada una según si es
    de rango privado (RFC 1918 / loopback) o pública.
    """
    candidatas = []

    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        candidatas.extend([ip.strip() for ip in xff.split(",") if ip.strip()])

    if req.remote_addr:
        candidatas.append(req.remote_addr)

    ip_privada = None
    ip_publica = None

    for ip_str in candidatas:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip_obj.is_private or ip_obj.is_loopback:
            ip_privada = ip_privada or ip_str
        else:
            ip_publica = ip_publica or ip_str

    return ip_privada, ip_publica


# --------------------------------------------------
# VISTAS
# --------------------------------------------------

@bp_citas.route("/")
@login_required
def agenda():
    return render_template("citas/agenda.html")

@bp_citas.route("/nueva")
@login_required
@requiere_permiso("citas", "create")
def nueva_cita():
    return render_template("citas/nueva.html")


@bp_citas.route("/test")
@login_required
def test_citas():
    try:
        data = repo.listar_por_fecha("2026-04-29")
        return jsonify({"ok": True, "total": len(data), "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: AGENDA
# --------------------------------------------------

@bp_citas.route("/api/agenda")
@login_required
def api_agenda():
    try:
        fecha = request.args.get("fecha")
        medico_id = request.args.get("medico_id", type=int)
        sede_id = request.args.get("sede_id", type=int)

        if not fecha:
            return {"ok": False, "error": "Fecha requerida"}, 400

        data = repo.listar_por_fecha(fecha=fecha, medico_id=medico_id, sede_id=sede_id)

        return {"ok": True, "total": len(data), "data": data}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: CREAR CITA
# --------------------------------------------------

@bp_citas.route("/api/crear", methods=["POST"])
@login_required
@requiere_permiso("citas", "create")
def api_crear_cita():
    try:
        data = request.json or {}
 
        # -----------------------------
        # EXTRAER PROCEDIMIENTOS ANTES
        # (no forman parte del payload de hc_citas)
        # -----------------------------
        procedimientos = data.pop("procedimientos", [])
 
        # -----------------------------
        # VALIDACIÓN EMPRESA
        # -----------------------------
        empresa = session.get("empresa_id") or data.get("empresa_id")
 
        if empresa is None:
            return {"ok": False, "error": "empresa_id es obligatorio"}, 400
 
        try:
            empresa = int(empresa)
        except:
            return {"ok": False, "error": "empresa_id inválido"}, 400
 
        data["empresa_id"] = empresa

        # -----------------------------
        # TRAZABILIDAD: quién crea la cita y desde dónde
        # -----------------------------
        usuario_sesion = session.get("user") or {}
        data["usuario_creacion_id"] = usuario_sesion.get("id")
        data["usuario_creacion"] = (
            usuario_sesion.get("full_name") or usuario_sesion.get("username") or None
        )
        data["ip_privada"], data["ip_publica"] = _clasificar_ips(request)

        # -----------------------------
        # FECHA DE SOLICITUD (para el indicador de oportunidad,
        # Resolución 256) — opcional. Si el usuario no la manda (caso
        # normal: la cita se agenda en el mismo momento en que se pide),
        # se deja en None y los reportes usan la fecha de creación del
        # registro como equivalente. Solo se necesita llenarla cuando
        # hay rezago real entre que alguien pidió la cita y que quedó
        # digitada en el sistema.
        # -----------------------------
        fecha_solicitud = (data.get("fecha_solicitud") or "").strip() or None
        if fecha_solicitud:
            try:
                datetime.strptime(fecha_solicitud, "%Y-%m-%d")
            except ValueError:
                return {"ok": False, "error": "Formato de fecha de solicitud inválido (YYYY-MM-DD)"}, 400
        data["fecha_solicitud"] = fecha_solicitud

        # -----------------------------
        # CAMPOS OBLIGATORIOS
        # -----------------------------
        campos_requeridos = [
            "paciente_id", "medico_id", "fecha", "hora_inicio",
            "tipo_atencion", "modalidad", "finalidad_consulta", "motivo_consulta",
            "tipo_consulta",
        ]

        for campo in campos_requeridos:
            if not data.get(campo):
                return {"ok": False, "error": f"Campo obligatorio: {campo}"}, 400

        # -----------------------------
        # TIPO DE CONSULTA (Primera vez / Control) — necesario para el
        # indicador de oportunidad de la Resolución 256, que solo mide
        # citas de primera vez. No existía antes un campo explícito para
        # esto; las citas creadas antes de este cambio quedan sin dato.
        # -----------------------------
        if data.get("tipo_consulta") not in ("PRIMERA_VEZ", "CONTROL"):
            return {"ok": False, "error": "Tipo de consulta inválido (use PRIMERA_VEZ o CONTROL)"}, 400
 
        # -----------------------------
        # TIPOS NUMÉRICOS
        # -----------------------------
        try:
            data["paciente_id"] = int(data["paciente_id"])
            data["medico_id"]   = int(data["medico_id"])
        except:
            return {"ok": False, "error": "paciente_id o medico_id inválidos"}, 400
 
        # -----------------------------
        # LIMPIEZA DE CAMPOS OPCIONALES
        # -----------------------------
        for campo in ["sede_id", "consultorio_id", "eps_id"]:
            valor = data.get(campo)
            if valor in (None, "", "None", "null"):
                data[campo] = None
            else:
                try:
                    data[campo] = int(valor)
                except:
                    data[campo] = None
 
        # -----------------------------
        # VALIDAR FORMATO HORA
        # -----------------------------
        try:
            hora_inicio = datetime.strptime(data["hora_inicio"], "%H:%M")
        except:
            return {"ok": False, "error": "Formato de hora inválido (HH:MM)"}, 400
 
        # -----------------------------
        # DURACIÓN
        # La duración viene del frontend (suma de procedimientos o ajuste manual).
        # Se respeta tal como llega — el usuario puede haberla modificado.
        # -----------------------------
        try:
            duracion = int(data.get("duracion", 20))
        except:
            return {"ok": False, "error": "duracion inválida"}, 400
 
        # -----------------------------
        # CALCULAR HORA FIN
        # -----------------------------
        hora_fin         = hora_inicio + timedelta(minutes=duracion)
        data["hora_fin"] = hora_fin.time().isoformat()
 
        # -----------------------------
        # VALIDAR CRUCES
        # -----------------------------
        citas = repo.listar_por_fecha(
            data["fecha"],
            medico_id=data["medico_id"],
            empresa_id=data["empresa_id"]
        )
 
        for c in citas:
            if c.get("estado") == "CANCELADA":
                continue
 
            try:
                inicio_existente = datetime.strptime(c["hora_inicio"][:5], "%H:%M")
                fin_existente    = datetime.strptime(
                    (c.get("hora_fin") or c["hora_inicio"])[:5], "%H:%M"
                )
            except:
                continue
 
            if hora_inicio < fin_existente and hora_fin > inicio_existente:
                if not data.get("es_adicional"):
                    return {
                        "ok": False,
                        "error": "El médico ya tiene una cita en ese horario"
                    }, 400
 
        # -----------------------------
        # CREAR CITA
        # -----------------------------
        # La validación de cruces de arriba (líneas ~156-181) tiene una
        # ventana de carrera: si dos personas dan "Guardar" casi al mismo
        # tiempo para el mismo médico/fecha/hora, ambas pueden pasar esa
        # validación antes de que cualquiera termine de guardar. El cierre
        # real de esa ventana está en la base de datos (índice único
        # parcial sobre medico_id+fecha+hora_inicio para citas no
        # canceladas). Si esa restricción rechaza el insert, Supabase
        # devuelve un APIError con code "23505" (unique_violation):
        # lo traducimos a un mensaje claro en vez de un 500 crudo.
        try:
            cita = repo.crear(data)
        except APIError as e:
            if e.code == "23505":
                return {
                    "ok": False,
                    "error": "Ese horario ya fue tomado por otra persona justo antes que tú. Por favor elige otro horario."
                }, 409
            raise

        if not cita:
            return {"ok": False, "error": "No se pudo crear la cita"}, 500
 
        # -----------------------------
        # GUARDAR PROCEDIMIENTOS
        # Solo se insertan si vienen en el payload.
        # -----------------------------
        if procedimientos:
            from repositories import hc_cita_procedimientos_repo
            hc_cita_procedimientos_repo.crear_bulk(cita["id"], procedimientos)

        # -----------------------------
        # CORREO AL PACIENTE (mejor esfuerzo -- si falla, no afecta la
        # cita que ya se guardó; email_service nunca lanza excepción).
        # -----------------------------
        try:
            detalle = repo.obtener_detalle(cita["id"], empresa_id=empresa)
            if detalle:
                email_service.enviar_cita_creada(_enriquecer_para_correo(detalle), request.host_url)
        except Exception as e:
            print(f"[api_crear_cita] No se pudo enviar el correo de cita creada: {e}")

        return {"ok": True, "data": cita}
 
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: CAMBIAR ESTADO
# --------------------------------------------------

@bp_citas.route("/api/estado", methods=["POST"])
@login_required
@requiere_permiso("citas", "edit")
def api_estado():
    try:
        data = request.get_json(force=True, silent=True) or {}

        cita_id = data.get("cita_id")
        estado = data.get("estado")

        if not cita_id or not estado:
            return {"ok": False, "error": "cita_id y estado son requeridos"}, 400

        # Validar estado permitido. CANCELADA queda fuera a propósito: cancelar
        # tiene su propio endpoint (/api/cancelar) con su propio permiso
        # (Eliminar), así que alguien con solo permiso de Editar no puede
        # colarse por aquí para cancelar una cita.
        estados_validos = {"PENDIENTE", "CONFIRMADA", "EN_ATENCION", "FINALIZADA", "FACTURADA"}
        if estado not in estados_validos:
            return {"ok": False, "error": f"Estado inválido. Use: {', '.join(estados_validos)}"}, 400

        repo.cambiar_estado(cita_id, estado)

        # Correo al paciente solo cuando el personal confirma manualmente
        # (por ejemplo, el paciente llamó). Los demás estados de este
        # endpoint son internos (iniciar atención, finalizar, facturar)
        # y no le interesan al paciente por correo.
        if estado == "CONFIRMADA":
            try:
                detalle = repo.obtener_detalle(cita_id)
                if detalle:
                    email_service.enviar_cita_confirmada(_enriquecer_para_correo(detalle))
            except Exception as e:
                print(f"[api_estado] No se pudo enviar el correo de cita confirmada: {e}")

        return {"ok": True, "msg": f"Estado actualizado a {estado}"}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: ACTUALIZAR CITA
# --------------------------------------------------

@bp_citas.route("/api/actualizar/<int:cita_id>", methods=["PUT"])
@login_required
@requiere_permiso("citas", "edit")
def api_actualizar_cita(cita_id):
    try:
        data = request.get_json(force=True, silent=True) or {}

        if not data:
            return {"ok": False, "error": "No hay datos para actualizar"}, 400

        # No permitir cambiar empresa_id ni id
        data.pop("empresa_id", None)
        data.pop("id", None)

        resultado = repo.actualizar(cita_id, data)

        return {"ok": True, "data": resultado}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: ELIMINAR CITA (soft delete vía estado)
# --------------------------------------------------

@bp_citas.route("/api/motivos-cancelacion")
@login_required
def api_motivos_cancelacion():
    try:
        from repositories import hc_motivos_cancelacion_repo as repo_motivos
        return {"ok": True, "data": repo_motivos.listar_activos()}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@bp_citas.route("/api/cancelar/<int:cita_id>", methods=["POST"])
@login_required
@requiere_permiso("citas", "delete")
def api_cancelar_cita(cita_id):
    try:
        body = request.get_json(force=True, silent=True) or {}

        # -----------------------------
        # MOTIVO DE CANCELACIÓN — obligatorio, para el reporte de citas
        # canceladas. Se valida contra la maestra en vez de aceptar
        # cualquier texto, para que el reporte agrupe de forma confiable.
        # -----------------------------
        try:
            motivo_id = int(body.get("motivo_cancelacion_id"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Debe indicar el motivo de cancelación"}, 400

        from repositories import hc_motivos_cancelacion_repo as repo_motivos
        motivos_validos = {m["id"] for m in repo_motivos.listar_activos()}
        if motivo_id not in motivos_validos:
            return {"ok": False, "error": "Motivo de cancelación inválido"}, 400

        repo.cambiar_estado(cita_id, "CANCELADA", extra={"motivo_cancelacion_id": motivo_id})

        try:
            detalle = repo.obtener_detalle(cita_id)
            if detalle:
                email_service.enviar_cita_cancelada(_enriquecer_para_correo(detalle))
        except Exception as e:
            print(f"[api_cancelar_cita] No se pudo enviar el correo de cita cancelada: {e}")

        return {"ok": True, "msg": "Cita cancelada"}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: REPROGRAMAR CITA
# --------------------------------------------------

@bp_citas.route("/api/motivos-reprogramacion")
@login_required
def api_motivos_reprogramacion():
    try:
        from repositories import hc_motivos_reprogramacion_repo as repo_motivos_reprog
        return {"ok": True, "data": repo_motivos_reprog.listar_activos()}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@bp_citas.route("/api/reprogramar/<int:cita_id>", methods=["POST"])
@login_required
@requiere_permiso("citas", "edit")
def api_reprogramar_cita(cita_id):
    try:
        data = request.get_json(force=True, silent=True) or {}

        nueva_fecha           = (data.get("nueva_fecha") or "").strip()
        nueva_hora_inicio_str = (data.get("nueva_hora_inicio") or "").strip()

        if not nueva_fecha or not nueva_hora_inicio_str:
            return {"ok": False, "error": "nueva_fecha y nueva_hora_inicio son requeridos"}, 400

        try:
            datetime.strptime(nueva_fecha, "%Y-%m-%d")
        except ValueError:
            return {"ok": False, "error": "Formato de fecha inválido (YYYY-MM-DD)"}, 400

        try:
            nueva_hora_inicio = datetime.strptime(nueva_hora_inicio_str, "%H:%M")
        except ValueError:
            return {"ok": False, "error": "Formato de hora inválido (HH:MM)"}, 400

        # -----------------------------
        # MOTIVO DE REPROGRAMACIÓN — obligatorio, validado contra la maestra
        # (mismo patrón que el motivo de cancelación).
        # -----------------------------
        try:
            motivo_id = int(data.get("motivo_reprogramacion_id"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Debe indicar el motivo de reprogramación"}, 400

        from repositories import hc_motivos_reprogramacion_repo as repo_motivos_reprog
        motivos_validos = {m["id"] for m in repo_motivos_reprog.listar_activos()}
        if motivo_id not in motivos_validos:
            return {"ok": False, "error": "Motivo de reprogramación inválido"}, 400

        cita_actual = repo.obtener(cita_id)
        if not cita_actual:
            return {"ok": False, "error": "Cita no encontrada"}, 404

        # Solo se pueden reprogramar citas que todavía no han ocurrido
        if cita_actual.get("estado") not in ("PENDIENTE", "CONFIRMADA"):
            return {
                "ok": False,
                "error": f"No se puede reprogramar una cita en estado {cita_actual.get('estado')}"
            }, 400

        # La duración se conserva igual a la que ya tenía la cita
        try:
            hora_inicio_actual = datetime.strptime(cita_actual["hora_inicio"][:5], "%H:%M")
            hora_fin_actual = datetime.strptime(
                (cita_actual.get("hora_fin") or cita_actual["hora_inicio"])[:5], "%H:%M"
            )
            duracion = int((hora_fin_actual - hora_inicio_actual).total_seconds() // 60) or 20
        except Exception:
            duracion = 20

        nueva_hora_fin = nueva_hora_inicio + timedelta(minutes=duracion)

        # -----------------------------
        # VALIDAR CRUCES en la nueva fecha/hora (mismo médico), excluyendo
        # la propia cita que se está moviendo.
        # -----------------------------
        citas_dia = repo.listar_por_fecha(
            nueva_fecha,
            medico_id=cita_actual["medico_id"],
            empresa_id=cita_actual["empresa_id"],
        )
        for c in citas_dia:
            if c.get("id") == cita_id or c.get("estado") == "CANCELADA":
                continue
            try:
                inicio_existente = datetime.strptime(c["hora_inicio"][:5], "%H:%M")
                fin_existente = datetime.strptime(
                    (c.get("hora_fin") or c["hora_inicio"])[:5], "%H:%M"
                )
            except Exception:
                continue
            if nueva_hora_inicio < fin_existente and nueva_hora_fin > inicio_existente:
                if not cita_actual.get("es_adicional"):
                    return {
                        "ok": False,
                        "error": "El médico ya tiene una cita en ese horario"
                    }, 400

        usuario_sesion = session.get("user") or {}
        usuario_reprogramacion = (
            usuario_sesion.get("full_name") or usuario_sesion.get("username") or None
        )

        try:
            resultado = repo.reprogramar(
                cita_id,
                nueva_fecha=nueva_fecha,
                nueva_hora_inicio=nueva_hora_inicio.time().isoformat(),
                nueva_hora_fin=nueva_hora_fin.time().isoformat(),
                motivo_reprogramacion_id=motivo_id,
                usuario_reprogramacion=usuario_reprogramacion,
            )
        except APIError as e:
            if e.code == "23505":
                return {
                    "ok": False,
                    "error": "Ese horario ya fue tomado por otra persona justo antes que tú. Por favor elige otro horario."
                }, 409
            raise

        try:
            detalle = repo.obtener_detalle(cita_id)
            if detalle:
                email_service.enviar_cita_reprogramada(_enriquecer_para_correo(detalle), request.host_url)
        except Exception as e:
            print(f"[api_reprogramar_cita] No se pudo enviar el correo de cita reprogramada: {e}")

        return {"ok": True, "data": resultado}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# PÁGINA PÚBLICA: el paciente confirma o cancela su cita desde el
# enlace del correo, sin iniciar sesión. Estas rutas NO llevan
# @login_required a propósito -- el control de acceso normal
# (gate_permisos_por_modulo en app.py) no bloquea peticiones sin sesión
# activa, así que quedan abiertas tal como se necesita aquí.
# --------------------------------------------------

# Motivo fijo con el que queda la cita cuando el propio paciente la
# cancela desde el correo (en vez de pedirle elegir uno de la maestra
# interna, que está pensada para el personal de la clínica). Debe existir
# en hc_motivos_cancelacion -- lo trae el SQL de esta funcionalidad.
MOTIVO_CANCELACION_PACIENTE = "Cancelada por el paciente (autogestión web)"

# Estados de una cita que ya no se pueden tocar desde el enlace público
# (ya pasó, ya se atendió, ya se facturó o ya está cancelada).
ESTADOS_NO_EDITABLES_PUBLICO = ("CANCELADA", "FINALIZADA", "EN_ATENCION", "FACTURADA")


def _token_dentro_de_plazo(cita: dict) -> bool:
    """
    El enlace deja de funcionar cuando falta menos de X horas para la
    cita -- X es el parámetro configurable en Configuración → Parámetros
    generales (hc_parametros_sistema.horas_limite_confirmacion_cita).
    Si por algún motivo no se puede calcular la fecha/hora de la cita,
    no bloqueamos por esto (mejor pecar de permisivos que romper el
    enlace por un dato mal formado).
    """
    from repositories import hc_parametros_repo

    try:
        horas_limite = float(hc_parametros_repo.obtener("horas_limite_confirmacion_cita", "24"))
    except (TypeError, ValueError):
        horas_limite = 24.0

    try:
        fecha_hora_cita = datetime.strptime(
            f"{cita['fecha']} {(cita.get('hora_inicio') or '00:00')[:5]}", "%Y-%m-%d %H:%M"
        )
    except Exception:
        return True

    limite = fecha_hora_cita - timedelta(hours=horas_limite)
    return datetime.now() < limite


def _cargar_cita_publica(token):
    """Devuelve (cita_detalle, error) para una vista pública dado un token."""
    cita_basica = repo.obtener_por_token(token)
    if not cita_basica:
        return None, "no_encontrado"

    detalle = repo.obtener_detalle(cita_basica["id"], empresa_id=cita_basica["empresa_id"])
    if not detalle:
        return None, "no_encontrado"

    return detalle, None


@bp_citas.route("/publico/<token>", methods=["GET"])
def publico_ver_cita(token):
    detalle, error = _cargar_cita_publica(token)

    if error:
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido=error)

    if detalle.get("estado") in ESTADOS_NO_EDITABLES_PUBLICO:
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="estado_no_editable", cita=detalle)

    if not _token_dentro_de_plazo(detalle):
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="fuera_de_plazo", cita=detalle)

    return render_template("citas/publico_cita.html", valido=True, cita=detalle, token=token)


@bp_citas.route("/publico/<token>/confirmar", methods=["POST"])
def publico_confirmar_cita(token):
    detalle, error = _cargar_cita_publica(token)

    if error:
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido=error)

    if detalle.get("estado") not in ("PENDIENTE", "CONFIRMADA"):
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="estado_no_editable", cita=detalle)

    if not _token_dentro_de_plazo(detalle):
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="fuera_de_plazo", cita=detalle)

    repo.cambiar_estado(detalle["id"], "CONFIRMADA")
    detalle_actualizado, _ = _cargar_cita_publica(token)

    return render_template("citas/publico_cita.html", valido=True, cita=detalle_actualizado, accion_realizada="confirmada")


@bp_citas.route("/publico/<token>/cancelar", methods=["POST"])
def publico_cancelar_cita(token):
    detalle, error = _cargar_cita_publica(token)

    if error:
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido=error)

    if detalle.get("estado") not in ("PENDIENTE", "CONFIRMADA"):
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="estado_no_editable", cita=detalle)

    if not _token_dentro_de_plazo(detalle):
        return render_template("citas/publico_cita.html", valido=False, motivo_invalido="fuera_de_plazo", cita=detalle)

    from repositories import hc_motivos_cancelacion_repo as repo_motivos
    motivo_paciente = next(
        (m for m in repo_motivos.listar() if m.get("nombre") == MOTIVO_CANCELACION_PACIENTE),
        None,
    )
    if not motivo_paciente:
        return render_template(
            "citas/publico_cita.html", valido=True, cita=detalle, token=token,
            error="No se pudo procesar la cancelación en este momento. Por favor comunícate con la clínica.",
        )

    repo.cambiar_estado(detalle["id"], "CANCELADA", extra={"motivo_cancelacion_id": motivo_paciente["id"]})
    detalle_actualizado, _ = _cargar_cita_publica(token)

    return render_template("citas/publico_cita.html", valido=True, cita=detalle_actualizado, accion_realizada="cancelada")


# blueprints/citas/routes.py  (agregar al final)

@bp_citas.route("/api/pacientes")
@login_required
def api_pacientes():
    try:
        from repositories import hc_pacientes_repo as pac_repo
        
        q = request.args.get("q", "")
        limite = request.args.get("limite", 15, type=int)
        
        # Si hay búsqueda, usar buscar. Si no, listar
        if q:
            data = pac_repo.buscar(q=q, limite=limite)
        else:
            data = pac_repo.listar(completo=False)
            
        return {"ok": True, "data": data}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    
# blueprints/citas/routes.py  (agregar al final)

@bp_citas.route("/api/medicos")
@login_required
def api_medicos():
    try:
        from repositories import hc_profesionales_repo as med_repo
        
        data = med_repo.listar()
        return {"ok": True, "data": data}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    
@bp_citas.route("/api/sedes")
@login_required
def api_sedes():
    try:
        from repositories import hc_sedes_repo as sede_repo

        data = sede_repo.listar()
        return {"ok": True, "data": data}
    
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    

# ------------------------------------------------------------------
# GET /citas/api/medico/<medico_id>/procedimientos
# Devuelve los CUPS asignados al médico (para poblar el buscador)
# ------------------------------------------------------------------
@bp_citas.route("/api/medico/<int:medico_id>/procedimientos", methods=["GET"])
@login_required
def api_procedimientos_medico(medico_id):
    try:
        from repositories import prof_procedimientos_repository as prof_cups
 
        data = prof_cups.listar_por_profesional(medico_id)
 
        resultado = []
        for row in data:
            cups = row.get("hc_cups") or {}
            resultado.append({
                "id":          row["id"],
                "cups_id":     row["cups_id"],
                "codigo":      cups.get("codigo", ""),
                "descripcion": cups.get("descripcion", ""),
                "duracion_min": row.get("duracion_min", 20),
            })
 
        return jsonify({"ok": True, "data": resultado})
 
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
 



@bp_citas.route("/api/detalle/<int:cita_id>", methods=["GET"])
@login_required
def api_detalle_cita(cita_id):
    try:
        detalle = repo.obtener_detalle(cita_id)
 
        if not detalle:
            return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
 
        return jsonify({"ok": True, "data": detalle})
 
    except Exception as e:
        import traceback
        print("ERROR /api/detalle:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500
    


def fmt_fecha(f):
    if not f:
        return "—"
    DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        d = datetime.strptime(f, "%Y-%m-%d")
        return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"
    except Exception:
        return str(f)


def fmt_hora(h):
    if not h:
        return "—"
    try:
        t = datetime.strptime(str(h)[:5], "%H:%M")
        hora = t.hour % 12 or 12
        ampm = "AM" if t.hour < 12 else "PM"
        return f"{hora}:{t.strftime('%M')} {ampm}"
    except Exception:
        return str(h)[:5]


def fmt_fecha_hora_creacion(f):
    """Formatea un timestamp completo (fecha_creacion) como 'dd/mm/aaaa hh:mm AM/PM'."""
    if not f:
        return None
    try:
        texto = str(f).replace("Z", "")
        # Soporta con o sin microsegundos/segundos
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                d = datetime.strptime(texto[:26], fmt)
                break
            except ValueError:
                continue
        else:
            return str(f)
        hora = d.hour % 12 or 12
        ampm = "AM" if d.hour < 12 else "PM"
        return f"{d.day:02d}/{d.month:02d}/{d.year} {hora}:{d.strftime('%M')} {ampm}"
    except Exception:
        return str(f)


def _enriquecer_para_correo(detalle: dict) -> dict:
    """
    Agrega al detalle de una cita los campos de fecha/hora ya formateados
    en español (mismo formato que usa la vista HTML/PDF), listos para
    usar directamente en las plantillas de correo -- ahí no queremos
    lógica de formato, solo mostrar el dato.
    """
    enriquecido = dict(detalle)
    enriquecido["fecha_larga"] = fmt_fecha(detalle.get("fecha"))
    enriquecido["hora_rango"] = (
        f"{fmt_hora(detalle.get('hora_inicio'))} – {fmt_hora(detalle.get('hora_fin'))}"
        if detalle.get("hora_fin") else fmt_hora(detalle.get("hora_inicio"))
    )
    if detalle.get("fecha_anterior"):
        enriquecido["fecha_anterior_larga"] = fmt_fecha(detalle.get("fecha_anterior"))
        enriquecido["hora_anterior_rango"] = (
            f"{fmt_hora(detalle.get('hora_inicio_anterior'))} – {fmt_hora(detalle.get('hora_fin_anterior'))}"
            if detalle.get("hora_fin_anterior") else fmt_hora(detalle.get("hora_inicio_anterior"))
        )
    return enriquecido


def _obtener_datos_cita(cita_id: int) -> dict:
    """Centraliza obtención de datos para cita (DRY)."""
    datos = repo.obtener_datos_pdf(cita_id)
    if not datos:
        raise ValueError("Cita no encontrada")

    # Logo como base64 (elimina dependencia de filesystem en producción)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logo_path = os.path.join(base_dir, "static", "img", "vitacore", "logo_vitacore.png")

    return {
        **datos,
        "cita_id": cita_id,
        "logo_b64": AssetHelper.img_to_base64(logo_path),
        "fecha_larga": fmt_fecha(datos.get("fecha")),
        "hora_inicio": fmt_hora(datos.get("hora_inicio")),
        "hora_fin": fmt_hora(datos.get("hora_fin")),
        "fecha_creacion": fmt_fecha_hora_creacion(datos.get("fecha_creacion")),
    }


# ============================================
# ENDPOINTS
# ============================================

@bp_citas.route("/api/detalle/<int:cita_id>/html", methods=["GET"])
@login_required
def api_html_cita(cita_id):
    """
    Devuelve HTML para previsualización en navegador.
    El médico/admin ve esto y decide si imprimir o descargar PDF.
    """
    try:
        ctx = _obtener_datos_cita(cita_id)
        return render_template("citas/pdf_cita.html", **ctx)
    
    except ValueError:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    except Exception as e:
        import traceback
        print("ERROR /html:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_citas.route("/api/detalle/<int:cita_id>/pdf", methods=["GET"])
@login_required
def api_pdf_cita(cita_id):
    """
    Genera PDF profesional vía Playwright (Chromium headless).
    MISMO template que /html, pero renderizado a PDF.
    """
    try:
        ctx = _obtener_datos_cita(cita_id)
        
        # Renderizar MISMO template
        html_str = render_template("citas/pdf_cita.html", **ctx)
        
        # Generar PDF con Playwright
        pdf_bytes = PDFService.sync_html_to_pdf(
            html_content=html_str,
            wait_for_network=False  # todo es inline/base64, no esperamos red
        )
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,           # True si quieres forzar descarga
            download_name=f"cita_{cita_id}_{ctx.get('paciente_doc', 'paciente')}.pdf"
        )

    except ValueError:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    except Exception as e:
        import traceback
        print("ERROR /pdf:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500



# --------------------------------------------------
# API: CLIENTES (para cascada en modal de cita)     
# --------------------------------------------------

@bp_citas.route("/api/clientes")
@login_required
def api_clientes():
    """Lista todos los clientes activos para el select del modal."""
    try:
        from repositories import hc_clientes_repo as cli_repo

        data = cli_repo.listar()
        # Filtrar solo activos
        activos = [c for c in data if c.get("estado") == "ACTIVO"]
        return jsonify({"ok": True, "data": activos})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: CONTRATOS POR CLIENTE
# --------------------------------------------------

@bp_citas.route("/api/cliente/<int:cliente_id>/contratos")
@login_required
def api_contratos_cliente(cliente_id):
    """Lista los contratos activos de un cliente específico."""
    try:
        from repositories import hc_contratos_repo as cont_repo

        todos = cont_repo.listar_por_cliente(cliente_id)
        # Filtrar solo activos
        activos = [c for c in todos if c.get("estado") == "ACTIVO"]
        return jsonify({"ok": True, "data": activos})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: TARIFAS DEL MANUAL TARIFARIO (por contrato)
# --------------------------------------------------

@bp_citas.route("/api/contrato/<int:contrato_id>/tarifas")
@login_required
def api_tarifas_contrato(contrato_id):
    """
    Dado un contrato, busca su manual_tarifario (por nombre)
    y devuelve los procedimientos con tarifas de ese manual.
    El valor_total depende del tipo_contrato:
      - PAQUETE → valor_paquete
      - EVENTO  → valor_procedimiento + valor_suministro
    """
    try:
        from repositories import hc_contratos_repo as cont_repo
        from repositories import hc_manuales_repo as man_repo
 
        # 1. Obtener el contrato
        contrato = cont_repo.obtener(contrato_id)
        if not contrato:
            return jsonify({"ok": False, "error": "Contrato no encontrado"}), 404
 
        nombre_manual = (contrato.get("manual_tarifario") or "").strip()
        tipo_contrato = (contrato.get("tipo_contrato") or "EVENTO").upper()
 
        if not nombre_manual:
            return jsonify({
                "ok": True,
                "data": [],
                "msg": "El contrato no tiene manual tarifario asignado"
            })
 
        # 2. Buscar el manual por nombre
        from services.supabase_service import get_supabase_public
        sb = get_supabase_public()
 
        res_manual = (
            sb.table("hc_manuales_tarifarios")
            .select("id, nombre, codigo")
            .eq("nombre", nombre_manual)
            .limit(1)
            .execute()
        )
 
        if not res_manual.data:
            return jsonify({
                "ok": True,
                "data": [],
                "msg": f"No se encontró el manual '{nombre_manual}'"
            })
 
        manual = res_manual.data[0]
        manual_id = manual["id"]
 
        # 3. Traer procedimientos del manual con tarifas
        procedimientos = man_repo.listar_procedimientos(manual_id)
 
        # 4. Formatear para el frontend
        resultado = []
        for p in procedimientos:
            vp  = float(p.get("valor_paquete") or 0)
            vpr = float(p.get("valor_procedimiento") or 0)
            vs  = float(p.get("valor_suministro") or 0)
 
            # Lógica según tipo de contrato
            if tipo_contrato == "PAQUETE":
                valor_total = vp
            else:
                valor_total = vpr + vs
 
            resultado.append({
                "id":                   p["id"],
                "manual_id":            manual_id,
                "manual_nombre":        manual["nombre"],
                "cod_proc":             p.get("cod_proc", ""),
                "nombre_procedimiento": p.get("nombre_procedimiento", ""),
                "cups_codigo":          p.get("cups_codigo", ""),
                "cups_descripcion":     p.get("cups_descripcion", ""),
                "tipo_contrato":        tipo_contrato,
                "valor_paquete":        vp,
                "valor_procedimiento":  vpr,
                "valor_suministro":     vs,
                "valor_total":          valor_total,
            })
 
        return jsonify({
            "ok": True,
            "tipo_contrato": tipo_contrato,
            "manual": {
                "id": manual_id,
                "nombre": manual["nombre"],
                "codigo": manual.get("codigo", ""),
            },
            "data": resultado,
        })
 
    except Exception as e:
        import traceback
        print("ERROR /api/contrato/tarifas:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: BUSCAR TARIFA DE UN CUPS ESPECÍFICO EN UN CONTRATO
# --------------------------------------------------

@bp_citas.route("/api/contrato/<int:contrato_id>/tarifa-cups/<int:cups_id>")
@login_required
def api_tarifa_cups(contrato_id, cups_id):
    """
    Busca la tarifa de un CUPS específico en el manual del contrato.
    El valor_total depende del tipo_contrato:
      - PAQUETE → valor_paquete
      - EVENTO  → valor_procedimiento + valor_suministro
    """
    try:
        from repositories import hc_contratos_repo as cont_repo
        from services.supabase_service import get_supabase_public
 
        sb = get_supabase_public()
 
        # 1. Obtener contrato y su manual
        contrato = cont_repo.obtener(contrato_id)
        if not contrato:
            return jsonify({"ok": False, "error": "Contrato no encontrado"}), 404
 
        nombre_manual = (contrato.get("manual_tarifario") or "").strip()
        tipo_contrato = (contrato.get("tipo_contrato") or "EVENTO").upper()
 
        if not nombre_manual:
            return jsonify({"ok": True, "data": None, "msg": "Sin manual tarifario"})
 
        # 2. Buscar manual por nombre
        res_manual = (
            sb.table("hc_manuales_tarifarios")
            .select("id")
            .eq("nombre", nombre_manual)
            .limit(1)
            .execute()
        )
 
        if not res_manual.data:
            return jsonify({"ok": True, "data": None, "msg": f"Manual '{nombre_manual}' no encontrado"})
 
        manual_id = res_manual.data[0]["id"]
 
        # 3. Buscar el procedimiento en el manual por cups_id
        res_proc = (
            sb.table("hc_mt_procedimientos")
            .select("*")
            .eq("manual_id", manual_id)
            .eq("cups_id", cups_id)
            .limit(1)
            .execute()
        )
 
        if not res_proc.data:
            return jsonify({
                "ok": True,
                "data": None,
                "msg": "Procedimiento no encontrado en el manual tarifario"
            })
 
        p   = res_proc.data[0]
        vp  = float(p.get("valor_paquete") or 0)
        vpr = float(p.get("valor_procedimiento") or 0)
        vs  = float(p.get("valor_suministro") or 0)
 
        # Lógica según tipo de contrato
        if tipo_contrato == "PAQUETE":
            valor_total = vp
        else:
            valor_total = vpr + vs
 
        return jsonify({
            "ok": True,
            "data": {
                "tipo_contrato":       tipo_contrato,
                "valor_paquete":       vp,
                "valor_procedimiento": vpr,
                "valor_suministro":    vs,
                "valor_total":         valor_total,
            }
        })
 
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
