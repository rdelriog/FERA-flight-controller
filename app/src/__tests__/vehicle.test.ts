import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SIM_KITS, SimTransport } from '../link/simTransport'
import { Vehicle } from '../link/vehicle'

describe('Vehicle over the simulated hub', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('comes online, reads modules, switches mode and survives the reboot', async () => {
    const v = new Vehicle()
    const sim = new SimTransport()
    sim.ports = SIM_KITS['Plane kit']
    await v.connect(sim)
    expect(v.getState().link).toBe('waiting')

    await vi.advanceTimersByTimeAsync(1500)
    let s = v.getState()
    expect(s.link).toBe('online')
    expect(s.portsSeen).toBe(true)
    expect(s.ports.map((p) => p.moduleType)).toEqual([0x10, 0x12, 0x13, 0x11])
    expect(s.autostart).toBe(4901)
    expect(s.voltage).toBeCloseTo(15.9)

    const applied = v.applyAutostart(2901)
    await vi.advanceTimersByTimeAsync(100)
    await applied
    expect(v.getState().autostart).toBe(2901)

    await vi.advanceTimersByTimeAsync(4500) // vehicle is silent while rebooting
    expect(v.getState().link).toBe('lost')
    await vi.advanceTimersByTimeAsync(3000)
    s = v.getState()
    expect(s.link).toBe('online')
    expect(await withTimers(v.readIntParam('SYS_AUTOSTART'))).toBe(2901)
    await v.disconnect()
  })
})

async function withTimers<T>(p: Promise<T>): Promise<T> {
  await vi.advanceTimersByTimeAsync(50)
  return p
}
