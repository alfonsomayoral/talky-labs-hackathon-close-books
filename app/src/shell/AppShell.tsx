// App frame: an icon rail that opens into the full sidebar on hover, and the routed view inside one
// sheet; plus the ⌘K palette. Below 900px the sidebar becomes a drawer.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Outlet, useLocation } from 'react-router'
import clsx from 'clsx'
import { Menu as MenuIcon, Search } from 'lucide-react'
import { IconButton, TalkyMark } from '@/components'
import { SCREENS } from '@/data'
import { getFocusable, trapTabKey, useGlobalShortcuts, useLayer } from '@/lib/keyboard'
import { CommandPalette } from './CommandPalette'
import { Sidebar } from './Sidebar'
import { useShellUi } from './uiStore'
import styles from './AppShell.module.css'

const WIDE = '(min-width: 901px)'
const subscribeWide = (cb: () => void) => {
  const mq = window.matchMedia(WIDE)
  mq.addEventListener('change', cb)
  return () => mq.removeEventListener('change', cb)
}
const isWide = () => window.matchMedia(WIDE).matches

const TITLES: Record<string, string> = Object.fromEntries(SCREENS.map((s) => [s.path, s.label]))

export function AppShell() {
  const { pathname } = useLocation()
  const togglePalette = useShellUi((s) => s.togglePalette)
  const [drawer, setDrawer] = useState(false)
  const [hover, setHover] = useState(false)
  const [focusIn, setFocusIn] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const desktop = useSyncExternalStore(subscribeWide, isWide)
  const expanded = drawer || hover || focusIn || menuOpen || !desktop

  // A short delay both ways, so crossing the rail on the way to the page does not open it.
  const hoverTo = (next: boolean) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setHover(next), next ? 120 : 200)
  }
  useEffect(() => () => clearTimeout(timer.current), [])
  const title = TITLES[pathname] ?? 'Página no encontrada'

  useEffect(() => {
    document.title = `${title} · Close the Books`
    setDrawer(false)
  }, [title])

  // The drawer is modal: Esc closes it, Tab stays inside, focus goes in and comes back to the menu button.
  const drawerRef = useRef<HTMLDivElement>(null)
  useLayer(drawer && !desktop, () => setDrawer(false))
  useEffect(() => {
    if (!drawer) return
    const previous = document.activeElement as HTMLElement | null
    if (drawerRef.current) getFocusable(drawerRef.current)[0]?.focus()
    return () => previous?.focus()
  }, [drawer])

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
        <div className={clsx(styles.rail, desktop && expanded && styles.railExpanded)}>
          <div
            ref={drawerRef}
            inert={!desktop && !drawer}
            className={clsx(styles.sidebarWrap, drawer && styles.drawerOpen)}
            onKeyDown={(e) => {
              if (drawer) trapTabKey(e, drawerRef.current)
            }}
            onMouseEnter={() => hoverTo(true)}
            onMouseLeave={() => hoverTo(false)}
            onFocus={(e) => setFocusIn(e.target.matches(':focus-visible'))}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocusIn(false)
            }}
          >
            <Sidebar expanded={expanded} onMenuOpenChange={setMenuOpen} />
          </div>
        </div>
        {drawer && <div className={styles.scrim} onClick={() => setDrawer(false)} aria-hidden />}
        <div className={styles.sheet}>
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
      <CommandPalette />
    </>
  )
}
