/**
 * One automatic retry rule for analytical reads.
 *
 * The server admits two active analytical requests per user and 30 attempts
 * per minute. A burst of clicks can still reach the rate limit, and the server
 * answers with `429 rate_limited` and a `Retry-After` header. This rule retries
 * that one response when the wait is short. Every other failure waits for the
 * user, because a blind retry would spend the per-minute budget.
 */
import { isApiError } from './client'

/**
 * The longest Retry-After the client waits automatically. A longer wait is
 * left to the user's Retry button. For example, "1" retries once after one
 * second; "30" does not retry and shows the error.
 */
export const AUTO_RETRY_MAX_AFTER_SECONDS = 5

/**
 * Decide whether React Query retries a failed query. Retry at most once
 * (failureCount counts the failures so far), and only for a `429 rate_limited`
 * response that names a wait of 5 seconds or less.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1 || !isApiError(error, 'rate_limited')) return false
  return error.retryAfter !== null && error.retryAfter <= AUTO_RETRY_MAX_AFTER_SECONDS
}

/**
 * Wait exactly as long as the server asked. React Query calls this only after
 * `shouldRetry` returned true, so `retryAfter` is a bounded whole number.
 */
export function retryDelay(_attemptIndex: number, error: unknown): number {
  return isApiError(error, 'rate_limited') && error.retryAfter !== null ? error.retryAfter * 1000 : 1000
}
