# ARCHITECTURE.md

Cómo está construido el repo y por qué. El problema está en [PROBLEM.md](PROBLEM.md); cómo se trabaja, en [CLAUDE.md](CLAUDE.md).

> **Estado:** 6 nov 2026. El reto real es **conciliación bancaria a escala** (PROBLEM.md). El backend (§7) es el producto: produce el CSV que se puntúa. Hoy solo existe su diseño. El frontend (§3–§6) está **congelado en la fase 0**: se construyó para el problema supuesto en la v0 (cierre contable con libro mayor e historial del ERP), solo se retoma si sobra tiempo para el vídeo, y sus secciones describen el código tal y como está.

## 1. Principios rectores

1. **Las reglas deciden; los modelos solo extraen.** Cada fila de la entrega sale de una regla determinista con nombre, que deja su evidencia (CONTRACT.md). Un modelo de lenguaje solo convierte documentos sucios (PDFs, avisos de remesa) en hechos estructurados, que se guardan en caché. Así la ejecución es reproducible, se explica fila a fila y no paga un modelo por movimiento.
2. **`POLICIES.md` es la especificación.** El golden la sigue al pie de la letra. Cada regla cita el apartado de la política que implementa; lo que la política no dice se aprende del golden de TRAIN, no se inventa.
3. **Se mide en local, con el evaluador oficial.** LIVE tiene 20 envíos al día y FINAL uno solo. Cada cambio se puntúa sobre `sample/` (segundos) y TRAIN (minutos) con `bankrec_score.py`, por segmento, antes de gastar un envío.
4. **No se fuerza ninguna casación.** Lo que ninguna regla respalda sale por una regla de respaldo (`UNIDENTIFIED` o una categoría), nunca como el candidato «más parecido».

## 2. Estructura del repo

```
talky-labs-hackathon-close-books/
├── CLAUDE.md            cómo se trabaja en el repo
├── PROBLEM.md           el problema: qué entra, qué sale, cómo se puntúa
├── ARCHITECTURE.md      este fichero
├── CONTRACT.md          lo que produce cada ejecución: entrega, explicaciones y run.json
├── README.md
├── justfile             comandos de todo el repo
├── backend/             el conciliador (Python), §7. Hoy solo un README
├── app/                 frontend (React), congelado en la fase 0, §3–§6
├── db/                  paquete oficial: bankrec-docs-and-masters/, train/, live/, final/. Ignorado por git
├── runs/                ejecuciones del backend (CONTRACT.md). Ignorado por git
└── .github/workflows/   CI: just fe-check
```

## 3. Frontend por capas

> **Congelado en la fase 0.** Lee un zip en el navegador y muestra un `Dataset` y un `Run` del modelo v0. Con el paquete real (2,3 GB) esa importación no es viable, y el `Run` v0 ya no lo produce nadie (CONTRACT.md). No se amplía sin decidirlo antes.

```
app/src/
├── domain/        tipos puros del dominio. Sin React ni E/S
├── data/          de dónde vienen los datos y cómo se normalizan
│   ├── sources/   fixtures · zip   (api, en fase 1)
│   ├── parsers/   csv · json · jsonl
│   ├── registry/  mappings.ts: qué ficheros lee cada tipo y cómo los mapea   ← punto de adaptación
│   │              views.tsx: columnas, búsqueda, faceta y detalle de cada tipo
│   ├── fixtures/  datos de muestra deterministas, con anomalías sembradas
│   ├── links.ts   relaciones entre objetos (factura → pedido → contrato → proveedor)
│   ├── store.ts   zustand: dataset cargado y run
│   └── index.ts   API pública de la capa
├── features/
│   ├── overview/  Resumen
│   ├── dataset/   página genérica de tabla, alimentada por el registro
│   ├── object/    panel lateral de cualquier objeto
│   └── import/    importar el zip y ver los ficheros no reconocidos
├── shell/         AppShell, Sidebar, selector de sociedad y periodo, ⌘K, rutas
├── components/    primitivas de UI (Amount, DataTable, SidePanel, Tabs, FilterBar…)
├── design/        tokens.css, global.css, fuentes
└── lib/           format, keyboard
```

**Dependencias en un solo sentido:**

```
shell ─▶ features ─▶ data (solo su index público) ─▶ domain
   └──────────┴─────▶ components ─▶ design, lib
```

- `domain/` no importa nada del proyecto.
- `features/` solo importa de `@/data` (su `index.ts`), `@/domain`, `@/components` y `@/lib`. Nunca de `data/sources`, `data/parsers` ni `data/registry` por dentro.
- El alcance (`?sociedad=`) y el objeto abierto (`?ver=`) viven en la URL, con los hooks de `lib/urlState.ts`.
- `components/` no conoce el dominio: recibe props.

## 4. Datos

### 4.1 Dos objetos, dos orígenes

| Objeto | Qué es | Quién lo produce |
| --- | --- | --- |
| `Dataset` | Las entradas del cliente, normalizadas: sociedades, proveedores, contratos, pedidos, facturas, transacciones, libro mayor e historial del ERP | El frontend, al leer el zip con el registro |
| `Run` | Las decisiones del agente: casaciones, alertas, asientos propuestos y métricas, cada una con su evidencia | El backend, con el formato de `CONTRACT.md`. En fase 0, un fixture con esa misma forma |

```ts
interface Dataset {
  meta: { name: string; period: string; source: 'fixtures' | 'zip'; loadedAt: string }
  entities: Entity[]
  vendors: Vendor[]
  contracts: Contract[]
  purchaseOrders: PurchaseOrder[]
  invoices: Invoice[]
  bankTransactions: BankTransaction[]
  ledgerEntries: LedgerEntry[]
  erpEvents: ErpEvent[]
  unmapped: RawFile[]     // ficheros que ningún spec reconoce: se ven en crudo, no se pierden
  issues: DataIssue[]     // filas que un spec no pudo mapear, con fichero y línea
}
```

Convenciones de todos los tipos:
- Importes en **céntimos enteros** con su `currency`. Nunca se suman monedas distintas; un total de grupo se da por moneda hasta que haya tipos de cambio.
- Todo objeto lleva `id` y `entityId`, que es lo que permite filtrar por sociedad en cualquier pantalla.
- Las referencias entre objetos son ids (`invoice.purchaseOrderId`, `purchaseOrder.contractId`…). `data/index.ts` las resuelve una vez al cargar.

### 4.2 El registro: el único sitio que conoce el formato

El registro tiene dos mitades, por tipo de dato:

```ts
// registry/mappings.ts — depende del formato del paquete. Puro: también corre en el worker de importación.
interface Mapping<T> {
  kind: DatasetKind                    // 'invoices', 'vendors'…
  files: (path: string) => boolean     // qué ficheros del zip alimentan este tipo
  map: (row: RawRow) => T              // columnas reales → tipo del dominio
}

// registry/views.tsx — solo depende del tipo del dominio
interface DatasetView<T> {
  kind: DatasetKind
  label: string                        // 'Facturas'
  path: string | null                  // '/facturas'; null si solo se ve en paneles (historial del ERP)
  icon: LucideIcon
  title, columns, search, facet?, detail   // cómo se nombra, se lista, se busca, se filtra y se detalla
}
```

- La barra lateral y las rutas de **DATOS** se generan a partir del registro. Un tipo de dato nuevo es un spec nuevo, no una página nueva.
- El día del evento, para cada tipo, se tocan `files` y `map` en `mappings.ts`. `views.tsx` trabaja sobre el tipo del dominio y no cambia.
- `map` lanza un error claro si falta un campo obligatorio. La fila va a `issues` y la carga sigue.

### 4.3 Fuentes

```ts
interface DataSource {
  load(): Promise<{ dataset: Dataset; run: Run | null }>
}
```

| Fuente | Cuándo | Notas |
| --- | --- | --- |
| `fixtures` | Arranque por defecto en fase 0 | ~3 sociedades, ~60 facturas, ~120 transacciones. Deterministas, sin librerías de datos falsos. Traen un `Run` de muestra con las anomalías del reto |
| `zip` | El usuario arrastra el paquete del cliente | Se descomprime en el navegador (fflate) y se parsea en un Web Worker para no bloquear la interfaz con un libro mayor grande |
| `api` | Fase 1 | Lee el `Run` del backend con el formato de `CONTRACT.md` |

Fase 0 no persiste nada: recargar la página vuelve a los fixtures. La persistencia (IndexedDB) se añade si el paquete real tarda en cargar.

## 5. Interfaz

### 5.1 Navegación

```
[◆] Close the Books · Talky
┌ <Holding>               ⇅ ┐   grupo, periodo y alcance: todo el grupo o una sociedad
└ sept 2026 · todo el grupo ┘
  Buscar               ⌘K

Cierre
  Resumen               5       alertas del agente
Datos del cliente               generado desde el registro (navLabel si el nombre no cabe)
  Sociedades            4       /sociedades (tarjetas)
  Proveedores          14       /proveedores
  Contratos             6       /contratos
  Pedidos              28       /pedidos
  Facturas             57       /facturas
  Banco                57       /banco
  Libro mayor         275       /libro-mayor
──────
  Importar datos                /importar
  ● Datos de muestra            origen de los datos cargados
```

- **El alcance va en la URL:** `?sociedad=<id>` y `?periodo=<yyyy-mm>`. Un enlace copiado abre la misma vista.
- **El panel lateral también va en la URL:** `?ver=invoice:F-2026-0012`. Se abre sobre cualquier tabla sin cambiar de página.
- **El historial del ERP no tiene pestaña propia.** Aparece en la pestaña **Historial** del panel lateral de cada objeto (por ejemplo, los cambios de IBAN de un proveedor). Si el paquete real trae un registro de auditoría rico, se promociona a una entrada «Auditoría» en CIERRE.

### 5.2 Resumen

Su pregunta: ¿qué queda para cerrar el periodo y qué necesita a una persona?

1. **Título y hallazgo:** «Cierre de septiembre de 2026» y, debajo, lo retenido por riesgo y lo pendiente de revisar. A la derecha, «Revisar alertas» (primaria) e «Importar datos».
2. **Una franja con los cinco criterios del jurado:** precisión contable, conciliación, detección de fraude, autonomía segura y auditabilidad. Salen del `Run`; sin `Run`, «—» y la definición en un tooltip.
3. **«Te necesitan»** (2/3): las alertas del `Run` por severidad, como tarjetas con motivo, tipo, objeto e importe. Cada una abre el panel lateral.
4. **Conciliación bancaria** (1/3): el porcentaje casado, la barra casadas/sugeridas/sin casar, los movimientos por revisar y una barra por sociedad.
5. **Sociedades del grupo:** una tarjeta por sociedad con su volumen y su conciliación; filtra toda la app.
6. **Datos del cliente:** una tarjeta por tipo con una vista previa de sus filas reales; abre su tabla.

### 5.3 Páginas de datos

Todas son la misma `DatasetPage`: título con el recuento y las filas con alertas, buscador y una faceta, y la `DataTable` virtualizada en su variante `cards`, donde cada fila es una tarjeta independiente sobre la hoja, con borde y sombra suave. Las páginas usan todo el ancho de la pantalla y el panel lateral se abre al 40 % del ancho. Sociedades, con pocas filas y cada una puerta a su alcance, se muestra como tarjetas. El panel lateral tiene las pestañas **Detalle** (alertas y datos) · **Relacionados** (tarjetas agrupadas por tipo) · **Historial** (línea temporal con antes y después). Las alertas del `Run` sobre un objeto se marcan en su fila.

### 5.4 Marca: Talky

La referencia es [usetalky.com](https://usetalky.com). El marino y la tinta salen de su CSS (variables `--marino`, `--tinta`…, leídas el 6 nov 2026) y sustituyen a los de Kalmora, que usaba un naranja genérico (`#F97316`) e Inter. El color de acento ya no es el naranja de Talky (`#F3572F`) sino un **verde bosque**: el clásico `#228B22` solo llega a 3,9:1 sobre la hoja oscura, así que se mantiene su tono (142°) y se aclara hasta pasar AA.

La app tiene **dos temas**. El claro vive en `:root` (la hoja blanca sobre la piedra de Talky) y el oscuro sobreescribe los colores bajo `[data-theme='dark']`: la tinta azulada de Talky pasa a ser el fondo y el texto es claro. `index.html` pone `data-theme` en `<html>` antes de pintar (la elección guardada en `localStorage`, si no la del sistema) y `src/lib/theme.ts` lo cambia desde la barra lateral. `color-scheme` hace que los controles nativos sigan al tema. El verde bosque mantiene el tono (142°) en los dos: `#2E9A5C` en claro, oscurecido para pasar sobre blanco (texto pequeño `#1F7A45`, 5,4:1), y `#46A86A` en oscuro. Los valores que siguen son los del tema oscuro.

| Token | Valor | Uso |
| --- | --- | --- |
| `--brand` | `#46A86A` (verde bosque) | El dato principal (lo conciliado), la selección y el foco. Sobre `--bg` llega a 5,8:1 |
| `--brand-line` | `#46A86A` | Indicadores verdes sin texto (foco, subrayado de la pestaña activa) |
| `--brand-soft` · `--brand-border` | `#182D3D` · `#254F4A` | Fondo y borde de la selección (el verde al 14 % y al 38 % sobre `--bg`) |
| `--brand-ink` | `#7CCB95` | Texto verde pequeño: 8,9:1 sobre `--bg` y 7,7:1 sobre `--bg-muted` |
| `--ink-inverse` | `#16224F` (marino) | Texto sobre rellenos claros: el botón primario y las casillas marcadas (verdes) |
| `--ink` · `--ink-strong` | `#E6E8F0` · `#F5F6FA` | Texto principal y titulares: blanco teñido de azul, no blanco puro |
| `--ink-2` · `--ink-3` · `--ink-4` | `#AEB3C7` · `#9499B0` · `#5D6484` | Texto secundario · terciario (AA sobre `--bg-muted`) · solo decorativo |
| `--ground` | `#0A0F24` | Fondo de la app, de la tinta de Talky (`#101938`) más honda. Rail y lienzo van sobre él |
| `--bg` | `#111936` | La hoja, las tarjetas, menús y diálogos: un escalón más claro que el fondo |
| `--bg-subtle` · `--bg-muted` | `#151E3E` · `#1B2547` | Hover y superficies neutras, cabeceras de tabla |
| `--line` · `--line-strong` | `#263052` · `#344070` | Bordes de 1 px; el fuerte, en hover |
| `--info` | `#6B8AF0` | Estado informativo, enlaces |

Los colores de estado son los de Kalmora en su variante para fondo oscuro (el `--ok` es un turquesa `#2DD4BF` y no un verde, para que no se confunda con el de marca: 30° de tono más allá, más saturado y más claro): el color base para puntos y barras, un relleno al 14 % y un borde al 38 % sobre `--bg`, y un texto más claro que pasa AA sobre ambos. Las sombras son negras y con más opacidad, porque sobre oscuro casi no se ven; el borde de 1 px hace la mayor parte del trabajo.

La tipografía sigue a [rex.inc](https://www.rex.inc/collections), que usa Tiempos Headline (light) para titulares, GD Gaio para el texto y Chivo Mono para códigos. Las dos primeras son comerciales, así que van sus equivalentes libres más cercanos:

| Tipografía | Familia | Uso |
| --- | --- | --- |
| Titulares y cifras clave | Newsreader, con tamaño óptico, a peso 300 | Títulos de página, de tarjeta y del panel; las cifras grandes |
| Texto | Geist (400–600) | Interfaz, tablas, botones |
| Mono | Chivo Mono (400) | Ids, cuentas, IBAN, reglas |

Se autoalojan con `@fontsource` (sin dependencia de Google Fonts en la demo).

Logo: el logo original de Talky, que conserva sus colores (la forma rosa con borde naranja y la palabra «Talky», `public/talky-logo.png` en claro y `public/talky-logo-dark.png`, con la palabra recoloreada a la tinta clara, en oscuro) junto al nombre del producto, «Close the Books», en la cabecera de la barra lateral. La forma sola es el favicon.

### 5.5 Reglas visuales

Estilo «achromatic ledger» de la skill de diseño, con la marca de Talky: tema oscuro, el cromo en tintas claras sobre la tinta de Talky, una sola acción primaria (relleno claro con texto marino, el único bloque claro de la hoja) y el verde bosque solo en el dato principal, la selección y el foco. La ventana, a la manera de las apps de macOS: un rail de iconos de 60 px sobre el fondo que, al pasar el ratón (o con el foco del teclado), se ensancha hasta la barra lateral completa y empuja la vista, que se recoloca a su lado (200 ms, solo se anima el ancho del rail); y cada vista dentro de una única hoja (`--bg`), un escalón más clara que el fondo, separada 8 px del borde, con radio de 12 px y borde de 1 px. Encima de la hoja van las tarjetas de su contenido, con borde de 1 px, una sombra suave en reposo (`--shadow-card`) que crece al pasar el ratón (`--shadow-card-hover`), como en el frontend de Kalmora, y radios de 8 y 6 px. En móvil la hoja ocupa toda la pantalla y la barra lateral es un cajón. Lo que abre otra cosa es una tarjeta (alertas, sociedades, tipos de dato, objetos relacionados), a la manera de rex.inc. Además, de Kalmora: colores de estado solo para estado; sin banners, ilustraciones ni degradados; filas de 36 px; números a la derecha con `tabular-nums`; importes con `<Amount>` e ids con `<Mono>`. El tono es el de la web de Talky: denso, centrado en el producto, con códigos en mono como elemento visual. Interfaz en español; código en inglés.

## 6. Qué se reutiliza del repo de Kalmora

Es código nuestro (`alfonsomayoral/talky-labs-hackathon`). Se copia y se recorta; nada de Kapia.

| Se copia | Se reescribe | Se deja fuera |
| --- | --- | --- |
| `design/` (estructura de tokens y global; valores de marca y fuentes cambian a los de Talky, §5.4), `lib/format`, `lib/keyboard`, `components/` salvo los acoplados al dominio, el parser CSV y `decodeText`/`decimalToCents` | `shell/` (más simple), `Badge`/`StatusDot`/`ProgressBar` sin tipos de Kalmora, store, tipos de dominio | Motor de derivación, score, asistente, comparar, observabilidad, ejecuciones, d3-sankey, recharts |

**Stack:** React 19, Vite 8, TypeScript 6 estricto, react-router, zustand, TanStack Virtual, CSS Modules, lucide-react, fflate y cmdk. Pruebas con vitest; lint con oxlint.

## 7. Backend

Diseño inicial: aún no hay código. Python 3.12 con **Polars** para las tablas, y las librerías de cada formato sucio: pypdf (PDFs), openpyxl (avisos xlsx), rapidfuzz (comparación difusa de nombres y referencias) y el SDK de Anthropic para la extracción con modelo. Lint con ruff y tests con pytest.

### 7.1 Una ejecución

```
db/<fase>/ + masters ─▶ load ─▶ index ─▶ documents ─▶ rules ─▶ resolve ─▶ output ─▶ score
```

| Paso | Qué hace |
| --- | --- |
| `load` | Lee una fase (`sample`, `train`, `live` o `final`) y sus maestros (en FINAL, los de `final/masters_final/`) a tablas de Polars, con importes en céntimos. No modifica nada |
| `index` | Índices sobre las partidas por sociedad, tercero, número impreso normalizado, importe y divisa; y sobre los ficheros de detalle por id de remesa, liquidación, ingreso y `end_to_end_id` |
| `documents` | Convierte avisos de remesa y PDFs en hechos: documentos pagados con importe y deducción, plazos, retención, anticipo, «anula y sustituye», mes del servicio, factor, IBAN nuevo. Primero con parsers; el modelo, solo para lo que no parsean. Caché en `runs/cache/` por hash del fichero |
| `rules` | Cada regla mira los movimientos aún sin resolver y propone qué partidas liquida cada uno, con su evidencia |
| `resolve` | Recorre los movimientos por fecha de operación, aplica la propuesta de mayor prioridad, calcula importe y excepción (§7.3) y actualiza el saldo abierto de cada partida |
| `output` | Escribe la carpeta de la ejecución (CONTRACT.md) y la valida con el evaluador oficial |
| `score` | En `sample` y `train`, puntúa contra el golden y guarda el desglose por segmento en `run.json` |

### 7.2 Módulos

```
backend/
├── pyproject.toml
├── src/closebooks/
│   ├── cli.py          closebooks run --phase live → runs/live-<fecha>/
│   ├── load.py         una fase → tablas
│   ├── normalize.py    números impresos, nombres de terceros, referencias
│   ├── documents/      avisos de remesa (pdf, csv, xlsx, txt) y PDFs → hechos
│   ├── rules/          una regla por fichero, agrupadas por familia (PROBLEM.md §10)
│   ├── state.py        saldo abierto por partida y su historia de liquidaciones
│   ├── policy.py       importe y excepción de cada fila (POLICIES.md §2–§3)
│   ├── categories.py   movimientos sin partida (POLICIES.md §4)
│   ├── resolve.py      prioridad, conflictos y respaldo
│   └── output.py       CSV, explicaciones y run.json
└── tests/              casos reales de sample/ y TRAIN, uno por comportamiento
```

El evaluador oficial se usa desde `db/bankrec-docs-and-masters/starter/bankrec_score.py`; no se copia al repo.

### 7.3 Reglas, política y estado

- **Una regla responde a una sola pregunta: qué partidas liquida este movimiento.** Devuelve los ids de partida, el dinero aplicado a cada una si el documento lo dice, su nombre y sus fuentes. No decide el importe final ni la excepción.
- **`policy.py` decide el importe y la excepción en un solo sitio,** con el movimiento, las partidas, su saldo abierto, sus condiciones de pago, los tipos de cambio y los hechos de los documentos. Así `SHORT_DISCOUNT`, `FX_DIFFERENCE` o `PARTIAL` se calculan igual venga la casación de donde venga.
- **El saldo abierto se lleva en orden de fecha.** Parte de `open_items_at_start` (LIVE y FINAL) más las partidas emitidas en la fase. Es lo que distingue un plazo intermedio (`PARTIAL`) del último (vacío), un pago normal de un `DUPLICATE_PAYMENT`, y lo que deja reabrir una partida con `RETURNED`.
- **Prioridad de las reglas:** primero las que tienen un fichero que lo dice (agregados, avisos de remesa, `end_to_end_id`), luego las de número impreso, luego tercero más importe, y al final el respaldo. Una partida que ya ha consumido una regla de más prioridad no la vuelve a proponer otra.
- **Respaldo:** un cobro sin casación es `UNIDENTIFIED`; un cargo sin casación lleva la categoría que digan su código y su texto. Siempre con regla `FALLBACK-*`.

### 7.4 Ensayo de FINAL

FINAL se publica a las 18:00 y los envíos cierran a las 19:30. El sistema tiene que correr con **un solo comando** sobre una fase que no ha visto, con una sociedad, una divisa y una numeración nuevas (ZA01), sin tocar código. Se ensaya sobre LIVE, cronometrado, antes de las 18:00. El envío lo hace una persona del equipo, después de validar el fichero en local.

## 8. Verificación

| Capa | Cómo se comprueba |
| --- | --- |
| `normalize`, `documents`, `rules`, `policy`, `state` | pytest, en TDD. Cada comportamiento con un caso real de `sample/` o TRAIN; los 36 ejemplos de la web son el primer lote |
| Ejecución completa | Puntuación local sobre `sample/` y TRAIN, por segmento. Ningún segmento baja sin explicarlo en la PR |
| Entrega | `bankrec_score.py` valida el fichero antes de cada envío |
| Frontend | `just fe-check` (typecheck, lint, test, build) en verde, también en CI |

## 9. Decisiones

| # | Decisión | Por qué |
| --- | --- | --- |
| 1 | Reglas deterministas; el modelo solo extrae, con caché | Reproducible, explicable fila a fila, sin coste por movimiento |
| 2 | Python con Polars, no Rust ni C | El volumen es moderado (el starter, en Python puro, procesa TRAIN en minutos) y Polars ya corre en nativo por debajo. Lo que cuesta es iterar sobre ~40 reglas, y el evaluador oficial es Python. Rust solo para un punto caliente medido, como extensión |
| 3 | Importe y excepción en un solo módulo (`policy.py`) | `POLICIES.md` §2–§3 se aplica igual a todas las reglas |
| 4 | Saldo abierto en orden de fecha | `PARTIAL`, `DUPLICATE_PAYMENT` y `RETURNED` dependen de la historia de la partida |
| 5 | Puntuación local con el evaluador oficial | 20 envíos al día en LIVE y uno en FINAL |
| 6 | Frontend congelado en la fase 0 | Se puntúa el CSV y la escala real no cabe en el navegador |
| 7 | Datos y ejecuciones en `db/` y `runs/`, fuera de git | El paquete es de la organización y pesa 2,3 GB |
