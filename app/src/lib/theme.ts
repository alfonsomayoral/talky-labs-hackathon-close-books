// Light or dark theme: `data-theme` on <html>, which tokens.css reads. index.html sets it before first paint
// (the saved choice, else the system's); this switches it and remembers the choice.
import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

/** localStorage key; index.html reads the same one. */
export const THEME_KEY = 'theme'

const listeners = new Set<() => void>()

function current(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Private mode or blocked storage: the switch still applies to this visit.
  }
  listeners.forEach((l) => l())
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  return [useSyncExternalStore(subscribe, current), setTheme]
}
