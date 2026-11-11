/** Small checks shared by the API adapters that validate untrusted JSON. */

export function isFiniteNumberInRange(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
}

export function isPositiveFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value !== ''
}
