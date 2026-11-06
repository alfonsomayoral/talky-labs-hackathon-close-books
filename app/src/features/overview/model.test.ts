import { buildDataset } from '@/data/build'
import { samplePackage } from '@/data/fixtures/sample'
import { matchCountsByEntity, sumCounts } from './model'

it('splits the run matches by entity and the parts add up to the run metrics', () => {
  const { files, run } = samplePackage()
  const ds = buildDataset(files, { name: 'm', period: '2026-09', source: 'fixtures', loadedAt: '' })
  const byEntity = matchCountsByEntity(ds, run)
  expect([...byEntity.keys()].sort()).toEqual(ds.entities.map((e) => e.id).sort())
  const total = sumCounts(byEntity.values())
  expect(total).toEqual({ ...run.metrics.reconciliation, total: run.matches.length })
})

it('gives every entity zeros when there is no run', () => {
  const { files } = samplePackage()
  const ds = buildDataset(files, { name: 'm', period: null, source: 'zip', loadedAt: '' })
  expect([...matchCountsByEntity(ds, null).values()].every((c) => c.total === 0)).toBe(true)
})
