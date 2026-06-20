import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    // Mirror the `@` alias from tsconfig.json so tests that transitively
    // import components (e.g. SmallcapChip → Chip) can resolve the path.
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    // Pure-function contract tests — no DOM needed.
    environment: 'node',
    // Include test files colocated with source or under __tests__/.
    include: ['**/*.test.ts', '**/*.test.tsx'],
    // Exclude Next.js build artefacts and node_modules.
    exclude: ['node_modules', '.next', 'coverage'],
  },
});
