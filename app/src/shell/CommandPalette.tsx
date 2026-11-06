// ⌘K: go to a screen, or find a movement or a case by id, text or document number and open it.
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Command as Cmdk } from 'cmdk'
import { Inbox, ListChecks, Search } from 'lucide-react'
import { Dialog, Kbd } from '@/components'
import { SCREENS, useCases, useCurrentRun, useTransactions } from '@/data'
import { MOD_KEY } from '@/lib/keyboard'
import { useScopedTo } from '@/lib/urlState'
import { useShellUi } from './uiStore'
import styles from './CommandPalette.module.css'

const MAX_RESULTS = 8
const DEBOUNCE_MS = 200

const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

export function CommandPalette() {
  const open = useShellUi((s) => s.paletteOpen)
  const setOpen = useShellUi((s) => s.setPaletteOpen)
  const navigate = useNavigate()
  const to = useScopedTo()
  const { runId } = useCurrentRun()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [query])

  const searching = open && debounced.length >= 2
  const txns = useTransactions(searching ? runId : null, { q: debounced, size: MAX_RESULTS })
  const cases = useCases(searching ? runId : null, { q: debounced, size: MAX_RESULTS })
  const visibleScreens = SCREENS.filter((s) => normalize(s.label).includes(normalize(query.trim())))

  const close = () => {
    setOpen(false)
    setQuery('')
    setDebounced('')
  }

  const go = (path: string, ver?: string) => {
    close()
    const scoped = to(path)
    const params = new URLSearchParams(scoped.search)
    if (ver) params.set('ver', ver)
    navigate({ pathname: scoped.pathname, search: params.size ? `?${params}` : '' })
  }

  return (
    <Dialog open={open} onClose={close} title="Paleta de comandos" bare placement="top" size="md" className={styles.dialog}>
      <Cmdk shouldFilter={false} loop label="Paleta de comandos" className={styles.root}>
        <div className={styles.inputRow}>
          <Search aria-hidden className={styles.searchIcon} />
          <Cmdk.Input value={query} onValueChange={setQuery} placeholder="Busca una pantalla, un movimiento, una factura, un caso…" className={styles.input} />
          <Kbd>Esc</Kbd>
        </div>
        <Cmdk.List className={styles.list}>
          <Cmdk.Empty className={styles.empty}>Sin resultados para «{query}»</Cmdk.Empty>
          {searching && txns.rows.length > 0 && (
            <Cmdk.Group heading="Movimientos" className={styles.group}>
              {txns.rows.slice(0, MAX_RESULTS).map((t) => (
                <Cmdk.Item key={t.bankTxnId} value={t.bankTxnId} onSelect={() => go('/conciliacion', t.bankTxnId)} className={styles.item}>
                  <span className={styles.icon}>
                    <ListChecks />
                  </span>
                  <span className={styles.label}>{t.text}</span>
                  <span className={styles.hint}>{t.bankTxnId}</span>
                </Cmdk.Item>
              ))}
            </Cmdk.Group>
          )}
          {searching && cases.rows.length > 0 && (
            <Cmdk.Group heading="Casos" className={styles.group}>
              {cases.rows.slice(0, MAX_RESULTS).map((c) => (
                <Cmdk.Item key={c.caseId} value={c.caseId} onSelect={() => go('/bandeja', c.caseId)} className={styles.item}>
                  <span className={styles.icon}>
                    <Inbox />
                  </span>
                  <span className={styles.label}>{c.summary}</span>
                  <span className={styles.hint}>{c.caseId}</span>
                </Cmdk.Item>
              ))}
            </Cmdk.Group>
          )}
          {visibleScreens.length > 0 && (
            <Cmdk.Group heading="Ir a" className={styles.group}>
              {visibleScreens.map((s) => (
                <Cmdk.Item key={s.id} value={s.path} onSelect={() => go(s.path)} className={styles.item}>
                  <span className={styles.icon}>
                    <s.icon />
                  </span>
                  <span className={styles.label}>{s.label}</span>
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
