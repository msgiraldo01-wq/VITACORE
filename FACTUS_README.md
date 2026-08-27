# Integración Factus (facturación electrónica DIAN) — Vitacore

Este documento resume lo que se modificó en el módulo de facturación y los
pasos que faltan de tu lado para dejarlo funcionando en sandbox.

## Qué se hizo

- **`config.py` / `.env.example`** — nuevas variables: `FACTUS_ENV`,
  `FACTUS_CLIENT_ID`, `FACTUS_CLIENT_SECRET`, `FACTUS_USERNAME`,
  `FACTUS_PASSWORD`, `FACTUS_HABILITADO`.
- **`services/factus_service.py`** (nuevo) — cliente HTTP de la API Factus
  v2: login OAuth2 con caché/renovación de token, crear y validar
  facturas, notas crédito/débito, consultar factura, descargar XML/PDF,
  eventos DIAN, tablas de referencia.
- **`services/factus_mapper.py`** (nuevo) — arma el "adquiriente" (paciente
  o cliente, según la regla de negocio que definimos) y los ítems con su
  tratamiento de IVA, y detecta datos DIAN faltantes antes de intentar
  facturar.
- **`services/factura_pdf_local.py`** (nuevo) — de paso, arregla un bug
  que ya existía: la descarga de PDF llamaba a un módulo
  (`services.fin_factura_pdf`) que no existía en el proyecto.
- **`repositories/fin_factus_repo.py`** (nuevo) — acceso a las tablas
  nuevas (mapeo de tipos de documento, caché de tablas de Factus, log de
  eventos) y consultas dedicadas de paciente/cliente para la DIAN.
- **`repositories/fin_facturacion_repo.py`** — se agregaron columnas
  nuevas a los `select` de listar/registrar facturas.
- **`blueprints/bp_financiero/facturacion/routes.py`** — `/api/facturar`
  ahora emite ante la DIAN vía Factus ANTES de crear la factura local (si
  Factus rechaza o faltan datos, no queda nada a medias); nuevas rutas:
  `/api/factura/<id>/reintentar-dian`, `/api/factura/<id>/xml`,
  `/api/adquiriente/completar`, `/api/factus/test-conexion`,
  `/api/factus/municipios`, `/api/factus/sincronizar-municipios`. El PDF y
  las notas crédito/débito también pasan por Factus cuando aplica.
- **Plantillas** (`facturacion.html`, `factura_vista.html`,
  `facturas_lista.html`, `facturacion_configuracion.html`) — pantalla de
  carga mientras se emite, modal para completar datos DIAN faltantes,
  CUFE/QR en la vista de factura, badge de estado DIAN en el listado, y
  el campo para configurar el *numbering range* de Factus por sede.
- **`db/migracion_factus.sql`** (nuevo) — todas las tablas/columnas
  nuevas. Ejecútalo en el SQL Editor de Supabase.

## Decisiones tomadas contigo

- Alcance: facturas + notas crédito/débito + eventos DIAN + reenvío por email.
- Adquiriente: el cliente contratante normalmente; el paciente cuando
  `hc_clientes.usa_paciente_como_adquiriente = true` (pago particular).
- Emisión síncrona, con animación de carga.
- Tratamiento de IVA por CUPS (`hc_cups.factus_tratamiento`), por defecto
  `EXCLUIDO` en todos los procedimientos existentes.
- Factus es la fuente de verdad del número de factura (vía
  `numbering_range_id` configurado por ti en el panel de Factus).
- Municipio/dirección/email se piden en el momento de facturar si faltan.
- Credenciales: las agregas tú directamente en el `.env` del servidor.
- Ambiente inicial: sandbox.

## Lo que falta de tu lado

1. **Ejecutar `db/migracion_factus.sql`** en Supabase (SQL Editor).
2. **Completar el `.env`** del servidor con las credenciales reales de
   Factus (las del correo que compartiste, sección "Credenciales de
   acceso V2"): `FACTUS_CLIENT_ID`, `FACTUS_CLIENT_SECRET`,
   `FACTUS_USERNAME`, `FACTUS_PASSWORD`. Déjalo en `FACTUS_ENV=sandbox`.
3. **Probar la conexión**: con el servidor corriendo y sesión iniciada,
   `GET /facturacion/api/factus/test-conexion` — debe responder `ok: true`.
4. **Crear el rango de numeración** en el panel de Factus (con tu
   resolución DIAN de pruebas) y pegar su ID en Facturación →
   Configuración → Nuevo consecutivo → "Numbering range ID de Factus"
   (o por SQL, ver el final de `migracion_factus.sql`).
5. **Sincronizar municipios**: `POST /facturacion/api/factus/sincronizar-municipios`
   (una vez, para que el buscador de municipios en el modal de "completar
   datos" tenga opciones).
6. **Revisar `hc_cups.factus_tratamiento`** si facturan también
   medicamentos/insumos gravados (por defecto todo quedó `EXCLUIDO`, típico
   para servicios de salud).
7. **Marcar clientes particulares**: si tienen un cliente genérico tipo
   "Particular" para pagos de bolsillo, márcalo con
   `usa_paciente_como_adquiriente = true` para que la factura electrónica
   quede a nombre del paciente y no de ese registro genérico.

## Endpoints de Factus con verificación pendiente

La mayoría de los endpoints usados están confirmados contra la
documentación oficial (`developers.factus.com.co`), pero algunos (marcados
`(VERIFICAR)` en `services/factus_service.py`) siguen el mismo patrón de
la API sin haber podido confirmarse 1:1 en la documentación pública al
momento de escribir esto: listar facturas, descargar PDF, XML con
documento adjunto, reenvío por email, notas débito, tablas de referencia
y numbering ranges. Antes de depender de esos en producción, verifícalos
contra la colección Postman oficial (`developers.factus.com.co/coleccion`)
— es un ajuste de una sola línea en `ENDPOINTS` si algo difiere.

## Nota sobre el flujo de facturación consolidada

`/api/facturar-consolidado` emite ante Factus DESPUÉS de crear la factura
y marcar las prefacturas como facturadas (a diferencia del flujo
individual, que lo hace antes). Si Factus falla ahí, la factura queda
creada con `factus_estado = ERROR_DIAN` y se puede reintentar con
`/api/factura/<id>/reintentar-dian` sin perder el trabajo de
consolidación ya hecho.
