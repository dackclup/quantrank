import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Pure-function contract tests — no DOM needed.
    environment: 'node',
    // Include test files colocated with source or under __tests__/.
    include: ['**/*.test.ts', '**/*.test.tsx'],
    // Exclude Next.js build artefacts and node_modules.
    exclude: ['node_modules', '.next', 'coverage'],
  },
});
