import type { RefObject } from 'react'

import {
  PART_LEVEL_TEXT,
  type DronePartId,
  type PartAnnotation,
  type PartLevel,
} from './droneParts'

/** In the order M1..M4, then the battery: also the keyboard tab order. */
const LABELED_PARTS: readonly DronePartId[] = [
  'motor-fl',
  'motor-fr',
  'motor-rr',
  'motor-rl',
  'battery',
]

const DOT: Record<PartLevel, string> = {
  nominal: 'bg-status-ok',
  attention: 'bg-status-warning',
  critical: 'bg-status-critical',
}

interface PartLabelsProps {
  annotations: Readonly<Partial<Record<DronePartId, PartAnnotation>>>
  selectedPart: DronePartId | null
  onPartSelect?: (part: DronePartId | null) => void
  /** The layer the 3D scene positions the labels in, each frame, from `data-label-part`. */
  layerRef: RefObject<HTMLDivElement | null>
}

/**
 * Labels over the 3D model. Each is a real button, so it is also a keyboard route to the selection,
 * and it states its level in words next to the colour. The scene only moves them
 * (`LabelProjector`); they hold no state of their own.
 */
export function PartLabels({ annotations, selectedPart, onPartSelect, layerRef }: PartLabelsProps) {
  return (
    <div ref={layerRef} className="pointer-events-none absolute inset-0 overflow-hidden">
      {LABELED_PARTS.map((part) => {
        const annotation = annotations[part]
        if (!annotation) return null
        const levelText = PART_LEVEL_TEXT[annotation.level]
        const selected = selectedPart === part
        return (
          <button
            key={part}
            type="button"
            data-label-part={part}
            disabled={!onPartSelect}
            aria-pressed={onPartSelect ? selected : undefined}
            aria-label={`${annotation.label}, ${levelText}`}
            onClick={() => onPartSelect?.(part)}
            // Hidden until the scene has placed it, so it never flashes in the corner.
            style={{ visibility: 'hidden' }}
            className={`pointer-events-auto absolute top-0 left-0 inline-flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap text-fg backdrop-blur focus-visible:outline-2 focus-visible:outline-accent @max-md:min-h-7 @max-md:gap-1 @max-md:px-2 @max-md:text-[11px] ${
              selected ? 'border-accent bg-surface-raised' : 'border-line bg-surface/85'
            } ${onPartSelect ? 'cursor-pointer hover:bg-surface-raised' : ''}`}
          >
            <span aria-hidden="true" className={`size-2 rounded-full ${DOT[annotation.level]}`} />
            {annotation.label}
            {annotation.level !== 'nominal' && (
              <span className="font-normal text-fg-muted">· {levelText}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
