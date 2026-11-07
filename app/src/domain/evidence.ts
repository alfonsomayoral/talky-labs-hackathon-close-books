// What kind of source backs each rule: what the movement's evidence is, at a glance.

export type EvidenceGroup = 'document' | 'movement' | 'party' | 'category' | 'memory' | 'fallback'

export const EVIDENCE_GROUP_LABEL: Record<EvidenceGroup, string> = {
  document: 'Documento o referencia',
  movement: 'Otro movimiento',
  party: 'Tercero e importe',
  category: 'Categoría sin partida',
  memory: 'Regla de una persona',
  fallback: 'Sin evidencia',
}

interface RuleEvidence {
  source: string
  group: EvidenceGroup
}

/** Longest prefix first where a family has exceptions. */
const BY_PREFIX: [string, RuleEvidence][] = [
  ['ADVICE-PDF', { source: 'PDF', group: 'document' }],
  ['ADVICE', { source: 'Aviso de remesa', group: 'document' }],
  ['FILE-PAYMENT', { source: 'Remesa de pagos', group: 'document' }],
  ['FILE-DD', { source: 'Recibos', group: 'document' }],
  ['FILE-CARD', { source: 'Tarjeta', group: 'document' }],
  ['FILE-CHEQUE', { source: 'Cheque', group: 'document' }],
  ['REF', { source: 'Texto del banco', group: 'document' }],
  ['CREDIT', { source: 'Referencia o PDF', group: 'document' }],
  ['PAIRED', { source: 'Otro movimiento', group: 'movement' }],
  ['PARTY-PLAN', { source: 'PDF', group: 'document' }],
  ['PARTY', { source: 'Maestro', group: 'party' }],
  ['CAT', { source: 'Código o texto', group: 'category' }],
  ['MEMORY', { source: 'Memoria', group: 'memory' }],
  ['FALLBACK', { source: 'Sin evidencia', group: 'fallback' }],
]

export function evidenceOf(rule: string): RuleEvidence {
  return BY_PREFIX.find(([prefix]) => rule === prefix || rule.startsWith(`${prefix}-`))?.[1] ?? { source: 'Otra', group: 'fallback' }
}
