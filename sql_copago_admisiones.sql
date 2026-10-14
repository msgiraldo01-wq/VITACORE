-- sql_copago_admisiones.sql
--
-- Soporte para "Cobrar copago" en Admisiones.
--
-- Agrega una columna cita_id (nullable, no rompe nada existente) a
-- fin_caja_movimientos, para poder enlazar con exactitud un copago
-- cobrado por anticipado en Admisiones con la factura que se genere
-- después para esa misma cita -- así el paso de facturación (que ya
-- registra el copago automáticamente al facturar) puede reconocer que
-- ya se cobró y enlazar el movimiento existente en vez de duplicarlo.
--
-- Ejecutar una sola vez en el editor SQL de Supabase.

ALTER TABLE fin_caja_movimientos ADD COLUMN IF NOT EXISTS cita_id integer;

CREATE INDEX IF NOT EXISTS idx_fin_caja_movimientos_cita_id
  ON fin_caja_movimientos (cita_id);
