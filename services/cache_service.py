"""
Caché en memoria para los catálogos.

Qué problema resuelve: las pantallas de formulario piden siempre los
mismos catálogos —sedes, especialidades, médicos, tipos de documento,
EPS, municipios— y cada uno es un viaje a Supabase de unos 250 ms.
"Nueva evolución" hacía nueve viajes para pintar una pantalla, y ocho
traían datos que no cambian de un minuto a otro.

Cómo funciona: cada función de lectura marcada con @cacheado guarda su
resultado unos minutos. Cuando alguien crea o edita un registro de ese
catálogo, la escritura llama a invalidar() y la siguiente lectura
vuelve a la base.

Tres cosas a tener en cuenta:

  - La caché vive en el proceso. Con varios workers (gunicorn -w 4),
    cada uno tiene la suya; un cambio puede tardar hasta TTL segundos
    en verse en todos. Para catálogos es aceptable.
  - La clave incluye la empresa de la sesión, así que una IPS nunca ve
    el catálogo de otra.
  - Devuelve el MISMO objeto guardado, no una copia. Quien lo reciba no
    debe modificarlo; si una vista necesita ordenar o filtrar, que
    trabaje sobre una copia propia.
"""

import functools
import time

TTL_POR_DEFECTO = 300          # 5 minutos

_cache = {}                    # clave -> (valor, momento)
_aciertos = 0
_fallos = 0


def _empresa_actual():
    try:
        from flask import session, has_request_context
        if has_request_context():
            return session.get("empresa_id")
    except Exception:
        pass
    return None


def cacheado(segundos: int = TTL_POR_DEFECTO):
    """
    Guarda el resultado de una función de lectura.

        @cacheado()
        def listar_select():
            ...
    """
    def decorador(func):
        espacio = f"{func.__module__.split('.')[-1]}.{func.__name__}"

        @functools.wraps(func)
        def envoltura(*args, **kwargs):
            global _aciertos, _fallos
            try:
                clave = (espacio, _empresa_actual(), args,
                         tuple(sorted(kwargs.items())))
                hash(clave)
            except TypeError:
                # argumentos no hashables: se consulta sin cachear
                return func(*args, **kwargs)

            guardado = _cache.get(clave)
            if guardado and (time.time() - guardado[1]) < segundos:
                _aciertos += 1
                return guardado[0]

            valor = func(*args, **kwargs)
            _cache[clave] = (valor, time.time())
            _fallos += 1
            return valor

        envoltura._espacio_cache = espacio
        return envoltura
    return decorador


def invalidar(prefijo: str = ""):
    """
    Borra lo cacheado. Sin argumento borra todo; con un prefijo
    ("hc_sedes_repo") borra solo lo de ese catálogo.

    Se llama desde las funciones que escriben, para que el usuario que
    acaba de crear una sede la vea de inmediato.
    """
    if not prefijo:
        _cache.clear()
        return

    for clave in [k for k in _cache if str(k[0]).startswith(prefijo)]:
        _cache.pop(clave, None)


def estadisticas():
    """Para medir si la caché está sirviendo."""
    total = _aciertos + _fallos
    return {
        "entradas": len(_cache),
        "aciertos": _aciertos,
        "fallos": _fallos,
        "tasa_acierto": round(_aciertos * 100 / total) if total else 0,
    }
