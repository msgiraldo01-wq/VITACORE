-- ============================================================
-- Migración: registro de errores de la aplicación (Soporte)
--
-- Crea la tabla donde aterrizan los errores de producción y el
-- módulo "Soporte" en la matriz de Roles y permisos, para que no
-- cualquiera que vea Configuración pueda leer trazas técnicas.
--
-- Es segura de correr más de una vez.
--
-- Correr en el SQL editor de Supabase ANTES de desplegar el código.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.app_errores (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

  -- Código que ve el usuario en pantalla y le dicta a soporte (VTC-7F3A91)
  codigo        text NOT NULL,

  -- Huella para agrupar el MISMO error repetido (tipo + ruta + línea).
  -- Si vuelve a ocurrir no se crea otra fila: se suma a 'veces'.
  huella        text NOT NULL,

  -- Contexto de quién y dónde
  empresa_id    bigint,
  usuario       text,
  usuario_id    text,
  ruta          text,
  metodo        text,
  modulo        text,

  -- El error
  tipo          text,
  mensaje       text,
  traceback     text,

  -- Del navegador (sin datos del formulario: ahí viajan datos del paciente)
  ip            text,
  user_agent    text,

  -- Gestión
  estado        text NOT NULL DEFAULT 'NUEVO',   -- NUEVO | REVISADO | IGNORADO
  notas         text,
  veces         integer NOT NULL DEFAULT 1,
  primera_vez   timestamptz NOT NULL DEFAULT now(),
  ultima_vez    timestamptz NOT NULL DEFAULT now()
);

-- Una fila por huella: así el panel muestra "este error ocurrió 23 veces"
-- en vez de 23 filas iguales.
CREATE UNIQUE INDEX IF NOT EXISTS app_errores_huella_key
  ON public.app_errores (huella);

CREATE INDEX IF NOT EXISTS app_errores_ultima_vez_idx
  ON public.app_errores (ultima_vez DESC);

CREATE INDEX IF NOT EXISTS app_errores_estado_idx
  ON public.app_errores (estado);

CREATE INDEX IF NOT EXISTS app_errores_codigo_idx
  ON public.app_errores (codigo);


-- Suma una ocurrencia a un error que ya existía. Se hace en Postgres
-- (y no leyendo + escribiendo desde Python) para que dos usuarios que
-- tropiezan con el mismo error al tiempo no se pisen el contador.
CREATE OR REPLACE FUNCTION public.app_registrar_error(
  p_codigo text, p_huella text, p_empresa_id bigint, p_usuario text,
  p_usuario_id text, p_ruta text, p_metodo text, p_modulo text,
  p_tipo text, p_mensaje text, p_traceback text, p_ip text, p_user_agent text
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
  v_codigo text;
BEGIN
  INSERT INTO public.app_errores (
    codigo, huella, empresa_id, usuario, usuario_id, ruta, metodo, modulo,
    tipo, mensaje, traceback, ip, user_agent
  ) VALUES (
    p_codigo, p_huella, p_empresa_id, p_usuario, p_usuario_id, p_ruta,
    p_metodo, p_modulo, p_tipo, p_mensaje, p_traceback, p_ip, p_user_agent
  )
  ON CONFLICT (huella) DO UPDATE SET
    veces      = public.app_errores.veces + 1,
    ultima_vez = now(),
    mensaje    = EXCLUDED.mensaje,
    traceback  = EXCLUDED.traceback,
    usuario    = EXCLUDED.usuario,
    -- si ya estaba revisado y vuelve a pasar, se reabre
    estado     = CASE WHEN public.app_errores.estado = 'REVISADO'
                      THEN 'NUEVO' ELSE public.app_errores.estado END
  RETURNING codigo INTO v_codigo;

  RETURN v_codigo;
END;
$$;


-- Módulo propio en Roles y permisos: las trazas técnicas pueden mostrar
-- rutas y datos internos, así que no van bajo el checkbox de Configuración.
INSERT INTO public.modulos (code, name, endpoint, icon, section, visible_in_sidebar, is_active, sort_order)
VALUES ('soporte', 'Soporte y errores', '/hc/configuracion/soporte', 'fa-life-ring',
        'Administrativo', false, true, 230)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, endpoint = EXCLUDED.endpoint, icon = EXCLUDED.icon,
  section = EXCLUDED.section, sort_order = EXCLUDED.sort_order, is_active = true;
