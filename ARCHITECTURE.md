# ARCHITECTURE.md

Cómo está construido el repo y por qué. El problema está en [PROBLEM.md](PROBLEM.md); cómo se trabaja, en [CLAUDE.md](CLAUDE.md).

> **Estado:** fase 0 (6 nov 2026). Solo existe el frontend en `app/`, con datos de muestra. El backend se monta el día del evento, cuando llegue el paquete real.

## 1. Principio rector

**El backend decide; el frontend enseña.** El frontend no toma ninguna decisión contable: muestra las **entradas** del cliente (`Dataset`) y las **decisiones** del agente (`Run`), con su evidencia. Así el frontend no cambia cuando cambian las reglas, y cada cifra que ve el jurado sale de un solo sitio.

El segundo principio es la adaptabilidad: mañana llegan datos reales con un formato que hoy no conocemos. **Todo lo que depende del formato vive en un único fichero, el registro** (§4). Adaptarse al paquete real es editar ese fichero, no las pantallas.

## 2. Estructura del repo

```
talky-labs-hackathon-close-books/
├── CLAUDE.md            cómo se trabaja en el repo
├── PROBLEM.md           el problema: qué entra, qué se evalúa, qué no sabemos
├── ARCHITECTURE.md      este fichero
├── CONTRACT.md          formato del Run: lo que el backend entrega al frontend
├── README.md
├── justfile             comandos de todo el repo
├── app/                 frontend (React)
├── backend/             fase 1: el agente de cierre (Python). Hoy solo un README
├── data/                paquete del cliente. Ignorado por git, nunca se commitea
└── .github/workflows/   CI: just fe-check
```

Monorepo: frontend y backend comparten `CONTRACT.md` y cambian a la vez en la misma PR cuando el contrato se mueve.

## 3. Frontend por capas

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

Todas son la misma `DatasetPage`: título con el recuento y las filas con alertas, buscador y una faceta, y la `DataTable` virtualizada dentro de una tarjeta. Sociedades, con pocas filas y cada una puerta a su alcance, se muestra como tarjetas. El panel lateral tiene las pestañas **Detalle** (alertas y datos) · **Relacionados** (tarjetas agrupadas por tipo) · **Historial** (línea temporal con antes y después). Las alertas del `Run` sobre un objeto se marcan en su fila.

### 5.4 Marca: Talky

La referencia es [usetalky.com](https://usetalky.com). Los valores siguientes salen de su CSS (variables `--naranja`, `--marino`, `--tinta`, `--papel`…, leídas el 6 nov 2026) y sustituyen a los de Kalmora, que usaba un naranja genérico (`#F97316`) e Inter.

| Token | Valor | Uso |
| --- | --- | --- |
| `--brand` | `#F3572F` (naranja Talky) | El dato principal (lo conciliado), la selección y el foco |
| `--brand-line` | `#E2481F` | Indicadores naranjas sin texto (foco, subrayado de la pestaña activa) |
| `--brand-soft` | `#FDEDE8` | Fondo de la selección |
| `--brand-ink` | Variante más oscura de `#F3572F` que llegue a 4,5:1 sobre blanco; se calcula en fase 0 | Texto naranja pequeño. `#F3572F` sobre blanco no llega a AA |
| `--navy` | `#16224F` (marino) · `#0F1838` (marino hondo) | La acción primaria de cada pantalla, plana |
| `--ink` | `#101938` (tinta) | Texto principal: tinta azulada, no negro |
| `--ink-2` · `--ink-3` · `--ink-4` | `#5E6377` · `#646979` · `#A2A5B2` | Texto secundario · terciario (AA sobre el fondo) · solo decorativo |
| `--ground` | `#F4F3F0` | Fondo de la app: una piedra de baja saturación sacada del papel de Talky (`#FAF5EA` se lee como crema). Las tarjetas son blancas |
| `--bg-muted` | `#EEF0F4` | Superficies neutras, cabeceras de tabla |
| `--info` | `#2E4DB3` | Estado informativo, enlaces |

| Tipografía | Familia | Uso |
| --- | --- | --- |
| Titulares | Outfit (300–500) | Frase de apertura del Resumen, títulos de página |
| Texto | Manrope (400–600) | Interfaz, tablas |
| Mono | Martian Mono (400–500) | Ids, cuentas, códigos (`ACC·214`, `VAT·021` en la web de Talky) |

Se autoalojan con `@fontsource` (sin dependencia de Google Fonts en la demo). Los colores de estado (ok, warn, danger) se mantienen de Kalmora, ajustados para no competir con el naranja.

Logo: el símbolo de Talky junto al nombre del producto, «Close the Books», en la cabecera de la barra lateral.

### 5.5 Reglas visuales

Estilo «achromatic ledger» de la skill de diseño, con la marca de Talky: el cromo en tinta, una sola acción primaria en marino y el naranja solo en el dato principal, la selección y el foco. Superficies planas: tarjetas blancas con borde de 1 px sobre el fondo, sin sombras en reposo, radios de 8 y 6 px. Lo que abre otra cosa es una tarjeta (alertas, sociedades, tipos de dato, objetos relacionados), a la manera de rex.inc. Además, de Kalmora: colores de estado solo para estado; sin banners, ilustraciones ni degradados; filas de 36 px; números a la derecha con `tabular-nums`; importes con `<Amount>` e ids con `<Mono>`. El tono es el de la web de Talky: denso, centrado en el producto, con códigos en mono como elemento visual. Interfaz en español; código en inglés.

## 6. Qué se reutiliza del repo de Kalmora

Es código nuestro (`alfonsomayoral/talky-labs-hackathon`). Se copia y se recorta; nada de Kapia.

| Se copia | Se reescribe | Se deja fuera |
| --- | --- | --- |
| `design/` (estructura de tokens y global; valores de marca y fuentes cambian a los de Talky, §5.4), `lib/format`, `lib/keyboard`, `components/` salvo los acoplados al dominio, el parser CSV y `decodeText`/`decimalToCents` | `shell/` (más simple), `Badge`/`StatusDot`/`ProgressBar` sin tipos de Kalmora, store, tipos de dominio | Motor de derivación, score, asistente, comparar, observabilidad, ejecuciones, d3-sankey, recharts |

**Stack:** React 19, Vite 8, TypeScript 6 estricto, react-router, zustand, TanStack Virtual, CSS Modules, lucide-react, fflate y cmdk. Pruebas con vitest; lint con oxlint.

## 7. Verificación

| Capa | Cómo se comprueba |
| --- | --- |
| `data/` (parsers, specs, relaciones, fixtures) | vitest: cada spec mapea una fila de ejemplo y rechaza una fila inválida; las anomalías sembradas están presentes en los fixtures |
| `features/` y `shell/` | En el navegador con los fixtures: navegación, filtro por sociedad, panel lateral, cero errores en consola |
| Todo el frontend | `just fe-check` (typecheck, lint, test, build) en verde, también en CI |

## 8. Decisiones

| # | Decisión | Por qué |
| --- | --- | --- |
| 1 | El frontend no decide nada contable | Una sola fuente de verdad; el jurado puntúa las decisiones del agente |
| 2 | Registro declarativo como único punto de adaptación | El formato real se conoce el día del evento |
| 3 | `Dataset` (entradas) separado de `Run` (decisiones) | Se pueden ver los datos sin backend, y comparar varias ejecuciones sobre los mismos datos |
| 4 | Monorepo con `CONTRACT.md` en la raíz | Backend y frontend cambian el contrato en la misma PR |
| 5 | Sin API ni persistencia en fase 0 | No hay backend todavía; se añaden cuando hagan falta |
| 6 | El historial del ERP va en el panel de cada objeto | Su valor está en contexto (un cambio de IBAN junto a su proveedor) |
