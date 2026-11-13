import { useMemo, useState } from 'react'

import { Drone3DViewer } from './Drone3DViewer'
import {
  MOTOR_IDS,
  PART_LEVEL_TEXT,
  type DronePartId,
  type PartAnnotation,
  type PartLevel,
} from './droneParts'

const LABELS: Partial<Record<DronePartId, string>> = {
  'motor-fl': 'M1',
  'motor-fr': 'M2',
  'motor-rr': 'M3',
  'motor-rl': 'M4',
  battery: 'Battery',
}
const DIAGNOSTIC_PARTS: readonly DronePartId[] = [...MOTOR_IDS, 'battery']
const LEVELS: readonly PartLevel[] = ['nominal', 'attention', 'critical']

/**
 * Dev-only harness for the 3D drone model (`/?preview=drone3d`). It is isolated from the app: no
 * map, no API. The health levels are forced here by hand so every highlight can be reviewed.
 * Not included in production builds.
 */
export default function DronePreviewPage() {
  const [animate, setAnimate] = useState(true)
  const [narrow, setNarrow] = useState(false)
  const [diagnostics, setDiagnostics] = useState(true)
  const [selected, setSelected] = useState<DronePartId | null>(null)
  const [levels, setLevels] = useState<Partial<Record<DronePartId, PartLevel>>>({})

  const annotations = useMemo(() => {
    const result: Partial<Record<DronePartId, PartAnnotation>> = {}
    for (const part of DIAGNOSTIC_PARTS) {
      result[part] = { label: LABELS[part] ?? part, level: levels[part] ?? 'nominal' }
    }
    return result
  }, [levels])

  return (
    <main className="min-h-dvh bg-canvas p-4 text-fg">
      <h1 className="text-lg font-semibold">Drone 3D model preview</h1>
      <div className="my-3 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={animate} onChange={(e) => setAnimate(e.target.checked)} />
          Animate propellers
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={narrow} onChange={(e) => setNarrow(e.target.checked)} />
          Narrow layout (360 px)
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={diagnostics}
            onChange={(e) => setDiagnostics(e.target.checked)}
          />
          Health highlights and labels
        </label>
        <span className="text-fg-muted">Selected part: {selected ?? 'none'}</span>
      </div>
      {diagnostics && (
        <div className="mb-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {DIAGNOSTIC_PARTS.map((part) => (
            <label key={part} className="flex items-center gap-2">
              {LABELS[part]}
              <select
                value={levels[part] ?? 'nominal'}
                onChange={(e) => setLevels({ ...levels, [part]: e.target.value as PartLevel })}
                className="rounded border border-line bg-surface px-1 py-0.5"
              >
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {PART_LEVEL_TEXT[level]}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      <Drone3DViewer
        animate={animate}
        annotations={diagnostics ? annotations : undefined}
        selectedPart={selected}
        onPartSelect={setSelected}
        className={`h-[min(70dvh,640px)] ${narrow ? 'w-[360px]' : 'w-full'}`}
      />
    </main>
  )
}
