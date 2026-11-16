// Minimal MAVLink 2 framing: just what the Configurator needs.

export interface Frame {
  seq: number
  sysid: number
  compid: number
  msgid: number
  payload: Uint8Array
}

const STX_V2 = 0xfd
const HEADER_LEN = 10

/** CRC_EXTRA and full (untruncated) payload length for each message we speak. */
export const MESSAGE_INFO: Record<number, { crcExtra: number; length: number }> = {
  0: { crcExtra: 50, length: 9 }, // HEARTBEAT
  1: { crcExtra: 124, length: 31 }, // SYS_STATUS
  20: { crcExtra: 214, length: 20 }, // PARAM_REQUEST_READ
  22: { crcExtra: 220, length: 25 }, // PARAM_VALUE
  23: { crcExtra: 168, length: 23 }, // PARAM_SET
  76: { crcExtra: 152, length: 33 }, // COMMAND_LONG
  77: { crcExtra: 143, length: 3 }, // COMMAND_ACK
  251: { crcExtra: 170, length: 18 }, // NAMED_VALUE_FLOAT
}

/** CRC-16/MCRF4XX as used by MAVLink. */
export function crcAccumulate(byte: number, crc: number): number {
  let tmp = byte ^ (crc & 0xff)
  tmp = (tmp ^ (tmp << 4)) & 0xff
  return ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xffff
}

function crcOf(bytes: Uint8Array, crcExtra: number): number {
  let crc = 0xffff
  for (const b of bytes) crc = crcAccumulate(b, crc)
  return crcAccumulate(crcExtra, crc)
}

export function encodeFrame(f: Frame): Uint8Array {
  const info = MESSAGE_INFO[f.msgid]
  if (!info) throw new Error(`Unknown message id ${f.msgid}`)
  // MAVLink 2 truncates trailing zero bytes of the payload (at least 1 byte stays).
  let len = f.payload.length
  while (len > 1 && f.payload[len - 1] === 0) len--
  const out = new Uint8Array(HEADER_LEN + len + 2)
  out[0] = STX_V2
  out[1] = len
  out[2] = 0 // incompat flags
  out[3] = 0 // compat flags
  out[4] = f.seq & 0xff
  out[5] = f.sysid
  out[6] = f.compid
  out[7] = f.msgid & 0xff
  out[8] = (f.msgid >> 8) & 0xff
  out[9] = (f.msgid >> 16) & 0xff
  out.set(f.payload.subarray(0, len), HEADER_LEN)
  const crc = crcOf(out.subarray(1, HEADER_LEN + len), info.crcExtra)
  out[HEADER_LEN + len] = crc & 0xff
  out[HEADER_LEN + len + 1] = crc >> 8
  return out
}

/** Streaming parser: feed it bytes as they arrive, get complete valid frames. */
export class FrameParser {
  private buf = new Uint8Array(0)
  crcErrors = 0

  push(chunk: Uint8Array): Frame[] {
    const merged = new Uint8Array(this.buf.length + chunk.length)
    merged.set(this.buf)
    merged.set(chunk, this.buf.length)
    this.buf = merged

    const frames: Frame[] = []
    let i = 0
    while (i < this.buf.length) {
      if (this.buf[i] !== STX_V2) {
        i++
        continue
      }
      if (this.buf.length - i < HEADER_LEN) break
      const len = this.buf[i + 1]
      const signed = (this.buf[i + 2] & 0x01) !== 0
      const total = HEADER_LEN + len + 2 + (signed ? 13 : 0)
      if (this.buf.length - i < total) break

      const msgid = this.buf[i + 7] | (this.buf[i + 8] << 8) | (this.buf[i + 9] << 16)
      const info = MESSAGE_INFO[msgid]
      if (!info) {
        // Not a message we speak, so its checksum can't be verified. It may also be
        // a stray 0xFD in noise, so step one byte rather than trusting its length.
        i++
        continue
      }
      const crc = crcOf(this.buf.subarray(i + 1, i + HEADER_LEN + len), info.crcExtra)
      const got = this.buf[i + HEADER_LEN + len] | (this.buf[i + HEADER_LEN + len + 1] << 8)
      if (crc !== got) {
        this.crcErrors++
        i++ // false start byte: resync
        continue
      }
      const payload = new Uint8Array(Math.max(info.length, len)) // re-pad truncated zeros
      payload.set(this.buf.subarray(i + HEADER_LEN, i + HEADER_LEN + len))
      frames.push({
        seq: this.buf[i + 4],
        sysid: this.buf[i + 5],
        compid: this.buf[i + 6],
        msgid,
        payload,
      })
      i += total
    }
    this.buf = this.buf.subarray(i)
    return frames
  }
}
