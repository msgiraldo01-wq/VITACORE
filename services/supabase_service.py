"""
Acceso a Supabase.

Antes este módulo creaba un cliente NUEVO en cada llamada, y como cada
repositorio lo pide por su cuenta, una sola pantalla abría varias
conexiones a Supabase, cada una con su negociación TLS completa. Medido
sobre esta base: "Nueva evolución" abría 9 clientes y gastaba 4,4
segundos solo en crearlos; "Ver paciente", 3 clientes y 1,6 segundos
(el 26 % de todo lo que tardaba la pantalla).

Ahora el cliente se crea una vez por proceso y se reutiliza. Dos
detalles que importan:

  - Se recicla cada CICLO_VIDA segundos. Una conexión que lleva horas
    quieta suele estar cerrada del otro lado y falla al reusarla; con el
    reciclaje se abre una nueva de vez en cuando y eso se evita.

  - El cliente de AUTENTICACIÓN no se comparte nunca. `sign_in_with_password`
    guarda la sesión del usuario dentro del cliente, así que reutilizarlo
    mezclaría la sesión de una persona con la de otra. Para eso está
    get_supabase_auth(), que siempre devuelve uno nuevo.
"""

import time

from flask import current_app
from supabase import create_client

# Cada cuánto se desecha el cliente y se abre otro (segundos).
CICLO_VIDA = 600

_clientes = {}          # (url, key) -> (cliente, momento_de_creacion)


def _cliente(url: str, key: str):
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o la llave correspondiente en el archivo .env"
        )

    clave = (url, key)
    guardado = _clientes.get(clave)
    if guardado and (time.time() - guardado[1]) < CICLO_VIDA:
        return guardado[0]

    cliente = create_client(url, key)
    _clientes[clave] = (cliente, time.time())
    return cliente


def get_supabase_public():
    """Cliente con la llave anónima, para lectura/escritura de datos."""
    return _cliente(
        current_app.config["SUPABASE_URL"],
        current_app.config["SUPABASE_ANON_KEY"],
    )


def get_supabase_admin():
    """Cliente con la llave de servicio. Es el que usa casi todo el proyecto."""
    return _cliente(
        current_app.config["SUPABASE_URL"],
        current_app.config["SUPABASE_SERVICE_ROLE_KEY"],
    )


def get_supabase_auth(url=None, key=None):
    """
    Cliente NUEVO cada vez, para iniciar sesión o cambiar contraseña.

    No se comparte a propósito: el cliente guarda adentro la sesión del
    usuario que acaba de autenticarse, y compartirlo haría que la sesión
    de uno viajara en las peticiones de otro.

    `url` y `key` se aceptan para poder crearlo desde un hilo, donde no
    hay contexto de aplicación y `current_app` no existe. El login los
    lee antes de lanzar el hilo y los pasa aquí.
    """
    return create_client(
        url or current_app.config["SUPABASE_URL"],
        key or current_app.config["SUPABASE_ANON_KEY"],
    )


def reiniciar_clientes():
    """Desecha los clientes guardados. Para pruebas, o si se cambia el .env
    sin reiniciar el proceso."""
    _clientes.clear()
