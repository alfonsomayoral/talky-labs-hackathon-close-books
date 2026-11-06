import { NavLink } from 'react-router'
import clsx from 'clsx'
import { Building2, ChevronsUpDown, Moon, Search, Sun } from 'lucide-react'
import { Kbd, Menu, TalkyLogo, TalkyMark, type MenuItem } from '@/components'
import { SCREENS, SCREEN_SECTIONS, useCurrentRun, useRunStats } from '@/data'
import { formatDate, formatNumber } from '@/lib/format'
import { MOD_KEY } from '@/lib/keyboard'
import { useTheme } from '@/lib/theme'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { useShellUi } from './uiStore'
import styles from './Sidebar.module.css'

const GROUP_NAME = 'Grupo Valtermia'

/** Group, period and entity scope in one control: the scope every screen is filtered by. */
function Scope({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const { runId } = useCurrentRun()
  const stats = useRunStats(runId, null).data
  const [entity, setEntity] = useEntityScope()
  const entities = stats?.byEntity ?? []
  const current = entities.find((e) => e.entity === entity)
  const items: MenuItem[] = [
    { type: 'label', id: 'h', label: 'Ver la conciliación de' },
    { id: 'all', label: 'Todo el grupo', hint: `${formatNumber(entities.length)} sociedades`, checked: !entity, onSelect: () => setEntity(null) },
    { type: 'separator', id: 's' },
    ...[...entities].sort((a, b) => a.entity.localeCompare(b.entity)).map<MenuItem>((e) => ({ id: e.entity, label: e.name, hint: e.entity, checked: e.entity === entity, onSelect: () => setEntity(e.entity) })),
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
            <span className={styles.scopeName}>{current?.name ?? GROUP_NAME}</span>
            <span className={styles.scopeSub}>
              {stats ? `${formatDate(stats.periodFrom)} – ${formatDate(stats.periodTo)}` : 'Sin ejecución'}
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
  const { run, runId, error } = useCurrentRun()
  const [entity] = useEntityScope()
  const stats = useRunStats(runId, entity).data
  const to = useScopedTo()
  const togglePalette = useShellUi((s) => s.togglePalette)
  const [theme, setTheme] = useTheme()
  const ThemeIcon = theme === 'dark' ? Sun : Moon
  const queue = stats?.reviewQueue ?? 0
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
        {SCREEN_SECTIONS.map((section) => (
          <div key={section.id} className={styles.section}>
            <div id={`nav-${section.id}`} className={styles.sectionTitle}>
              {section.label}
            </div>
            <ul className={styles.entries} aria-labelledby={`nav-${section.id}`}>
              {SCREENS.filter((s) => s.section === section.id).map((s) => (
                <li key={s.id}>
                  <NavLink to={to(s.path)} end={s.path === '/'} className={entry}>
                    <s.icon aria-hidden className={styles.entryIcon} />
                    <span className={styles.entryLabel}>{s.label}</span>
                    {s.id === 'inbox' && queue > 0 && (
                      <span className={styles.alertCount}>
                        {formatNumber(queue)}
                        <span className="sr-only"> casos</span>
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <button type="button" className={styles.entry} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          <ThemeIcon aria-hidden className={styles.entryIcon} />
          <span className={styles.entryLabel}>{theme === 'dark' ? 'Tema claro' : 'Tema oscuro'}</span>
        </button>
        <div className={styles.source}>
          <span className={styles.sourceDot} data-live={run ? 'true' : undefined} aria-hidden />
          <span className={styles.sourceText}>{run ? run.runId : error ? 'Sin conexión con la API' : 'Sin ejecución'}</span>
        </div>
      </div>
    </aside>
  )
}
