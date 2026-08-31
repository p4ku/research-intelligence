import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'
import { defineConfig } from 'eslint/config'

const eslintConfig = defineConfig([
  // Agent-local build dirs (see the multi-agent build workflow); eslint-config-next
  // only knows to ignore `.next/`.
  { ignores: ['.next-agent*/**', '.next-build/**'] },
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      '@next/next/no-img-element': 'off',
      'prefer-const': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', destructuredArrayIgnorePattern: '^_' },
      ],
    },
  },
])

export default eslintConfig
