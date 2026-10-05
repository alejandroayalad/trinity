# Publication proposal

Date: October 4, 2026. Mode: proposal only.

[ME] Alayala requested `proposal.md` for Publication while another agent continues
Refresh Task 5 in the same checkout.

[YOU] Inspected baseline `4ce9a8f`, the Refresh handoff, registration source,
publication readers and canonical A9/A16/A19/A20/A22/A23 contracts. Created
[the separate Publication proposal](../../sdd/publication/proposal.md), preserving
the existing Build Refresh proposal and active implementation.

The proposal covers automatic/approved publication, durable dispatch, atomic
activation, retry/discard and reader acceptance. Setup, scheduler, refresh recovery
commands and retained deployment remain explicitly separate. Approval advances the
specification gate only; implementation is not authorized by this drafting request.

Checks: all nine proposal local link targets exist; proposal whitespace and tracked
`git diff --check` passed. No runtime test, service, migration or cloud operation ran.
Later status inspection showed concurrent Task 5 edits and a new 0007 migration;
those belong to the other agent and were not modified. The proposal requires using
the actual final migration head rather than assigning a competing revision now.

Done: proposal drafted. Pending: user review and subsequent specification/design.
Blocker to implementation: separate authorization and verified Task 5 handoff.
Next: [ME] review the Publication proposal.
