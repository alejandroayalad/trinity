/**
 * API contract types, written by hand from docs/openapi.json.
 *
 * Each enum is also a runtime list, so types.test.ts can compare it with the
 * OpenAPI file. A later contract change then fails that test instead of
 * silently drifting. Decimal, Counter and date values stay strings.
 */

/** Exact decimal text, for example "100056.000000". Never a JSON float. */
export type DecimalText = string
/** Nonnegative integer as text, for example a revision "3" or run_seq "1044". */
export type Counter = string
/** Calendar date text, YYYY-MM-DD. */
export type DateText = string
/** UTC event time in RFC 3339 form. */
export type Timestamp = string
/** Source identifier. Keep case and leading zeros exactly. */
export type SourceId = string

export const CAPABILITIES = [
  'national:read',
  'catalog:read',
  'preview:national',
  'preview:detail',
  'sql:execute',
  'settings:read',
  'settings:write',
  'refresh:read',
  'refresh:start',
  'refresh:recover',
  'candidate:review',
] as const
export type Capability = (typeof CAPABILITIES)[number]

export const ROLES = ['viewer', 'analyst', 'admin'] as const
export type Role = (typeof ROLES)[number]

export const LANDING_SCREENS = ['waiting', 'setup', 'refresh_runs', 'national_dashboard', 'explorer'] as const
export type LandingScreen = (typeof LANDING_SCREENS)[number]

export const DATASET_KEYS = ['national_outages', 'facility_outages', 'generator_outages'] as const
export type DatasetKey = (typeof DATASET_KEYS)[number]

export const RUN_STATUSES = [
  'requested',
  'running',
  'awaiting_approval',
  'publishing',
  'publication_failed',
  'succeeded',
  'failed',
  'discarded',
  'superseded',
] as const
export type RunStatus = (typeof RUN_STATUSES)[number]

export const ACTION_NAMES = ['start_refresh', 'rerun', 'delete_warning', 'approve', 'publication_retry', 'discard'] as const
export type ActionName = (typeof ACTION_NAMES)[number]

export const BLOCK_CODES = [
  'setup_required',
  'schedule_disabled',
  'refresh_active',
  'review_required',
  'publication_in_progress',
  'failure_unresolved',
  'candidate_ineligible',
  'candidate_discarded',
  'candidate_superseded',
  'already_published',
  'no_unresolved_warning',
  'not_applicable',
  'dependency_unavailable',
] as const
export type BlockCode = (typeof BLOCK_CODES)[number]

export const ERROR_CODES = [
  'invalid_json',
  'invalid_request',
  'unsupported_media_type',
  'authentication_required',
  'invalid_session',
  'forbidden',
  'resource_not_found',
  'dataset_not_found',
  'data_unavailable',
  'publication_changed',
  'invalid_cursor',
  'setup_required',
  'refresh_blocked',
  'idempotency_key_required',
  'idempotency_conflict',
  'action_not_allowed',
  'candidate_ineligible',
  'precondition_required',
  'revision_mismatch',
  'sql_not_allowed',
  'query_failed',
  'request_too_large',
  'rate_limited',
  'auth_unavailable',
  'dependency_unavailable',
  'query_resource_limit',
  'query_timeout',
  'internal_error',
  'invalid_credentials',
] as const
export type ErrorCode = (typeof ERROR_CODES)[number]

export const STEP_STAGES = ['extract', 'prepare', 'validate', 'publish'] as const
export type StepStage = (typeof STEP_STAGES)[number]

export const WARNING_STAGES = ['extract', 'prepare', 'validate', 'publish', 'dispatch'] as const
export type WarningStage = (typeof WARNING_STAGES)[number]

export const STEP_STATUSES = ['pending', 'running', 'succeeded', 'failed', 'abandoned'] as const
export type StepStatus = (typeof STEP_STATUSES)[number]

export const REVIEW_STATUSES = ['not_ready', 'not_required', 'required', 'approved', 'discarded'] as const
export type ReviewStatus = (typeof REVIEW_STATUSES)[number]

export const PUBLICATION_STATUSES = ['not_started', 'queued', 'publishing', 'failed', 'published', 'blocked'] as const
export type PublicationStatus = (typeof PUBLICATION_STATUSES)[number]

export const COLUMN_TYPES = ['string', 'date', 'timestamp', 'decimal', 'integer', 'boolean'] as const
export type ColumnType = (typeof COLUMN_TYPES)[number]

export const RECEIPT_RESULTS = ['queued', 'warning_resolved', 'discarded'] as const
export type ReceiptResult = (typeof RECEIPT_RESULTS)[number]

export const DASHBOARD_PRESETS = ['30d', '90d', '1y'] as const
export type DashboardPreset = (typeof DASHBOARD_PRESETS)[number]

export type MetricNullReason = 'not_reported' | 'zero_capacity'

export type LoginResponse = {
  access_token: string
  token_type: 'Bearer'
  expires_at: Timestamp
}

export type Publication = {
  publication_event_id: string
  version_id: string
  published_at: Timestamp
  coverage_start: DateText
  coverage_end: DateText
  latest_observation_date: DateText
}

export type Action = {
  action: ActionName
  enabled: boolean
  reason_code: BlockCode | null
}

export type Blocker = {
  code: BlockCode
  message: string
  run_id: string | null
  version_id: string | null
  warning_id: string | null
}

export type RefreshSummary = {
  run_id: string
  status: RunStatus
  requested_at: Timestamp
  finished_at: Timestamp | null
}

export type AdminContext = {
  setup_completed: boolean
  refresh_blocker: Blocker | null
  active_run: RefreshSummary | null
  actions: Action[]
}

export type MeResponse = {
  user_id: string
  role: Role
  capabilities: Capability[]
  data_ready: boolean
  landing_screen: LandingScreen
  publication: Publication | null
  admin_context: AdminContext | null
}

export type SettingsRequest = {
  schedule_enabled: boolean
  daily_time: string
  timezone: string
}

export type SettingsResponse = {
  setup_completed_at: Timestamp | null
  schedule_enabled: boolean
  daily_time: string | null
  timezone: string | null
  revision: Counter
  updated_at: Timestamp
  updated_by: string | null
}

export type ScheduleStatus = {
  settings_revision: Counter
  schedule_enabled: boolean
  next_check_at: Timestamp | null
  next_check_local: string | null
  timezone: string | null
  evaluated_at: Timestamp
  eligible_now: boolean
  blocker: Blocker | null
}

export type Column = {
  name: string
  type: ColumnType
  nullable: boolean
  unit: 'MW' | 'percent' | null
}

export type MetricDefinition = {
  key: 'offline_share_percent'
  label: string
  unit: 'percent'
  formula: string
  null_reasons: MetricNullReason[]
  display_decimal_places: number
}

export type Dataset = {
  key: DatasetKey
  label: string
  description: string
  daily_key: string[]
  columns: Column[]
  available_filters: ('start' | 'end' | 'facility' | 'generator')[]
}

export type Freshness = {
  latest_observation_date: DateText | null
  published_at: Timestamp | null
  last_refresh: { status: RunStatus; requested_at: Timestamp; finished_at: Timestamp | null } | null
}

export type CatalogResponse = {
  datasets: Dataset[]
  metrics: MetricDefinition[]
  data_ready: boolean
  publication: Publication | null
  freshness: Freshness
}

export type Diagnostic = {
  code: string
  severity: 'info' | 'warning'
  scope: 'national' | 'facility' | 'generator' | 'all'
  message: string
  affected_count: Counter
}

export type MetricValue = {
  value: DecimalText | null
  reason: MetricNullReason | null
}

export type MetricResponse = {
  publication: Publication
  period: DateText
  metric: MetricValue
  diagnostics: Diagnostic[]
}

export type NationalDay = {
  period: DateText
  capacity: DecimalText | null
  outage: DecimalText | null
  percentOutage: DecimalText | null
  offline_share_percent: DecimalText | null
  reason: MetricNullReason | null
}

export type DateRange = { start: DateText; end: DateText }

export type DashboardResponse = {
  publication: Publication
  range: DateRange
  summary: NationalDay
  days: NationalDay[]
  diagnostics: Diagnostic[]
  freshness: Freshness
}

/** A cell is text, a boolean or null. Dates, IDs, decimals and integers are text. */
export type Cell = string | boolean | null

export type PreviewResponse = {
  publication: Publication
  dataset_key: DatasetKey
  range: DateRange
  columns: Column[]
  rows: Cell[][]
  returned_rows: number
  next_cursor: string | null
  reason: 'not_reported' | null
  diagnostics: Diagnostic[]
}

export type FacilityOption = { facility: SourceId; facilityName: string | null }
export type GeneratorOption = { facility: SourceId; generator: SourceId }

export type FacilityOptions = {
  publication: Publication
  range: DateRange
  items: FacilityOption[]
  next_cursor: string | null
}

export type GeneratorOptions = {
  publication: Publication
  range: DateRange
  facility: SourceId
  items: GeneratorOption[]
  next_cursor: string | null
}

export type QueryResponse = {
  publication: Publication
  columns: Column[]
  rows: Cell[][]
  returned_rows: number
  truncated: boolean
  execution_ms: number
  diagnostics: Diagnostic[]
}

export type FailureWarning = {
  warning_id: string
  run_id: string
  version_id: string | null
  stage: WarningStage
  code: string
  message: string
  created_at: Timestamp
  resolved_at: Timestamp | null
  resolution: 'rerun' | 'delete_warning' | 'publication_retry' | 'discard' | 'superseded' | null
  resolved_by: string | null
}

export type Progress = {
  processed_count: Counter
  total_count: Counter | null
  unit: 'rows' | 'files' | 'checks' | 'tasks'
}

export type Step = {
  step_id: string
  step_seq: Counter
  stage: StepStage
  work_key: string
  attempt: number
  status: StepStatus
  started_at: Timestamp | null
  finished_at: Timestamp | null
  progress: Progress
  error_code: string | null
  error_summary: string | null
}

export type CandidateRef = {
  version_id: string
  review_status: ReviewStatus
  publication_status: PublicationStatus
}

export type Run = {
  run_id: string
  run_seq: Counter
  revision: Counter
  trigger_kind: 'manual' | 'scheduled' | 'rerun'
  requested_by: string | null
  rerun_of_run_id: string | null
  requested_at: Timestamp
  started_at: Timestamp | null
  finished_at: Timestamp | null
  status: RunStatus
  settings_revision: Counter
  workflow_policy: 'warnings-v1'
  requested_start: DateText
  requested_end: DateText | null
  candidate: CandidateRef | null
  warning: FailureWarning | null
  actions: Action[]
  steps: Step[]
  next_steps_cursor: string | null
  poll_after_seconds: number | null
}

export type RunList = {
  items: RefreshSummary[]
  next_cursor: string | null
  active_run: RefreshSummary | null
  unresolved_warning: FailureWarning | null
  blocker: Blocker | null
  actions: Action[]
}

export type ValidationCheck = {
  code: string
  scope: 'national' | 'facility' | 'generator' | 'all'
  status: 'pass' | 'fail' | 'error'
  checked_count: Counter
  failed_count: Counter
  checked_at: Timestamp
  message: string
}

export type Validation = {
  status: 'pending' | 'running' | 'passed' | 'failed' | 'incomplete'
  step_id: string | null
  checkset: 'trinity-data-v1'
  expected_required_count: number
  passed_required_count: number
  checks: ValidationCheck[]
}

export type Approval = {
  approval_id: string
  approved_by: string
  approved_at: Timestamp
  manifest_sha256: string
  validation_step_id: string
  review_warning_digest: string
}

export type PublicationProgress = {
  status: PublicationStatus
  generation: Counter
  attempt: number
  error_code: string | null
  error_summary: string | null
  published_at: Timestamp | null
  publication_event_id: string | null
}

export type Candidate = {
  version_id: string
  run_id: string
  revision: Counter
  validation_status: 'preparing' | 'validating' | 'validated' | 'rejected'
  disposition: 'active' | 'discarded' | 'superseded'
  created_at: Timestamp
  coverage: DateRange
  latest_observation_date: DateText
  manifest_sha256: string | null
  validation: Validation
  diagnostics: Diagnostic[]
  review_warning_count: Counter | null
  review_warning_digest: string | null
  review_status: ReviewStatus
  approval_required: boolean | null
  approval: Approval | null
  publication: PublicationProgress
  failure_warning: FailureWarning | null
  discarded_at: Timestamp | null
  discarded_by: string | null
  actions: Action[]
}

export type ActionReceipt = {
  operation_id: string
  action: ActionName
  accepted_at: Timestamp
  run_id: string
  version_id: string | null
  status_url: string
  result: ReceiptResult
  replayed: boolean
}

export type FieldError = { field: string; code: string; message: string }

export type Problem = {
  type: string
  title: string
  status: number
  detail: string
  code: ErrorCode
  request_id: string
  errors: FieldError[]
  blocker: Blocker | null
  current_revision: Counter | null
}
