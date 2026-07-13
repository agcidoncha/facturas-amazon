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

### 3.1 Módulo de Carga (antes "Módulo de Conexión") — revisado 2026-07-13
- **Cambio de diseño importante:** se verificó que la SP-API oficial de Amazon no tiene ningún endpoint para descargar los PDF de las facturas que Amazon emite al vendedor (logística, publicidad, etc. — las de la Biblioteca de Documentos Fiscales). Existe una petición de funcionalidad de terceros pidiendo justo esto, abierta en 2021 y cerrada sin que Amazon la implementara. La única vía oficial (Finances API) da datos de las transacciones, no el documento PDF. Se descartó deliberadamente automatizar esto vía scraping/bot de Seller Central, por: riesgo de incumplir los términos de uso de Amazon, fragilidad ante cambios de la interfaz web, y la necesidad de almacenar credenciales de la cuenta de Amazon dentro del sistema.
- **Diseño resultante:** el usuario sigue descargando manualmente los PDF desde la Biblioteca de Documentos Fiscales de Amazon (como hace hoy) y los **sube/arrastra** a la aplicación. A partir de ahí, todo el resto del sistema (3.2, 3.3, 3.4) funciona igual que estaba previsto, sin intervención manual.
- **Implementado y verificado en producción (13/07/2026):** pantalla en `/subir` (`app/carga.py`), protegida por contraseña (`APP_TOKEN`). Calcula la huella SHA-256, descarta duplicados, guarda el PDF en el disco persistente de Render y detecta emisor/tipo de documento reutilizando `extract_invoices.py`. Probado con una factura real de Amazon Ads, detectada correctamente.
- No interpreta ni transforma nada — solo recibe el documento que el usuario sube.
- El Cron Job de descarga automática mensual (día 7, ya desplegado en Render) se reconvierte en un simple **recordatorio** (aviso en el panel o notificación) de que toca subir las facturas del mes — ya no dispara ninguna descarga real.
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
- **Implementado y verificado en producción (13/07/2026):** `app/extraccion.py` conecta `process_invoice()` (prototipo `extract_invoices.py`) con la base de datos. Al subir un PDF se guardan todos los campos extraídos, el `tipo_gasto` y el `estado` real (revisado / necesita revisión), y se resuelven las relaciones nota de crédito → factura original. Probado con una factura y una nota de crédito sintéticas contra Postgres real: detección correcta, campos guardados, relación resuelta.

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
| 2026-07-13 | Infraestructura desplegada: Render (Web Service + Disco + Cron Job) + Neon Postgres (Frankfurt), verificada en producción | Usuario + Claude |
| 2026-07-13 | Amazon aprueba el registro de desarrollador — Módulo de Conexión (3.1) ya no está bloqueado | Amazon |
| 2026-07-13 | Verificado: la SP-API no permite descargar los PDF de facturas de Amazon al vendedor. El Módulo de Conexión (3.1) pasa a ser Módulo de Carga manual; se descarta el scraping de Seller Central | Claude (investigación) + Usuario |
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

**Implementado y verificado en producción (13/07/2026):** tabla en `/facturas` (`app/vista.py`) con estas 8 columnas, protegida con autenticación básica HTTP (usuario cualquiera, contraseña = `APP_TOKEN`). Sin estilos todavía (fase visual pendiente, deliberadamente pospuesta a petición del usuario). Probado localmente contra Postgres real, incluyendo una prueba de inyección HTML para confirmar que los valores se escapan correctamente.

**Ampliación (13/07/2026):** cada fila tiene un enlace "Ver" que lleva a `/facturas/{id}`, una página de detalle con **todos** los campos extraídos de esa factura (no solo las 8 columnas), en una lista simple sin agrupar (decisión deliberada: con el volumen de campos y usuarios de este proyecto, plegar/paginar añadiría complejidad sin beneficio real). Señala los campos marcados como "necesita revisión".

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
1. ~~Descarga automática mensual (desde el día 7) + descarga manual bajo demanda, desde Seller Central.~~ → **Revisado:** descarga manual (Amazon no lo permite por API, sección 3.1) + carga manual a la aplicación. **Hecho y verificado (13/07/2026).**
2. Almacenamiento organizado de los PDF originales (fuente de verdad) con detección de duplicados. **Hecho y verificado (13/07/2026).**
3. Extracción flexible de datos (sin esquema fijo, con origen/confianza/revisión por dato). **Hecho y verificado (13/07/2026).**
4. Vista básica en pantalla con las columnas por defecto acordadas (sección 7.7). **Hecho y verificado (13/07/2026).**

**MVP funcional completo.** Pendiente solo la fase visual (CSS/estética), deliberadamente pospuesta.

**Justo después del MVP (segunda iteración inmediata, no una fase lejana):**
5. Exportación a Excel. → **Hecho y verificado (13/07/2026):** `/facturas/exportar.xlsx`, mismas 8 columnas, importes como números reales (no texto) para poder sumarlos en Excel.

**Explícitamente fuera del MVP** (se decidirá más adelante, no ahora):
- Consultas avanzadas personalizadas (más allá de la vista por defecto).
- Categorización/agrupación manual de conceptos de gasto.
- Cualquier funcionalidad fuera del módulo de facturas.

---

## 11. Plan de infraestructura técnica (fase inicial)

**Contexto:** el usuario cuenta con un hosting compartido tipo cPanel/Plesk para la web de la empresa (melopido.shop), no adecuado para alojar la aplicación (necesita procesos automáticos en segundo plano). Presupuesto ajustado; prioriza empezar gratis.

**Hosting elegido para la aplicación (revisado 2026-07-13):** Render, con el **plan de workspace Hobby (gratis)** — no hace falta un workspace de pago: el límite de "1 puesto" de Hobby es sobre quién administra el panel de Render, no sobre los 2 usuarios administradores de la aplicación de facturas (eso lo gestiona la propia app). Lo que sí se paga es el **cómputo** de los servicios (Web Service y Cron Job) y el disco, con presupuesto máximo de referencia de 10 €/mes y prioridad explícita en simplicidad y fiabilidad sobre ahorro. **Cuenta de Render ya creada ("Melopido").**

Se descartó el plan gratuito de *cómputo* de Render para el Web Service porque no admite disco persistente (los PDF desaparecerían en cada redeploy) ni una base de datos Postgres duradera (la gratuita caduca a los 30 días). También se descartó consolidar todo en Railway: su facturación por consumo real hace que el coste de una app pequeña sea variable y, según casos reales, pueda oscilar entre 5 y 40 €/mes — no compatible con un presupuesto fijo de 10 €/mes.

**Arquitectura de hosting acordada:**
- **Render — Workspace Hobby:** 0 €/mes.
- **Render — Web Service (cómputo Starter, ~7 $/mes):** aplicación FastAPI, interfaz web, botón de descarga manual, API. Siempre activo, sin cold start. Necesario para poder tener disco persistente.
- **Render — Disco persistente (5 GB × 0,25 $/GB/mes ≈ 1,25 $/mes):** Almacén de Documentos Originales (sección 3.2) — los PDF se guardan aquí, con huella/hash para deduplicación.
- **Render — Cron Job (cómputo Starter, ~0,00016 $/minuto, prorrateado por segundo):** dispara la descarga + extracción automática el día 7 de cada mes, reutilizando el mismo código que el botón manual. Coste real, dado que corre pocos minutos al mes, es prácticamente nulo (céntimos).
- **Neon — Postgres (plan gratuito, externo a Render):** único servicio fuera de Render. Se eligió porque el Postgres gratuito de Render caduca a los 30 días y el de pago no aporta nada que Neon no dé gratis para este volumen de datos (0,5 GB, sin caducidad). Es el único punto de dependencia externa además de Render.
- **Coste total estimado: ~7,7-9 €/mes**, dentro del presupuesto de 10 €/mes, con precio previsible (solo varía ligeramente con el tamaño del disco y el ancho de banda real).

**Pasos acordados, en orden:**
1. ~~Elegir un hosting en la nube adecuado para la aplicación~~ → Hecho: Render (workspace Hobby + cómputo de pago, ver arriba) + Neon (Postgres).
2. Crear un subdominio en el panel del hosting actual de la empresa (ej. `facturas.melopido.shop`). → **Hecho: subdominio `facturas.melopido.shop` creado, con certificado SSL Let's Encrypt (HTTPS activo).**
3. Configurar el DNS de ese subdominio para que apunte al nuevo hosting de la aplicación (Render). → **Hecho y verificado (13/07/2026):** registro CNAME `facturas` → `facturas-amazon-web.onrender.com` creado (sustituyendo el registro A anterior), dominio verificado en Render, certificado SSL emitido automáticamente. `https://facturas.melopido.shop/facturas` funciona igual que la URL de Render.
4. Registrar una aplicación de tipo desarrollador en Amazon Seller Central, para la conexión oficial (trámite en la web de Amazon, no programación). → **Hecho: perfil de desarrollador privado enviado (13/07/2026), aprobado por Amazon (13/07/2026).** Ya no hay ningún bloqueante externo pendiente para empezar a programar el Módulo de Conexión (3.1).
5. Prueba de conexión antes de construir el resto del sistema.
6. Repositorio de código creado y con el primer commit → **Hecho: https://github.com/agcidoncha/facturas-amazon (rama `main`), con `render.yaml` (Web Service + Disco + Cron Job) y un esqueleto FastAPI probado localmente.**
7. Crear el Blueprint en Render desde ese repositorio (Web Service + Disco + Cron Job) y el proyecto Postgres en Neon. → **Hecho (13/07/2026): Web Service, Disco (5GB) y Cron Job desplegados y verificados (`/health` responde `{"status":"ok"}`); Postgres en Neon (región Frankfurt) conectado vía `DATABASE_URL`.**

Los pasos 1-7 no implican programar la lógica de negocio todavía (solo infraestructura). Con Amazon aprobado y la infraestructura desplegada, el siguiente trabajo es programar de verdad: el Módulo de Conexión (3.1), el modelo de datos en Postgres, y la vista básica.

## 11.1 Diseño técnico del backend (acordado 2026-07-13)

- **Lenguaje/framework:** Python + FastAPI. Elegido por su ecosistema maduro de extracción de PDF (`pdfplumber`, `PyMuPDF`), necesario porque el idioma de las facturas no es fijo (sección 7.3) y algunos conceptos llegan como código interno crudo (sección 7.4).
- **Modelo de datos (concepto, sobre Postgres/Neon):**
  - `documentos`: un registro por PDF (hash SHA-256, emisor, fecha de descarga, estado, ruta en el disco de Render). Es el ancla de todo.
  - `datos_extraidos`: tabla flexible campo-valor (campo, valor, origen, confianza, necesita_revision, documento_id) — un campo nuevo no exige migrar nada (condición 4, sección 2).
  - `relaciones_documentos`: enlaza notas de crédito con su(s) factura(s) original(es) (secciones 7.1 y 7.10), sin fusionar importes.
  - Se eligió una tabla campo-valor sobre Postgres relacional en vez de una base NoSQL: cumple la condición de esquema flexible (sección 2, condición 2) sin perder las garantías relacionales que sí hacen falta para vincular documentos entre sí.
- **Implementado y verificado en producción (13/07/2026):** modelos SQLAlchemy en `app/models.py`, conexión en `app/db.py` (driver psycopg3, corregido tras un fallo de despliegue por conflicto psycopg2/psycopg3), tablas creadas automáticamente al arrancar. Verificado con una petición real a `/health/db` contra la base de datos de Neon, confirmando las 3 tablas creadas.

---

## 12. Siguiente paso más pequeño propuesto

Con la infraestructura desplegada (Render + Neon, verificada en producción), el registro de desarrollador de Amazon aprobado, y confirmado que la descarga de PDF debe ser manual (sección 3.1), el siguiente paso es programar el MVP en este orden:
1. Modelo de datos real en Postgres (`documentos`, `datos_extraidos`, `relaciones_documentos`, sección 11.1).
2. Módulo de Carga (3.1): pantalla para subir/arrastrar los PDF descargados manualmente de Amazon.
3. Integrar el prototipo de extracción (`extract_invoices.py`) con la base de datos, para que los datos extraídos se guarden en vez de solo generar un JSON suelto.
4. Vista básica en pantalla con las columnas por defecto (sección 7.7).

Pendiente, no bloqueante: configurar el DNS de `facturas.melopido.shop` hacia Render (paso 3, sección 11); reconvertir el Cron Job existente en un recordatorio simple en vez de un disparador de descarga.

