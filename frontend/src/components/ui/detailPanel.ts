/**
 * Shared layout for the contextual detail panels (one is open at a time).
 * On narrow screens the panel sits above the bottom edge (`bottom-9`) so the Mapbox attribution
 * in the bottom-right corner stays visible, and it scrolls instead of covering the whole map.
 */
export const DETAIL_PANEL_CLASS =
  'absolute inset-x-3 bottom-9 z-20 max-h-[60dvh] overflow-y-auto rounded-lg border border-line bg-surface p-4 shadow-lg sm:inset-x-auto sm:top-3 sm:bottom-auto sm:left-3 sm:max-h-[calc(100%-1.5rem)] sm:w-80'
