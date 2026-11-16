// Encoders / decoders for the handful of MAVLink messages the app uses.
import { MESSAGE_INFO } from './frame'

export const MSG = {
  HEARTBEAT: 0,
  SYS_STATUS: 1,
  PARAM_REQUEST_READ: 20,
  PARAM_VALUE: 22,
  PARAM_SET: 23,
  COMMAND_LONG: 76,
  COMMAND_ACK: 77,
  NAMED_VALUE_FLOAT: 251,
} as const

export const MAV_PARAM_TYPE_INT32 = 6
export const MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN = 246
export const MAV_MODE_FLAG_SAFETY_ARMED = 0x80

const view = (p: Uint8Array) => new DataView(p.buffer, p.byteOffset, p.byteLength)
const blank = (msgid: number) => new Uint8Array(MESSAGE_INFO[msgid].length)

function putString(p: Uint8Array, offset: number, size: number, s: string) {
  for (let i = 0; i < size && i < s.length; i++) p[offset + i] = s.charCodeAt(i)
}
function getString(p: Uint8Array, offset: number, size: number): string {
  let s = ''
  for (let i = 0; i < size && p[offset + i] !== 0; i++) s += String.fromCharCode(p[offset + i])
  return s
}

// --- HEARTBEAT -------------------------------------------------------------
export interface Heartbeat {
  customMode: number
  type: number
  autopilot: number
  baseMode: number
  systemStatus: number
}
export function encodeHeartbeat(h: Heartbeat): Uint8Array {
  const p = blank(MSG.HEARTBEAT)
  const v = view(p)
  v.setUint32(0, h.customMode, true)
  p[4] = h.type
  p[5] = h.autopilot
  p[6] = h.baseMode
  p[7] = h.systemStatus
  p[8] = 3 // mavlink_version
  return p
}
export function decodeHeartbeat(p: Uint8Array): Heartbeat {
  return {
    customMode: view(p).getUint32(0, true),
    type: p[4],
    autopilot: p[5],
    baseMode: p[6],
    systemStatus: p[7],
  }
}

// --- SYS_STATUS (battery only) ---------------------------------------------
export interface SysStatus {
  voltage: number // volts
  current: number // amps, NaN if unknown
  remaining: number // percent, -1 if unknown
}
export function encodeSysStatus(s: SysStatus): Uint8Array {
  const p = blank(MSG.SYS_STATUS)
  const v = view(p)
  v.setUint16(14, Math.round(s.voltage * 1000), true)
  v.setInt16(16, Number.isNaN(s.current) ? -1 : Math.round(s.current * 100), true)
  v.setInt8(30, s.remaining)
  return p
}
export function decodeSysStatus(p: Uint8Array): SysStatus {
  const v = view(p)
  const cA = v.getInt16(16, true)
  return {
    voltage: v.getUint16(14, true) / 1000,
    current: cA < 0 ? NaN : cA / 100,
    remaining: v.getInt8(30),
  }
}

// --- Parameters ------------------------------------------------------------
// PX4 sends INT32 parameters with the integer's bytes placed in the float field.
export interface ParamValue {
  id: string
  type: number
  value: number
}
export function encodeParamRequestRead(sys: number, comp: number, id: string): Uint8Array {
  const p = blank(MSG.PARAM_REQUEST_READ)
  view(p).setInt16(0, -1, true)
  p[2] = sys
  p[3] = comp
  putString(p, 4, 16, id)
  return p
}
export function decodeParamRequestRead(p: Uint8Array) {
  return { sys: p[2], comp: p[3], id: getString(p, 4, 16) }
}
export function encodeParamValue(pv: ParamValue): Uint8Array {
  const p = blank(MSG.PARAM_VALUE)
  const v = view(p)
  if (pv.type === MAV_PARAM_TYPE_INT32) v.setInt32(0, pv.value, true)
  else v.setFloat32(0, pv.value, true)
  v.setUint16(4, 1, true)
  putString(p, 8, 16, pv.id)
  p[24] = pv.type
  return p
}
export function decodeParamValue(p: Uint8Array): ParamValue {
  const v = view(p)
  const type = p[24]
  return {
    id: getString(p, 8, 16),
    type,
    value: type === MAV_PARAM_TYPE_INT32 ? v.getInt32(0, true) : v.getFloat32(0, true),
  }
}
export function encodeParamSet(sys: number, comp: number, pv: ParamValue): Uint8Array {
  const p = blank(MSG.PARAM_SET)
  const v = view(p)
  if (pv.type === MAV_PARAM_TYPE_INT32) v.setInt32(0, pv.value, true)
  else v.setFloat32(0, pv.value, true)
  p[4] = sys
  p[5] = comp
  putString(p, 6, 16, pv.id)
  p[22] = pv.type
  return p
}
export function decodeParamSet(p: Uint8Array): ParamValue {
  const v = view(p)
  const type = p[22]
  return {
    id: getString(p, 6, 16),
    type,
    value: type === MAV_PARAM_TYPE_INT32 ? v.getInt32(0, true) : v.getFloat32(0, true),
  }
}

// --- Commands --------------------------------------------------------------
export function encodeCommandLong(
  sys: number,
  comp: number,
  command: number,
  params: number[] = [],
): Uint8Array {
  const p = blank(MSG.COMMAND_LONG)
  const v = view(p)
  for (let i = 0; i < 7; i++) v.setFloat32(i * 4, params[i] ?? 0, true)
  v.setUint16(28, command, true)
  p[30] = sys
  p[31] = comp
  return p
}
export function decodeCommandLong(p: Uint8Array) {
  const v = view(p)
  return {
    command: v.getUint16(28, true),
    params: Array.from({ length: 7 }, (_, i) => v.getFloat32(i * 4, true)),
  }
}
export function encodeCommandAck(command: number, result: number): Uint8Array {
  const p = blank(MSG.COMMAND_ACK)
  view(p).setUint16(0, command, true)
  p[2] = result
  return p
}
export function decodeCommandAck(p: Uint8Array) {
  return { command: view(p).getUint16(0, true), result: p[2] }
}

// --- NAMED_VALUE_FLOAT (interim carrier for FERA port status) ---------------
export function encodeNamedValueFloat(name: string, value: number): Uint8Array {
  const p = blank(MSG.NAMED_VALUE_FLOAT)
  view(p).setFloat32(4, value, true)
  putString(p, 8, 10, name)
  return p
}
export function decodeNamedValueFloat(p: Uint8Array) {
  return { name: getString(p, 8, 10), value: view(p).getFloat32(4, true) }
}
