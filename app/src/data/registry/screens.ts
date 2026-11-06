// The list of screens: routes, sidebar and ⌘K are generated from here (docs/PLAN.md §2.3).
import { BookOpenCheck, Brain, Building, Database, Inbox, Landmark, LayoutDashboard, ListChecks, Play, type LucideIcon } from 'lucide-react'

export interface Screen {
  id: 'overview' | 'inbox' | 'reconciliation' | 'collections' | 'suppliers' | 'accounts' | 'explorer' | 'memory' | 'runs'
  path: string
  label: string
  icon: LucideIcon
  section: 'operation' | 'management' | 'data' | 'system'
  /** Opens with no run yet: the FINAL console is how the first one starts. */
  worksWithoutRun?: boolean
}

export const SCREEN_SECTIONS: { id: Screen['section']; label: string }[] = [
  { id: 'operation', label: 'Operación' },
  { id: 'management', label: 'Gestión' },
  { id: 'data', label: 'Datos' },
  { id: 'system', label: 'Sistema' },
]

export const SCREENS: Screen[] = [
  { id: 'overview', path: '/', label: 'Resumen', icon: LayoutDashboard, section: 'operation' },
  { id: 'inbox', path: '/bandeja', label: 'Te necesitan', icon: Inbox, section: 'operation' },
  { id: 'reconciliation', path: '/conciliacion', label: 'Conciliación', icon: ListChecks, section: 'operation' },
  { id: 'collections', path: '/cobros', label: 'Cobros', icon: BookOpenCheck, section: 'management' },
  { id: 'suppliers', path: '/proveedores', label: 'Proveedores', icon: Building, section: 'management' },
  { id: 'accounts', path: '/cuentas', label: 'Cuentas bancarias', icon: Landmark, section: 'data' },
  { id: 'explorer', path: '/explorador', label: 'Explorador', icon: Database, section: 'data' },
  { id: 'memory', path: '/memoria', label: 'Memoria y reglas', icon: Brain, section: 'system' },
  { id: 'runs', path: '/ejecuciones', label: 'Ejecuciones', icon: Play, section: 'system', worksWithoutRun: true },
]
