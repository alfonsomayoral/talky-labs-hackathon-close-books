// Pure logic shared by the screens that work cases (Te necesitan, Cobros, Proveedores).
import type { CaseDetail, CaseStatus } from '@/domain'

export const ACTION_LABEL: Record<CaseDetail['suggestedAction'], string> = {
  none: 'Sin acción',
  ask: 'Responder pregunta',
  email_customer: 'Escribir al cliente',
  email_supplier: 'Escribir al proveedor',
  review: 'Revisar',
}

export type PrimaryAction ='answer' | 'email' | 'prepare_email' | 'done' | 'closed'

type ActionInput = Pick<CaseDetail, 'suggestedAction'> & {
  status: CaseStatus
  question?: Pick<NonNullable<CaseDetail['question']>, 'status'> | null
  draft?: Pick<NonNullable<CaseDetail['draft']>, 'status'> | null
}

/** The one button that leads the case. Marking it handled always exists; it leads when nothing else is left to do. */
export function primaryAction(c: ActionInput): PrimaryAction {
  if (c.status === 'done') return 'closed'
  if (c.suggestedAction === 'ask') return c.question?.status === 'open' ? 'answer' : 'done'
  if (c.suggestedAction === 'email_customer' || c.suggestedAction === 'email_supplier') {
    if (!c.draft) return 'prepare_email'
    return c.draft.status === 'draft' ? 'email' : 'done'
  }
  return 'done'
}
