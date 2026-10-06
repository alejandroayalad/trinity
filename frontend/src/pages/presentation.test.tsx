import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { DataTable } from './shared'
import { NationalChart } from './dashboard/NationalChart'
import { setMediaMatches } from '../test/setup'

afterEach(() => vi.unstubAllGlobals())

test('duplicate SQL headers preserve ordered names and cells without React key warnings', () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  try {
    const columns = [{ name: 'value', type: 'decimal' as const, nullable: false, unit: 'MW' as const }, { name: 'value', type: 'decimal' as const, nullable: false, unit: 'MW' as const }]
    const view = render(<DataTable columns={columns} rows={[["001.00", "2.50"]]} sql />)
    expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['value (MW)', 'value (MW)'])
    expect(screen.getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['001.00', '2.50'])
    view.rerender(<DataTable columns={columns} rows={[["3.00", "4.50"]]} sql />)
    expect(screen.getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['3.00', '4.50'])
    expect(errors).not.toHaveBeenCalled()
  } finally { errors.mockRestore() }
})

test('chart uses measured mobile width and preserves missing/outlier keyboard interaction', () => {
  setMediaMatches(['(prefers-reduced-motion: reduce)'])
  let resize!: ResizeObserverCallback
  const disconnect = vi.fn()
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { resize = callback }
    observe() { /* The test controls when layout measurement arrives. */ }
    disconnect = disconnect
  })
  const onSelect = vi.fn()
  const view = render(<NationalChart selected={null} onSelect={onSelect} days={[
    { period: '2026-10-01', capacity: '100', outage: '120', percentOutage: null, offline_share_percent: '120.00', reason: null },
    { period: '2026-10-02', capacity: null, outage: null, percentOutage: null, offline_share_percent: null, reason: 'not_reported' },
  ]} />)
  // The callback changes geometry only; exact source measurements stay strings.
  act(() => resize([{ contentRect: { width: 222 } } as ResizeObserverEntry], {} as ResizeObserver))
  const chart = screen.getByRole('application')
  expect(chart).toHaveAttribute('viewBox', '0 0 222 310')
  fireEvent.keyDown(chart, { key: 'ArrowRight' }); fireEvent.keyDown(chart, { key: 'Enter' })
  expect(onSelect).toHaveBeenLastCalledWith('2026-10-02')
  expect(screen.getByText(/○ Not reported/)).toBeInTheDocument()
  expect(chart.querySelector('.outlier')).not.toBeNull()
  act(() => resize([{ contentRect: { width: 1000 } } as ResizeObserverEntry], {} as ResizeObserver))
  expect(chart).toHaveAttribute('viewBox', '0 0 1000 310')
  view.unmount()
  expect(disconnect).toHaveBeenCalledOnce()
})
