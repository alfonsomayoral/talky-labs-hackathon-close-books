import { EXPLORER_SPECS, type ExplorerSpec } from '@/data'

/** Name of a facet value as its spec declares it; an unknown value stays readable. */
export const facetLabel = (spec: ExplorerSpec['id'], value: string) =>
  EXPLORER_SPECS.find((s) => s.id === spec)?.facet.options.find((o) => o.value === value)?.label ?? value
