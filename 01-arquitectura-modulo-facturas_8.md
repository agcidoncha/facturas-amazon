# Arquitectura propuesta — Módulo de Facturas de Amazon

**Estado: PROPUESTA INICIAL, no es una decisión técnica cerrada.** Se revisará y ajustará a medida que avancemos.

**Fecha:** 11 de julio de 2026

---

## 1. Contexto

- Negocio con una cuenta de Seller Central, un solo marketplace.
- Facturas objetivo: las que Amazon emite al vendedor (comisiones, publicidad, logística/envío, almacenaje...).
- Volumen actual: ~10 facturas/mes, descargadas hoy a mano desde la Biblioteca de Documentos Fiscales, una a una en PDF.
- Uso previsto: 2 personas, ambas con permisos de administrador.
- Acceso: aplicación web.
- El Excel actual ("Libro Registro de Facturas") se ha usado solo como referencia del flujo de trabajo actual — **no** como plantilla que limite el diseño.

## 2. Principios de diseño (condiciones acordadas)

1. El **PDF original siempre se conserva** como fuente de verdad. Ningún dato extraído sustituye al documento original.
2. La extracción **no asume** que todas las facturas tienen la misma estructura (una factura de logística no tiene por qué parecerse a una de publicidad).
3. Cada dato extraído guarda, junto a su valor: **de dónde salió** (origen), **su nivel de confianza**, y **si necesita revisión manual**.
4. Si aparece un campo nuevo en una factura, el sistema debe poder **incorporarlo sin modificar toda la base de datos** ni romper lo ya guardado.
5. Se deben **evitar duplicados**, aunque la misma factura se descargue varias veces (por ejemplo, tras una descarga manual y luego la automática mensual).
6. La arquitectura debe poder tratar **Amazon EU SARL** y **Amazon Online Spain, SLU** como emisores/fuentes distintos, si técnicamente es necesario diferenciarlos (se ha observado en el Excel que efectivamente son entidades distintas: la primera emite logística y tarifas de venta, la segunda publicidad).
7. Diseño modular: preparado para crecer con funcionalidades futuras aún no definidas, sin rehacer lo ya construido.

## 3. Módulos propuestos

### 3.1 Módulo de Conexión
- Única responsabilidad: conectarse a Seller Central y obtener las facturas disponibles.
- No interpreta ni transforma nada — solo trae el documento.
- Se ejecuta automáticamente cada mes (desde el día 7) y también bajo demanda (botón manual).
- No necesita saber nada de contabilidad, campos ni destino de los datos.

### 3.2 Almacén de Documentos Originales
- Guarda cada PDF descargado tal cual, sin modificar.
- A cada documento se le calcula una **huella única** (hash del contenido) para detectar si esa misma factura ya se había descargado antes, evitando duplicados aunque se dispare la descarga dos veces (manual + automática, por ejemplo).
- Metadatos mínimos por documento: fecha de descarga, emisor detectado (Amazon EU SARL / Amazon Online Spain / otro), estado (nuevo, procesado, con error).
- Es la **fuente de verdad**: siempre se puede volver a este PDF, pase lo que pase con los datos extraídos.

### 3.3 Módulo de Extracción
- Lee cada PDF y extrae **todos** los datos identificables (no un conjunto fijo de 5 o 10 campos).
- Cada dato extraído se guarda como una entrada independiente con esta forma conceptual:
  - **Campo** (ej. "importe total", "concepto", "fecha factura"...)
  - **Valor**
  - **Origen** (de qué parte del documento/proceso salió ese dato)
  - **Confianza** (qué tan fiable es la extracción de ese dato concreto)
  - **Necesita revisión manual** (sí/no)
- No hay un "molde" rígido de columnas: si una factura de publicidad trae campos distintos a una de logística, ambas conviven sin conflicto.
- Si en el futuro aparece un campo que nunca se había visto, el sistema simplemente añade esa nueva pieza de información sin necesitar rediseñar la base de datos ni tocar las facturas ya procesadas.
- El emisor (Amazon EU SARL, Amazon Online Spain, u otro) se guarda como un dato más, permitiendo tratarlos como fuentes distintas cuando haga falta.

### 3.4 Módulo de Consulta y Vistas
- Aquí es donde se decide, en cada momento, qué mirar: 1 dato, 10 datos, filtrado por fecha, por emisor, por concepto, etc.
- Permite crear vistas nuevas o exportar a Excel **sin tocar** los módulos de conexión, almacenamiento o extracción.
- Como los datos ya están guardados de forma flexible (ver 3.3), una consulta nueva es solo una forma distinta de mirar lo que ya existe.

## 4. Por qué esta separación

Separar **"traer y guardar todo"** (módulos 3.1–3.3) de **"decidir qué mirar"** (módulo 3.4) significa que:
- Cambiar qué se ve en pantalla o en el Excel de salida no obliga a tocar cómo se descargan o guardan las facturas.
- Añadir un campo nuevo no rompe lo que ya funciona.
- El sistema puede crecer hacia otras áreas del negocio en el futuro reutilizando el mismo patrón (documento original + datos flexibles + vistas a medida), aunque hoy no sepamos qué serán esas áreas.

## 5. Lo que esta propuesta NO define todavía

- Tecnologías concretas (base de datos, lenguaje, hosting...).
- Cómo se conecta exactamente el módulo de conexión a Seller Central (API oficial vs. otro método).
- El diseño exacto de pantallas o de la exportación a Excel.
- Todo esto se decidirá en fases posteriores, cuando corresponda.

## 6. Historial de decisiones

| Fecha | Decisión/condición | Origen |
|---|---|---|
| 2026-07-11 | Facturas objetivo: las que Amazon cobra al vendedor | Usuario |
| 2026-07-11 | Descarga automática mensual (día 7) + manual bajo demanda | Usuario |
| 2026-07-11 | Guardado organizado + extracción de datos para contabilidad | Usuario |
| 2026-07-11 | Aplicación web | Usuario |
| 2026-07-11 | Una cuenta, un marketplace, 2 usuarios administradores | Usuario |
| 2026-07-11 | Histórico de varios años | Usuario |
| 2026-07-11 | Extracción flexible, sin campos fijos predefinidos | Usuario |
| 2026-07-11 | PDF como fuente de verdad, extracción con origen/confianza/revisión, sin duplicados, campos dinámicos, emisores diferenciables | Usuario |
| 2026-07-11 | Vista por defecto: fecha, emisor, tipo de gasto, nº factura, base, IVA, total, estado | Usuario |
| 2026-07-13 | Presupuesto de hosting: hasta 10 €/mes, priorizando simplicidad y fiabilidad sobre ahorro | Usuario |
| 2026-07-13 | Backend: Python + FastAPI | Claude (delegado) |
| 2026-07-13 | Hosting revisado: Render de pago (Web Starter + Disco persistente + Cron Job, ~9 $/mes) + Neon Postgres gratis como único servicio externo | Usuario + Claude |

---

## 7. Catálogo de campos observado (primera muestra real, 14 facturas)

Análisis de una muestra real de 14 documentos descargados de la Biblioteca de Documentos Fiscales. Confirma y amplía varias condiciones de la arquitectura.

### 7.1 Tipos de documento identificados
- **Factura (Tax Invoice / Factura fiscal / Rechnung / Facture pour la TVA)** — documento estándar de cobro.
- **Nota de crédito de impuestos (Tax Credit Note)** — reembolsos o correcciones. Trae importes negativos y **referencia una o varias facturas originales** por número, que pueden ser de periodos ya cerrados o incluso de años anteriores no descargados todavía. Esto implica que el modelo de datos necesita poder **relacionar un documento con otro(s) documento(s)**, no solo guardar filas sueltas.

### 7.2 Emisores/fuentes distintos confirmados
- **Amazon Online Spain, S.L.U.** (NIF ESB87523825) — factura los cargos de publicidad (Amazon Ads). Documentos largos y muy estructurados: resumen general, desglose por "portfolio", desglose por campaña (clics, CPC medio, importe), ajustes con fecha y comentario, tarifas regulatorias por país/jurisdicción, y una sección de preguntas frecuentes que no aporta datos de negocio.
- **Amazon EU S.à r.l., Sucursal en España** (NIF ESW0184081H) — factura logística/venta. Documentos muy simples: una sola línea de concepto, importe, % IVA, IVA, total.

### 7.3 El idioma del documento no es fijo
Se ha observado la **misma entidad** (Amazon EU SARL) emitiendo el mismo tipo de documento en español, alemán y francés, con las etiquetas de campo traducidas ("Fecha de la factura" / "Rechnungsdatum" / "Date de la facture"). **Consecuencia para el diseño:** la extracción no puede basarse en coincidencia de texto de etiqueta en un solo idioma; necesita una estrategia más robusta (posiciones relativas, patrones, o normalización multi-idioma).

### 7.4 El "concepto" del gasto no siempre es legible
En algunas facturas de Amazon EU SARL el concepto aparece como código interno (`ais_fulfillment_by_amazon_fees_text`, `ais_selling_on_amazon_fees_text`, `ais_refunded_fees_text`) y en otras como texto ya traducido ("Tarifas de logística de Amazon", "Tarifas de vender en Amazon"). **Consecuencia:** conviene guardar el valor tal cual aparece (dato crudo) y, aparte, permitir un mapeo/normalización a un concepto legible, sin perder el original.

### 7.5 Nivel de detalle muy distinto entre emisores
Las facturas de Amazon Ads llegan a desglosar hasta el nivel de campaña individual dentro de cada factura; las de Amazon EU SARL solo traen un importe agregado. Confirma que el "esquema flexible sin estructura fija" (condición 2 de la arquitectura) es necesario y no una precaución excesiva.

### 7.6 Implicación para el módulo de detección de duplicados
Se ha confirmado que el número de factura por sí solo es un identificador fiable y estable (no se repite entre documentos distintos en la muestra), lo cual es positivo, pero **no sustituye** a la huella/hash del PDF acordada en la arquitectura: una nota de crédito y su factura original tienen números distintos pero están relacionadas, y esa relación debe quedar reflejada, no tratarse como duplicado.

### 7.7 Vista por defecto aprobada

Columnas que se mostrarán por defecto en el panel principal de facturas (sin necesidad de hacer ninguna consulta especial):

1. Fecha de factura
2. Emisor (Amazon EU SARL / Amazon Online Spain)
3. Tipo de gasto (logística, venta, publicidad...)
4. Número de factura
5. Importe base (sin IVA)
6. IVA
7. Importe total
8. Estado (nuevo / revisado / con nota de crédito asociada)

Cualquier otro dato disponible (desglose por campaña, detalle de ajustes, jurisdicciones de tarifas regulatorias, etc.) queda accesible a través del módulo de Consulta y Vistas (sección 3.4), sin estar en la vista por defecto.

### 7.8 Tratamiento del "tipo de gasto" / concepto

Se decide **no** usar una lista cerrada de categorías predefinidas. El sistema guardará el concepto tal como aparece en cada factura (ya sea texto legible como "Tarifas de logística de Amazon" o un código interno como `ais_fulfillment_by_amazon_fees_text`), y el usuario decidirá más adelante cómo agruparlos en categorías propias. Esto es coherente con el principio de extracción flexible (condición 2, sección 2) y evita que una categorización rígida quede obsoleta si Amazon introduce nuevos tipos de cargo.

### 7.9 Criterio para el campo "Estado"

El sistema marcará automáticamente una factura como **"revisado"** cuando todos sus datos extraídos tengan alta confianza y ninguno esté señalado como pendiente de revisión manual (ver condición 3, sección 2). Si algún dato tiene baja confianza o necesita revisión, la factura queda marcada como **"necesita revisión"** hasta que el usuario la confirme manualmente. Esto evita que haya que revisar las ~10 facturas del mes una a una, concentrando la atención solo en las dudosas.

### 7.10 Tratamiento de las notas de crédito en el panel

Las notas de crédito se mostrarán como una **fila independiente con su propio importe negativo**, no fusionadas ni ajustando automáticamente el total de la factura original. La relación con la(s) factura(s) original(es) (ver sección 7.1) se conserva como un enlace/referencia entre documentos, visible al consultar el detalle, pero sin alterar los importes ya registrados de la factura original.

### 7.11 Tratamiento de duplicados

Cuando el sistema detecta (vía huella/hash del PDF, sección 3.2) que una factura ya existe, no crea una fila ni una copia nueva. No interrumpe al usuario con avisos, pero mantiene un registro discreto y consultable (ej. "X duplicados detectados este mes, ya existentes") para que quede constancia de que no se ha perdido información, sin necesidad de revisarlo activamente.

---

## 9. MVP (primera versión mínima) — alcance acordado

**Incluido en el MVP:**
1. Descarga automática mensual (desde el día 7) + descarga manual bajo demanda, desde Seller Central.
2. Almacenamiento organizado de los PDF originales (fuente de verdad) con detección de duplicados.
3. Extracción flexible de datos (sin esquema fijo, con origen/confianza/revisión por dato).
4. Vista básica en pantalla con las columnas por defecto acordadas (sección 7.7).

**Justo después del MVP (segunda iteración inmediata, no una fase lejana):**
5. Exportación a Excel.

**Explícitamente fuera del MVP** (se decidirá más adelante, no ahora):
- Consultas avanzadas personalizadas (más allá de la vista por defecto).
- Categorización/agrupación manual de conceptos de gasto.
- Cualquier funcionalidad fuera del módulo de facturas.

---

## 11. Plan de infraestructura técnica (fase inicial)

**Contexto:** el usuario cuenta con un hosting compartido tipo cPanel/Plesk para la web de la empresa (melopido.shop), no adecuado para alojar la aplicación (necesita procesos automáticos en segundo plano). Presupuesto ajustado; prioriza empezar gratis.

**Hosting elegido para la aplicación (revisado 2026-07-13):** Render, **plan de pago**, para tener rendimiento y precio predecibles desde el principio (sin "despertar" tras inactividad, sin caducidad de bases de datos gratuitas). Decisión técnica delegada por el usuario en Claude, con presupuesto máximo de referencia de 10 €/mes y prioridad explícita en simplicidad y fiabilidad sobre ahorro. **Cuenta de Render ya creada ("Melopido").**

Se descartó el plan gratuito de Render porque no ofrece disco persistente (los PDF desaparecerían en cada redeploy) ni una base de datos Postgres duradera (la gratuita caduca a los 30 días). También se descartó consolidar todo en Railway: su facturación por consumo real hace que el coste de una app pequeña sea variable y, según casos reales, pueda oscilar entre 5 y 40 €/mes — no compatible con un presupuesto fijo de 10 €/mes.

**Arquitectura de hosting acordada:**
- **Render — Web Service (plan Starter, ~7 $/mes):** aplicación FastAPI, interfaz web, botón de descarga manual, API. Siempre activo, sin cold start.
- **Render — Disco persistente (~0,25 $/GB/mes, pocos GB):** Almacén de Documentos Originales (sección 3.2) — los PDF se guardan aquí, con huella/hash para deduplicación.
- **Render — Cron Job (~1 $/mes mínimo):** dispara la descarga + extracción automática el día 7 de cada mes, reutilizando el mismo código que el botón manual.
- **Neon — Postgres (plan gratuito, externo a Render):** único servicio fuera de Render. Se eligió porque el Postgres gratuito de Render caduca a los 30 días y el de pago no aporta nada que Neon no dé gratis para este volumen de datos (0,5 GB, sin caducidad). Es el único punto de dependencia externa además de Render.
- **Coste total estimado: ~9 $/mes (~9 €/mes)**, dentro del presupuesto de 10 €/mes, con precio fijo y predecible (no facturación por consumo variable).

**Pasos acordados, en orden:**
1. ~~Elegir un hosting en la nube adecuado para la aplicación~~ → Hecho: Render (revisado a plan de pago, ver arriba) + Neon (Postgres).
2. Crear un subdominio en el panel del hosting actual de la empresa (ej. `facturas.melopido.shop`). → **Hecho: subdominio `facturas.melopido.shop` creado, con certificado SSL Let's Encrypt (HTTPS activo).**
3. Configurar el DNS de ese subdominio para que apunte al nuevo hosting de la aplicación (Render).
4. Registrar una aplicación de tipo desarrollador en Amazon Seller Central, para la conexión oficial (trámite en la web de Amazon, no programación). → **Hecho (13/07/2026): perfil de desarrollador privado enviado, con el caso de uso "Finanzas y contabilidad". Estado: en revisión por Amazon.**
5. Prueba de conexión antes de construir el resto del sistema.

Ninguno de estos pasos implica programar todavía.

## 11.1 Diseño técnico del backend (acordado 2026-07-13)

- **Lenguaje/framework:** Python + FastAPI. Elegido por su ecosistema maduro de extracción de PDF (`pdfplumber`, `PyMuPDF`), necesario porque el idioma de las facturas no es fijo (sección 7.3) y algunos conceptos llegan como código interno crudo (sección 7.4).
- **Modelo de datos (concepto, sobre Postgres/Neon):**
  - `documentos`: un registro por PDF (hash SHA-256, emisor, fecha de descarga, estado, ruta en el disco de Render). Es el ancla de todo.
  - `datos_extraidos`: tabla flexible campo-valor (campo, valor, origen, confianza, necesita_revision, documento_id) — un campo nuevo no exige migrar nada (condición 4, sección 2).
  - `relaciones_documentos`: enlaza notas de crédito con su(s) factura(s) original(es) (secciones 7.1 y 7.10), sin fusionar importes.
  - Se eligió una tabla campo-valor sobre Postgres relacional en vez de una base NoSQL: cumple la condición de esquema flexible (sección 2, condición 2) sin perder las garantías relacionales que sí hacen falta para vincular documentos entre sí.

---

## 12. Siguiente paso más pequeño propuesto

Con la cuenta de Render creada, el subdominio con SSL listo, el registro de desarrollador de Amazon en revisión, y el diseño técnico del backend ya decidido (sección 11.1: Python/FastAPI + Render de pago + Neon), el siguiente paso pendiente es crear el Web Service, el Disco y el Cron Job en Render, y la base de datos en Neon, y empezar a programar el MVP — sin esperar a la aprobación de Amazon para el módulo de Extracción (3.3) y el modelo de datos, que no dependen de la conexión oficial. La aprobación de Amazon solo bloquea el Módulo de Conexión (3.1).

