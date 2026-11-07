import { useState } from 'react'
import { Link } from 'react-router'
import { FilePlus2, Paperclip } from 'lucide-react'
import { Badge, Button, Pill, toast } from '@/components'
import { useDecideCase, useDraftActions } from '@/data'
import { useScopedTo } from '@/lib/urlState'
import type { CaseDetail, Draft } from '@/domain'
import { TextField } from './TextField'
import { recipientLine, attachmentSearch } from './model'
import styles from './DraftEditor.module.css'

interface DraftEditorProps {
  caseDetail: CaseDetail
  runId: string
}

const SENT_LABEL: Record<Exclude<Draft['status'], 'draft'>, string> = { sent: 'Enviado', manual: 'Lo lleva una persona' }

/** The email a case suggests: edit it, send it or take it by hand. Without a draft, it offers to prepare one. */
export function DraftEditor({ caseDetail, runId }: DraftEditorProps) {
  const { draft } = caseDetail
  const actions = useDraftActions(runId)

  if (!draft) {
    const kind = caseDetail.suggestedAction === 'email_supplier' ? 'email_supplier' : 'email_customer'
    return (
      <div className={styles.editor}>
        <Button
          variant="primary"
          leadingIcon={<FilePlus2 />}
          loading={actions.create.isPending}
          onClick={() =>
            actions.create.mutate(
              { caseId: caseDetail.caseId, kind },
              { onError: (error) => toast.error('No se ha podido preparar el correo', { description: error.message }) },
            )
          }
        >
          Preparar correo
        </Button>
        <p className={styles.note}>Se redacta un borrador con los datos del caso; lo revisas antes de enviarlo.</p>
      </div>
    )
  }
  return <DraftForm key={draft.draftId} draft={draft} runId={runId} />
}

function DraftForm({ draft, runId }: { draft: Draft; runId: string }) {
  const decide = useDecideCase(runId)
  const explorer = useScopedTo()('/explorador')
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const actions = useDraftActions(runId)
  const closed = draft.status !== 'draft'
  const dirty = subject !== draft.subject || body !== draft.body
  const busy = actions.save.isPending || actions.send.isPending || actions.manual.isPending || decide.isPending

  const fail = (title: string) => (error: Error) => toast.error(title, { description: error.message })

  const save = () => actions.save.mutate({ draftId: draft.draftId, subject, body }, { onSuccess: () => toast.success('Cambios guardados'), onError: fail('No se han podido guardar los cambios') })

  const send = async () => {
    try {
      if (dirty) await actions.save.mutateAsync({ draftId: draft.draftId, subject, body })
      await actions.send.mutateAsync(draft.draftId)
      toast.success('Envío registrado', { description: `Para ${draft.toName ?? 'el destinatario'}. No ha salido ningún correo.` })
    } catch (error) {
      fail('No se ha podido enviar')(error as Error)
    }
  }

  // A person takes it from here, so it leaves the queue: the draft's own action only writes the outbox.
  const takeManually = async () => {
    try {
      await actions.manual.mutateAsync(draft.draftId)
      await decide.mutateAsync({ caseId: draft.caseId, action: 'manual' })
      toast.success('Anotado: lo llevas tú')
    } catch (error) {
      fail('No se ha podido anotar')(error as Error)
    }
  }

  return (
    <div className={styles.editor}>
      {closed && (
        <div>
          <Badge emphasis={draft.status === 'sent' ? 'positive' : 'quiet'}>{SENT_LABEL[draft.status as keyof typeof SENT_LABEL]}</Badge>
        </div>
      )}
      <TextField label="Para" value={recipientLine(draft)} onChange={() => {}} readOnly />
      {!draft.to && <p className={styles.note}>Sin dirección en el maestro: el envío queda registrado igual.</p>}
      <TextField label="Asunto" value={subject} onChange={setSubject} readOnly={closed} />
      <TextField label="Mensaje" value={body} onChange={setBody} rows={10} readOnly={closed} />
      {draft.attachments && draft.attachments.length > 0 && (
        <ul className={styles.attachments} aria-label="Adjuntos">
          {draft.attachments.map((a) => (
            <li key={a.ref}>
              <Link className={styles.attachment} to={{ pathname: explorer.pathname, search: attachmentSearch(explorer.search, a.ref) }} aria-label={`Abrir el adjunto ${a.label ?? a.ref}`}>
                <Pill icon={<Paperclip />}>{a.label ?? a.ref}</Pill>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {!closed && (
        <>
          <div className={styles.buttons}>
            <Button variant="primary" onClick={send} loading={actions.send.isPending} disabled={busy && !actions.send.isPending}>
              Enviar
            </Button>
            {dirty && (
              <Button onClick={save} loading={actions.save.isPending} disabled={busy && !actions.save.isPending}>
                Guardar cambios
              </Button>
            )}
            <Button variant="ghost" onClick={takeManually} loading={actions.manual.isPending} disabled={busy && !actions.manual.isPending}>
              Lo llevo yo
            </Button>
          </div>
          <p className={styles.note}>Enviar deja constancia en el sistema; no sale ningún correo.</p>
        </>
      )}
    </div>
  )
}
