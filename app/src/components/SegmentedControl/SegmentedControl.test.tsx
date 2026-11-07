import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SegmentedControl } from './SegmentedControl'

function Phase() {
  const [value, setValue] = useState('')
  const options = ['live', 'holdout', 'final'].map((v) => ({ value: v, label: v }))
  return <SegmentedControl aria-label="Fase" options={options} value={value} onChange={setValue} />
}

describe('SegmentedControl with nothing chosen yet', () => {
  it('can be reached with Tab', async () => {
    render(<Phase />)
    await userEvent.tab()
    expect(screen.getByRole('radio', { name: 'live' })).toHaveFocus()
  })

  it('moves from the focused option, not from the start', async () => {
    render(<Phase />)
    screen.getByRole('radio', { name: 'holdout' }).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('radio', { name: 'final' })).toHaveFocus()
    expect(screen.getByRole('radio', { name: 'final' })).toBeChecked()
  })
})
