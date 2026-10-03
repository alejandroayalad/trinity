# Session Dependency versions accepted

Date: October 3, 2026. Branch: `docs/backend-decisions-architecture`.

## Objective and contributions

[ME] Alayala approved dependency versions and requested updating decisions, committing, and pushing that change. He will review the API and security contracts separately. [YOU] AI promoted A17 to accepted and moved the exact version table into DECISIONS.md so the dependency commit stands alone without publishing the local API/security draft.

## Scope and decision references

[A17](../../DECISIONS.md#a17--dependency-versions-and-update-policy-closed) records Python, uv, package/server versions, and the lockfile/update policy. Values are unchanged from the October 3 proposal. A10–A15 and A9 remain in force. The API/security contract, SQL subset, role/session lookups, async/pool choices and limits, scheduling, and runtime isolation are not accepted by this action.

The commit includes only DECISIONS.md, README.md, AGENTS.md, NOTES.md, and this session. AI stages the dependency-specific content of shared files while preserving existing local proposal edits. No source code, installed dependency, lockfile, deployment, PR, or merge is included. The dependency decision does not assert runtime compatibility.

## Verification

Passed: reviewed the dependency-only patch; 78 local links and 19 anchors resolve against the planned commit snapshot; 16 decision IDs are unique; all 15 original package release links are preserved; fences and whitespace are valid. The commit snapshot contains no link to the unpublished API/security draft. Dependency resolution, advisory review, native-wheel checks, and runtime tests remain pending implementation. The earlier release/metadata lookup is not rerun for this acceptance; no version update is inferred from approval.

## Publication and next action

[ME] Authorized the dependency-only commit and push. [YOU] Execute on the existing branch and verify the remote branch identifies the new commit. API/security proposal edits remain local for review.

Next: [ME] Review the human overview and proposed API/security contract locally.
