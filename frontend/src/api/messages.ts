/**
 * Safe user messages for API error codes (spec R59).
 *
 * The backend sends a stable `code` and a generic `detail` (the HTTP status
 * phrase). Screens therefore show the message for the code. An unknown code
 * shows the generic message with the request ID, so support can trace it.
 * No message contains raw response text, SQL text or a stack trace.
 */
import { ApiError } from './client'

const MESSAGES: Record<string, string> = {
  invalid_credentials: 'Account or password is incorrect.',
  auth_unavailable: 'Sign-in is unavailable. Try again later.',
  authentication_required: 'Your session ended. Sign in again.',
  invalid_session: 'Your session ended. Sign in again.',
  forbidden: 'Your account does not have access to this action.',
  resource_not_found: 'This item was not found.',
  dataset_not_found: 'This dataset does not exist or is not available to your account.',
  data_unavailable: 'Nothing to show yet. An admin still needs to publish the first set of data.',
  publication_changed: 'The data was updated. The table restarted from the first page.',
  invalid_cursor: 'This page link is no longer valid. Start again from the first page.',
  invalid_request: 'The request was not accepted. Check the values and try again.',
  invalid_json: 'The request was not accepted. Check the values and try again.',
  request_too_large: 'The request is too large.',
  sql_not_allowed:
    'This query is not allowed. Use one read-only SELECT on national_outages, facility_outages or generator_outages.',
  query_failed: 'The query could not run. Check the column names and value types.',
  query_timeout: 'The query took longer than 30 seconds and was stopped. Add filters or a LIMIT. Your SQL is kept.',
  query_resource_limit: 'The query needed more memory or output than allowed. Add filters or a LIMIT. Your SQL is kept.',
  setup_required: 'Complete the initial setup first.',
  refresh_blocked: 'A refresh cannot start now. Resolve the current run first.',
  action_not_allowed: 'This action is not allowed in the current state. Reload the page.',
  candidate_ineligible: 'This candidate cannot take that action now. Reload the page.',
  idempotency_conflict: 'This action was already sent with different details. Reload the page and try again.',
  idempotency_key_required: 'The action was sent without its tracking key. Try again.',
  precondition_required: 'The page data is out of date. Reload and try again.',
  revision_mismatch: 'This item changed in another session. Reload it and try again.',
  dependency_unavailable: 'A required service is unavailable. Try again later.',
  network_error: 'The server did not respond. Check that the local API is running, then try again.',
}

/** Return the safe message for an error. Rate limits include the wait time. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Reload the page and try again.'
  if (error.code === 'rate_limited') {
    return error.retryAfter === null
      ? 'Too many requests. Wait a moment and try again.'
      : `Too many requests. Try again in ${error.retryAfter} seconds.`
  }
  const known = MESSAGES[error.code]
  if (known !== undefined) return known
  return error.requestId === null
    ? 'Something went wrong. Try again.'
    : `Something went wrong. Request ID: ${error.requestId}.`
}
