// Public API of the data layer. Views import from '@/data' only (CLAUDE.md §6).
export { useData, type DataState } from './store'
export { countByKind } from './build'
export { refKey, parseRefKey, type AnyObject, type Links } from './links'
export { VIEWS, PAGE_VIEWS, viewOf, viewOfObject, type DatasetView, type Facet } from './registry/views'
export { SEVERITY, SEVERITY_ORDER, ALERT_TYPE, MATCH_STATUS, OBJECT_LABEL } from './registry/vocabulary'
