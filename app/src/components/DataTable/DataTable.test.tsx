import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable, type Column } from './DataTable'

interface Row {
  id: string
  amount: number
}

const columns: Column<Row>[] = [
  { id: 'id', header: 'Partida', cell: (r) => r.id },
  { id: 'amount', header: 'Importe', cell: (r) => r.amount, sortValue: (r) => r.amount },
]

describe('DataTable', () => {
  it('sorts from the keyboard: Tab reaches the sortable header and Enter sorts', async () => {
    render(<DataTable aria-label="Partidas" rows={[{ id: 'a', amount: 2 }]} columns={columns} getRowId={(r) => r.id} height={200} />)
    await userEvent.tab()
    expect(screen.getByRole('grid', { name: 'Partidas' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Importe' })).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(screen.getByRole('columnheader', { name: 'Importe' })).toHaveAttribute('aria-sort', 'ascending')
  })

  it('moves the cursor with j/k when the page only passes the open row as selectedId', async () => {
    const rows = [{ id: 'a', amount: 1 }, { id: 'b', amount: 2 }, { id: 'c', amount: 3 }]
    const { rerender } = render(<DataTable aria-label="Partidas" rows={rows} columns={columns} getRowId={(r) => r.id} selectedId={null} height={200} />)
    const grid = screen.getByRole('grid', { name: 'Partidas' })
    grid.focus()
    await userEvent.keyboard('jj')
    expect(grid.getAttribute('aria-activedescendant')).toMatch(/-r1$/)
    await userEvent.keyboard('k')
    expect(grid.getAttribute('aria-activedescendant')).toMatch(/-r0$/)
    // The page opens another row: its choice wins over the old cursor.
    rerender(<DataTable aria-label="Partidas" rows={rows} columns={columns} getRowId={(r) => r.id} selectedId="c" height={200} />)
    expect(grid.getAttribute('aria-activedescendant')).toMatch(/-r2$/)
  })
})
