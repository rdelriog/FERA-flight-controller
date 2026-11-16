import { MODULE_NAMES, PORTS, type ModeDef, type PortStatus } from './fera/spec'

// Top-down view of the hub, FRONT at the top.
const SLOTS = [
  { x: 160, y: 34 }, // FRONT
  { x: 316, y: 160 }, // RIGHT
  { x: 160, y: 286 }, // BACK
  { x: 4, y: 160 }, // LEFT
]

function portState(p: PortStatus, accepted?: readonly number[]) {
  if (!p.present) return { cls: 'empty', note: 'Empty' }
  if (accepted && !accepted.includes(p.moduleType)) return { cls: 'wrong', note: 'Wrong module' }
  if (!p.latched) return { cls: 'open', note: 'Latch open' }
  return { cls: 'good', note: 'Latched' }
}

export function HubDiagram({ ports, mode }: { ports: readonly PortStatus[]; mode?: ModeDef }) {
  const octagon = Array.from({ length: 8 }, (_, i) => {
    const a = ((22.5 + 45 * i) * Math.PI) / 180
    return `${160 + 70 * Math.cos(a)},${160 + 70 * Math.sin(a)}`
  }).join(' ')

  return (
    <svg className="hub" viewBox="-70 0 460 320" role="img" aria-label="Modules attached to the hub">
      {SLOTS.map((s, i) => (
        <line key={i} x1={160} y1={160} x2={s.x} y2={s.y} className="arm" />
      ))}
      <polygon points={octagon} className="body" />
      <text x={160} y={156} className="hub-label">
        FERA
      </text>
      <text x={160} y={174} className="hub-sub">
        ▲ front
      </text>
      {SLOTS.map((s, i) => {
        const p = ports[i]
        const st = portState(p, mode?.requires[i])
        const name = p.present ? (MODULE_NAMES[p.moduleType] ?? 'Unknown module') : PORTS[i]
        return (
          <g key={i} className={`slot ${st.cls}`}>
            <rect x={s.x - 62} y={s.y - 24} width={124} height={48} rx={8} />
            <text x={s.x} y={s.y - 3} className="slot-name">
              {name}
            </text>
            <text x={s.x} y={s.y + 14} className="slot-note">
              {p.present ? `${PORTS[i]} · ${st.note}` : st.note}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
