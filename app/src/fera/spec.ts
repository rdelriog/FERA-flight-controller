// The FERA Port spec as data. Mirrors docs/port-spec.md — change that first.

export const PORTS = ['FRONT', 'RIGHT', 'BACK', 'LEFT'] as const
export type PortName = (typeof PORTS)[number]

export const ModuleType = {
  NONE: 0x00,
  QUAD_ARM: 0x01,
  PLANE_NOSE: 0x10,
  PLANE_WING_LEFT: 0x11,
  PLANE_WING_RIGHT: 0x12,
  PLANE_TAIL: 0x13,
  WHEEL_DRIVE: 0x20,
  TRACK_DRIVE: 0x21,
  PONTOON: 0x30,
  CAP: 0x7f,
} as const

export const MODULE_NAMES: Record<number, string> = {
  [ModuleType.NONE]: 'Empty',
  [ModuleType.QUAD_ARM]: 'Quad arm',
  [ModuleType.PLANE_NOSE]: 'Plane nose',
  [ModuleType.PLANE_WING_LEFT]: 'Left wing',
  [ModuleType.PLANE_WING_RIGHT]: 'Right wing',
  [ModuleType.PLANE_TAIL]: 'Plane tail',
  [ModuleType.WHEEL_DRIVE]: 'Wheel drive',
  [ModuleType.TRACK_DRIVE]: 'Track drive',
  [ModuleType.PONTOON]: 'Pontoon + thruster',
  [ModuleType.CAP]: 'Blanking cap',
}

export interface PortStatus {
  present: boolean
  latched: boolean
  moduleType: number
}

export const EMPTY_PORT: PortStatus = { present: false, latched: false, moduleType: 0 }

/**
 * Interim wire format: the firmware streams NAMED_VALUE_FLOAT "FERA_P0".."FERA_P3"
 * whose value is an integer: bits 0-7 module type, bit 8 latched, bit 9 present.
 */
export function decodePortWord(word: number): PortStatus {
  const w = Math.round(word)
  return { moduleType: w & 0xff, latched: (w & 0x100) !== 0, present: (w & 0x200) !== 0 }
}
export function encodePortWord(p: PortStatus): number {
  return (p.moduleType & 0xff) | (p.latched ? 0x100 : 0) | (p.present ? 0x200 : 0)
}

export type ModeId = 'quad' | 'plane' | 'rover' | 'crawler' | 'boat'

export interface ModeDef {
  id: ModeId
  name: string
  blurb: string
  /** PX4 SYS_AUTOSTART of the FERA airframe (IDs to be registered in the PX4 fork). */
  autostart: number
  /** Accepted module types per port, in PORTS order. */
  requires: readonly (readonly number[])[]
}

const { QUAD_ARM, PLANE_NOSE, PLANE_WING_LEFT, PLANE_WING_RIGHT, PLANE_TAIL } = ModuleType
const { WHEEL_DRIVE, TRACK_DRIVE, PONTOON, CAP } = ModuleType

export const MODES: readonly ModeDef[] = [
  {
    id: 'quad',
    name: 'Quadcopter',
    blurb: 'Four arms, X layout',
    autostart: 4901,
    requires: [[QUAD_ARM], [QUAD_ARM], [QUAD_ARM], [QUAD_ARM]],
  },
  {
    id: 'plane',
    name: 'Fixed wing',
    blurb: 'Nose, tail and two wings',
    autostart: 2901,
    requires: [[PLANE_NOSE], [PLANE_WING_RIGHT], [PLANE_TAIL], [PLANE_WING_LEFT]],
  },
  {
    id: 'rover',
    name: 'Rover',
    blurb: 'Wheel drives, skid steer',
    autostart: 50901,
    requires: [[WHEEL_DRIVE, CAP], [WHEEL_DRIVE], [WHEEL_DRIVE, CAP], [WHEEL_DRIVE]],
  },
  {
    id: 'crawler',
    name: 'Crawler',
    blurb: 'Two track modules',
    autostart: 50902,
    requires: [[CAP], [TRACK_DRIVE], [CAP], [TRACK_DRIVE]],
  },
  {
    id: 'boat',
    name: 'Boat',
    blurb: 'Two pontoons with thrusters',
    autostart: 50903,
    requires: [[CAP], [PONTOON], [CAP], [PONTOON]],
  },
]

export interface PortIssue {
  port: PortName
  problem: string
}

/** Everything that stops `mode` from being usable with the modules now attached. */
export function evaluateMode(mode: ModeDef, ports: readonly PortStatus[]): PortIssue[] {
  const issues: PortIssue[] = []
  PORTS.forEach((port, i) => {
    const s = ports[i] ?? EMPTY_PORT
    const accepted = mode.requires[i]
    const wanted = accepted.map((t) => MODULE_NAMES[t]).join(' or ')
    if (!s.present) {
      issues.push({ port, problem: `Nothing attached — needs ${wanted}` })
    } else if (!accepted.includes(s.moduleType)) {
      const got = MODULE_NAMES[s.moduleType] ?? `unknown module 0x${s.moduleType.toString(16)}`
      issues.push({ port, problem: `${got} attached — needs ${wanted}` })
    } else if (!s.latched) {
      issues.push({ port, problem: 'Latch is open' })
    }
  })
  return issues
}

/** The mode whose requirements the attached modules satisfy, if any. */
export function detectMode(ports: readonly PortStatus[]): ModeDef | undefined {
  return MODES.find((m) => evaluateMode(m, ports).length === 0)
}

/** Like detectMode but ignores latches: "what is the user trying to build?" */
export function suggestMode(ports: readonly PortStatus[]): ModeDef | undefined {
  const latched = ports.map((p) => ({ ...p, latched: true }))
  return detectMode(latched)
}
