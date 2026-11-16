import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import './App.css'
import { HubDiagram } from './HubDiagram'
import { MODES, evaluateMode, suggestMode, type ModeDef, type ModeId } from './fera/spec'
import { SIM_KITS, SimTransport } from './link/simTransport'
import { SerialTransport, webSerialSupported } from './link/transport'
import { Vehicle } from './link/vehicle'

const vehicle = new Vehicle()
// "?demo" opens straight into the simulator; "?demo=Plane kit" picks the modules.
const DEMO = new URLSearchParams(location.search).get('demo')
const DEMO_KIT = DEMO !== null && DEMO in SIM_KITS ? DEMO : 'Quad arms'
const LOW_BATTERY_V = 14.0 // 3.5 V per cell on 4S

interface Check {
  label: string
  ok: boolean
  detail?: string
}

export default function App() {
  const state = useSyncExternalStore(vehicle.subscribe, vehicle.getState)
  const simRef = useRef<SimTransport | undefined>(undefined)
  const [simulated, setSimulated] = useState(DEMO !== null)
  const [kit, setKit] = useState(DEMO_KIT)
  const [picked, setPicked] = useState<ModeId>()
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string }>()

  const connected = state.link !== 'disconnected' && state.link !== 'connecting'
  const suggested = suggestMode(state.ports)
  const active = MODES.find((m) => m.autostart === state.autostart)
  const mode: ModeDef | undefined =
    MODES.find((m) => m.id === picked) ?? suggested ?? active ?? undefined
  const issues = useMemo(() => (mode ? evaluateMode(mode, state.ports) : []), [mode, state.ports])

  const checks: Check[] = [
    {
      label: 'Vehicle link',
      ok: state.link === 'online',
      detail:
        state.link === 'online'
          ? `Connected over ${state.transportLabel}`
          : state.link === 'lost'
            ? 'No heartbeat — it may be restarting'
            : 'Waiting for the vehicle',
    },
    {
      label: 'Battery',
      ok: state.voltage !== undefined && state.voltage >= LOW_BATTERY_V,
      detail:
        state.voltage === undefined
          ? 'No battery reading yet'
          : `${state.voltage.toFixed(1)} V` +
            (state.batteryPercent !== undefined ? ` · ${state.batteryPercent}%` : '') +
            (state.voltage < LOW_BATTERY_V ? ' — charge before use' : ''),
    },
    {
      label: 'Modules reported',
      ok: state.portsSeen,
      detail: state.portsSeen ? 'All four ports are reporting' : 'No port data from the vehicle yet',
    },
    {
      label: mode ? `Modules match ${mode.name}` : 'Modules match a mode',
      ok: !!mode && state.portsSeen && issues.length === 0,
      detail: !mode
        ? 'Pick a mode'
        : issues.length === 0
          ? 'Every port has the right module, latched'
          : issues.map((i) => `${i.port}: ${i.problem}`).join(' · '),
    },
    { label: 'Disarmed', ok: !state.armed, detail: state.armed ? 'Disarm to change mode' : undefined },
  ]
  const ready = checks.every((c) => c.ok)
  const alreadyActive = !!mode && active?.id === mode.id

  useEffect(() => {
    if (DEMO === null) return
    const t = new SimTransport()
    t.ports = SIM_KITS[DEMO_KIT]
    simRef.current = t
    void vehicle.connect(t)
    return () => void vehicle.disconnect()
  }, [])

  async function connect(kind: 'usb' | 'sim') {
    setNotice(undefined)
    if (kind === 'sim') {
      const t = new SimTransport()
      t.ports = SIM_KITS[kit]
      simRef.current = t
      setSimulated(true)
      await vehicle.connect(t)
    } else {
      simRef.current = undefined
      setSimulated(false)
      await vehicle.connect(new SerialTransport())
    }
  }

  async function apply() {
    if (!mode) return
    setBusy(true)
    setNotice(undefined)
    try {
      await vehicle.applyAutostart(mode.autostart)
      setNotice({ kind: 'ok', text: `${mode.name} mode set. The vehicle is restarting.` })
    } catch (e) {
      setNotice({ kind: 'error', text: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>
          FERA <span>Configurator</span>
        </h1>
        <div className="link">
          <span className={`dot ${state.link}`} aria-hidden />
          {connected ? (
            <>
              <span>
                {state.link === 'online' ? 'Connected' : state.link === 'lost' ? 'Link lost' : 'Waiting'}
                {' · '}
                {state.transportLabel}
              </span>
              <button onClick={() => void vehicle.disconnect()}>Disconnect</button>
            </>
          ) : (
            <span>Not connected</span>
          )}
        </div>
      </header>

      {!connected ? (
        <main className="connect">
          <h2>Connect your FERA hub</h2>
          <p>Plug the hub in over USB, or try the app with a simulated hub.</p>
          <div className="actions">
            <button
              className="primary"
              disabled={!webSerialSupported || state.link === 'connecting'}
              onClick={() => void connect('usb')}
            >
              Connect over USB
            </button>
            <button disabled={state.link === 'connecting'} onClick={() => void connect('sim')}>
              Use simulator
            </button>
          </div>
          {!webSerialSupported && (
            <p className="hint">USB needs Chrome or Edge on a computer. The simulator works anywhere.</p>
          )}
          {state.error && <p className="notice error">{state.error}</p>}
        </main>
      ) : (
        <main className="workspace">
          <section className="panel">
            <h2>Modules</h2>
            <HubDiagram ports={state.ports} mode={mode} />
            {simulated && (
              <label className="sim">
                Simulated modules
                <select
                  value={kit}
                  onChange={(e) => {
                    setKit(e.target.value)
                    if (simRef.current) simRef.current.ports = SIM_KITS[e.target.value]
                    setPicked(undefined)
                  }}
                >
                  {Object.keys(SIM_KITS).map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </label>
            )}
          </section>

          <section className="panel">
            <h2>Mode</h2>
            <div className="modes" role="radiogroup" aria-label="Operation mode">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  role="radio"
                  aria-checked={mode?.id === m.id}
                  className={`mode ${mode?.id === m.id ? 'selected' : ''}`}
                  onClick={() => setPicked(m.id)}
                >
                  <strong>{m.name}</strong>
                  <small>{m.blurb}</small>
                  <span className="tags">
                    {active?.id === m.id && <em>Active</em>}
                    {suggested?.id === m.id && <em>Matches modules</em>}
                  </span>
                </button>
              ))}
            </div>

            <h2>Checks</h2>
            <ul className="checks">
              {checks.map((c) => (
                <li key={c.label} className={c.ok ? 'ok' : 'bad'}>
                  <span className="mark" aria-hidden>
                    {c.ok ? '✓' : '!'}
                  </span>
                  <div>
                    <strong>{c.label}</strong>
                    {c.detail && <small>{c.detail}</small>}
                  </div>
                </li>
              ))}
            </ul>

            <button className="primary wide" disabled={!ready || busy || alreadyActive} onClick={() => void apply()}>
              {busy
                ? 'Setting mode…'
                : !mode
                  ? 'Pick a mode'
                  : !ready
                    ? `Fix the checks above to use ${mode.name} mode`
                    : alreadyActive
                      ? `${mode.name} mode is active`
                      : `Set ${mode.name} mode and restart`}
            </button>
            {notice && <p className={`notice ${notice.kind}`}>{notice.text}</p>}
          </section>
        </main>
      )}
    </div>
  )
}
