import { Page, PageHeader, TabPanel, Tabs } from '@/components'
import { useTextParam } from '@/lib/urlState'
import { CompareTab } from './CompareTab'
import { FinalConsole } from './FinalConsole'
import { HistoryTab } from './HistoryTab'

const TABS = [
  { id: 'historial', label: 'Historial' },
  { id: 'comparar', label: 'Comparar' },
  { id: 'final', label: 'Consola FINAL' },
]
const ID_PREFIX = 'runs'

export function RunsPage() {
  const [vista, setVista] = useTextParam('vista')
  const tab = TABS.find((t) => t.id === vista)?.id ?? 'historial'
  return (
    <Page fill={tab === 'historial'}>
      <PageHeader title="Ejecuciones" subtitle="Qué ha hecho cada ejecución, si ha mejorado y si estamos listos para FINAL." />
      <Tabs aria-label="Vistas" tabs={TABS} value={tab} onChange={setVista} idPrefix={ID_PREFIX} />
      <TabPanel idPrefix={ID_PREFIX} id={tab}>
        {tab === 'historial' && <HistoryTab onGoToConsole={() => setVista('final')} />}
        {tab === 'comparar' && <CompareTab />}
        {tab === 'final' && <FinalConsole />}
      </TabPanel>
    </Page>
  )
}
