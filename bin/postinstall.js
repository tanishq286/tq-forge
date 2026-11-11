#!/usr/bin/env node
/**
 * tq-forge postinstall.
 *
 * Prints how much context the user's ~/.claude setup loads on every turn and
 * the one command that trims it. It only reads files, makes no network call,
 * waits at most a few seconds, and exits 0 whatever happens, so it can never
 * fail or stall an install.
 *
 * Skipped in CI and when TQ_FORGE_SKIP_POSTINSTALL is set. npm hides lifecycle
 * output unless it runs with --foreground-scripts; `npx tq-forge measure --root ~`
 * prints the same number on demand.
 */

'use strict';

const MEASURE_TIMEOUT_MS = 5000;
const COMMAND = 'npx tq-forge auto-improve --root ~ --apply';

function currentBloat() {
  const fs = require('fs');
  const os = require('os');
  const path = require('path');
  const { spawnSync } = require('child_process');

  const home = os.homedir();
  if (!fs.existsSync(path.join(home, '.claude'))) return null;
  const script = path.join(__dirname, '..', 'scripts', 'lib', 'optimize.py');
  const result = spawnSync('python3', [script, 'measure', '--root', home], {
    encoding: 'utf8',
    timeout: MEASURE_TIMEOUT_MS,
    stdio: ['ignore', 'pipe', 'ignore'],
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  });
  if (result.status !== 0) return null;
  const tokens = JSON.parse(result.stdout).estimated_tokens;
  return Number.isInteger(tokens) ? tokens : null;
}

try {
  if (!process.env.CI && !process.env.TQ_FORGE_SKIP_POSTINSTALL) {
    const tokens = currentBloat();
    const found =
      tokens === null
        ? 'tq-forge: installed.'
        : `tq-forge: your ~/.claude setup loads about ${tokens.toLocaleString('en-US')} tokens on every turn (estimate).`;
    console.log(`\n${found}\n  Preview a trim:  ${COMMAND.replace(' --apply', '')}\n  Apply it:        ${COMMAND}\n`);
  }
} catch {
  // An install must never fail because of this message.
}
