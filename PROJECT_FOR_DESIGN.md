# Facturas Amazon — Documento de contexto para diseño

Este documento describe una aplicación web real, ya construida y en producción, para que una IA de diseño (Claude Design) pueda proponer mockups de interfaz con la máxima fidelidad posible. No es un documento técnico para programadores: no hace falta entender código para leerlo.

---

# 1. Resumen del proyecto

**Objetivo de la aplicación:** ayudar a una pequeña empresa (venta en Amazon, marca "Melopido") a gestionar las facturas que **Amazon le cobra a ella** (no las que ella emite a sus clientes) — comisiones de venta, logística/FBA, publicidad (Amazon Ads), y sus notas de crédito asociadas.

**Problema que resuelve:** hasta ahora, cada mes había que entrar a mano a la Biblioteca de Documentos Fiscales de Amazon, descargar cada factura en PDF una por una, abrir cada PDF, leer los datos importantes (fecha, importe, concepto...) y copiarlos a mano en un Excel ("Libro Registro de Facturas"). Era lento y propenso a errores, especialmente porque:
- Amazon usa **dos entidades distintas** que facturan cosas distintas (logística/venta vs. publicidad), con formatos de documento muy diferentes entre sí.
- Los documentos llegan en **distintos idiomas** (español, alemán, francés, inglés) según el caso.
- Existen **notas de crédito** que hacen referencia a facturas de meses o incluso años anteriores.

**Público objetivo:** 2 personas administradoras de la misma pequeña empresa. Una de ellas (la que ha dirigido el desarrollo de esta aplicación) se define como **usuaria novata, no técnica**. La otra persona, que aún no ha usado la aplicación, es quien gestiona las facturas y la contabilidad en el día a día y entiende mejor el dominio contable — su opinión sobre la interfaz todavía está pendiente de recoger.

**Flujo general de uso (resumen):**
1. La persona descarga manualmente los PDF de la Biblioteca de Documentos Fiscales de Amazon (esto no lo automatiza la aplicación — ver sección 9).
2. Sube esos PDF a la aplicación arrastrándolos/seleccionándolos en una pantalla, con una contraseña compartida.
3. La aplicación guarda cada PDF, detecta si ya existía (evita duplicados), y **lee automáticamente todos los datos relevantes** de cada factura (fecha, importe, concepto, número, etc.), sin que el usuario tenga que copiar nada a mano.
4. La persona consulta un panel con todas las facturas (histórico completo, no solo lo recién subido), puede ver el detalle completo de cualquiera, y exportar todo o una factura concreta a Excel.

---

# 2. Funcionalidades actuales

Todas estas funcionalidades están **implementadas y verificadas en producción**, no son ideas ni planes futuros:

1. **Página de inicio** con una tarjeta por "módulo" de la aplicación (hoy solo existe el módulo de Facturas; está pensada para crecer con más módulos de negocio en el futuro).
2. **Subida de PDF** (uno o varios a la vez), protegida por una contraseña compartida entre los 2 usuarios.
3. **Detección de duplicados**: si un PDF ya se había subido antes (se compara el contenido exacto del archivo, no el nombre), no se vuelve a guardar ni a procesar; se informa de ello sin ser intrusivo.
4. **Extracción automática de datos** de cada factura: número de documento, fecha, importe base, IVA, importe total, concepto/tipo de gasto, emisor, tipo de documento (factura o nota de crédito), y — según el tipo de factura — datos adicionales como el desglose de gasto por campaña publicitaria.
5. **Reconocimiento de emisor**: distingue automáticamente entre las dos entidades de Amazon que facturan cosas distintas (una para logística/venta, otra para publicidad), cada una con su propio formato de documento.
6. **Vinculación de notas de crédito** con la(s) factura(s) original(es) a la(s) que hacen referencia, aunque esas facturas originales sean de fechas anteriores.
7. **Estado automático por factura**: cada factura queda marcada como "revisado" (todo se leyó bien) o "necesita revisión" (falta algún dato clave), para poder centrarse solo en las dudosas en vez de revisar todas.
8. **Panel/listado de todas las facturas** (histórico completo y permanente, no solo lo último subido), con las columnas: fecha, emisor, tipo de gasto, número de factura, base imponible, IVA, total, estado.
9. **Página de detalle por factura**: muestra absolutamente todos los datos que se extrajeron de esa factura (no solo el resumen de 8 columnas), y avisa qué campos concretos necesitan revisión manual si los hay.
10. **Reprocesar una factura o todas**: permite volver a ejecutar la lectura/extracción de datos sobre un PDF ya guardado, sin tener que subirlo de nuevo — útil si se mejora la forma de leer los datos y hay facturas antiguas que se beneficiarían de la mejora.
11. **Exportar a Excel**, en dos niveles:
    - Exportación general: todas las facturas, con las mismas 8 columnas del panel, con los importes como números reales (para poder sumarlos directamente en Excel).
    - Exportación individual: una única factura con todos sus campos de detalle.

---

# 3. Arquitectura de pantallas

### 3.1 Inicio (`/`)
- **Objetivo:** punto de entrada a la aplicación; en el futuro, hub de navegación entre distintos módulos de negocio.
- **Elementos:** título de la aplicación ("Melopido"), y una tarjeta clicable por módulo disponible (hoy: una única tarjeta "Gestión de Facturas" con una breve descripción).
- **Acciones posibles:** hacer clic en una tarjeta de módulo para entrar a él.
- **Relación con otras pantallas:** la tarjeta "Gestión de Facturas" lleva al Panel de facturas (3.3).

### 3.2 Subir facturas (`/subir`)
- **Objetivo:** permitir cargar uno o varios PDF de facturas descargados manualmente de Amazon.
- **Elementos:** título, texto explicativo breve, un campo de contraseña, un selector de archivos (acepta múltiples PDF a la vez), y un botón de envío ("Subir").
- **Acciones posibles:** seleccionar archivos y enviarlos.
- **Relación con otras pantallas:** al enviar, lleva a la pantalla de Resultado de la subida (3.2.1). Accesible desde la navegación superior en cualquier pantalla, y desde un botón destacado en el Panel de facturas.

### 3.2.1 Resultado de la subida (aparece tras enviar el formulario anterior)
- **Objetivo:** informar de qué pasó con cada archivo enviado.
- **Elementos:** tres listas separadas — "Guardados" (con el emisor/tipo/estado detectado de cada uno), "Duplicados, ya existían", y "Errores" (ej. un archivo que no es PDF) — cada una con su contador entre paréntesis.
- **Acciones posibles:** volver a la pantalla de subida ("Subir más").
- **Relación con otras pantallas:** vuelve a 3.2 (Subir facturas).

### 3.3 Panel de facturas (`/facturas`)
- **Objetivo:** ver de un vistazo el histórico completo de todas las facturas subidas (no solo las recientes), con lo esencial de cada una.
- **Elementos:** título "Facturas"; una barra de acciones con tres enlaces/botones ("Subir facturas" como botón principal destacado, "Exportar a Excel", "Reprocesar todas"); una tabla con columnas Fecha, Emisor, Tipo de gasto, Nº factura, Base, IVA, Total, Estado, y una columna de acciones por fila ("Ver", y "Reprocesar" solo si a esa factura le faltan datos).
- **Acciones posibles:** ir a subir facturas; exportar todo a Excel; reprocesar todas las facturas de golpe; ver el detalle de una factura; reprocesar una factura individual (si le faltan datos).
- **Relación con otras pantallas:** el enlace "Ver" de cada fila lleva a la Página de detalle (3.4). Es la pantalla "central" a la que se vuelve desde el resto.

### 3.4 Detalle de una factura (`/facturas/{id}`)
- **Objetivo:** ver absolutamente todos los datos que se extrajeron de una factura concreta, no solo el resumen de 8 columnas.
- **Elementos:** enlace para volver a la lista; título con el nombre del archivo original; un enlace para exportar solo esa factura a Excel; una ficha con los datos generales del documento (emisor, tipo de documento, tipo de gasto, estado, fecha de subida); si aplica, un aviso destacado listando qué campos concretos necesitan revisión; y una tabla de dos columnas (Campo / Valor) con cada dato extraído, en el orden en que se extrajo (incluye datos complejos como el desglose de campañas publicitarias, mostrado como texto legible).
- **Acciones posibles:** volver a la lista; exportar esta factura a Excel.
- **Relación con otras pantallas:** vuelve al Panel de facturas (3.3).

### Notas de navegación transversales
- Todas las pantallas comparten una **cabecera fija** con el nombre de la marca (enlaza a Inicio) a la izquierda. Los dos enlaces de navegación del módulo de Facturas ("Ver facturas", "Subir facturas") solo aparecen a la derecha **cuando se está dentro de ese módulo** (Panel, Subir, Detalle) — en la portada de Inicio no se muestran, porque pertenecen a un módulo concreto, no a la navegación general entre módulos. El enlace activo se resalta visualmente.
- Todas las pantallas menos "Inicio" y "Subir facturas" (en su versión GET) requieren autenticación mediante el diálogo nativo de usuario/contraseña del navegador.

---

# 4. Flujo del usuario

1. El usuario entra a la aplicación (dirección propia con https, ej. `facturas.melopido.shop`) y llega a la pantalla de **Inicio**, donde ve la tarjeta del módulo de Facturas.
2. Hace clic en esa tarjeta y llega al **Panel de facturas**, donde ve el histórico completo ya existente.
3. Cuando le llegan facturas nuevas de Amazon (normalmente una vez al mes, ~10 facturas), las descarga manualmente desde la web de Amazon a su ordenador.
4. Va a **Subir facturas**, escribe la contraseña compartida, selecciona todos los PDF nuevos de golpe, y los envía.
5. Ve la pantalla de **Resultado**, confirmando cuántos se guardaron, cuántos ya existían, y si hubo algún error.
6. Vuelve al **Panel de facturas** y ve las nuevas filas ya con todos los datos extraídos automáticamente (fecha, importes, etc.), sin haber tenido que teclear nada.
7. Si alguna factura aparece como "necesita revisión", entra a su **Detalle** para ver exactamente qué campo no se pudo leer bien, y decide si hace falta corregirlo manualmente en su contabilidad.
8. Cuando necesita los datos para su gestor o su propia contabilidad, pulsa **Exportar a Excel** (todas las facturas, o solo una desde su detalle) y descarga el archivo.
9. Ocasionalmente, si se mejora la forma en que la aplicación lee las facturas, usa **Reprocesar todas** para que las facturas ya subidas se actualicen con la mejora, sin tener que volver a descargarlas ni subirlas.

---

# 5. Modelo de datos

Tres entidades principales (simplificado, sin jerga técnica de base de datos):

**Documento** — un PDF subido. Guarda: nombre del archivo original, huella única del contenido (para detectar duplicados), dónde está guardado el PDF, quién es el emisor (Amazon EU o Amazon Ads), qué tipo de documento es (factura o nota de crédito), el tipo de gasto (texto libre, ej. "Publicidad (Amazon Ads)" o "Tarifas de logística de Amazon"), el estado (revisado / necesita revisión), y cuándo se subió.

**Dato extraído** — cada pieza de información que se leyó de un Documento (una factura puede tener 10, 15 o más). Cada uno guarda: a qué Documento pertenece, el nombre del campo (ej. "fecha_documento", "importe_total", "numero_documento"...), su valor, de dónde salió esa lectura, qué tan fiable es, y si necesita revisión manual. Un dato extraído puede ser un texto simple o una lista más compleja (ej. el desglose de gasto por campaña publicitaria).

**Relación entre documentos** — conecta una nota de crédito con la factura original a la que hace referencia (que puede ser de un mes o un año anterior). Guarda qué número de factura se referencia, y el enlace real a esa factura si ya está en el sistema.

Relación entre ellas: un Documento tiene muchos Datos extraídos (relación 1 a muchos), y puede tener Relaciones con otros Documentos (una nota de crédito → una o varias facturas originales).

---

# 6. Componentes reutilizables

- **Cabecera de navegación**: marca a la izquierda (enlace a inicio) + enlaces de navegación a la derecha, con el activo resaltado. Se adapta envolviendo los enlaces en pantallas estrechas.
- **Tarjeta genérica** (`.tarjeta`): contenedor con fondo blanco, borde suave y esquinas redondeadas, usado para agrupar formularios y bloques de contenido.
- **Tarjeta de módulo** (`.tarjeta-modulo`): variante clicable de la tarjeta genérica, usada en la página de Inicio; tiene un título y una descripción corta, y reacciona al pasar el ratón por encima.
- **Botón principal** (`.boton`): botón sólido de color destacado, para la acción principal de cada pantalla (ej. "Subir", "Subir facturas").
- **Enlace secundario** (`.enlace-secundario`): acciones de menor jerarquía visual que el botón principal (ej. "Exportar a Excel", "Ver", "Reprocesar").
- **Formulario simple**: etiqueta encima del campo, campos de ancho completo, usado en "Subir facturas".
- **Tabla de datos**: cabecera con fondo diferenciado y texto en mayúsculas pequeñas, filas con separación sutil y resaltado al pasar el ratón. **En pantallas estrechas (móvil en vertical), cada fila se transforma en una tarjeta apilada** con pares etiqueta/valor, en vez de forzar scroll horizontal — esto es una decisión de diseño ya tomada y funcionando, no una limitación pendiente de arreglar.
- **Ficha de datos en dos columnas** (`dl.ficha`): pares etiqueta/valor para mostrar los datos generales de una factura (usado en la pantalla de Detalle). En móvil pasa a una sola columna.
- **Aviso destacado** (`.aviso`): caja con fondo e borde de color de advertencia, usada para señalar campos que necesitan revisión manual.
- **Lista de resultado**: lista simple sin viñetas, con separadores sutiles entre elementos, usada en la pantalla de Resultado de la subida.

---

# 7. Identidad visual actual

**Esto describe el estilo REAL ya implementado (segunda versión, "modernist", 14/07/2026), sin inventar nada:**

- **Colores:** fondo general gris cálido muy claro (`#f3f2f2`); superficies (tarjetas, tabla) en un gris ligeramente más oscuro (`#eae9e9`); texto principal casi negro (`#201e1d`); color de acento **rojo/naranja intenso** (`#ec3013`, con variantes más oscuras para hover/texto sobre fondo claro); las etiquetas de "necesita revisión" usan el mismo acento (fondo sólido rojo, texto claro) para destacar, y "revisado" usa un gris neutro discreto.
- **Tipografía:** una sola familia, "Archivo" (Google Fonts, cargada por `@import`), en dos pesos: 800 (muy negrita) para títulos y elementos destacados, 400 para el cuerpo del texto. Titulares grandes y contundentes (h1 de 32px en negrita).
- **Espaciados:** sistema de variables de espacio (4/8/12/16/24/32px) reutilizado en toda la aplicación.
- **Esquinas:** **totalmente rectas, sin bordes redondeados en ningún elemento** (radio 0 en tarjetas, botones, inputs, tablas, diálogo) — es una decisión estética deliberada de este segundo skin, no un olvido.
- **Iconografía:** iconos SVG en línea (estilo trazo, heredan el color del texto) en prácticamente todas las acciones y estados — subir, descargar, reprocesar, ver, aviso, documento, candado, etc. (`app/iconos.py`).
- **Jerarquía visual:** más marcada que en la primera versión — botones primarios sólidos en rojo, secundarios con borde, "ghost" solo icono para acciones de fila; etiquetas de estado con color sólido para lo que necesita atención.
- **Responsive:** mismo enfoque mobile-first con punto de corte en 640px (tabla → tarjetas apiladas en móvil). Probado en móvil vertical, tablet y escritorio.
- **Historial:** este es el **segundo** skin aplicado — sustituyó a una primera versión (paleta cálida crema+dorado, tipografía serif Cormorant Garamond+Lora, esquinas redondeadas) generada también con Claude Design a partir de una versión anterior de este documento. Ambos fueron implementaciones completas y funcionales; se optó por esta segunda.

---

# 8. Problemas detectados

Desde el punto de vista de UX/UI, esto es lo que se podría mejorar (observaciones honestas, no una lista de tareas obligatorias):

1. **Jerarquía visual plana**: todo tiene aproximadamente el mismo peso — no hay una escala clara entre "esto es lo más importante de la pantalla" y "esto es secundario", más allá del botón sólido vs. enlace de texto.
2. **Sin identidad de marca propia**: los colores (azul genérico) no derivan de ninguna marca definida; hay margen para darle una identidad visual propia a "Melopido" si se desea.
3. **Iconografía ausente**: no hay iconos que ayuden a escanear la pantalla más rápido (ej. un icono de subida en el botón de subir, un icono de descarga en los enlaces de Excel, un icono de ojo en "Ver").
4. **Estado vacío poco cuidado**: cuando no hay facturas todavía, el panel solo muestra una fila de tabla con el texto "No hay facturas todavía" — podría ser un estado más ilustrado/amigable.
5. **Feedback de acciones limitado**: acciones como "Reprocesar todas" no dan ninguna indicación de progreso mientras se ejecutan (puede tardar si hay muchas facturas) — vuelven a la lista de golpe sin mensaje de confirmación.
6. **Densidad de la tabla de detalle**: en la pantalla de Detalle, cuando hay muchos campos (15-20+), la lista plana campo/valor puede llegar a ser larga de recorrer visualmente — podría beneficiarse de una agrupación visual (sin ocultar nada, ver restricciones).
7. **Formularios básicos**: el selector de archivos usa el control nativo del navegador sin ningún estilo ni zona de arrastrar-y-soltar visual, aunque funcionalmente sí acepta arrastrar archivos.
8. **Sin confirmación en acciones**: "Reprocesar" y "Reprocesar todas" se ejecutan con un solo clic sin paso de confirmación (es una decisión consciente de simplicidad, pero visualmente no hay ninguna distinción entre un enlace "de solo lectura" como "Ver" y uno "que cambia datos" como "Reprocesar").

---

# 9. Restricciones IMPORTANTES

**Qué NO debe cambiar:**
- La aplicación **no descarga facturas de Amazon automáticamente** y nunca lo hará por esta vía: se comprobó que la API oficial de Amazon no lo permite, y se descartó deliberadamente cualquier alternativa no oficial (rodear la web de Amazon) por motivos de términos de uso y seguridad. La subida de PDF **debe seguir siendo manual** — cualquier propuesta de diseño no debe sugerir ni implicar una "conexión automática con Amazon".
- El **PDF original nunca se modifica ni se sustituye** — es la fuente de verdad. Ninguna pantalla debe dar a entender que se edita el documento original.
- La **detección de duplicados por huella del archivo** debe seguir funcionando igual; no debe eliminarse ni ocultarse la posibilidad de ver cuántos se detectaron.
- El **acceso protegido por contraseña compartida** (no hay usuarios individuales ni roles) debe mantenerse tal cual — no proponer un sistema de login con usuarios distintos salvo que se pida explícitamente.
- La **vista por defecto de 8 columnas** (fecha, emisor, tipo de gasto, número, base, IVA, total, estado) fue decidida explícitamente por el usuario y debe seguir siendo lo primero que se ve — cualquier rediseño puede mejorar cómo se presentan, pero no debe quitar ninguna de estas columnas de la vista principal ni esconderlas detrás de pasos adicionales.
- Debe seguir siendo posible **ver el detalle completo de una factura con todos sus campos**, no solo el resumen.
- Debe seguir existiendo la **exportación a Excel**, tanto general como individual.
- La aplicación está **pensada para crecer con más módulos de negocio** además de facturas (de ahí la pantalla de Inicio con tarjetas) — cualquier propuesta de diseño debería poder acomodar más tarjetas de módulo en el futuro sin rehacer la navegación.

**Comportamientos obligatorios:**
- Debe funcionar bien en **escritorio, tablet y móvil en orientación vertical** (no solo horizontal) — este punto se pidió explícitamente y ya está resuelto a nivel funcional (transformación de tablas en tarjetas apiladas en móvil).
- El sistema debe seguir distinguiendo visual o textualmente qué facturas **"necesitan revisión"** frente a las que están **"revisadas"**, de forma que se pueda identificar rápido dónde hay que prestar atención.

---

# 10. Objetivo para Claude Design

El objetivo de este documento **NO es pedir funcionalidades nuevas**. Todo lo que hace la aplicación hoy (sección 2) ya es exactamente lo que debe seguir haciendo.

Claude Design deberá, al proponer mockups o mejoras de interfaz:

- **Mantener el 100% de la funcionalidad existente** descrita en la sección 2 — ni una función menos.
- **Mejorar únicamente la experiencia visual y de interacción** (UX/UI): jerarquía visual, identidad de marca, iconografía, estados vacíos, feedback de acciones, densidad de información — los puntos detallados en la sección 8 son un buen punto de partida, no una lista cerrada.
- **Proponer una interfaz moderna, limpia y profesional**, adecuada para una herramienta interna de gestión financiera usada a diario por personas no necesariamente técnicas.
- **Mantener la arquitectura de pantallas** descrita en la sección 3 (las mismas pantallas, con las mismas relaciones entre ellas) — se puede rediseñar cómo se ven, no qué pantallas existen ni cómo se conectan, salvo que se proponga explícitamente y se justifique.
- **No eliminar ninguna acción existente** (subir, ver, exportar general, exportar individual, reprocesar, reprocesar todas).
- **Respetar todas las restricciones de la sección 9** sin excepción.
- **Priorizar claridad, rapidez y facilidad de uso** por encima de la sofisticación visual — el público objetivo incluye a una persona que se autodefine como usuaria novata, y a otra persona (la que gestiona la contabilidad día a día) cuya opinión sobre la interfaz aún está pendiente de recoger, por lo que conviene proponer opciones razonablemente conservadoras antes que apuestas visuales arriesgadas.
