-- ============================================================
-- Migración: contabilización automática de facturas
--
-- EL PROBLEMA. La clínica lleva meses facturando -- 27 facturas,
-- 31 líneas de detalle, 4 notas crédito, pagos en cartera y 48
-- eventos de facturación electrónica -- y los libros contables
-- están en CERO. No es que nadie los haya usado: es que no existe
-- forma de que se alimenten solos. El único sitio del proyecto que
-- escribe en fin_comprobantes es la propia pantalla de contabilidad.
--
-- DOS TABLAS, y conviene entender por qué cada una:
--
-- 1) fin_cuentas_por_concepto
--    Qué cuenta usar para los ingresos, para la cartera, para el
--    IVA. Va en una tabla y no en el código porque Vitacore se le
--    alquila a varias IPS y cada una tiene su plan de cuentas.
--
-- 2) fin_comprobantes_propuestos
--    El asiento que el sistema propone, ANTES de que el contador lo
--    apruebe. Vive fuera de fin_comprobantes a propósito: crear el
--    comprobante consume un número de fin_consecutivos_contables, y
--    un borrador que quizá nunca se apruebe dejaría un hueco en la
--    numeración contable. Aquí no se consume nada hasta aprobar.
--
--    De paso, el libro diario nunca enseña asientos sin confirmar.
--
-- Es segura de correr más de una vez.
-- ============================================================

-- ------------------------------------------------------------
-- 1) Parametrización de cuentas
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fin_cuentas_por_concepto (
  id               bigserial PRIMARY KEY,
  empresa_id       bigint  NOT NULL,
  concepto         text    NOT NULL,
  cuenta_id        bigint  NOT NULL REFERENCES public.fin_puc(id),
  centro_costo_id  bigint  REFERENCES public.fin_centros_costo(id),
  nota             text,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now()
);

COMMENT ON TABLE public.fin_cuentas_por_concepto IS
  'Qué cuenta del PUC usa cada concepto contable. Cada empresa define las suyas.';

-- Un concepto no puede apuntar a dos cuentas: el asiento sería ambiguo.
CREATE UNIQUE INDEX IF NOT EXISTS fin_cuentas_concepto_uk
  ON public.fin_cuentas_por_concepto (empresa_id, concepto);

-- ------------------------------------------------------------
-- 2) Asientos propuestos, pendientes de aprobación
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fin_comprobantes_propuestos (
  id                bigserial PRIMARY KEY,
  empresa_id        bigint NOT NULL,
  sede_id           bigint,

  -- De qué documento salió. Es la clave de la idempotencia.
  origen_tabla      text   NOT NULL,
  origen_id         text   NOT NULL,

  tipo_comprobante  text   NOT NULL,
  fecha             date   NOT NULL,
  descripcion       text,

  -- Las líneas tal como se le pasarán a fin_registrar_comprobante.
  -- En jsonb y no en una tabla hija porque una propuesta es un
  -- borrador que se descarta entero: no se edita línea a línea.
  lineas            jsonb  NOT NULL,
  total_debito      numeric(18,2) NOT NULL DEFAULT 0,
  total_credito     numeric(18,2) NOT NULL DEFAULT 0,

  --   PROPUESTO  esperando al contador
  --   APROBADO   ya está en los libros, comprobante_id dice cuál
  --   DESCARTADO el contador no lo quiere
  --   FALLIDO    se intentó aprobar y la función lo rechazó; el
  --              motivo queda en `error` para poder corregir la
  --              parametrización y reintentar
  estado            text   NOT NULL DEFAULT 'PROPUESTO',
  error             text,
  comprobante_id    bigint REFERENCES public.fin_comprobantes(id),

  created_at        timestamptz DEFAULT now(),
  created_by        text,
  resuelto_en       timestamptz,
  resuelto_por      text
);

COMMENT ON TABLE public.fin_comprobantes_propuestos IS
  'Asientos que el sistema propone a partir de facturas, pagos y cierres de caja. '
  'No consumen consecutivo: eso ocurre solo al aprobarlos.';

-- ------------------------------------------------------------
-- 3) La garantía de que nada se contabiliza dos veces
--
-- Contabilizar una factura dos veces DUPLICA los ingresos, y un
-- libro contable no se arregla borrando filas. Comprobarlo en el
-- código no basta: dos peticiones a la vez pasarían las dos. Aquí
-- lo impide la base.
--
-- Los descartados quedan fuera del índice para poder volver a
-- proponer un asiento que el contador rechazó.
-- ------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS fin_propuestos_origen_uk
  ON public.fin_comprobantes_propuestos (empresa_id, origen_tabla, origen_id)
  WHERE estado <> 'DESCARTADO';

CREATE INDEX IF NOT EXISTS fin_propuestos_pendientes_idx
  ON public.fin_comprobantes_propuestos (empresa_id, fecha)
  WHERE estado = 'PROPUESTO';

ALTER TABLE public.fin_comprobantes_propuestos
  DROP CONSTRAINT IF EXISTS fin_propuestos_estado_ck;
ALTER TABLE public.fin_comprobantes_propuestos
  ADD CONSTRAINT fin_propuestos_estado_ck
  CHECK (estado IN ('PROPUESTO','APROBADO','DESCARTADO','FALLIDO'));

-- ------------------------------------------------------------
-- 4) Parametrización inicial para la empresa 1
--
-- Las cuentas se buscan por código, no por id, porque los ids
-- cambian entre instalaciones. Si alguna no existe, esa fila
-- simplemente no se inserta y el servicio lo dirá al proponer,
-- en vez de contabilizar contra una cuenta equivocada.
--
-- El centro de costo es obligatorio en las cuentas de ingreso
-- (fin_puc.exige_centro_costo), así que se fija el de la sede
-- principal.
-- ------------------------------------------------------------
INSERT INTO public.fin_cuentas_por_concepto (empresa_id, concepto, cuenta_id, centro_costo_id, nota)
SELECT 1, v.concepto, p.id,
       CASE WHEN p.exige_centro_costo
            THEN (SELECT id FROM public.fin_centros_costo
                   WHERE empresa_id = 1 AND codigo = 'CC-001' LIMIT 1)
            ELSE NULL END,
       v.nota
  FROM (VALUES
    ('CLIENTES',              '130505', 'Cartera por cobrar a la EPS'),
    ('INGRESO_CONSULTA',      '415505', 'CUPS que empiezan por 89'),
    ('INGRESO_PROCEDIMIENTO', '415510', 'El resto de CUPS'),
    ('IVA_GENERADO',          '240805', 'Servicios de salud suelen ir excluidos'),
    ('GLOSA_ACEPTADA',        '417505', 'Lo que la EPS objeta y se acepta'),
    ('CAJA',                  '110505', 'Recaudos en efectivo'),
    ('BANCOS',                '111005', 'Recaudos por transferencia')
  ) AS v(concepto, codigo, nota)
  JOIN public.fin_puc p
    ON p.codigo = v.codigo AND p.empresa_id = 1
 WHERE NOT EXISTS (
   SELECT 1 FROM public.fin_cuentas_por_concepto c
    WHERE c.empresa_id = 1 AND c.concepto = v.concepto
 );
