import { describe, expect, it } from 'vitest'
import { MODES, decodePortWord, detectMode, encodePortWord, evaluateMode, suggestMode } from '../fera/spec'
import { SIM_KITS } from '../link/simTransport'

const mode = (id: string) => MODES.find((m) => m.id === id)!

describe('FERA port spec', () => {
  it('round-trips the port status word', () => {
    const p = { present: true, latched: false, moduleType: 0x13 }
    expect(decodePortWord(encodePortWord(p))).toEqual(p)
  })

  it('detects each complete kit as its mode', () => {
    expect(detectMode(SIM_KITS['Quad arms'])?.id).toBe('quad')
    expect(detectMode(SIM_KITS['Plane kit'])?.id).toBe('plane')
    expect(detectMode(SIM_KITS['Rover (4 wheels)'])?.id).toBe('rover')
    expect(detectMode(SIM_KITS['Crawler tracks'])?.id).toBe('crawler')
    expect(detectMode(SIM_KITS['Boat pontoons'])?.id).toBe('boat')
  })

  it('blocks a mode when a latch is open but still recognises the kit', () => {
    const ports = SIM_KITS['Quad, one latch open']
    expect(detectMode(ports)).toBeUndefined()
    expect(suggestMode(ports)?.id).toBe('quad')
    expect(evaluateMode(mode('quad'), ports)).toEqual([{ port: 'RIGHT', problem: 'Latch is open' }])
  })

  it('reports wrong and missing modules per port', () => {
    const issues = evaluateMode(mode('quad'), SIM_KITS['Mixed up'])
    expect(issues.map((i) => i.port)).toEqual(['RIGHT', 'BACK'])
    expect(issues[0].problem).toContain('Right wing attached')
    expect(issues[1].problem).toContain('Nothing attached')
  })

  it('does not accept wings on the wrong side', () => {
    const swapped = [...SIM_KITS['Plane kit']]
    ;[swapped[1], swapped[3]] = [swapped[3], swapped[1]]
    expect(evaluateMode(mode('plane'), swapped).length).toBe(2)
  })
})
