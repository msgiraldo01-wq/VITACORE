-- ============================================================
-- VITACORE · Feature: Correos al paciente — interruptor general
-- Ejecutar en el SQL Editor de Supabase
-- ============================================================

-- Nuevo parámetro: interruptor general para prender/apagar el envío
-- de los 4 correos automáticos (crear/confirmar/cancelar/reprogramar
-- cita) desde Configuración → Parámetros generales, sin tocar código
-- ni el .env. Por defecto queda 'true' (activado).
INSERT INTO hc_parametros_sistema (clave, valor, descripcion) VALUES
    ('correos_activos', 'true',
     'Activa o desactiva el envío de correos a pacientes (crear/confirmar/cancelar/reprogramar cita)')
ON CONFLICT (clave) DO NOTHING;
