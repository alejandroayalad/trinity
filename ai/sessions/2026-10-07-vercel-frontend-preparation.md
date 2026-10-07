# Vercel frontend preparation

Mode: deployment preparation. References: A26 frontend stack, A28 EC2 hosting.

- [ME] Alayala asked to move toward frontend deployment on Vercel and signed in.
- [YOU] Prepared frontend build settings, an HTTPS API rewrite to the existing
  EC2 origin, no-store API headers, and a React fallback excluding API/assets.
- [YOU] Preserved existing changes in NOTES.md, docs/schema.md, and the schema
  readability session. No application/authentication or dependency change.

Browser input `/api/v1/me` is forwarded to EC2 with the same API path. A page
URL loads React. API errors must remain API responses; missing hashed assets
must remain 404. Vercel runtime verification is pending.

Checks: JSON parsing and fallback examples checked locally; diff whitespace
checked. [ME] Ran `npm --prefix frontend run build`; the supplied October 7
07:49 screenshot shows Vite 8.3.2 built 208 modules and the bundle-content check
passed. This is user-run local build evidence, not Vercel runtime evidence.
At the preparation checkpoint, no commit or push had been performed. Vercel
deployment and authenticated browser checks remain pending.
Node 24.x is available on Vercel, but its
managed patch version has not been compared with the exact repository pin.

Sources: https://vercel.com/docs/project-configuration/vercel-json and
https://vercel.com/docs/functions/runtimes/node-js/node-js-versions .

Open boundaries: Vercel must receive the local configuration before a Git-based
deployment; the EC2 IP is unreserved. A28 remains the deployed configuration.
[ME] Authorized commit and push, including the existing schema documentation.
[YOU] Reviewed both slices for separate commits and verified main matched the
freshly fetched origin/main before delivery.
Next action: [ME] import Trinity in Vercel with Root Directory `frontend`.
