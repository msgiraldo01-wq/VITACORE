-- ============================================================
-- Migración: caducidad de la sesión, configurable por empresa
--
-- Hasta ahora la sesión de Vitacore duraba hasta que se cerraba
-- el navegador. Ni caducidad ni cierre por inactividad: un equipo
-- del consultorio con la pantalla abierta seguía dentro al día
-- siguiente, con la historia clínica de un paciente a la vista de
-- quien pasara por ahí.
--
-- Son dos límites distintos y hacen falta los dos:
--
--   sesion_inactividad_min  cuánto puede estar la pantalla sin que
--                           nadie la toque. Se mide por interacción
--                           real (tecla, clic), NO por tráfico: la
--                           página llama sola a /ping cada 30
--                           segundos para vigilar la conexión, y si
--                           eso contara como actividad la sesión no
--                           caducaría jamás.
--
--   sesion_jornada_horas    tope absoluto desde que entró, por mucho
--                           que se mueva el ratón. Una sesión no
--                           debería sobrevivir a la jornada.
--
-- Se deja por empresa a propósito: cada IPS tiene su política, y una
-- clínica con los equipos en zona de paso no quiere lo mismo que un
-- consultorio cerrado.
--
-- Si una empresa las deja en nulo, el código cae a lo que diga .env
-- y, si tampoco hay nada, a 30 minutos y 12 horas.
--
-- Es segura de correr más de una vez.
-- ============================================================

ALTER TABLE public.hc_empresas
  ADD COLUMN IF NOT EXISTS sesion_inactividad_min integer,
  ADD COLUMN IF NOT EXISTS sesion_jornada_horas   integer;

COMMENT ON COLUMN public.hc_empresas.sesion_inactividad_min IS
  'Minutos sin interacción real antes de cerrar la sesión. Nulo = valor por defecto del sistema (30).';

COMMENT ON COLUMN public.hc_empresas.sesion_jornada_horas IS
  'Horas máximas de sesión desde el login, haya actividad o no. Nulo = valor por defecto del sistema (12).';

-- Valores razonables para las empresas que ya existen. Quedan
-- explícitos en vez de en nulo para que al abrir la pantalla de la
-- empresa se vea qué política tiene, en lugar de un campo vacío.
UPDATE public.hc_empresas
   SET sesion_inactividad_min = 30
 WHERE sesion_inactividad_min IS NULL;

UPDATE public.hc_empresas
   SET sesion_jornada_horas = 12
 WHERE sesion_jornada_horas IS NULL;

-- Cordura: nadie debería poder dejar una sesión abierta una semana
-- ni cerrarla cada 30 segundos por un cero de más.
ALTER TABLE public.hc_empresas
  DROP CONSTRAINT IF EXISTS hc_empresas_sesion_inactividad_ck;
ALTER TABLE public.hc_empresas
  ADD CONSTRAINT hc_empresas_sesion_inactividad_ck
  CHECK (sesion_inactividad_min IS NULL
         OR sesion_inactividad_min BETWEEN 5 AND 480);

ALTER TABLE public.hc_empresas
  DROP CONSTRAINT IF EXISTS hc_empresas_sesion_jornada_ck;
ALTER TABLE public.hc_empresas
  ADD CONSTRAINT hc_empresas_sesion_jornada_ck
  CHECK (sesion_jornada_horas IS NULL
         OR sesion_jornada_horas BETWEEN 1 AND 24);
