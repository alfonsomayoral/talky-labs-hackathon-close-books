import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import styles from './SearchBox.module.css'

export interface SearchBoxProps {
  /** The committed value (the URL's). */
  value: string
  onCommit: (value: string) => void
  placeholder: string
  'aria-label': string
  /** Quiet time before the value is committed. */
  delay?: number
}

/** Text search that commits to the URL (and so to the API) only when the user pauses typing. */
export function SearchBox({ value, onCommit, placeholder, delay = 250, ...aria }: SearchBoxProps) {
  const [draft, setDraft] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  const change = (next: string) => {
    setDraft(next)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      onCommit(next)
      setDraft(null)
    }, delay)
  }

  return (
    <label className={styles.box}>
      <Search className={styles.icon} aria-hidden />
      <input
        type="search"
        className={styles.input}
        value={draft ?? value}
        placeholder={placeholder}
        onChange={(e) => change(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        {...aria}
      />
    </label>
  )
}
