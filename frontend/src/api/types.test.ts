import { describe, expect, it } from 'vitest'
// Vite's ?raw suffix imports the file as text. The test parses the real
// contract file, so a contract change that is not copied here fails.
import openapiText from '../../../docs/openapi.json?raw'
import {
  ACTION_NAMES,
  BLOCK_CODES,
  CAPABILITIES,
  COLUMN_TYPES,
  DASHBOARD_PRESETS,
  DATASET_KEYS,
  ERROR_CODES,
  LANDING_SCREENS,
  PUBLICATION_STATUSES,
  RECEIPT_RESULTS,
  REVIEW_STATUSES,
  ROLES,
  RUN_STATUSES,
  STEP_STAGES,
  STEP_STATUSES,
  WARNING_STAGES,
} from './types'

type Schema = { enum?: string[]; properties?: Record<string, Schema>; items?: Schema; anyOf?: Schema[]; oneOf?: Schema[] }
type OpenApi = {
  components: { schemas: Record<string, Schema> }
  paths: Record<string, Record<string, { parameters?: { name?: string; schema?: Schema }[] }>>
}

const openapi = JSON.parse(openapiText) as OpenApi
const schemas = openapi.components.schemas

function enumOf(schema: Schema | undefined): string[] {
  if (schema === undefined) throw new Error('Schema not found in docs/openapi.json')
  if (schema.enum !== undefined) return schema.enum
  for (const alternative of [...(schema.anyOf ?? []), ...(schema.oneOf ?? [])]) {
    if (alternative.enum !== undefined) return alternative.enum
  }
  throw new Error('Schema has no enum')
}

describe('hand-written contract types', () => {
  it('match every enum in docs/openapi.json', () => {
    expect([...CAPABILITIES]).toEqual(enumOf(schemas.Capability))
    expect([...RUN_STATUSES]).toEqual(enumOf(schemas.RunStatus))
    expect([...ACTION_NAMES]).toEqual(enumOf(schemas.ActionName))
    expect([...BLOCK_CODES]).toEqual(enumOf(schemas.BlockCode))
    expect([...ERROR_CODES]).toEqual(enumOf(schemas.ErrorCode))
    expect([...DATASET_KEYS]).toEqual(enumOf(schemas.DatasetKey))
    expect([...ROLES]).toEqual(enumOf(schemas.MeResponse.properties?.role))
    expect([...LANDING_SCREENS]).toEqual(enumOf(schemas.MeResponse.properties?.landing_screen))
    expect([...STEP_STAGES]).toEqual(enumOf(schemas.Step.properties?.stage))
    expect([...STEP_STATUSES]).toEqual(enumOf(schemas.Step.properties?.status))
    expect([...WARNING_STAGES]).toEqual(enumOf(schemas.FailureWarning.properties?.stage))
    expect([...REVIEW_STATUSES]).toEqual(enumOf(schemas.CandidateRef.properties?.review_status))
    expect([...PUBLICATION_STATUSES]).toEqual(enumOf(schemas.CandidateRef.properties?.publication_status))
    expect([...COLUMN_TYPES]).toEqual(enumOf(schemas.Column.properties?.type))
    expect([...RECEIPT_RESULTS]).toEqual(enumOf(schemas.ActionReceipt.properties?.result))
    const preset = openapi.paths['/dashboard/national'].get.parameters?.find((parameter) => parameter.name === 'preset')
    expect([...DASHBOARD_PRESETS]).toEqual(enumOf(preset?.schema))
  })
})
