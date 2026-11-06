// App frame: sidebar + routed page on one ground, plus the object panel and the ⌘K palette.
// Below 900px the sidebar becomes a drawer opened from a 48px top bar.
import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import clsx from 'clsx'
import { Menu as MenuIcon, Search } from 'lucide-react'
import { IconButton, TalkyMark } from '@/components'
import { PAGE_VIEWS } from '@/data'
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
  const togglePalette = useShellUi((s) => s.togglePalette)
  const [drawer, setDrawer] = useState(false)
  const title = TITLES[pathname] ?? 'Página no encontrada'

  useEffect(() => {
    document.title = `${title} · Close the Books`
    setDrawer(false)
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
        <div className={clsx(styles.drawer, drawer && styles.drawerOpen)}>
          <Sidebar />
        </div>
        {drawer && <div className={styles.scrim} onClick={() => setDrawer(false)} aria-hidden />}
        <div className={styles.main}>
          <header className={styles.mobileBar}>
            <TalkyMark size={20} />
            <span className={styles.mobileTitle}>{title}</span>
            <IconButton icon={<Search />} label="Buscar" onClick={togglePalette} />
            <IconButton icon={<MenuIcon />} label="Menú" onClick={() => setDrawer(true)} />
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
