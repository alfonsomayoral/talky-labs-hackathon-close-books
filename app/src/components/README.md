# Componentes base

Import everything from `@/components`. Tokens: `src/design/tokens.css` (Talky brand, ARCHITECTURE.md §5.4).

## Rules

- **Colour carries meaning only.** Deep green (`--brand`) = main data, selection, focus. Status colours = status. Everything else is ink on the surfaces with hairline borders (`--line`). Light and dark themes (`data-theme` on `<html>`, `@/lib/theme`); the values below are the dark theme's.
- **One primary button per view** (`--action`: deep green, a lightened one on dark). The rest: `secondary` (outlined in `--brand-ink`) or `ghost`.
- **Small green text** uses `--brand-ink` (AA on `--bg` in both themes). Status text on tinted fills uses `--ok-ink`, `--warn-ink`, `--danger-ink`, `--info-ink`.
- **Green indicators** (selected border or underline, focus ring, check) use `--brand-line` (≥ 3:1). Green fills take `--ink-inverse` text, as the checked filter box does. `--brand` stays for large areas and icons next to a label.
- **Grey text** is `--ink-3` at least (AA on `--bg` and `--bg-muted`); `--ink-4` is only for disabled text and decorative icons.
- **Ids, accounts, codes, policy refs** → `Mono`. **Money** → `Amount` (never format cents by hand), right-aligned in tables. Dates/percent/durations → `@/lib/format`.
- **Density:** rows 44px, 13px text, 16px lucide icons with 1.5 stroke (set globally by `LucideProvider` in `main.tsx`; just render `<Icon />`).
- No banners, illustrations or heavy shadows. Gradients only on `[data-surface='feature']` (the Overview header and large-figure cards) and the primary button on hover. Empty states: an icon, a sentence, one action.
- Copy in Spanish; identifiers in English.

## Tones (`status.ts`)

`Tone` = `neutral | brand | ok | warn | danger | info`; `toneColor(tone)` gives the CSS colour for custom SVG.

## Catalogue

**Action**
- `Button` — `variant` primary|secondary(default)|ghost|danger, `size` sm|md, `loading`, `leadingIcon`, `trailingIcon`, plus all `<button>` props. `ButtonLink` = same look on a router `Link` (`to`). `buttonClassName()` for custom elements.
- `IconButton` — `icon`, `label` (required: aria-label + tooltip), `shortcut?`, `variant` ghost|secondary, `size`, `active` (pressed).
- `Kbd` — one key per element: `<Kbd>G</Kbd><Kbd>R</Kbd>`.
- `TalkyMark` — Talky's logo symbol (`public/talky-mark.svg`): `size` (px width, 22 default), `title` (accessible name; omit next to text).

**Status**
- `StatusDot` — `tone`, `label` (pass `""` when text sits next to it), `pulse` for in-progress.
- `Badge` — `tone`, `variant` soft|outline, `dot`, `icon`. For priority, case status, risk and exceptions use `emphasis` strong (filled `--action`)|medium (outlined green)|quiet (text only) instead of `tone`: never red or yellow there (`CASE_STATUS_EMPHASIS`, `RISK_EMPHASIS`). Domain labels and tones (severity, match status) live in `@/data` (`SEVERITY`, `MATCH_STATUS`): use them, don't recolour.
- `Pill` — rounded tag for metadata/counts: `tone`, `icon`, `count`, `onRemove`.
- `ConfidenceBand` — `value` 0..1|null, `showValue`.

**Data**
- `Amount` — `cents`, `currency` (EUR default; **always pass the object's currency**), `signed`, `compact` («1,2 M€», exact value in tooltip), `decimals`, `mono`, `colorize` (green +/red −), `hideCurrency`. null → «—», zero muted.
- `Mono` — `muted`. For ids: API004128, 40090000, BL0000085, §2.2.3.
- `KeyValue` — `items: {label, value, mono?}[]`, `columns` 1|2, `labelWidth`.
- `Metric` — `label`, `value` (preformatted), `delta` + `deltaTone` ok|danger|neutral, `comparison`, `hint` (info tooltip), `size` md|lg, `loading`. 3–4 per row.
- `ProgressBar` — simple: `value`/`max`/`tone`; stacked: `segments`, `showLegend`, `size` sm|md, `label`.
- `DataTable` — see below.

**Structure**
- `Page` — route wrapper (24px padding). `fill` makes it viewport-high so a DataTable scrolls inside; `width="narrow"` caps at 960px.
- `PageHeader` — `title`, `subtitle`, `breadcrumb` (in-page context; the topbar already shows the route), `actions`, `filters` (a FilterBar).
- `Card` — `title`, `description`, `actions`, `padding` none|sm|md, `interactive`.
- `Section` — titled block without surface: `title`, `description`, `count`, `actions`.
- `Tabs` — `tabs: {id, label, count?, disabled?}[]`, `value`, `onChange`, `idPrefix`; wrap content in `TabPanel` with the same `idPrefix`.
- `SegmentedControl` — `options: {value, label, icon?}[]`, `value`, `onChange`, `aria-label` (required), `size`.
- `FilterBar` — row of chips: `onClear` (pass only while a filter is active), `end` slot (result count).
- `FilterChip` — multi-select facet: `label`, `options: {value, label, count?, icon?}[]`, `selected: string[]`, `onChange`, `searchable` (auto when > 7 options).
- `EmptyState` — `icon` (lucide element), `title`, `description`, `action`, `size` sm|md.
- `Skeleton` — `width`, `height`, `radius`, `lines`.
- `Breadcrumb` — `items: {label, to?}[]`.

**Layers** (Esc closes only the topmost one; `lib/keyboard` `useLayer`)
- `SidePanel` — non-modal right panel: `open`, `onClose`, `title`, `actions`, `footer`, `defaultWidth` 560, `minWidth`, `storageKey` (remember dragged width). Tab cycles inside; list j/k keep working behind it.
- `Dialog` — modal: `open`, `onClose`, `title`, `description`, `footer` (primary last), `size` sm|md|lg, `placement` center|top, `bare`. On open, focus goes to an `autoFocus` child, else the first field, else the first control after the header.
- `Menu` — `trigger` (a Button/IconButton element), `items` (`{id, label, icon?, hint?, description?, checked?, disabled?, danger?, onSelect}` | `{type:'separator'}` | `{type:'label'}`), `side`, `align`.
- `Popover` — low-level anchored surface (`open`, `onClose`, `anchor`, `side`, `align`, `initialFocus`). Prefer Menu/FilterChip.
- `Tooltip` — `content`, `shortcut`, `side`, `delay`; child must accept pointer/focus handlers. Supplementary only.
- `toast(title, {description, tone, action, duration})`, `toast.success`, `toast.error`, `toast.dismiss(id)`. `<Toaster />` is mounted once in `main.tsx`.

## DataTable

```tsx
const columns = useMemo<Column<Invoice>[]>(() => [
  { id: 'number', header: 'Número', width: 140, cell: (i) => <Mono>{i.number}</Mono>, sortValue: (i) => i.number },
  { id: 'vendor', header: 'Proveedor', width: 'minmax(200px, 1fr)', cell: (i) => vendorName(i.vendorId) },
  { id: 'total', header: 'Total', width: 140, align: 'right', cell: (i) => <Amount cents={i.totalCents} currency={i.currency} />, sortValue: (i) => i.totalCents },
], [])

<DataTable aria-label="Facturas" rows={invoices} columns={columns} getRowId={(i) => i.id}
  sort={sort} onSortChange={setSort} onOpen={(i) => open(i.id)} globalKeys />
```

- Virtualized (tested with 40k rows); header is sticky (small uppercase); rows 44px. **Memoize `columns`** (and `rows`), or sorting reruns every render.
- `width`: px number or any grid track; default `minmax(0, 1fr)`. Horizontal scroll appears when fixed widths exceed the space.
- Sort: click a header with `sortValue` (asc → desc → off); nulls last. Controlled with `sort`/`onSortChange` or uncontrolled with `defaultSort`.
- Groups: `groupBy`, `groupOrder`, `renderGroup`; headers collapse on click and show counts.
- Keyboard: `j`/`k`/`↓`/`↑` move the cursor (brand-soft row), `Enter` → `onOpen`. `Tab` reaches the sortable headers and the group headers (`Enter` sorts or collapses). `globalKeys` listens on the whole page (use it on the page's main list, once per page).
- Height: inside `<Page fill>` it fills the remaining space; elsewhere pass `height` (px).
- Built on `@tanstack/react-virtual` only (sorting/grouping are a few pure functions in `DataTable/model.ts`), so column definitions need no TanStack Table types.

## Shell (`@/shell/…`, `@/lib/…`)

- The list of screens is `data/registry/screens.ts`: routes, sidebar and ⌘K come from it.
- URL state (`lib/urlState.ts`): `useEntityScope` (`?sociedad=`), `useRunParam` (`?run=`), `useOpenObject` (`?ver=<id>`, the object open in a screen's SidePanel), `useListParam` (multi-value facet), `useTextParam`, `useScopedTo` (links that keep run and entity).
- Global keys (`lib/keyboard.ts`): ⌘K/Ctrl+K palette, `?` help, Esc closes the top layer. Use `shouldIgnoreHotkey(e)` for your own keys.
