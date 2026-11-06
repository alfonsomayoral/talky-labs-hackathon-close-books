// State that lives in the URL so a copied link opens the same view (ARCHITECTURE.md §5.1):
// the entity scope (?sociedad=) and the object open in the side panel (?ver=kind:id).
import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

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

/** Key `kind:id` of the object open in the side panel, or null. */
export const useOpenObject = () => useParam(OPEN)

/** Link to a page keeping the entity scope (and dropping the open panel). */
export function useScopedTo() {
  const [params] = useSearchParams()
  const entity = params.get(ENTITY)
  return (pathname: string) => ({ pathname, search: entity ? `?${ENTITY}=${encodeURIComponent(entity)}` : '' })
}
