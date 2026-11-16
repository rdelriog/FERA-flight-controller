/** A raw byte pipe to a vehicle. MAVLink runs on top of this. */
export interface Transport {
  readonly label: string
  open(onData: (bytes: Uint8Array) => void, onClose: (reason?: string) => void): Promise<void>
  write(bytes: Uint8Array): Promise<void>
  close(): Promise<void>
}

export const webSerialSupported = typeof navigator !== 'undefined' && 'serial' in navigator

/** USB / serial connection through the browser's Web Serial API (Chrome, Edge). */
export class SerialTransport implements Transport {
  readonly label = 'USB'
  private port?: SerialPort
  private reader?: ReadableStreamDefaultReader<Uint8Array>
  private writer?: WritableStreamDefaultWriter<Uint8Array>
  private closing = false
  private readonly baudRate: number

  constructor(baudRate = 57600) {
    this.baudRate = baudRate
  }

  async open(onData: (bytes: Uint8Array) => void, onClose: (reason?: string) => void) {
    // Must be called from a user gesture; shows the browser's port picker.
    this.port = await navigator.serial.requestPort()
    await this.port.open({ baudRate: this.baudRate })
    this.writer = this.port.writable!.getWriter()
    this.reader = this.port.readable!.getReader()
    void this.readLoop(onData, onClose)
  }

  private async readLoop(onData: (b: Uint8Array) => void, onClose: (reason?: string) => void) {
    try {
      for (;;) {
        const { value, done } = await this.reader!.read()
        if (done) break
        if (value) onData(value)
      }
      if (!this.closing) onClose('The serial port closed')
    } catch (e) {
      if (!this.closing) onClose(e instanceof Error ? e.message : 'The serial port was lost')
    }
  }

  async write(bytes: Uint8Array) {
    await this.writer?.write(bytes)
  }

  async close() {
    this.closing = true
    await this.reader?.cancel().catch(() => {})
    this.reader?.releaseLock()
    this.writer?.releaseLock()
    await this.port?.close().catch(() => {})
  }
}
