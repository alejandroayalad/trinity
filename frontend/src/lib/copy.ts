/**
 * Visible sentences for API codes and enum values (spec UF-X01).
 *
 * The API sends stable machine values such as `review_required` or
 * `awaiting_approval`. Screens never show those values. Each typed Record
 * below maps every value to a short sentence, so TypeScript fails when the
 * contract adds a value that has no text. An unknown value at run time gets
 * a general sentence; the raw code stays only in the network response.
 */
import type { BlockCode, Candidate, Role, RunStatus, StepStage, StepStatus } from '../api/types'
import type { Tone } from '../components/feedback/StatusBadge'

export const ROLE_LABELS: Record<Role, string> = { viewer: 'Viewer', analyst: 'Analyst', admin: 'Admin' }

/** The sentence for a code that this build does not know. */
export const GENERIC_REASON = 'This action is not available now.'

/** Why an action such as "Start refresh" is disabled (spec UF-X10). */
export const BLOCK_REASONS: Record<BlockCode, string> = {
  setup_required: 'Complete the initial setup first.',
  schedule_disabled: 'The daily schedule is off.',
  refresh_active: 'A run is already in progress.',
  review_required: 'Resolve the candidate awaiting review first.',
  publication_in_progress: 'A publication is in progress. Wait for it to finish.',
  failure_unresolved: 'The last run failed. Run again or resolve its warning first.',
  candidate_ineligible: 'This candidate cannot take that action now.',
  candidate_discarded: "This candidate was discarded. It can't be brought back.",
  candidate_superseded: 'A newer candidate replaced this one.',
  already_published: 'This candidate is already published.',
  no_unresolved_warning: 'There is no unresolved warning.',
  not_applicable: 'This action does not apply now.',
  dependency_unavailable: 'A required service is unavailable. Try again later.',
}

/**
 * Return the sentence for a block code. `null` means the server gave no
 * reason, so the general sentence is used. An unknown code also gets the
 * general sentence instead of the raw code.
 */
export function blockReason(code: string | null | undefined): string {
  return (code !== null && code !== undefined && Object.hasOwn(BLOCK_REASONS, code)) ? BLOCK_REASONS[code as BlockCode] : GENERIC_REASON
}

/** Badge look and the one-sentence summary for each run status (spec R48, UF-R05, UF-X10). */
export const RUN_STATUS: Record<RunStatus, { tone: Tone; glyph: string; label: string; summary: string }> = {
  requested: { tone: 'running', glyph: '◐', label: 'Running', summary: 'In progress. The current publication stays up.' },
  running: { tone: 'running', glyph: '◐', label: 'Running', summary: 'In progress. The current publication stays up.' },
  awaiting_approval: { tone: 'warning', glyph: '!', label: 'Awaiting review', summary: 'Checks are done. Waiting for review.' },
  publishing: { tone: 'running', glyph: '◐', label: 'Publishing', summary: 'Publishing. The current publication stays up until this finishes.' },
  publication_failed: { tone: 'error', glyph: '✕', label: 'Publication failed', summary: 'Publishing failed. The current publication was not replaced.' },
  succeeded: { tone: 'success', glyph: '✓', label: 'Published', summary: 'Published.' },
  failed: { tone: 'error', glyph: '✕', label: 'Failed', summary: 'Stopped. The current publication was not replaced.' },
  discarded: { tone: 'neutral', glyph: '–', label: 'Discarded', summary: 'Candidate discarded. Nothing was published.' },
  superseded: { tone: 'neutral', glyph: '–', label: 'Superseded', summary: 'A newer run replaced this candidate. Nothing from this run was published.' },
}

/** Timeline titles. The API calls the first stage `extract`; the screens call it Retrieve. */
export const STAGE_LABELS: Record<StepStage, string> = { extract: 'Retrieve', prepare: 'Prepare', validate: 'Validate', publish: 'Publish' }

/** Words for one step attempt status, used in the attempt lines under a stage. */
export const STEP_STATUS_LABELS: Record<StepStatus, string> = {
  pending: 'Waiting',
  running: 'In progress',
  succeeded: 'Done',
  failed: 'Failed',
  abandoned: 'Stopped',
}

/** Describe the server outcome for a candidate without inferring permission to run an action. */
export function candidateCopy(candidate: Candidate): string {
  if (candidate.disposition === 'discarded' || candidate.review_status === 'discarded') return 'This candidate was discarded and cannot be published.'
  if (candidate.disposition === 'superseded') return 'This candidate was superseded and will not replace the current publication.'
  if (candidate.publication.status === 'published') return 'This candidate was published successfully.'
  if (candidate.publication.status === 'failed') return 'Publication failed. This attempt did not replace the current publication.'
  if (candidate.publication.status === 'blocked' || candidate.validation_status === 'rejected') return 'Publication is blocked. Approval cannot bypass required checks.'
  if (candidate.publication.status === 'queued' || candidate.publication.status === 'publishing') return 'Publication is in progress. The current publication stays in place until this candidate is published successfully.'
  if (candidate.review_status === 'required') return 'Review warnings require Admin approval before publication. The current publication stays in place.'
  if (candidate.review_status === 'approved') return 'Review warnings were approved. The current publication stays in place until publication succeeds.'
  if (candidate.review_status === 'not_required') return 'No review approval is required. This candidate follows automatic publication after the required checks pass.'
  return 'Validation is not complete. Approval requirements are not yet known.'
}
