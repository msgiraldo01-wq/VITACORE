-- =====================================================================
-- MIGRACIÓN — Integración Factus (facturación electrónica DIAN) v2
-- Vitacore — módulo de facturación
-- =====================================================================
-- Cómo aplicar: pega este archivo completo en el SQL Editor de Supabase
-- (Project → SQL Editor → New query) y ejecútalo una sola vez. Todos los
-- ALTER/CREATE usan IF NOT EXISTS, así que es seguro volver a ejecutarlo
-- si algo queda a medias.
--
-- Después de ejecutar esto, hay 3 tareas manuales pendientes (ver el
-- final de este archivo, sección "PASOS MANUALES DESPUÉS DE MIGRAR"):
--   1) Configurar factus_numbering_range_id por sede.
--   2) Completar el mapeo de tipos de documento (fin_factus_doc_tipo_map).
--   3) Revisar/ajustar hc_cups.factus_tratamiento donde algo NO sea
--      excluido de IVA (medicamentos, insumos gravados, etc).
-- =====================================================================


-- =============================================================
-- 1) fin_facturas — resultado de la emisión electrónica
-- =============================================================
ALTER TABLE public.fin_facturas
  ADD COLUMN IF NOT EXISTS cufe                text,
  ADD COLUMN IF NOT EXISTS qr_image             text,
  ADD COLUMN IF NOT EXISTS estado_dian          text,              -- VALIDADA | PENDIENTE | ERROR_DIAN | DATOS_INCOMPLETOS | NO_APLICA
  ADD COLUMN IF NOT EXISTS factus_estado        text DEFAULT 'NO_APLICA',
  ADD COLUMN IF NOT EXISTS factus_response      jsonb,
  ADD COLUMN IF NOT EXISTS factus_errores       jsonb,
  ADD COLUMN IF NOT EXISTS adquiriente_tipo     text,              -- PACIENTE | CLIENTE
  ADD COLUMN IF NOT EXISTS enviado_dian_at      timestamptz;

CREATE INDEX IF NOT EXISTS idx_fin_facturas_cufe ON public.fin_facturas (cufe);
CREATE INDEX IF NOT EXISTS idx_fin_facturas_factus_estado ON public.fin_facturas (factus_estado);


-- =============================================================
-- 2) fin_notas_credito_debito — notas electrónicas
-- =============================================================
ALTER TABLE public.fin_notas_credito_debito
  ADD COLUMN IF NOT EXISTS numero_nota_dian  text,
  ADD COLUMN IF NOT EXISTS cude              text,
  ADD COLUMN IF NOT EXISTS estado_dian       text DEFAULT 'NO_APLICA',
  ADD COLUMN IF NOT EXISTS factus_response   jsonb;


-- =============================================================
-- 3) fin_consecutivos_facturacion — mapeo a rango de numeración Factus
-- =============================================================
-- El rango de numeración (prefijo + consecutivos autorizados por la DIAN)
-- se crea y administra DENTRO del panel de Factus. Aquí solo guardamos a
-- qué numbering_range_id de Factus corresponde cada consecutivo/sede local.
ALTER TABLE public.fin_consecutivos_facturacion
  ADD COLUMN IF NOT EXISTS factus_numbering_range_id bigint;


-- =============================================================
-- 4) hc_municipios — código DIAN cacheado (para el campo
--    municipality_code que exige Factus en el adquiriente)
-- =============================================================
ALTER TABLE public.hc_municipios
  ADD COLUMN IF NOT EXISTS codigo_dian text;


-- =============================================================
-- 5) hc_clientes — datos DIAN del adquiriente + regla "particular"
-- =============================================================
ALTER TABLE public.hc_clientes
  ADD COLUMN IF NOT EXISTS municipio_id bigint REFERENCES public.hc_municipios(id),
  ADD COLUMN IF NOT EXISTS direccion    text,
  ADD COLUMN IF NOT EXISTS email        text,
  ADD COLUMN IF NOT EXISTS telefono     text,
  ADD COLUMN IF NOT EXISTS tipo_identificacion text DEFAULT 'NIT',   -- CC | NIT | CE | PA | TI ...
  ADD COLUMN IF NOT EXISTS dv           text,                        -- dígito de verificación (solo NIT)
  -- Si es TRUE, la factura electrónica de ESTE cliente usa al PACIENTE
  -- como adquiriente ante la DIAN en vez del cliente contratante
  -- (caso típico: un cliente genérico "Particular" usado para pagos
  -- de bolsillo sin convenio). Configúralo manualmente donde aplique.
  ADD COLUMN IF NOT EXISTS usa_paciente_como_adquiriente boolean DEFAULT false;


-- =============================================================
-- 6) hc_cups — tratamiento tributario por procedimiento/producto
-- =============================================================
ALTER TABLE public.hc_cups
  ADD COLUMN IF NOT EXISTS factus_tratamiento    text DEFAULT 'EXCLUIDO',  -- EXCLUIDO | EXENTO | GRAVADO
  ADD COLUMN IF NOT EXISTS factus_tributo_codigo text,                     -- código de tributo Factus/DIAN (solo si GRAVADO)
  ADD COLUMN IF NOT EXISTS factus_tarifa         numeric DEFAULT 0,        -- % de IVA (solo si GRAVADO)
  ADD COLUMN IF NOT EXISTS factus_unidad_medida  text DEFAULT '94',        -- 94 = Unidad (DIAN)
  ADD COLUMN IF NOT EXISTS factus_standard_code  text DEFAULT '4';         -- 4 = estándar adoptado por el contribuyente

DO $$ BEGIN
  ALTER TABLE public.hc_cups
    ADD CONSTRAINT chk_hc_cups_factus_tratamiento
    CHECK (factus_tratamiento IN ('EXCLUIDO', 'EXENTO', 'GRAVADO'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================
-- 7) fin_factus_doc_tipo_map — mapeo tipo de documento local → Factus
-- =============================================================
CREATE TABLE IF NOT EXISTS public.fin_factus_doc_tipo_map (
  codigo_local   text PRIMARY KEY,      -- coincide con hc_tipos_documento.codigo
  codigo_factus  text,                  -- código que exige Factus/DIAN (tabla 13.2.1)
  descripcion    text,
  updated_at     timestamptz DEFAULT now()
);

-- Semillas con los códigos DIAN estándar más comunes (tabla nacional
-- 13.2.1 "Tipo de documento"). VERIFICAR contra la tabla de referencia
-- de Factus (GET /v2/common/document-types) antes de producción — si
-- Factus usa una numeración propia distinta, actualiza codigo_factus.
INSERT INTO public.fin_factus_doc_tipo_map (codigo_local, codigo_factus, descripcion) VALUES
  ('RC',  '11', 'Registro civil'),
  ('TI',  '12', 'Tarjeta de identidad'),
  ('CC',  '13', 'Cédula de ciudadanía'),
  ('CE',  '22', 'Cédula de extranjería'),
  ('NIT', '31', 'NIT'),
  ('PA',  '41', 'Pasaporte')
ON CONFLICT (codigo_local) DO NOTHING;


-- =============================================================
-- 8) fin_factus_referencias — caché de tablas de referencia de Factus
--    (municipios, tributos, unidades de medida, etc.)
-- =============================================================
CREATE TABLE IF NOT EXISTS public.fin_factus_referencias (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tabla       text NOT NULL,       -- 'municipalities', 'document-types', ...
  codigo      text NOT NULL,
  nombre      text,
  extra       jsonb,
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fin_factus_referencias_tabla ON public.fin_factus_referencias (tabla, codigo);
CREATE INDEX IF NOT EXISTS idx_fin_factus_referencias_nombre ON public.fin_factus_referencias (tabla, nombre);


-- =============================================================
-- 9) fin_factus_eventos_log — auditoría de todo lo enviado/recibido
-- =============================================================
CREATE TABLE IF NOT EXISTS public.fin_factus_eventos_log (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  documento_tipo  text NOT NULL,    -- FACTURA | NOTA_CREDITO | NOTA_DEBITO
  documento_id    bigint,
  accion          text NOT NULL,    -- CREAR_VALIDAR | REINTENTO | CONSULTA_EVENTOS | EMAIL
  payload_envio   jsonb,
  respuesta       jsonb,
  ok              boolean NOT NULL DEFAULT false,
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fin_factus_eventos_doc ON public.fin_factus_eventos_log (documento_tipo, documento_id);


-- =============================================================
-- 10) CORRECCIÓN (2026-08-27) — hc_cups.factus_standard_code
--     El valor sembrado en el paso 6 era '4'. Factus rechazó una
--     factura real de prueba con "El campo código estándar es
--     inválido" — su ejemplo oficial ("factura estándar a consumidor
--     final") usa '999' para ítems sin código UNSPSC/GTIN reconocido.
--     Este bloque es idempotente: se puede correr varias veces sin
--     problema.
-- =============================================================
ALTER TABLE public.hc_cups
  ALTER COLUMN factus_standard_code SET DEFAULT '999';

UPDATE public.hc_cups
SET factus_standard_code = '999'
WHERE factus_standard_code = '4';


-- =====================================================================
-- PASOS MANUALES DESPUÉS DE MIGRAR
-- =====================================================================
-- 1) Por cada sede que facture, crea (o ubica) su rango de numeración en
--    el panel de Factus (dashboard.factus.com.co → Configuración →
--    Rangos de numeración) y guarda su ID aquí, por ejemplo:
--
--      UPDATE public.fin_consecutivos_facturacion
--      SET factus_numbering_range_id = 8   -- <- el ID que te da Factus
--      WHERE sede_id = 1 AND es_principal = true;
--
-- 2) Revisa/ajusta el mapeo de tipos de documento sembrado en el paso 7
--    contra la tabla de referencia real de Factus (una vez tengas
--    credenciales activas, el endpoint de diagnóstico
--    GET /facturacion/api/factus/test-conexion ayuda a confirmar que la
--    autenticación funciona antes de ir más lejos).
--
-- 3) Por defecto TODOS los procedimientos (hc_cups) quedaron marcados
--    como 'EXCLUIDO' de IVA (típico en servicios de salud humana). Si
--    facturan también medicamentos/insumos gravados, actualiza esas filas:
--
--      UPDATE public.hc_cups
--      SET factus_tratamiento = 'GRAVADO',
--          factus_tributo_codigo = '01',   -- IVA — confirmar código exacto con Factus
--          factus_tarifa = 19
--      WHERE codigo IN ('...', '...');
--
-- 4) Sincroniza el caché de municipios para que el formulario de
--    "completar datos DIAN" pueda sugerir opciones (una vez configuradas
--    las credenciales reales en el .env del servidor):
--
--      POST /facturacion/api/factus/sincronizar-municipios
--
-- 5) Para clientes "particulares" (donde el adquiriente ante la DIAN
--    debe ser el paciente y no el cliente contratante), marca:
--
--      UPDATE public.hc_clientes
--      SET usa_paciente_como_adquiriente = true
--      WHERE codigo = 'PARTICULAR';   -- ajusta al código real que usen
-- =====================================================================
