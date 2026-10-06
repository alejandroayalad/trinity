/**
 * Display forms for identifiers (spec R21).
 *
 * The API uses UUIDs for publications, versions and runs. The screens show the
 * first 8 characters in mono and keep the full value available. A run also
 * has a sequence number, run_seq, shown as "Run #N".
 */

/** "4f1c2a9e-1111-4222-8333-444455556666" gives "4f1c2a9e". */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

/** run_seq "1044" gives "Run #1044". The counter stays text; it is never converted. */
export function runLabel(runSeq: string): string {
  return `Run #${runSeq}`
}
