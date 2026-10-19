-- ============================================================
-- Migración: anulación y auditoría de la evolución clínica
--
-- DOS COSAS, en la misma tabla:
--
-- 1) AUDITORÍA. Una cita guarda quién la creó, cuándo, desde qué IP.
--    Una evolución solo guardaba created_by. Es al revés de como
--    debería ser: la nota clínica es el documento que la Resolución
--    1995 de 1999 exige poder atribuir a alguien.
--
-- 2) ANULACIÓN. La historia clínica no admite enmendaduras: no se
--    puede borrar ni editar una evolución. Lo que sí se puede es
--    MARCARLA como anulada, dejando el registro original intacto
--    junto con quién la anuló, cuándo y por qué.
--
--    Sobre el RDA ya transmitido: la Resolución 1888 de 2025 y el
--    Manual de operaciones IHCE v1.4 NO definen ninguna figura de
--    anulación ante el Ministerio -- solo contemplan reenviar
--    corregido lo que el Ministerio rechazó. Por eso aquí se guarda
--    el composition_id que se le había enviado: el día que exista un
--    procedimiento, esa columna dice exactamente qué documentos hay
--    que corregir allá, sin tener que reconstruir la lista.
--
-- Es segura de correr más de una vez.
-- ============================================================

-- ------------------------------------------------------------
-- 1) Auditoría de creación
-- ------------------------------------------------------------
ALTER TABLE public.hc_evoluciones
  ADD COLUMN IF NOT EXISTS usuario_creacion    text,
  ADD COLUMN IF NOT EXISTS usuario_creacion_id text,
  ADD COLUMN IF NOT EXISTS ip_privada          text,
  ADD COLUMN IF NOT EXISTS ip_publica          text,
  -- fecha_creacion es CUÁNDO SE REGISTRÓ; `fecha` es cuándo ocurrió
  -- la atención. Hoy suelen coincidir, pero dejan de hacerlo apenas
  -- alguien registre una atención de ayer.
  ADD COLUMN IF NOT EXISTS fecha_creacion      timestamptz DEFAULT now();

-- ------------------------------------------------------------
-- 2) Anulación (nunca borrado)
-- ------------------------------------------------------------
ALTER TABLE public.hc_evoluciones
  ADD COLUMN IF NOT EXISTS anulada             boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS anulada_motivo      text,
  ADD COLUMN IF NOT EXISTS anulada_por         text,
  ADD COLUMN IF NOT EXISTS anulada_por_id      text,
  ADD COLUMN IF NOT EXISTS anulada_en          timestamptz,
  ADD COLUMN IF NOT EXISTS anulada_ip          text,
  -- la evolución nueva que corrige a esta, cuando la hay
  ADD COLUMN IF NOT EXISTS reemplazada_por_id  bigint
      REFERENCES public.hc_evoluciones(id),
  -- qué se le había enviado al Ministerio en el momento de anular
  ADD COLUMN IF NOT EXISTS rda_composition_id  text,
  ADD COLUMN IF NOT EXISTS rda_pendiente_ministerio boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.hc_evoluciones.rda_pendiente_ministerio IS
  'La evolución se anuló aquí pero su RDA ya estaba en el Ministerio y no '
  'existe procedimiento para retirarlo. Queda marcada para cuando lo haya.';

CREATE INDEX IF NOT EXISTS hc_evoluciones_anuladas_idx
  ON public.hc_evoluciones (paciente_id) WHERE anulada;

CREATE INDEX IF NOT EXISTS hc_evoluciones_rda_pendiente_idx
  ON public.hc_evoluciones (empresa_id) WHERE rda_pendiente_ministerio;

-- ------------------------------------------------------------
-- 3) Las evoluciones que ya existen quedan como no anuladas
--    (el DEFAULT false ya lo hace; esto es por si la columna
--    existía de antes con nulos)
-- ------------------------------------------------------------
UPDATE public.hc_evoluciones SET anulada = false WHERE anulada IS NULL;
