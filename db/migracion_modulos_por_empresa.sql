-- ============================================================
-- Migración: módulos contratados por empresa
--
-- Hasta ahora los permisos eran por ROL ("este rol puede ver
-- Farmacia"). Esto agrega la capa de arriba, que es comercial:
-- "esta IPS contrató Farmacia". Un usuario ve un módulo solo si
-- su empresa lo tiene contratado Y su rol tiene permiso.
--
-- También declara las dependencias reales entre módulos, que
-- hasta ahora solo existían implícitas en el código (Admisiones
-- lee citas y caja, Facturación lee citas, caja y cartera...).
--
-- Es segura de correr más de una vez.
-- Correr en el SQL editor de Supabase ANTES de desplegar el código.
-- ============================================================

-- ------------------------------------------------------------
-- 1) Qué módulos tiene contratados cada empresa
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.empresas_modulos (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  empresa_id   bigint NOT NULL REFERENCES public.hc_empresas(id) ON DELETE CASCADE,
  modulo_id    bigint NOT NULL REFERENCES public.modulos(id) ON DELETE CASCADE,
  activo       boolean NOT NULL DEFAULT true,
  activado_en  timestamptz NOT NULL DEFAULT now(),
  activado_por text,
  notas        text,
  UNIQUE (empresa_id, modulo_id)
);

CREATE INDEX IF NOT EXISTS empresas_modulos_empresa_idx
  ON public.empresas_modulos (empresa_id) WHERE activo;


-- ------------------------------------------------------------
-- 2) Dependencias entre módulos
--
-- "modulo_id NECESITA requiere_id para funcionar". Salen de leer
-- qué repositorios importa cada blueprint: no son una opinión de
-- diseño, es lo que hoy se rompería al apagar el otro.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.modulos_dependencias (
  modulo_id   bigint NOT NULL REFERENCES public.modulos(id) ON DELETE CASCADE,
  requiere_id bigint NOT NULL REFERENCES public.modulos(id) ON DELETE CASCADE,
  motivo      text,
  PRIMARY KEY (modulo_id, requiere_id),
  CHECK (modulo_id <> requiere_id)
);


-- ------------------------------------------------------------
-- 3) Cargar las dependencias detectadas en el código
-- ------------------------------------------------------------
WITH pares(modulo, requiere, motivo) AS (
  VALUES
    ('citas',            'pacientes',        'La cita se agenda sobre un paciente registrado'),
    ('citas',            'contratos',        'Toma tarifa y contrato del cliente al agendar'),
    ('admisiones',       'citas',            'Admite pacientes de las citas del día'),
    ('admisiones',       'caja',             'Cobra el copago al admitir'),
    ('historia_clinica', 'pacientes',        'La nota clínica pertenece a un paciente'),
    ('historia_clinica', 'medicamentos',     'El formulario de evolución formula del catálogo'),
    ('rda',              'historia_clinica', 'El RDA se arma desde la evolución'),
    ('rda',              'pacientes',        'Reporta los datos del paciente al Ministerio'),
    ('farmacia',         'historia_clinica', 'La dispensación valida contra la fórmula médica'),
    ('facturacion',      'citas',            'Factura los procedimientos de las citas'),
    ('facturacion',      'caja',             'Registra el cobro de la factura en caja'),
    ('facturacion',      'cartera',          'Sincroniza la factura emitida a cartera'),
    ('facturacion_config',      'facturacion', 'Configura los consecutivos de facturación'),
    ('facturacion_diagnostico', 'facturacion', 'Diagnostica los envíos de facturación'),
    ('cartera',          'contratos',        'La cartera se lleva por cliente y contrato'),
    ('glosas',           'cartera',          'La glosa se aplica sobre una factura en cartera'),
    ('radicacion',       'cartera',          'Radica facturas que viven en cartera'),
    ('reportes',         'citas',            'Los indicadores se calculan sobre las citas')
)
INSERT INTO public.modulos_dependencias (modulo_id, requiere_id, motivo)
SELECT m.id, r.id, p.motivo
FROM pares p
JOIN public.modulos m ON m.code = p.modulo
JOIN public.modulos r ON r.code = p.requiere
ON CONFLICT (modulo_id, requiere_id) DO UPDATE SET motivo = EXCLUDED.motivo;


-- ------------------------------------------------------------
-- 4) Punto de partida: las empresas que YA existen conservan todo
--
-- Sin esto, el día del despliegue todas las IPS quedarían sin
-- módulos. A partir de aquí se apaga desde la pantalla lo que
-- cada cliente no haya contratado.
-- ------------------------------------------------------------
INSERT INTO public.empresas_modulos (empresa_id, modulo_id, activo, activado_por, notas)
SELECT e.id, m.id, true, 'migracion', 'Activado en la migración inicial'
FROM public.hc_empresas e
CROSS JOIN public.modulos m
WHERE m.is_active
ON CONFLICT (empresa_id, modulo_id) DO NOTHING;
