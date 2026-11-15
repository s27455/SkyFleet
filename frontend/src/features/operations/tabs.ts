export const OPERATIONS_TABS = ['drones', 'hubs', 'orders', 'events', 'copilot'] as const
export type OperationsTab = (typeof OPERATIONS_TABS)[number]
