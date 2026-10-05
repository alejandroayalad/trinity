import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import { exactNumberRules } from './eslint.numeric-rules.js'

export default defineConfig([
  // The lint probe contains banned code on purpose; src/lint.test.ts lints it.
  globalIgnores(['dist', 'coverage', 'playwright-report', 'test-results', 'blob-report', 'src/test/lint-probe']),
  {
    // Type-aware rules catch unsafe `any` values and unhandled promises.
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, tseslint.configs.recommendedTypeChecked, reactHooks.configs.flat.recommended],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  // Ban float conversions everywhere in the application source, and ban
  // console output so no token, password or response body reaches a log.
  { files: ['src/**/*.{ts,tsx}'], ...exactNumberRules },
  { files: ['src/**/*.{ts,tsx}'], rules: { 'no-console': 'error' } },
  {
    // Only the decimal helper tests may build floats, to show the failure they prevent.
    files: ['src/lib/**/*.test.ts'],
    rules: { 'no-restricted-globals': 'off', 'no-restricted-properties': 'off', 'no-restricted-syntax': 'off' },
  },
  {
    files: ['**/*.{js,mjs}'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
])
