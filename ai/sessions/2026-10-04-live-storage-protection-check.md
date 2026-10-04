# Live storage protection check — partial

Date: 2026-10-04. Tested source: `fde733b` on `main`.

## Scope and contributions

[ME] Alayala requested testing the existing EIA → Parquet → validation → S3 flow, supplied a gated execution plan, requested a local `.env`, and requested continuation after filling it in. [YOU] AI checked the baseline, Python writer identity and synthetic S3 operations. No connector or storage implementation was added. A9/A14/A16 retain validation and unpublished-candidate boundaries; maintain data evidence — ongoing.

The initially clean checkout was fast-forwarded from `4afac5d` to `fde733b`. The baseline passed 32 storage tests, 18 preparation tests and the full suite: 245 discovered, 220 passed, 25 opt-in PostgreSQL checks skipped. These used the existing `backend/.venv/bin/python`; `uv` was absent. No fresh locked install was performed.

Python identity initially failed with `MissingDependencyException`. AI installed only `awscrt==0.36.0` into the existing virtual environment, the exact optional CRT requirement declared by installed Botocore. This is a local diagnostic supplement, not a lockfile change or a reproducible locked installation. The 32 storage tests passed again after installation. Python STS then confirmed the assumed `trinity-writer` role, with static AWS credential environment variables removed from that process.

AI created ignored `backend/.env` with mode `0600`, an empty key field, and the existing destination/profile settings. Alayala supplied the key locally. Continuation checked only whether required values were set; no secret values were printed or retained in evidence. The application still does not load `.env` automatically.

## Observed live object checks

Destination: `s3://trinity-alayala-dev-01/private/candidates/0df76da1-6cc6-4dbb-92fb-89517aaa3d24/synthetic-protection-probe.txt`, region `us-east-1`. This is a new synthetic namespace, not a real candidate. Only a 66-byte probe was created. It remains in place.

| Check | Observed result |
|---|---|
| Direct `PutObject` with `IfNoneMatch="*"` | HTTP 200. |
| Exact `GetObject` readback | 66 bytes; SHA-256 `b2277d597aaa80b92e13968235d8f00a184baa92484f67b7cdf8946b8a6b611e`. |
| Second direct conditional PUT with different bytes | HTTP 412 `PreconditionFailed`; original bytes unchanged. |
| PUT without condition | HTTP 403 `AccessDenied`; original bytes unchanged. |
| Unsigned GET of the known object | HTTP 403 `AccessDenied`. |
| Writer `DeleteObject` | HTTP 403 `AccessDenied`; original bytes unchanged. |

The probe used direct SDK operations with bounded connection/read timeouts and one total attempt. It stopped on an unexpected result. No existing candidate was overwritten or deleted. Sanitized local receipt: `backend/artifacts/live-protection-0df76da1-6cc6-4dbb-92fb-89517aaa3d24/result.json` (ignored local evidence). Adapter reuse behavior remains covered by offline tests; it was not independently tested live here.

## Remaining gate and evidence limits

Read-only operator inspection through `trinity-local` returned `AccessDenied` for `GetPublicAccessBlock`, `GetBucketPolicyStatus`, `GetBucketLifecycleConfiguration`, `GetBucketVersioning` and `GetBucketPolicy`. These denials prove only that this identity cannot perform those inspections. They do not prove that lifecycle deletion is absent, that version deletion is forbidden, or that all policy-changing rights are absent. Writer permissions were not broadened and no AWS configuration was changed.

Gate 0 passed in the existing environment. Python writer identity and local settings are ready. Gate 2 object probes passed, but deployed-policy/lifecycle review remains incomplete. Gates 3–5 did not run: no new EIA request, real preparation candidate, independent stored-candidate verification or publication occurred. No commit or push was requested or performed. Existing anomaly findings remain unchanged.

## Operator evidence supplied after the probes

[ME] Alayala supplied a console screenshot identifying `trinity-alayala-dev-01` and showing no lifecycle rules. He then pasted the bucket policy statements. [YOU] AI reviewed that supplied evidence separately from the denied SDK inspection.

The supplied `DenyCandidateWritesWithoutIfNoneMatch` statement denies `s3:PutObject` on `private/candidates/*` when the conditional header is absent and `s3:ObjectCreationOperation` is true. This agrees with the observed unconditional PUT denial and [AWS's documented conditional-write enforcement](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html). `DenyCandidateDeletion` denies both `s3:DeleteObject` and `s3:DeleteObjectVersion` for all principals on that prefix. Version-delete protection is supported by policy inspection, not a direct version-delete probe. The screenshot supports absence of lifecycle rules at the time captured, not a new successful SDK read.

Remaining: confirm that `trinity-writer` cannot change the bucket protections. AI attempted `ListRolePolicies` and `ListAttachedRolePolicies` through `trinity-local`; both returned `AccessDenied`. These inspection failures do not establish the writer's effective permissions. No permissions were changed and gates 3–5 remain unexecuted.

## Subsequent gate progress

Alayala supplied a writer permission policy allowing only `s3:GetObject` and `s3:PutObject` on the candidate prefix. Based on the supplied policies, console evidence and live probes, gate 2 was accepted with the stated assumption that this is the writer's only permission policy. Its lack of policy-management grants was inspected; no destructive policy-modification probe was attempted.

Alayala's screenshot confirms gate 3: both existing EIA live tests passed in 5.537 seconds. His first preparation failed on a valid leading-decimal percentage. The authorized correction and new-version retry are recorded in the [parser-fix session](2026-10-04-leading-decimal-parser-fix.md). Gate 4 remains blocked by missing October 3 data, and gate 5 remains pending. Earlier pending statements above describe their time of observation.

Next: [ME] decide whether to verify the available October 1–2 window separately.

Subsequent action: alayala authorized October 1–2. Gates 4–5 passed for that separate window: all required checks, stored unpublished candidate and fresh-process verification of all 50 remote objects. See the [final session](2026-10-04-october-1-2-live-preparation.md). This does not change the earlier three-day coverage failure or the permission-review evidence boundaries.
