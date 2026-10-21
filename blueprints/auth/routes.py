import threading
import time

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app)
from repositories.auth_repository import obtener_perfil_por_username
from repositories.auth_historial_repo import registrar_intento, listar_historial_usuario
from services.supabase_service import get_supabase_auth, get_supabase_admin
from services import sesion_service
from services.geoip_service import obtener_ip_cliente, localizar_ip, parsear_user_agent
from . decorators import login_required

bp_auth = Blueprint("auth", __name__, url_prefix="/auth")


def _cliente_auth_adelantado():
    """
    Empieza a crear el cliente de autenticación sin esperar a que esté.

    Crear ese cliente abre una conexión TLS nueva con Supabase y cuesta
    unos 260 ms medidos, pero no depende de nada del usuario: solo de la
    URL y la llave. Lanzándolo aquí, la conexión se abre mientras la
    consulta del perfil va y vuelve, y para cuando toca autenticar ya
    está listo. Antes los dos tiempos se sumaban.

    `current_app` no existe dentro del hilo, así que la configuración se
    lee aquí y se pasa por parámetro.

    Devuelve una función que entrega el cliente, esperándolo si hiciera
    falta.
    """
    url = current_app.config["SUPABASE_URL"]
    key = current_app.config["SUPABASE_ANON_KEY"]
    caja = {}

    def crear():
        try:
            caja["cliente"] = get_supabase_auth(url, key)
        except Exception as e:          # la red puede fallar aquí igual
            caja["error"] = e

    hilo = threading.Thread(target=crear, daemon=True)
    hilo.start()

    def recoger():
        hilo.join(timeout=15)
        if "error" in caja:
            raise caja["error"]
        # Si el hilo no acabó a tiempo, se crea aquí y ya: será tan lento
        # como antes, pero un login no se puede colgar por culpa de una
        # optimización.
        return caja.get("cliente") or get_supabase_auth(url, key)

    return recoger


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("inicio"))

    if request.method == "GET":
        # A quien lo sacó el servidor hay que decírselo, y decirle cuál
        # de los dos límites fue. Antes salía "Sesión cerrada
        # correctamente", como si se hubiera salido él.
        caducada = request.args.get("caducada")
        if caducada == "inactividad":
            flash("Cerramos tu sesión por inactividad. Vuelve a entrar.", "warning")
        elif caducada == "jornada":
            flash("Tu sesión alcanzó el máximo permitido. Vuelve a entrar.", "warning")
        return render_template("auth/login.html")

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Debes ingresar usuario y contraseña.", "warning")
        return render_template("auth/login.html")

    # El cliente de autenticación se empieza a crear YA, antes de
    # consultar el perfil, para que las dos esperas se solapen.
    recoger_cliente_auth = _cliente_auth_adelantado()

    # 📍 Auditoría de accesos: datos del intento, calculados una sola
    # vez porque no cambian entre las distintas ramas de abajo.
    ip_address = obtener_ip_cliente(request)
    user_agent = request.headers.get("User-Agent", "")
    dispositivo = parsear_user_agent(user_agent)
    pais, ciudad = localizar_ip(ip_address)

    app_obj = current_app._get_current_object()

    def _registrar(exito, motivo, user_id=None):
        """
        Deja constancia del intento.

        Los intentos FALLIDOS se escriben antes de responder, como
        siempre: son los que sirven para detectar que alguien está
        probando contraseñas, y a quien acaba de equivocarse no le hace
        falta que le ahorremos 200 ms a cambio de arriesgar la huella.

        Los EXITOSOS se escriben en segundo plano: el usuario está
        esperando a entrar, y de ese registro ya sabemos lo esencial
        porque queda en la sesión. Si el proceso muriera justo entre
        responder y escribir, se perdería ese registro -- por eso solo
        se hace así donde perderlo no duele.
        """
        datos = dict(
            username=username,
            exito=exito,
            motivo=motivo,
            user_id=user_id,
            ip_address=ip_address,
            pais=pais,
            ciudad=ciudad,
            dispositivo=dispositivo,
            user_agent=user_agent,
        )

        if not exito:
            registrar_intento(**datos)
            return

        def escribir():
            # El hilo no hereda el contexto de la petición, y el
            # repositorio necesita uno para leer la configuración.
            with app_obj.app_context():
                try:
                    registrar_intento(**datos)
                except Exception as e:
                    print("[AUTH] no se pudo registrar el acceso:", e)

        threading.Thread(target=escribir, daemon=True).start()

    try:
        perfil = obtener_perfil_por_username(username)

        if not perfil:
            flash("El usuario no existe.", "danger")
            _registrar(False, "usuario_no_existe")
            return render_template("auth/login.html")

        if not perfil.get("is_active", True):
            flash("Tu usuario está inactivo.", "warning")
            _registrar(False, "cuenta_inactiva", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        email = (perfil.get("email") or "").strip().lower()
        if not email:
            flash("El usuario no tiene correo configurado.", "danger")
            _registrar(False, "sin_correo_configurado", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        # 🔐 Login con Supabase. El cliente se empezó a crear al entrar
        # en la vista, así que normalmente ya está esperando aquí.
        supabase = recoger_cliente_auth()
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        user = getattr(response, "user", None)
        user_session = getattr(response, "session", None)

        if not user or not user_session:
            flash("Usuario o contraseña incorrectos.", "danger")
            _registrar(False, "credenciales_invalidas", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        # 🔥 SESSION LIMPIA (SIN roles raros)
        session["user"] = {
            "id": perfil["id"],
            "username": perfil["username"],
            "full_name": perfil.get("full_name") or "",
            "email": perfil.get("email") or "",
            "role": perfil.get("role", ""),          # 🔥 DESDE BD (legado, SUPER_ADMIN vive aquí)
            "role_id": perfil.get("role_id"),        # 🔥 NECESARIO para la matriz de permisos por módulo
            "empresa_id": perfil.get("empresa_id")   # 🔥 CLAVE MULTIEMPRESA
        }

        # 🔥 ACCESO DIRECTO (para no depender de session["user"])
        session["rol"] = perfil.get("role", "")
        session["empresa_id"] = perfil.get("empresa_id")

        session["supabase_access_token"] = user_session.access_token
        session["supabase_refresh_token"] = user_session.refresh_token

        # Las dos marcas que gobiernan la caducidad: cuándo entró (tope
        # de jornada) y cuándo se le vio por última vez (inactividad).
        # Sin ellas, app.py trata la sesión como caducada.
        ahora = time.time()
        session["inicio_sesion"] = ahora
        session["ultima_actividad"] = ahora

        _registrar(True, "ok", user_id=perfil.get("id"))

        # 🧪 DEBUG (puedes quitar después)
        print("ROL:", session.get("rol"))
        print("EMPRESA:", session.get("empresa_id"))

        flash("Bienvenido a Vitacore.", "success")

        # 👑 SUPER ADMIN → selector de empresa
        if session.get("rol") == "SUPER_ADMIN":
            return redirect("/empresa/seleccionar")

        # 🏥 USUARIO NORMAL SIN EMPRESA → error
        if not session.get("empresa_id"):
            flash("Usuario sin empresa asignada.", "warning")
            return redirect(url_for("auth.login"))

        # 🏥 USUARIO NORMAL → sistema
        return redirect("/hc")  # o url_for("inicio")

    except Exception as e:
        print("ERROR LOGIN:", e)
        flash("Usuario o contraseña incorrectos.", "danger")
        _registrar(False, "error_interno")
        return render_template("auth/login.html")


@bp_auth.route("/logout")
def logout():
    # El contador del navegador manda aquí con ?caducada=... cuando se
    # agotó el tiempo. No es lo mismo irse que ser sacado, y el mensaje
    # tiene que distinguirlo: el de caducidad lo pone la pantalla de
    # login leyendo ese mismo parámetro.
    caducada = request.args.get("caducada")
    session.clear()
    if caducada in ("inactividad", "jornada"):
        return redirect(url_for("auth.login", caducada=caducada))
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))


@bp_auth.route("/mi-perfil")
@login_required
def mi_perfil():

    if not session.get("user"):
        return redirect(url_for("auth.login"))

    user = session.get("user")
    historial = listar_historial_usuario(user.get("id"), limit=20) or []

    # Los intentos FALLIDOS van aparte y primero. Mezclados entre veinte
    # accesos correctos no los ve nadie, y son justo lo que esta pantalla
    # existe para enseñar: que alguien estuvo probando tu contraseña.
    fallidos = [h for h in historial if not h.get("exito")]
    correctos = [h for h in historial if h.get("exito")]

    # Cuál de los accesos correctos es el de ahora mismo, para poder
    # decir "este equipo" y que el resto se lea por contraste.
    ip_actual = obtener_ip_cliente(request)
    actual_id = None
    for h in correctos:
        if h.get("ip_address") == ip_actual:
            actual_id = h.get("id")
            break

    # La institución: el sistema es multiempresa y la pantalla de la
    # cuenta no decía en cuál estás.
    empresa_nombre = None
    try:
        empresa_id = session.get("empresa_id")
        if empresa_id:
            r = (get_supabase_admin()
                 .table("hc_empresas")
                 .select("razon_social,nombre_comercial")
                 .eq("id", empresa_id)
                 .limit(1)
                 .execute())
            fila = (r.data or [{}])[0]
            empresa_nombre = fila.get("nombre_comercial") or fila.get("razon_social")
    except Exception as e:
        print("[AUTH] no se pudo leer la empresa del perfil:", e)

    return render_template(
        "auth/mi_perfil.html",
        user=user,
        historial=historial,
        fallidos=fallidos,
        correctos=correctos,
        acceso_actual_id=actual_id,
        empresa_nombre=empresa_nombre,
        politica=sesion_service.politica(session.get("empresa_id")),
        entro_en=session.get("inicio_sesion"),
    )


@bp_auth.route("/cambiar-password", methods=["POST"])
@login_required
def cambiar_password():

    if not session.get("user"):
        return redirect(url_for("auth.login"))

    password_actual = request.form.get("password_actual")
    password_nueva = request.form.get("password_nueva")

    if not password_actual or not password_nueva:
        flash("Debes completar todos los campos.", "warning")
        return redirect(url_for("auth.mi_perfil"))

    try:

        email = session["user"]["email"]

        supabase = get_supabase_auth()

        # volver a autenticar
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password_actual
        })

        if not getattr(response, "user", None):
            flash("La contraseña actual es incorrecta.", "danger")
            return redirect(url_for("auth.mi_perfil"))

        access_token = response.session.access_token

        supabase.auth.update_user(
            {"password": password_nueva},
            access_token
        )

        flash("Contraseña actualizada correctamente.", "success")

    except Exception as e:
        flash(f"Error al cambiar contraseña: {str(e)}", "danger")

    return redirect(url_for("auth.mi_perfil"))