import React, { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { UnsavedChangesProvider } from './UnsavedChangesContext'
import { useUnsavedChangesScope, useUnsavedChangesStatus } from './useUnsavedChanges'

function SettingsHarness() {
  const [dirty, setDirty] = useState(false)
  const { discardUnsavedChanges } = useUnsavedChangesStatus()
  useUnsavedChangesScope('test-settings', dirty)
  return (
    <>
      <button type="button" onClick={() => setDirty(true)}>修改配置</button>
      <button type="button" onClick={discardUnsavedChanges}>确认放弃</button>
    </>
  )
}

describe('UnsavedChangesProvider', () => {
  it('blocks an accidental unload but allows the confirmed navigation immediately', () => {
    render(
      <UnsavedChangesProvider>
        <SettingsHarness />
      </UnsavedChangesProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '修改配置' }))
    const accidentalUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(accidentalUnload)
    expect(accidentalUnload.defaultPrevented).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '确认放弃' }))
    const confirmedUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(confirmedUnload)
    expect(confirmedUnload.defaultPrevented).toBe(false)
  })
})
