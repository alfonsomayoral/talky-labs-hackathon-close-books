import { useRef } from 'react'
import { Search } from 'lucide-react'
import styles from './SearchBox.module.css'

const DEBOUNCE_MS = 300

interface SearchBoxProps {
  /** Value in the URL: it only seeds the field, so typing is never fought by a re-render. Remount (`key`) to reseed. */
  value: string
  onSearch: (value: string) => void
  placeholder: string
}

/** Text search that reaches the URL (and so the API) a moment after the last keystroke. */
export function SearchBox({ value, onSearch, placeholder }: SearchBoxProps) {
  const timer = useRef<number>(undefined)
  return (
    <label className={styles.box}>
      <Search aria-hidden />
      <input
        type="search"
        defaultValue={value}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(e) => {
          const next = e.target.value.trim()
          window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => onSearch(next), DEBOUNCE_MS)
        }}
      />
    </label>
  )
}
