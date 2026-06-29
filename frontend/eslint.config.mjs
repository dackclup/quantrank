// eslint-config-next@16 exports flat-config arrays natively — no FlatCompat
// shim needed (ESLint 9 dropped .eslintrc.json support; Next.js 16 removed
// the `eslint` key from next.config.js; this file is the replacement).
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

const eslintConfig = [...nextCoreWebVitals];

export default eslintConfig;
