import type { HealthResponse } from '../types/health'
import { apiGet } from './client'

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health', signal)
}
