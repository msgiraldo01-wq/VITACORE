-- ============================================================
-- Migración: unificar el sistema de permisos en la matriz por
-- módulo (roles_modulos), que es la que ya se ve en
-- /hc/configuracion/roles-permisos con checkboxes Ver/Crear/
-- Editar/Eliminar.
--
-- Qué hace:
--   1) Crea/actualiza en `modulos` un registro por cada item del
--      menú lateral (sidebar), usando como `code` el mismo valor
--      que ahora usa el backend para decidir accesos y visibilidad
--      del sidebar. Es un UPSERT por `code`, así que es seguro
--      correrla más de una vez y no borra nada que ya exista.
--   2) Para los roles que HOY NO tengan ninguna fila en
--      roles_modulos (o sea, roles que nunca se configuraron en
--      esa pantalla), les da acceso completo a todos los módulos
--      como punto de partida -- para que nadie quede bloqueado el
--      día que esto entra en producción. De ahí en adelante, cada
--      rol se restringe manualmente desde la pantalla de
--      Roles y permisos.
--
-- Correr esto UNA vez en el SQL editor de Supabase antes de
-- desplegar el código nuevo.
-- ============================================================

-- 1) Módulos (uno por item del sidebar que SÍ requiere permiso;
--    "Inicio" queda siempre visible y no se gestiona aquí).
INSERT INTO public.modulos (code, name, endpoint, icon, section, visible_in_sidebar, is_active, sort_order)
VALUES
  ('dashboard_clinico', 'Dashboard clínico', '/hc/', 'fa-chart-line', 'Clínico', true, true, 10),
  ('pacientes',         'Pacientes',          '/hc/pacientes', 'fa-user-injured', 'Clínico', true, true, 20),
  ('admisiones',        'Admisiones',         '/hc/admisiones', 'fa-door-open', 'Clínico', true, true, 30),
  ('citas',             'Citas',              '/citas', 'fa-calendar-check', 'Clínico', true, true, 40),
  ('historia_clinica',  'Historia clínica',   '/hc/historia-clinica', 'fa-notes-medical', 'Clínico', true, true, 50),
  ('rda',               'Envíos / Visor RDA', '/rda', 'fa-cloud-arrow-up', 'Clínico', true, true, 60),
  ('farmacia',          'Farmacia',           '/inventario/dashboard', 'fa-pills', 'Clínico', true, true, 70),

  ('dashboard_financiero','Dashboard financiero','/financiero/dashboard', 'fa-chart-pie', 'Financiero', true, true, 100),
  ('contratos',         'Contratos',          '/financiero/contratos/', 'fa-file-signature', 'Financiero', true, true, 110),
  ('facturacion',       'Facturación',        '/facturacion/', 'fa-file-invoice-dollar', 'Financiero', true, true, 120),
  ('radicacion',        'Radicación',         '/financiero/radicacion/', 'fa-folder-open', 'Financiero', true, true, 130),
  ('glosas',            'Glosas',             '/financiero/glosas/', 'fa-triangle-exclamation', 'Financiero', true, true, 140),
  ('cartera',           'Cartera',            '/financiero/cartera/', 'fa-wallet', 'Financiero', true, true, 150),
  ('conciliaciones',    'Conciliaciones',     '/financiero/conciliaciones/', 'fa-money-check-dollar', 'Financiero', true, true, 160),
  ('tesoreria',         'Tesorería',          '/financiero/tesoreria/', 'fa-building-columns', 'Financiero', true, true, 170),
  ('config_financiera', 'Configuración financiera', '/financiero/configuracion/', 'fa-sliders', 'Financiero', true, true, 180),

  ('caja',              'Caja / auditoría',   '/caja', 'fa-cash-register', 'Administrativo', true, true, 200),
  ('reportes',          'Reportes',           '/hc/reportes', 'fa-chart-pie', 'Administrativo', true, true, 210),
  ('configuracion',     'Configuración',      '/hc/configuracion', 'fa-gear', 'Administrativo', true, true, 220)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  endpoint = EXCLUDED.endpoint,
  icon = EXCLUDED.icon,
  section = EXCLUDED.section,
  sort_order = EXCLUDED.sort_order,
  is_active = true;

-- 2) Punto de partida: los roles que aún no tienen NINGUNA fila en
--    roles_modulos reciben acceso completo a todos los módulos, para
--    no bloquear a nadie el día que el nuevo control de acceso entra
--    en vigor. Después de correr esto, cada rol se ajusta desde
--    /hc/configuracion/roles-permisos.
INSERT INTO public.roles_modulos (role_id, modulo_id, can_view, can_create, can_edit, can_delete)
SELECT r.id, m.id, true, true, true, true
FROM public.roles r
CROSS JOIN public.modulos m
WHERE r.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM public.roles_modulos rm WHERE rm.role_id = r.id
  );
