// ⌘K: go to a page, or find any object of the package by id, name or number and open it in the panel.
import { useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { Command as Cmdk } from 'cmdk'
import { LayoutDashboard, Search, Upload } from 'lucide-react'
import { Dialog, Kbd } from '@/components'
import { KIND_OF } from '@/domain'
import { PAGE_VIEWS, VIEWS, refKey, useData, type AnyObject } from '@/data'
import { MOD_KEY } from '@/lib/keyboard'
import { useScopedTo } from '@/lib/urlState'
import { useShellUi } from './uiStore'
import styles from './CommandPalette.module.css'

const MAX_RESULTS = 12

const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

export function CommandPalette() {
  const open = useShellUi((s) => s.paletteOpen)
  const setOpen = useShellUi((s) => s.setPaletteOpen)
  const dataset = useData((s) => s.dataset)
  const links = useData((s) => s.links)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const to = useScopedTo()
  const [query, setQuery] = useState('')

  const pages = useMemo(
    () => [
      { id: '/', label: 'Resumen', icon: <LayoutDashboard /> },
      ...PAGE_VIEWS.map((v) => ({ id: v.path!, label: v.label, icon: <v.icon /> })),
      { id: '/importar', label: 'Importar datos', icon: <Upload /> },
    ],
    [],
  )

  const results = useMemo(() => {
    const q = normalize(query.trim())
    if (q.length < 2 || !dataset || !links) return []
    const out: { key: string; label: string; hint: string; icon: ReactNode }[] = []
    for (const v of VIEWS) {
      for (const o of dataset[v.kind] as AnyObject[]) {
        if (!normalize(v.search(o, links)).includes(q)) continue
        out.push({ key: refKey({ kind: KIND_OF[v.kind], id: o.id }), label: v.title(o, links), hint: o.id, icon: <v.icon /> })
        if (out.length >= MAX_RESULTS) return out
      }
    }
    return out
  }, [query, dataset, links])

  const visiblePages = pages.filter((p) => normalize(p.label).includes(normalize(query.trim())))

  const close = () => {
    setOpen(false)
    setQuery('')
  }

  const go = (target: string, open?: string) => {
    close()
    const scoped = to(target)
    const params = new URLSearchParams(scoped.search)
    if (open) params.set('ver', open)
    navigate({ pathname: scoped.pathname, search: params.size ? `?${params}` : '' })
  }

  return (
    <Dialog open={open} onClose={close} title="Paleta de comandos" bare placement="top" size="md" className={styles.dialog}>
      <Cmdk shouldFilter={false} loop label="Paleta de comandos" className={styles.root}>
        <div className={styles.inputRow}>
          <Search aria-hidden className={styles.searchIcon} />
          <Cmdk.Input value={query} onValueChange={setQuery} placeholder="Busca una página, un proveedor, una factura, un IBAN…" className={styles.input} />
          <Kbd>Esc</Kbd>
        </div>
        <Cmdk.List className={styles.list}>
          <Cmdk.Empty className={styles.empty}>Sin resultados para «{query}»</Cmdk.Empty>
          {results.length > 0 && (
            <Cmdk.Group heading="Objetos" className={styles.group}>
              {results.map((r) => (
                <Cmdk.Item key={r.key} value={r.key} onSelect={() => go(pathname, r.key)} className={styles.item}>
                  <span className={styles.icon}>{r.icon}</span>
                  <span className={styles.label}>{r.label}</span>
                  <span className={styles.hint}>{r.hint}</span>
                </Cmdk.Item>
              ))}
            </Cmdk.Group>
          )}
          {visiblePages.length > 0 && (
            <Cmdk.Group heading="Ir a" className={styles.group}>
              {visiblePages.map((p) => (
                <Cmdk.Item key={p.id} value={p.id} onSelect={() => go(p.id)} className={styles.item}>
                  <span className={styles.icon}>{p.icon}</span>
                  <span className={styles.label}>{p.label}</span>
                </Cmdk.Item>
              ))}
            </Cmdk.Group>
          )}
        </Cmdk.List>
        <div className={styles.footer}>
          <span>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navegar
          </span>
          <span>
            <Kbd>↵</Kbd> abrir
          </span>
          <span className={styles.footerEnd}>
            <Kbd>{MOD_KEY}</Kbd>
            <Kbd>K</Kbd> abrir o cerrar
          </span>
        </div>
      </Cmdk>
    </Dialog>
  )
}
