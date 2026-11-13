import type { DronePartId, PartAnnotation } from '../drone3d/droneParts'
import {
  motorTemperatureLevel,
  worstLevel,
  type HealthAssessment,
  type HealthLevel,
  type TelemetryReadings,
} from './deriveTelemetry'
import {
  MODEL_PART_FOR_COMPONENT,
  MOTOR_POSITION,
  REFERENCE,
  type SelectableComponentId,
} from './telemetryConfig'

export interface ComponentFinding {
  id: string
  level: HealthLevel
  detail: string
}

/** The health of one selectable component, judged by the same thresholds as `assessHealth`. */
export interface ComponentStatus {
  id: SelectableComponentId
  /** Short label, e.g. `M1` or `Battery`. */
  label: string
  /** Full name, e.g. `Motor M1 (front left)`. */
  name: string
  level: HealthLevel
  /** One finding per judged reading, nominal ones included, so a panel can say what was checked. */
  findings: ComponentFinding[]
}

export type ComponentStatuses = Partial<Record<SelectableComponentId, ComponentStatus>>

/**
 * Per-component health from the displayed readings. Each motor is judged by its own temperature
 * (the overall assessment only names the hottest one); the battery by its charge and temperature.
 * No threshold is defined here: motors use `REFERENCE`, the battery uses the assessment's findings.
 */
export function componentStatuses(
  readings: TelemetryReadings,
  health: HealthAssessment,
): ComponentStatuses {
  const statuses: ComponentStatuses = {}

  for (const motor of readings.motors ?? []) {
    const level = motorTemperatureLevel(motor.temperatureC)
    const { attention, critical } = REFERENCE.motorTempC
    statuses[motor.id] = {
      id: motor.id,
      label: motor.label,
      name: `Motor ${motor.label} (${MOTOR_POSITION[motor.id]})`,
      level,
      findings: [
        {
          id: `${motor.id}-temperature`,
          level,
          detail:
            level === 'nominal'
              ? `${motor.label} at ${motor.temperatureC.toFixed(1)} °C, within the ${attention} °C reference.`
              : `${motor.label} at ${motor.temperatureC.toFixed(1)} °C is above the ${
                  level === 'critical' ? critical : attention
                } °C ${level} threshold.`,
        },
      ],
    }
  }

  const batteryFindings = health.indicators
    .filter((indicator) => indicator.componentId === 'battery')
    .map(({ id, level, detail }) => ({ id, level, detail }))
  statuses.battery = {
    id: 'battery',
    label: 'Battery',
    name: 'Battery',
    level: worstLevel(batteryFindings.map((finding) => finding.level)),
    findings: batteryFindings,
  }

  return statuses
}

/** What the 3D viewer draws: a label and a level per model part. Motors absent from the airframe are skipped. */
export function annotationsFor(
  statuses: ComponentStatuses,
): Partial<Record<DronePartId, PartAnnotation>> {
  const annotations: Partial<Record<DronePartId, PartAnnotation>> = {}
  for (const status of Object.values(statuses)) {
    const part = MODEL_PART_FOR_COMPONENT[status.id]
    if (part) annotations[part] = { label: status.label, level: status.level }
  }
  return annotations
}
