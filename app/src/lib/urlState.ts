// State that lives in the URL so a copied link opens the same view (ARCHITECTURE.md §5.1):
// the run (?run=), the entity scope (?sociedad=) and the object open in the side panel (?ver=id).
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

const RUN = 'run'
const ENTITY = 'sociedad'
const OPEN = 'ver'

function useParam(name: string): [string | null, (value: string | null) => void] {
  const [params, setParams] = useSearchParams()
  const set = useCallback(
    (value: string | null) =>
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set(name, value)
        else next.delete(name)
        return next
      }),
    [name, setParams],
  )
  return [params.get(name), set]
}

/** Selected entity id, or null for the whole group. */
export const useEntityScope = () => useParam(ENTITY)

/** Run chosen in the URL, or null for the latest one. */
export const useRunParam = () => useParam(RUN)

/** Id of the object open in the side panel, or null. */
export const useOpenObject = () => useParam(OPEN)

/** Link to a page keeping the run and the entity scope (and dropping the open panel and the page's filters). */
export function useScopedTo() {
  const [params] = useSearchParams()
  return (pathname: string) => {
    const kept = new URLSearchParams()
    for (const name of [RUN, ENTITY]) {
      const value = params.get(name)
      if (value) kept.set(name, value)
    }
    return { pathname, search: kept.size ? `?${kept}` : '' }
  }
}

/** A multi-value filter in the URL (`?regla=A,B`), with its setter. Changing it keeps the other params. */
export function useListParam(name: string): [string[], (next: string[]) => void] {
  const [value, setValue] = useParam(name)
  const list = useMemo(() => (value ? value.split(',') : []), [value])
  const set = useCallback((next: string[]) => setValue(next.length ? next.join(',') : null), [setValue])
  return [list, set]
}

/** A plain text or value param in the URL (`?q=`), with its setter. */
export const useTextParam = useParam
