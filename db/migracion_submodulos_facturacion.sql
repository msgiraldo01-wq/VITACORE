-- ============================================================
-- Migración: separar "Facturación" en 3 módulos independientes
-- dentro de la matriz de Roles y permisos:
--   - facturacion             -> el día a día (facturas, prefacturas, notas)
--   - facturacion_config      -> consecutivos / resoluciones DIAN
--   - facturacion_diagnostico -> panel técnico de eventos Factus
--
-- Antes, un rol con acceso a Facturación veía también la configuración de
-- consecutivos y el panel de diagnóstico técnico de Factus, sin poder
-- separarlos. Con esto quedan como filas propias en
-- /hc/configuracion/roles-permisos.
--
-- Es seguro correrla más de una vez (upsert por code). Copia los
-- permisos que cada rol ya tenía en "facturacion" hacia los dos módulos
-- nuevos, para que nadie pierda acceso de golpe -- de ahí en adelante se
-- ajustan por separado desde los checkboxes.
-- ============================================================

INSERT INTO public.modulos (code, name, endpoint, icon, section, visible_in_sidebar, is_active, sort_order)
VALUES
  ('facturacion_config', 'Configuración de facturación', '/facturacion/configuracion', 'fa-sliders', 'Financiero', false, true, 121),
  ('facturacion_diagnostico', 'Diagnóstico Factus', '/facturacion/factus/eventos', 'fa-stethoscope', 'Financiero', false, true, 122)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  endpoint = EXCLUDED.endpoint,
  icon = EXCLUDED.icon,
  section = EXCLUDED.section,
  sort_order = EXCLUDED.sort_order,
  is_active = true;

INSERT INTO public.roles_modulos (role_id, modulo_id, can_view, can_create, can_edit, can_delete)
SELECT rm.role_id, m.id, rm.can_view, rm.can_create, rm.can_edit, rm.can_delete
FROM public.roles_modulos rm
JOIN public.modulos origen ON origen.id = rm.modulo_id AND origen.code = 'facturacion'
CROSS JOIN public.modulos m
WHERE m.code IN ('facturacion_config', 'facturacion_diagnostico')
  AND NOT EXISTS (
    SELECT 1 FROM public.roles_modulos rm2
    WHERE rm2.role_id = rm.role_id AND rm2.modulo_id = m.id
  );
