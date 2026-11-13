import { useState } from 'react'

import { Drone3DViewer } from './Drone3DViewer'
import type { DronePartId } from './droneParts'

/**
 * Dev-only harness for the 3D drone model (`/?preview=drone3d`). It is isolated from the app: no
 * map, no API, no selection state. Not included in production builds.
 */
export default function DronePreviewPage() {
  const [animate, setAnimate] = useState(true)
  const [narrow, setNarrow] = useState(false)
  const [lastPart, setLastPart] = useState<DronePartId | null>(null)

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
        <span className="text-fg-muted">Last clicked part: {lastPart ?? 'none'}</span>
      </div>
      <Drone3DViewer
        animate={animate}
        onPartSelect={setLastPart}
        className={`h-[min(70dvh,640px)] ${narrow ? 'w-[360px]' : 'w-full'}`}
      />
    </main>
  )
}
