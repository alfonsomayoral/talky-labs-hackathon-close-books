// Pure logic of the Memoria y reglas screen: what each kind of rule asks for (CONTRACT.md §4).
import { categoryLabel, type MemoryRule, type MemoryRuleKind } from '@/domain'

export interface FieldSpec {
  name: string
  label: string
  placeholder: string
  /** Ids, codes and patterns are shown in the mono face. */
  mono?: boolean
}

export interface KindSpec {
  kind: MemoryRuleKind
  label: string
  /** One line: what the rule teaches the next run. */
  summary: string
  fields: FieldSpec[]
}

export const RULE_KINDS: KindSpec[] = [
  {
    kind: 'payer_is_customer',
    label: 'Pagador es cliente',
    summary: 'Los cobros de este pagador son de un cliente concreto.',
    fields: [
      {
        name: 'partyId',
        label: 'Cliente',
        placeholder: 'CES01000001',
        mono: true,
      },
      {
        name: 'payerName',
        label: 'Nombre del pagador',
        placeholder: 'Como viene en el banco',
      },
      {
        name: 'iban',
        label: 'IBAN del pagador',
        placeholder: 'ES91 2100 0418 4502 0005 1332',
        mono: true,
      },
    ],
  },
  {
    kind: 'reference_alias',
    label: 'Alias de referencia',
    summary: 'Una referencia sucia que el cliente usa para una factura o un tercero.',
    fields: [
      {
        name: 'pattern',
        label: 'Referencia',
        placeholder: 'Texto que aparece en el banco',
        mono: true,
      },
      {
        name: 'documentNumber',
        label: 'Factura',
        placeholder: 'FV-2025-0123',
        mono: true,
      },
      {
        name: 'partyId',
        label: 'Tercero',
        placeholder: 'CES01000001',
        mono: true,
      },
    ],
  },
  {
    kind: 'supplier_nets_credit_notes',
    label: 'Proveedor compensa abonos',
    summary: 'Nuestros pagos a este proveedor van netos de sus abonos.',
    fields: [
      {
        name: 'partyId',
        label: 'Proveedor',
        placeholder: 'SES01000001',
        mono: true,
      },
    ],
  },
  {
    kind: 'always_category',
    label: 'Siempre esta categoría',
    summary: 'Los movimientos que casen no liquidan partidas: van a una categoría.',
    fields: [
      {
        name: 'category',
        label: 'Categoría',
        placeholder: 'BANK_FEES',
        mono: true,
      },
      {
        name: 'textPattern',
        label: 'Texto del movimiento',
        placeholder: 'COMISION MANTENIMIENTO',
        mono: true,
      },
      {
        name: 'bank',
        label: 'Banco (opcional)',
        placeholder: 'Id del banco',
        mono: true,
      },
      {
        name: 'bankCode',
        label: 'Código bancario',
        placeholder: '0123',
        mono: true,
      },
      {
        name: 'bankSubcode',
        label: 'Subcódigo (opcional)',
        placeholder: '001',
        mono: true,
      },
    ],
  },
  {
    kind: 'ignore_suffix',
    label: 'Ignorar sufijo',
    summary: 'Se descarta un sufijo de las referencias de un tercero antes de casarlas.',
    fields: [
      {
        name: 'partyId',
        label: 'Tercero',
        placeholder: 'CES01000001',
        mono: true,
      },
      {
        name: 'regex',
        label: 'Expresión regular',
        placeholder: '-\\d{2}$',
        mono: true,
      },
    ],
  },
  {
    kind: 'parent_pays',
    label: 'La matriz paga',
    summary: 'Un tercero paga las facturas de otro.',
    fields: [
      {
        name: 'payerPartyId',
        label: 'Paga',
        placeholder: 'CES01000001',
        mono: true,
      },
      {
        name: 'forPartyId',
        label: 'Por cuenta de',
        placeholder: 'CES01000002',
        mono: true,
      },
    ],
  },
]

const SPEC = new Map(RULE_KINDS.map((k) => [k.kind, k]))

export const ruleKindLabel = (kind: MemoryRuleKind) => SPEC.get(kind)?.label ?? kind

export type Params = Record<string, string>

/** Trims every value, drops the empty ones and writes the IBAN without spaces and in capitals. */
export function cleanParams(raw: Params): Params {
  const out: Params = {}
  for (const [name, value] of Object.entries(raw)) {
    const v = name === 'iban' ? value.replace(/\s+/g, '').toUpperCase() : value.trim()
    if (v) out[name] = v
  }
  return out
}

const REQUIRED = 'Obligatorio.'
const IBAN = /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/

/** Error by field name for already cleaned params; `{}` when the rule can be saved. */
export function validateParams(kind: MemoryRuleKind, p: Params): Record<string, string> {
  const errors: Record<string, string> = {}
  const need = (...names: string[]) => names.forEach((n) => !p[n] && (errors[n] = REQUIRED))
  const oneOf = (first: string, message: string, ...names: string[]) => names.some((n) => p[n]) || (errors[first] = message)

  switch (kind) {
    case 'payer_is_customer':
      need('partyId')
      oneOf('payerName', 'Indica el nombre del pagador o su IBAN.', 'payerName', 'iban')
      if (p.iban && !IBAN.test(p.iban)) errors.iban = 'No parece un IBAN.'
      break
    case 'reference_alias':
      need('pattern')
      oneOf('documentNumber', 'Indica la factura o el tercero.', 'documentNumber', 'partyId')
      break
    case 'supplier_nets_credit_notes':
      need('partyId')
      break
    case 'always_category':
      need('category')
      if (p.category && !/^[A-Z][A-Z_]*$/.test(p.category)) errors.category = 'En mayúsculas y con guiones bajos, como en categories.csv.'
      oneOf('textPattern', 'Indica el texto o el código bancario.', 'textPattern', 'bankCode')
      break
    case 'ignore_suffix':
      need('partyId', 'regex')
      if (p.regex) {
        try {
          new RegExp(p.regex)
        } catch {
          errors.regex = 'La expresión no es válida.'
        }
      }
      break
    case 'parent_pays':
      need('payerPartyId', 'forPartyId')
      if (p.payerPartyId && p.payerPartyId === p.forPartyId) errors.forPartyId = 'Tiene que ser otro tercero.'
      break
  }
  return errors
}

/** The sentence the rule shows in the list; the person can edit it before saving. */
export function describeRule(kind: MemoryRuleKind, p: Params): string {
  switch (kind) {
    case 'payer_is_customer':
      return `${p.payerName ? `«${p.payerName}»` : `El IBAN ${p.iban}`} es un pago del cliente ${p.partyId}.`
    case 'reference_alias':
      return `La referencia «${p.pattern}» corresponde ${p.documentNumber ? `a la factura ${p.documentNumber}` : `al tercero ${p.partyId}`}.`
    case 'supplier_nets_credit_notes':
      return `Los pagos al proveedor ${p.partyId} van netos de sus abonos.`
    case 'always_category': {
      const code = p.bankCode ? `código ${p.bankCode}${p.bankSubcode ? `/${p.bankSubcode}` : ''}` : null
      const filters = [p.bank && `del banco ${p.bank}`, code, p.textPattern && `con «${p.textPattern}»`].filter(Boolean)
      return `Los movimientos ${filters.join(', ')} van siempre a ${categoryLabel(String(p.category))}.`
    }
    case 'ignore_suffix':
      return `En las referencias del tercero ${p.partyId} se ignora el sufijo ${p.regex}.`
    case 'parent_pays':
      return `${p.payerPartyId} paga las facturas de ${p.forPartyId}.`
  }
}

export function validateDescription(text: string): string | null {
  const t = text.trim()
  if (!t) return 'Escribe qué enseña la regla.'
  return t.length > 300 ? 'Máximo 300 caracteres.' : null
}

/** The params of a rule that the form knows, in the form's order, with their labels. */
export function keyParams(rule: MemoryRule): { label: string; value: string }[] {
  const fields = SPEC.get(rule.kind)?.fields ?? []
  return fields.flatMap((f) => {
    const value = rule.params[f.name]
    return value == null || value === '' ? [] : [{ label: f.label.replace(' (opcional)', ''), value: String(value) }]
  })
}

/** The rules that apply in a scope: those of that entity and the ones for the whole group. */
export const rulesInScope = (rules: MemoryRule[], entity: string | null) =>
  entity ? rules.filter((r) => !r.scope.entity || r.scope.entity === entity) : rules

export const runCommand = (runId: string) => `closebooks run --memory runs/${runId}/human/`
