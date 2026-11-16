// MAVLink session with one vehicle, exposed as an observable state snapshot.
import { FrameParser, encodeFrame } from '../mavlink/frame'
import * as m from '../mavlink/messages'
import { EMPTY_PORT, decodePortWord, type PortStatus } from '../fera/spec'
import type { Transport } from './transport'

const GCS_SYS = 255
const GCS_COMP = 190
const HEARTBEAT_TIMEOUT_MS = 3500

export interface VehicleState {
  link: 'disconnected' | 'connecting' | 'waiting' | 'online' | 'lost'
  transportLabel?: string
  error?: string
  armed: boolean
  voltage?: number
  batteryPercent?: number
  ports: PortStatus[]
  portsSeen: boolean
  autostart?: number
}

const INITIAL: VehicleState = {
  link: 'disconnected',
  armed: false,
  ports: [EMPTY_PORT, EMPTY_PORT, EMPTY_PORT, EMPTY_PORT],
  portsSeen: false,
}

interface Pending<T> {
  match: (msgid: number, payload: Uint8Array) => T | undefined
  resolve: (value: T) => void
}

export class Vehicle {
  private state: VehicleState = INITIAL
  private listeners = new Set<() => void>()
  private transport?: Transport
  private parser = new FrameParser()
  private seq = 0
  private sysid = 1
  private compid = 1
  private lastHeartbeat = 0
  private timers: ReturnType<typeof setInterval>[] = []
  private pending = new Set<Pending<unknown>>()

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
  getState = () => this.state

  private set(patch: Partial<VehicleState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((fn) => fn())
  }

  /** Bumped by every connect/disconnect so a superseded call can tell and stand down. */
  private generation = 0

  async connect(transport: Transport) {
    const gen = ++this.generation
    const previous = this.transport
    this.teardown()
    await previous?.close()
    if (gen !== this.generation) return
    this.set({ ...INITIAL, link: 'connecting', transportLabel: transport.label })
    try {
      await transport.open(
        (bytes) => gen === this.generation && this.onBytes(bytes),
        (reason) => {
          if (gen !== this.generation) return
          this.teardown()
          this.set({ ...INITIAL, error: reason })
        },
      )
    } catch (e) {
      if (gen !== this.generation) return
      // The user dismissing the port picker is not an error worth showing.
      const cancelled = e instanceof DOMException && e.name === 'NotFoundError'
      this.set({ ...INITIAL, error: cancelled ? undefined : describe(e) })
      return
    }
    if (gen !== this.generation) {
      await transport.close()
      return
    }
    this.transport = transport
    this.parser = new FrameParser()
    this.lastHeartbeat = 0
    this.set({ link: 'waiting' })
    this.timers.push(
      setInterval(() => this.sendGcsHeartbeat(), 1000),
      setInterval(() => this.watchdog(), 500),
    )
  }

  async disconnect() {
    this.generation++
    const t = this.transport
    this.teardown()
    await t?.close()
    this.set(INITIAL)
  }

  private teardown() {
    this.timers.forEach(clearInterval)
    this.timers = []
    this.pending.clear()
    this.transport = undefined
  }

  private watchdog() {
    if (this.state.link === 'online' && Date.now() - this.lastHeartbeat > HEARTBEAT_TIMEOUT_MS) {
      this.set({ link: 'lost' })
    }
  }

  private send(msgid: number, payload: Uint8Array) {
    const frame = encodeFrame({
      seq: this.seq++ & 0xff,
      sysid: GCS_SYS,
      compid: GCS_COMP,
      msgid,
      payload,
    })
    return this.transport?.write(frame) ?? Promise.resolve()
  }

  private sendGcsHeartbeat() {
    // type 6 = GCS, autopilot 8 = invalid (not a flight controller)
    void this.send(
      m.MSG.HEARTBEAT,
      m.encodeHeartbeat({ customMode: 0, type: 6, autopilot: 8, baseMode: 0, systemStatus: 4 }),
    )
  }

  private onBytes(bytes: Uint8Array) {
    for (const f of this.parser.push(bytes)) {
      if (f.sysid === GCS_SYS) continue
      for (const p of this.pending) {
        const hit = p.match(f.msgid, f.payload)
        if (hit !== undefined) {
          this.pending.delete(p)
          p.resolve(hit)
        }
      }
      switch (f.msgid) {
        case m.MSG.HEARTBEAT: {
          const hb = m.decodeHeartbeat(f.payload)
          this.sysid = f.sysid
          this.compid = f.compid
          this.lastHeartbeat = Date.now()
          const wasOnline = this.state.link === 'online'
          this.set({ link: 'online', armed: (hb.baseMode & m.MAV_MODE_FLAG_SAFETY_ARMED) !== 0 })
          if (!wasOnline) void this.refreshAutostart()
          break
        }
        case m.MSG.SYS_STATUS: {
          const s = m.decodeSysStatus(f.payload)
          this.set({
            voltage: s.voltage,
            batteryPercent: s.remaining >= 0 ? s.remaining : undefined,
          })
          break
        }
        case m.MSG.NAMED_VALUE_FLOAT: {
          const { name, value } = m.decodeNamedValueFloat(f.payload)
          const match = /^FERA_P([0-3])$/.exec(name)
          if (match) {
            const ports = [...this.state.ports]
            ports[Number(match[1])] = decodePortWord(value)
            this.set({ ports, portsSeen: true })
          }
          break
        }
      }
    }
  }

  /** Send something and wait for the matching reply, retrying like a GCS does. */
  private async request<T>(
    sendFn: () => Promise<void>,
    match: Pending<T>['match'],
    what: string,
  ): Promise<T> {
    for (let attempt = 0; attempt < 3; attempt++) {
      const got = await new Promise<T | undefined>((resolve) => {
        const p: Pending<T> = { match, resolve }
        this.pending.add(p as Pending<unknown>)
        void sendFn()
        setTimeout(() => {
          this.pending.delete(p as Pending<unknown>)
          resolve(undefined)
        }, 1000)
      })
      if (got !== undefined) return got
    }
    throw new Error(`The vehicle did not answer (${what})`)
  }

  async readIntParam(id: string): Promise<number> {
    const pv = await this.request(
      () => this.send(m.MSG.PARAM_REQUEST_READ, m.encodeParamRequestRead(this.sysid, this.compid, id)),
      (msgid, p) => (msgid === m.MSG.PARAM_VALUE && m.decodeParamValue(p).id === id ? m.decodeParamValue(p) : undefined),
      `read ${id}`,
    )
    return pv.value
  }

  async writeIntParam(id: string, value: number): Promise<void> {
    const pv = { id, type: m.MAV_PARAM_TYPE_INT32, value }
    const echoed = await this.request(
      () => this.send(m.MSG.PARAM_SET, m.encodeParamSet(this.sysid, this.compid, pv)),
      (msgid, p) => (msgid === m.MSG.PARAM_VALUE && m.decodeParamValue(p).id === id ? m.decodeParamValue(p) : undefined),
      `write ${id}`,
    )
    if (echoed.value !== value) throw new Error(`The vehicle rejected ${id} = ${value}`)
  }

  private async refreshAutostart() {
    try {
      this.set({ autostart: await this.readIntParam('SYS_AUTOSTART') })
    } catch {
      this.set({ autostart: undefined })
    }
  }

  /** Select a FERA airframe and reboot the autopilot so it takes effect. */
  async applyAutostart(autostart: number): Promise<void> {
    if (this.state.armed) throw new Error('Disarm the vehicle before changing mode')
    await this.writeIntParam('SYS_AUTOSTART', autostart)
    this.set({ autostart })
    const ack = await this.request(
      () =>
        this.send(
          m.MSG.COMMAND_LONG,
          m.encodeCommandLong(this.sysid, this.compid, m.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, [1]),
        ),
      (msgid, p) =>
        msgid === m.MSG.COMMAND_ACK &&
        m.decodeCommandAck(p).command === m.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
          ? m.decodeCommandAck(p)
          : undefined,
      'reboot',
    )
    if (ack.result !== 0) throw new Error('The vehicle refused to reboot')
  }
}

function describe(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
