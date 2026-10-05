// Check the production build for content that must never ship (spec S26).
//
// The build must not contain prototype controls, synthetic fixture values or
// local test identities. A match fails the build with the file and marker,
// never with surrounding text, so no secret-like value is printed.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const FORBIDDEN = [
  'Continue as',
  'Illustrative data',
  'PROTOTYPE',
  'user_example_',
  '00000000-0000-4000-8000-',
  'synthetic-test-password',
]

function files(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

const problems = []
for (const path of files('dist')) {
  if (!/\.(html|js|css|json|txt|map)$/.test(path)) continue
  const text = readFileSync(path, 'utf8')
  for (const marker of FORBIDDEN) {
    if (text.includes(marker)) problems.push(`${path}: contains "${marker}"`)
  }
}

if (problems.length > 0) {
  console.error(`Build check failed:\n${problems.join('\n')}`)
  process.exit(1)
}
console.log('Build check passed: no prototype controls, fixtures or test identities in dist/.')
