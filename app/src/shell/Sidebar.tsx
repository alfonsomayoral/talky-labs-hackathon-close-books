import { NavLink } from 'react-router'
import clsx from 'clsx'
import { Building2, ChevronsUpDown, LayoutDashboard, Moon, Search, Sun, Upload } from 'lucide-react'
import { Kbd, Menu, TalkyLogo, TalkyMark, type MenuItem } from '@/components'
import { PAGE_VIEWS, useData } from '@/data'
import { formatMonth, formatNumber } from '@/lib/format'
import { MOD_KEY } from '@/lib/keyboard'
import { useTheme } from '@/lib/theme'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { useShellUi } from './uiStore'
import styles from './Sidebar.module.css'

/** Group, period and entity scope in one control: the scope every screen is filtered by. */
function Scope({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const dataset = useData((s) => s.dataset)
  const run = useData((s) => s.run)
  const [entity, setEntity] = useEntityScope()
  const entities = dataset?.entities ?? []
  const current = entities.find((e) => e.id === entity)
  const holding = entities.find((e) => !e.parentId)
  const period = dataset?.meta.period ?? run?.period ?? null
  const items: MenuItem[] = [
    { type: 'label', id: 'h', label: 'Ver el cierre de' },
    { id: 'all', label: 'Todo el grupo', hint: `${formatNumber(entities.length)} sociedades`, checked: !entity, onSelect: () => setEntity(null) },
    { type: 'separator', id: 's' },
    ...entities.map<MenuItem>((e) => ({ id: e.id, label: e.name, hint: `${e.id} · ${e.currency}`, checked: e.id === entity, onSelect: () => setEntity(e.id) })),
  ]
  return (
    <Menu
      aria-label="Cambiar de sociedad"
      className={styles.menu}
      items={items}
      onOpenChange={onOpenChange}
      trigger={
        <button type="button" className={styles.scope} aria-label="Cambiar de sociedad">
          <Building2 aria-hidden className={styles.entryIcon} />
          <span className={styles.scopeText}>
            <span className={styles.scopeName}>{current?.name ?? holding?.name ?? dataset?.meta.name ?? 'Sin datos'}</span>
            <span className={styles.scopeSub}>
              {period ? formatMonth(period) : 'Periodo por determinar'} · {current ? `sociedad ${current.id}` : 'todo el grupo'}
            </span>
          </span>
          <ChevronsUpDown aria-hidden className={styles.chevron} />
        </button>
      }
    />
  )
}

export interface SidebarProps {
  /** Labels shown. Collapsed, only the icons of the rail are visible. */
  expanded: boolean
  /** The scope menu opened or closed: the shell keeps the sidebar open meanwhile. */
  onMenuOpenChange: (open: boolean) => void
}

export function Sidebar({ expanded, onMenuOpenChange }: SidebarProps) {
  const dataset = useData((s) => s.dataset)
  const run = useData((s) => s.run)
  const [entity] = useEntityScope()
  const to = useScopedTo()
  const togglePalette = useShellUi((s) => s.togglePalette)
  const [theme, setTheme] = useTheme()
  const ThemeIcon = theme === 'dark' ? Sun : Moon
  const alerts = (run?.alerts ?? []).filter((a) => !entity || a.entityId === entity).length

  const count = (rows: { entityId?: string; id: string }[]) => (entity ? rows.filter((r) => (r.entityId ?? r.id) === entity).length : rows.length)
  const entry = ({ isActive }: { isActive: boolean }) => clsx(styles.entry, isActive && styles.active)

  return (
    <aside className={styles.sidebar} data-expanded={expanded || undefined}>
      <div className={styles.product}>
        <TalkyMark size={24} className={styles.markOnly} title="Talky" />
        <TalkyLogo height={30} className={styles.logoFull} />
        <span className={styles.productDivider} aria-hidden />
        <span className={styles.productName}>Close the Books</span>
      </div>
      <div className={styles.controls}>
        <Scope onOpenChange={onMenuOpenChange} />
        <button type="button" className={styles.search} onClick={togglePalette}>
          <Search aria-hidden className={styles.entryIcon} />
          <span className={styles.searchLabel}>Buscar</span>
          <span className={styles.keys}>
            <Kbd>{MOD_KEY}</Kbd>
            <Kbd>K</Kbd>
          </span>
        </button>
      </div>

      <nav className={styles.nav} aria-label="Principal">
        <div className={styles.section}>
          <div id="nav-close" className={styles.sectionTitle}>
            Cierre
          </div>
          <ul className={styles.entries} aria-labelledby="nav-close">
            <li>
              <NavLink to={to('/')} end className={entry}>
                <LayoutDashboard aria-hidden className={styles.entryIcon} />
                <span className={styles.entryLabel}>Resumen</span>
                {alerts > 0 && (
                  <span className={styles.alertCount}>
                    {formatNumber(alerts)}
                    <span className="sr-only"> alertas</span>
                  </span>
                )}
              </NavLink>
            </li>
          </ul>
        </div>
        <div className={styles.section}>
          <div id="nav-data" className={styles.sectionTitle}>
            Datos del cliente
          </div>
          <ul className={styles.entries} aria-labelledby="nav-data">
            {PAGE_VIEWS.map((v) => (
              <li key={v.kind}>
                <NavLink to={to(v.path!)} className={entry}>
                  <v.icon aria-hidden className={styles.entryIcon} />
                  <span className={styles.entryLabel}>{v.navLabel ?? v.label}</span>
                  <span className={styles.count}>{dataset ? formatNumber(count(dataset[v.kind] as { entityId?: string; id: string }[])) : ''}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <div className={styles.footer}>
        <NavLink to={to('/importar')} className={entry}>
          <Upload aria-hidden className={styles.entryIcon} />
          <span className={styles.entryLabel}>Importar datos</span>
        </NavLink>
        <button type="button" className={styles.entry} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          <ThemeIcon aria-hidden className={styles.entryIcon} />
          <span className={styles.entryLabel}>{theme === 'dark' ? 'Tema claro' : 'Tema oscuro'}</span>
        </button>
        <div className={styles.source}>
          <span className={styles.sourceDot} data-source={dataset?.meta.source} aria-hidden />
          <span className={styles.sourceText}>{dataset?.meta.source === 'zip' ? `Paquete: ${dataset.meta.name}` : 'Datos de muestra'}</span>
        </div>
      </div>
    </aside>
  )
}
