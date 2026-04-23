-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.hc_cie10 (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo character varying NOT NULL,
  nombre text NOT NULL,
  descripcion text,
  categoria text,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_cie10_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_consultorios (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  sede_id bigint NOT NULL,
  codigo text NOT NULL,
  nombre text NOT NULL,
  piso text,
  descripcion text,
  estado text NOT NULL DEFAULT 'ACTIVO'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT hc_consultorios_pkey PRIMARY KEY (id),
  CONSTRAINT hc_consultorios_sede_id_fkey FOREIGN KEY (sede_id) REFERENCES public.hc_sedes(id)
);
CREATE TABLE public.hc_especialidades (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo text NOT NULL UNIQUE,
  nombre text NOT NULL,
  descripcion text,
  estado text NOT NULL DEFAULT 'ACTIVA'::text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_especialidades_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_evolucion_medicamentos (
  id bigint NOT NULL DEFAULT nextval('hc_evolucion_medicamentos_id_seq'::regclass),
  evolucion_id bigint NOT NULL,
  medicamento_id bigint,
  medicamento_nombre character varying,
  dosis character varying,
  frecuencia character varying,
  duracion character varying,
  via_administracion character varying,
  observaciones text,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT hc_evolucion_medicamentos_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_evoluciones (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  paciente_id bigint NOT NULL,
  fecha timestamp with time zone DEFAULT now(),
  motivo_consulta text,
  enfermedad_actual text,
  examen_fisico text,
  impresion_diagnostica text,
  plan text,
  medico character varying,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  cie10_codigo text,
  medico_id bigint,
  CONSTRAINT hc_evoluciones_pkey PRIMARY KEY (id),
  CONSTRAINT fk_evolucion_paciente FOREIGN KEY (paciente_id) REFERENCES public.hc_pacientes(id),
  CONSTRAINT fk_evolucion_medico FOREIGN KEY (medico_id) REFERENCES public.hc_profesionales(id)
);
CREATE TABLE public.hc_medicamentos (
  id bigint NOT NULL DEFAULT nextval('hc_medicamentos_id_seq'::regclass),
  codigo character varying,
  nombre character varying NOT NULL,
  forma_farmaceutica character varying,
  concentracion character varying,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT hc_medicamentos_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_pacientes (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  tipo_documento_id bigint NOT NULL,
  numero_documento character varying NOT NULL UNIQUE,
  nombres character varying NOT NULL,
  apellidos character varying NOT NULL,
  fecha_nacimiento date,
  sexo character varying,
  telefono character varying,
  celular character varying,
  email character varying,
  direccion text,
  aseguradora character varying,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_pacientes_pkey PRIMARY KEY (id),
  CONSTRAINT fk_paciente_tipo_doc FOREIGN KEY (tipo_documento_id) REFERENCES public.hc_tipos_documento(id)
);
CREATE TABLE public.hc_paises (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo_iso2 character varying NOT NULL UNIQUE,
  codigo_iso3 character varying,
  nombre character varying NOT NULL,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp without time zone DEFAULT now(),
  updated_at timestamp without time zone,
  CONSTRAINT hc_paises_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_profesionales (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  tipo_documento_id bigint NOT NULL,
  numero_documento character varying NOT NULL,
  nombres character varying NOT NULL,
  apellidos character varying NOT NULL,
  nombre_completo character varying,
  especialidad_id bigint,
  sede_id bigint,
  consultorio_id bigint,
  registro_profesional character varying,
  correo character varying,
  telefono character varying,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_profesionales_pkey PRIMARY KEY (id),
  CONSTRAINT fk_prof_tipo_doc FOREIGN KEY (tipo_documento_id) REFERENCES public.hc_tipos_documento(id),
  CONSTRAINT fk_prof_especialidad FOREIGN KEY (especialidad_id) REFERENCES public.hc_especialidades(id),
  CONSTRAINT fk_prof_sede FOREIGN KEY (sede_id) REFERENCES public.hc_sedes(id),
  CONSTRAINT fk_prof_consultorio FOREIGN KEY (consultorio_id) REFERENCES public.hc_consultorios(id)
);
CREATE TABLE public.hc_sedes (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo text NOT NULL UNIQUE,
  nombre text NOT NULL,
  ciudad text,
  direccion text,
  telefono text,
  estado text DEFAULT 'ACTIVA'::text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_sedes_pkey PRIMARY KEY (id)
);
CREATE TABLE public.hc_servicios (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo character varying NOT NULL UNIQUE,
  nombre character varying NOT NULL,
  especialidad_id bigint,
  descripcion text,
  activo boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  estado character varying DEFAULT 'ACTIVO'::character varying,
  CONSTRAINT hc_servicios_pkey PRIMARY KEY (id),
  CONSTRAINT fk_servicio_especialidad FOREIGN KEY (especialidad_id) REFERENCES public.hc_especialidades(id)
);
CREATE TABLE public.hc_signos_vitales (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  paciente_id bigint NOT NULL,
  fecha timestamp with time zone DEFAULT now(),
  peso numeric,
  talla numeric,
  imc numeric,
  presion_sistolica integer,
  presion_diastolica integer,
  frecuencia_cardiaca integer,
  frecuencia_respiratoria integer,
  temperatura numeric,
  observaciones text,
  CONSTRAINT hc_signos_vitales_pkey PRIMARY KEY (id),
  CONSTRAINT fk_signos_paciente FOREIGN KEY (paciente_id) REFERENCES public.hc_pacientes(id)
);
CREATE TABLE public.hc_tipos_documento (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  codigo character varying NOT NULL,
  nombre character varying NOT NULL,
  descripcion character varying,
  estado character varying DEFAULT 'ACTIVO'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT hc_tipos_documento_pkey PRIMARY KEY (id)
);
CREATE TABLE public.modulos (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  endpoint text,
  icon text,
  section text,
  visible_in_sidebar boolean DEFAULT true,
  is_active boolean DEFAULT true,
  sort_order integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT modulos_pkey PRIMARY KEY (id)
);
CREATE TABLE public.profiles (
  id uuid NOT NULL,
  username text NOT NULL UNIQUE,
  full_name text,
  email text UNIQUE,
  role text DEFAULT 'user'::text,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  role_id bigint,
  CONSTRAINT profiles_pkey PRIMARY KEY (id),
  CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id),
  CONSTRAINT profiles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id)
);
CREATE TABLE public.roles (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT roles_pkey PRIMARY KEY (id)
);
CREATE TABLE public.roles_modulos (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  role_id bigint NOT NULL,
  modulo_id bigint NOT NULL,
  can_view boolean DEFAULT true,
  can_create boolean DEFAULT false,
  can_edit boolean DEFAULT false,
  can_delete boolean DEFAULT false,
  CONSTRAINT roles_modulos_pkey PRIMARY KEY (id),
  CONSTRAINT roles_modulos_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id),
  CONSTRAINT roles_modulos_modulo_id_fkey FOREIGN KEY (modulo_id) REFERENCES public.modulos(id)
);
CREATE TABLE public.roles_rutas (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  role_id bigint NOT NULL,
  ruta_id bigint NOT NULL,
  CONSTRAINT roles_rutas_pkey PRIMARY KEY (id),
  CONSTRAINT roles_rutas_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id),
  CONSTRAINT roles_rutas_ruta_id_fkey FOREIGN KEY (ruta_id) REFERENCES public.rutas(id)
);
CREATE TABLE public.rutas (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  endpoint text NOT NULL UNIQUE,
  ruta text NOT NULL,
  metodos text,
  nombre text,
  modulo_code text,
  visible_sidebar boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT rutas_pkey PRIMARY KEY (id)
);