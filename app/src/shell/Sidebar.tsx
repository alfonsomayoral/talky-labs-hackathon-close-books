import { NavLink } from 'react-router'
import clsx from 'clsx'
import { Building2, ChevronsUpDown, Command, LayoutDashboard, Upload } from 'lucide-react'
import { Kbd, Menu, TalkyMark, type MenuItem } from '@/components'
import { PAGE_VIEWS, useData } from '@/data'
import { formatMonth, formatNumber } from '@/lib/format'
import { MOD_KEY } from '@/lib/keyboard'
import { useEntityScope, useScopedTo } from '@/lib/urlState'
import { useShellUi } from './uiStore'
import styles from './Sidebar.module.css'

function EntityScope() {
  const entities = useData((s) => s.dataset?.entities ?? [])
  const [entity, setEntity] = useEntityScope()
  const current = entities.find((e) => e.id === entity)
  const items: MenuItem[] = [
    { id: 'all', label: 'Todas las sociedades', hint: formatNumber(entities.length), checked: !entity, onSelect: () => setEntity(null) },
    { type: 'separator', id: 's' },
    ...entities.map<MenuItem>((e) => ({ id: e.id, label: e.name, hint: `${e.id} · ${e.currency}`, checked: e.id === entity, onSelect: () => setEntity(e.id) })),
  ]
  return (
    <Menu
      aria-label="Cambiar de sociedad"
      className={styles.switcherMenu}
      items={items}
      trigger={
        <button type="button" className={styles.switcher}>
          <Building2 aria-hidden className={styles.entryIcon} />
          <span className={styles.switcherText}>
            <span className={styles.switcherName}>{current ? current.name : 'Todas las sociedades'}</span>
            <span className={styles.switcherSub}>{current ? `${current.id} · ${current.country} · ${current.currency}` : 'Vista consolidada del grupo'}</span>
          </span>
          <ChevronsUpDown aria-hidden className={styles.switcherIcon} />
        </button>
      }
    />
  )
}

export function Sidebar() {
  const dataset = useData((s) => s.dataset)
  const run = useData((s) => s.run)
  const [entity] = useEntityScope()
  const to = useScopedTo()
  const togglePalette = useShellUi((s) => s.togglePalette)
  const holding = dataset?.entities.find((e) => !e.parentId)
  const period = dataset?.meta.period ?? run?.period ?? null

  const count = (rows: { entityId?: string; id: string }[]) => (entity ? rows.filter((r) => (r.entityId ?? r.id) === entity).length : rows.length)
  const entry = ({ isActive }: { isActive: boolean }) => clsx(styles.entry, isActive && styles.active)

  return (
    <aside className={styles.sidebar}>
      <div className={styles.top}>
        <div className={styles.brand}>
          <TalkyMark className={styles.mark} />
          <span className={styles.switcherText}>
            <span className={styles.switcherName}>{holding?.name ?? dataset?.meta.name ?? 'Sin datos'}</span>
            <span className={styles.switcherSub}>{period ? `Cierre de ${formatMonth(period)}` : 'Periodo por determinar'}</span>
          </span>
        </div>
      </div>
      <div className={styles.scope}>
        <EntityScope />
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
              </NavLink>
            </li>
          </ul>
        </div>
        <div className={styles.section}>
          <div id="nav-data" className={styles.sectionTitle}>
            Datos
          </div>
          <ul className={styles.entries} aria-labelledby="nav-data">
            {PAGE_VIEWS.map((v) => {
              const Icon = v.icon
              const n = dataset ? count(dataset[v.kind] as { entityId?: string; id: string }[]) : 0
              return (
                <li key={v.kind}>
                  <NavLink to={to(v.path!)} className={entry}>
                    <Icon aria-hidden className={styles.entryIcon} />
                    <span className={styles.entryLabel}>{v.label}</span>
                    <span className={clsx(styles.badge, 'tabular')}>{formatNumber(n)}</span>
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </div>
      </nav>

      <div className={styles.footer}>
        <NavLink to={to('/importar')} className={({ isActive }) => clsx(styles.entry, styles.footerEntry, isActive && styles.active)}>
          <Upload aria-hidden className={styles.entryIcon} />
          <span className={styles.entryLabel}>Importar datos</span>
        </NavLink>
        <button type="button" className={clsx(styles.entry, styles.footerEntry)} onClick={togglePalette}>
          <Command aria-hidden className={styles.entryIcon} />
          <span className={styles.entryLabel}>Comandos</span>
          <span className={styles.keys}>
            <Kbd>{MOD_KEY}</Kbd>
            <Kbd>K</Kbd>
          </span>
        </button>
      </div>
    </aside>
  )
}
