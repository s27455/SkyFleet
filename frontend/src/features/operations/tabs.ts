export const OPERATIONS_TABS = ['drones', 'hubs', 'orders', 'events'] as const
export type OperationsTab = (typeof OPERATIONS_TABS)[number]
