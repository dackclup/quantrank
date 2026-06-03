/** @type {import('next').NextConfig} */
const { execSync } = require('node:child_process');

// Build-time version string for the sidebar chip (NEXT_PUBLIC_APP_VERSION).
// NEVER hardcode the version — it goes stale the moment main moves past the
// release tag. Precedence: explicit env override -> `git describe` (a clean
// "TAG+N" string when tags are present, e.g. local dev) -> CI/Vercel commit
// SHA (shallow clones have no tags) -> 'dev'.
function appVersion() {
  if (process.env.NEXT_PUBLIC_APP_VERSION) return process.env.NEXT_PUBLIC_APP_VERSION;
  try {
    const desc = execSync('git describe --tags --always --dirty', {
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .toString()
      .trim();
    // "v1.4.0-phase4.6-30-g5f9113b" -> "v1.4.0-phase4.6+30"; a bare SHA stays as-is.
    return desc.replace(/-(\d+)-g[0-9a-f]+(-dirty)?$/, '+$1$2');
  } catch {
    const sha = process.env.VERCEL_GIT_COMMIT_SHA || process.env.GITHUB_SHA;
    return sha ? sha.slice(0, 7) : 'dev';
  }
}

const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: true,
  env: { NEXT_PUBLIC_APP_VERSION: appVersion() },
};

module.exports = nextConfig;
