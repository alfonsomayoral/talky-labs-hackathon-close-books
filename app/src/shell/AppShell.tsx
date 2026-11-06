// App frame: sidebar + topbar + routed page, plus the object panel and the ⌘K palette.
import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router'
import { Badge } from '@/components'
import { PAGE_VIEWS, useData } from '@/data'
import { ObjectPanelHost } from '@/features/object/ObjectPanel'
import { useGlobalShortcuts } from '@/lib/keyboard'
import { CommandPalette } from './CommandPalette'
import { Sidebar } from './Sidebar'
import { useShellUi } from './uiStore'
import styles from './AppShell.module.css'

const TITLES: Record<string, string> = {
  '/': 'Resumen',
  '/importar': 'Importar datos',
  ...Object.fromEntries(PAGE_VIEWS.map((v) => [v.path!, v.label])),
}

export function AppShell() {
  const { pathname } = useLocation()
  const source = useData((s) => s.dataset?.meta.source)
  const togglePalette = useShellUi((s) => s.togglePalette)
  const title = TITLES[pathname] ?? 'Página no encontrada'

  useEffect(() => {
    document.title = `${title} · Close the Books`
  }, [title])

  useGlobalShortcuts({ onPalette: togglePalette, onHelp: togglePalette, onGo: () => false })

  return (
    <>
      <a
        href="#contenido"
        className={styles.skipLink}
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('contenido')?.focus()
        }}
      >
        Saltar al contenido
      </a>
      <div className={styles.shell}>
        <Sidebar />
        <div className={styles.main}>
          <header className={styles.topbar}>
            <span className={styles.topbarTitle}>{title}</span>
            <div className={styles.topbarActions}>{source === 'fixtures' && <Badge variant="outline">Datos de muestra</Badge>}</div>
          </header>
          <main id="contenido" tabIndex={-1} className={styles.content}>
            <Outlet />
          </main>
        </div>
      </div>
      <ObjectPanelHost />
      <CommandPalette />
    </>
  )
}
