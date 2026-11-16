// @vitest-environment jsdom
import { StrictMode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

async function open(query: string) {
  vi.resetModules()
  window.history.replaceState(null, '', `/${query}`)
  const { default: App } = await import('../App')
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  await act(() => vi.advanceTimersByTimeAsync(1600))
}

describe('App in demo mode (StrictMode double-mount)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('shows the connect screen without ?demo', async () => {
    await open('')
    expect(screen.getByText('Connect your FERA hub')).toBeTruthy()
  })

  it('connects and recognises a quad', async () => {
    await open('?demo')
    expect(screen.getByText(/Connected · Simulator/)).toBeTruthy()
    expect(screen.getByText('Modules match Quadcopter')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Quadcopter mode is active' })).toHaveProperty('disabled', true)
  })

  it('offers to switch when a plane kit is attached, then applies it', async () => {
    await open('?demo=Plane%20kit')
    const apply = screen.getByRole('button', { name: 'Set Fixed wing mode and restart' })
    expect(apply).toHaveProperty('disabled', false)
    await act(async () => {
      apply.click()
      await vi.advanceTimersByTimeAsync(200)
    })
    expect(screen.getByText('Fixed wing mode set. The vehicle is restarting.')).toBeTruthy()
  })

  it('blocks the mode and names the port when a latch is open', async () => {
    await open('?demo=Quad,%20one%20latch%20open')
    expect(screen.getByText('RIGHT: Latch is open')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Fix the checks above to use Quadcopter mode' })).toHaveProperty('disabled', true)
  })

  it('asks for a mode when the modules match nothing', async () => {
    await open('?demo=Mixed%20up')
    expect(screen.getByText(/Connected · Simulator/)).toBeTruthy()
    expect(screen.getByText('Wrong module', { exact: false })).toBeTruthy()
  })
})
