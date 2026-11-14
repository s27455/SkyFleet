/** The global rain warning (Feature 020): `active` means NEW takeoffs are suspended. */
export interface RainWarning {
  active: boolean
  /** ISO 8601 UTC, or null if it never was activated. */
  activatedAt: string | null
  clearedAt: string | null
}
