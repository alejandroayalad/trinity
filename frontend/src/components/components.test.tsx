import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './overlay/Dialog'
import { Segmented } from './controls/Segmented'
import { MissingChip, StatusBadge } from './feedback/StatusBadge'
import { Switch } from './controls/Switch'
import { Tabs } from './controls/Tabs'

function DialogHarness({ onConfirm }: { onConfirm: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Discard
      </button>
      <button type="button">Behind the dialog</button>
      {open && (
        <ConfirmDialog
          title="Discard candidate?"
          confirmLabel="Discard candidate"
          tone="destructive"
          onConfirm={onConfirm}
          onCancel={() => setOpen(false)}
        >
          This drops the candidate permanently.
        </ConfirmDialog>
      )}
    </>
  )
}

describe('ConfirmDialog', () => {
  it('moves focus inside, traps Tab, and returns focus to the opener on Escape', async () => {
    const user = userEvent.setup()
    render(<DialogHarness onConfirm={vi.fn()} />)
    const opener = screen.getByRole('button', { name: 'Discard' })
    await user.click(opener)

    const dialog = screen.getByRole('dialog', { name: 'Discard candidate?' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const confirm = screen.getByRole('button', { name: 'Discard candidate' })
    expect(cancel).toHaveFocus()

    await user.tab()
    expect(confirm).toHaveFocus()
    // Tab on the last control wraps to the first; focus never reaches the page behind.
    await user.tab()
    expect(cancel).toHaveFocus()
    await user.tab({ shift: true })
    expect(confirm).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('confirms with the keyboard', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<DialogHarness onConfirm={onConfirm} />)
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    await user.tab()
    await user.keyboard('{Enter}')
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('disables both buttons and ignores Escape while the command is in flight', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(
      <ConfirmDialog title="Approve?" confirmLabel="Approve and publish" busy onConfirm={vi.fn()} onCancel={onCancel}>
        Body
      </ConfirmDialog>,
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(onCancel).not.toHaveBeenCalled()
  })
})

describe('Tabs', () => {
  function TabsHarness() {
    const [tab, setTab] = useState<'chart' | 'daily'>('chart')
    return (
      <Tabs
        label="View"
        idPrefix="view"
        tabs={[
          { value: 'chart', label: 'Chart' },
          { value: 'daily', label: 'Daily values' },
        ]}
        value={tab}
        onChange={setTab}
      />
    )
  }

  it('selects tabs with the arrow keys and keeps only the selected tab in the Tab order', async () => {
    const user = userEvent.setup()
    render(<TabsHarness />)
    const chart = screen.getByRole('tab', { name: 'Chart' })
    const daily = screen.getByRole('tab', { name: 'Daily values' })
    expect(chart).toHaveAttribute('aria-selected', 'true')
    expect(daily).toHaveAttribute('tabindex', '-1')

    await user.tab()
    expect(chart).toHaveFocus()
    await user.keyboard('{ArrowRight}')
    expect(daily).toHaveFocus()
    expect(daily).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowRight}')
    expect(chart).toHaveAttribute('aria-selected', 'true')
  })
})

describe('Switch and Segmented', () => {
  it('toggles the switch with Space and reports its state', async () => {
    const user = userEvent.setup()
    function SwitchHarness() {
      const [on, setOn] = useState(false)
      return (
        <>
          <span id="label">Schedule enabled</span>
          <Switch checked={on} onChange={setOn} labelledBy="label" />
        </>
      )
    }
    render(<SwitchHarness />)
    const toggle = screen.getByRole('switch', { name: 'Schedule enabled' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    await user.tab()
    await user.keyboard(' ')
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('marks the selected segment with aria-pressed', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <Segmented
        label="Range"
        options={[
          { value: '30d', label: '30 days' },
          { value: '90d', label: '90 days' },
        ]}
        value="30d"
        onChange={onChange}
      />,
    )
    expect(screen.getByRole('button', { name: '30 days' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: '90 days' }))
    expect(onChange).toHaveBeenCalledWith('90d')
  })
})

describe('status and missing values', () => {
  it('pairs every status color with a glyph and a text label', () => {
    render(
      <StatusBadge tone="error" glyph="✕">
        Failed
      </StatusBadge>,
    )
    expect(screen.getByText('Failed')).toBeVisible()
    expect(screen.getByText('✕')).toHaveAttribute('aria-hidden', 'true')
  })

  it('shows a missing value as "Not reported", never as 0', () => {
    render(<MissingChip />)
    expect(screen.getByText('○ Not reported')).toBeVisible()
  })
})
