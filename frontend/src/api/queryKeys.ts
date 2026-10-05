/**
 * React Query cache keys. The token is never part of a key, so it never
 * reaches the query cache or its debugging output.
 */
import type { DatasetKey } from './types'

export const queryKeys = {
  me: ['me'] as const,
  catalog: ['catalog'] as const,
  dashboardAll: ['dashboard'] as const,
  dashboard: (range: string) => ['dashboard', range] as const,
  metric: (period: string) => ['metric', period] as const,
  previewAll: ['preview'] as const,
  preview: (datasetKey: DatasetKey, filters: Record<string, string | undefined>) =>
    ['preview', datasetKey, filters] as const,
  facilityDay: (period: string) => ['preview', 'facility-day', period] as const,
  facilitySpark: (facility: string, end: string) => ['preview', 'facility-spark', facility, end] as const,
  facilities: (datasetKey: DatasetKey, search: string) => ['facilities', datasetKey, search] as const,
  generators: (facility: string) => ['generators', facility] as const,
  runs: ['runs'] as const,
  run: (runId: string) => ['run', runId] as const,
  candidate: (versionId: string) => ['candidate', versionId] as const,
  settings: ['settings'] as const,
  scheduleStatus: ['schedule-status'] as const,
}
