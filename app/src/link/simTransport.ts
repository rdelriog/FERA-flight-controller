// A simulated FERA hub that speaks real MAVLink bytes, so the whole app stack
// (framing, parsing, parameters, commands) is exercised without hardware.
import { FrameParser, encodeFrame } from '../mavlink/frame'
import * as m from '../mavlink/messages'
import { EMPTY_PORT, ModuleType, encodePortWord, type PortStatus } from '../fera/spec'
import type { Transport } from './transport'

const SYS = 1
const COMP = 1
const cap: PortStatus = { present: true, latched: true, moduleType: ModuleType.CAP }
const mod = (moduleType: number, latched = true): PortStatus => ({
  present: true,
  latched,
  moduleType,
})

/** Module sets the demo can "plug in". Order: FRONT, RIGHT, BACK, LEFT. */
export const SIM_KITS: Record<string, PortStatus[]> = {
  'Quad arms': Array.from({ length: 4 }, () => mod(ModuleType.QUAD_ARM)),
  'Quad, one latch open': [
    mod(ModuleType.QUAD_ARM),
    mod(ModuleType.QUAD_ARM, false),
    mod(ModuleType.QUAD_ARM),
    mod(ModuleType.QUAD_ARM),
  ],
  'Plane kit': [
    mod(ModuleType.PLANE_NOSE),
    mod(ModuleType.PLANE_WING_RIGHT),
    mod(ModuleType.PLANE_TAIL),
    mod(ModuleType.PLANE_WING_LEFT),
  ],
  'Rover (4 wheels)': Array.from({ length: 4 }, () => mod(ModuleType.WHEEL_DRIVE)),
  'Crawler tracks': [cap, mod(ModuleType.TRACK_DRIVE), cap, mod(ModuleType.TRACK_DRIVE)],
  'Boat pontoons': [cap, mod(ModuleType.PONTOON), cap, mod(ModuleType.PONTOON)],
  'Mixed up': [
    mod(ModuleType.QUAD_ARM),
    mod(ModuleType.PLANE_WING_RIGHT),
    EMPTY_PORT,
    mod(ModuleType.QUAD_ARM),
  ],
  'Nothing attached': [EMPTY_PORT, EMPTY_PORT, EMPTY_PORT, EMPTY_PORT],
}

export class SimTransport implements Transport {
  readonly label = 'Simulator'
  ports: PortStatus[] = SIM_KITS['Quad arms']
  private params = new Map<string, number>([['SYS_AUTOSTART', 4901]])
  private parser = new FrameParser()
  private seq = 0
  private timers: ReturnType<typeof setInterval>[] = []
  private onData: (b: Uint8Array) => void = () => {}
  private open_ = false
  private kick?: ReturnType<typeof setTimeout>

  async open(onData: (bytes: Uint8Array) => void) {
    this.onData = onData
    this.open_ = true
    this.startTelemetry()
  }

  private startTelemetry() {
    const status = () => {
      this.send(
        m.MSG.HEARTBEAT,
        m.encodeHeartbeat({ customMode: 0, type: 2, autopilot: 12, baseMode: 0, systemStatus: 3 }),
      )
      this.send(m.MSG.SYS_STATUS, m.encodeSysStatus({ voltage: 15.9, current: 0.4, remaining: 78 }))
    }
    const ports = () =>
      this.ports.forEach((p, i) =>
        this.send(m.MSG.NAMED_VALUE_FLOAT, m.encodeNamedValueFloat(`FERA_P${i}`, encodePortWord(p))),
      )
    this.timers.push(setInterval(status, 1000), setInterval(ports, 500))
    // First report right away (after the caller has finished connecting).
    this.kick = setTimeout(() => {
      status()
      ports()
    }, 50)
  }

  private stopTelemetry() {
    this.timers.forEach(clearInterval)
    this.timers = []
    clearTimeout(this.kick)
  }

  private send(msgid: number, payload: Uint8Array) {
    this.onData(encodeFrame({ seq: this.seq++ & 0xff, sysid: SYS, compid: COMP, msgid, payload }))
  }

  async write(bytes: Uint8Array) {
    for (const f of this.parser.push(bytes)) {
      if (f.msgid === m.MSG.PARAM_REQUEST_READ) {
        const { id } = m.decodeParamRequestRead(f.payload)
        const value = this.params.get(id)
        if (value !== undefined) {
          this.send(m.MSG.PARAM_VALUE, m.encodeParamValue({ id, type: m.MAV_PARAM_TYPE_INT32, value }))
        }
      } else if (f.msgid === m.MSG.PARAM_SET) {
        const pv = m.decodeParamSet(f.payload)
        this.params.set(pv.id, pv.value)
        this.send(m.MSG.PARAM_VALUE, m.encodeParamValue(pv))
      } else if (f.msgid === m.MSG.COMMAND_LONG) {
        const { command } = m.decodeCommandLong(f.payload)
        this.send(m.MSG.COMMAND_ACK, m.encodeCommandAck(command, 0))
        if (command === m.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN) {
          // Go quiet like a rebooting autopilot, then come back.
          this.stopTelemetry()
          setTimeout(() => this.timers.length === 0 && this.open_ && this.startTelemetry(), 5000)
        }
      }
    }
  }

  async close() {
    this.open_ = false
    this.stopTelemetry()
    this.onData = () => {}
  }
}
