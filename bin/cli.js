#!/usr/bin/env node
/**
 * tq-forge installer CLI.
 *
 * Installs the tq-forge skills into Claude Code's user skills dir and the
 * support scripts/templates into the state home, so the skills resolve their
 * scripts whether or not they were loaded as a native plugin.
 *
 * Pure Node stdlib — no dependencies.
 *
 * Commands:
 *   npx tq-forge install     copy skills + scripts, seed state, check deps
 *   npx tq-forge uninstall   remove installed skills + scripts (keeps your data)
 *   npx tq-forge doctor      verify the install and dependencies
 *   npx tq-forge --version   print version
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync } = require('child_process');

const PKG_ROOT = path.resolve(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(PKG_ROOT, 'package.json'), 'utf8'));

const HOME = os.homedir();
const TQ_HOME = process.env.TQ_FORGE_HOME || path.join(HOME, '.tq-forge');
const INSTALL_DIR = path.join(TQ_HOME, 'install'); // scripts + templates land here
const SKILLS_DIR = process.env.CLAUDE_SKILLS_DIR || path.join(HOME, '.claude', 'skills');

const c = {
  g: (s) => `\x1b[32m${s}\x1b[0m`,
  y: (s) => `\x1b[33m${s}\x1b[0m`,
  r: (s) => `\x1b[31m${s}\x1b[0m`,
  b: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function have(cmd) {
  try {
    execSync(process.platform === 'win32' ? `where ${cmd}` : `command -v ${cmd}`, {
      stdio: 'ignore',
      shell: true,
    });
    return true;
  } catch {
    return false;
  }
}

function listSkillDirs() {
  const skillsSrc = path.join(PKG_ROOT, 'skills');
  if (!fs.existsSync(skillsSrc)) return [];
  return fs
    .readdirSync(skillsSrc, { withFileTypes: true })
    .filter((d) => d.isDirectory() && fs.existsSync(path.join(skillsSrc, d.name, 'SKILL.md')))
    .map((d) => d.name);
}

function checkDeps() {
  const bash = have('bash');
  const py = have('python3') || have('python');
  console.log(`  ${bash ? c.g('✓') : c.r('✗')} bash`);
  console.log(`  ${py ? c.g('✓') : c.r('✗')} python3`);
  return bash && py;
}

function seedState() {
  fs.mkdirSync(path.join(TQ_HOME, 'sandbox', 'forged-skills'), { recursive: true });
  fs.mkdirSync(path.join(TQ_HOME, 'sandbox', 'forged-agents'), { recursive: true });
  const log = path.join(TQ_HOME, 'skill-log.json');
  const queue = path.join(TQ_HOME, 'forge-queue.json');
  const ctx = path.join(TQ_HOME, 'context.md');
  if (!fs.existsSync(log)) fs.writeFileSync(log, '[]\n');
  if (!fs.existsSync(queue)) fs.writeFileSync(queue, '{"queue":[],"needs_manual_review":[]}\n');
  if (!fs.existsSync(ctx)) {
    fs.writeFileSync(
      ctx,
      '# Domain context\n\n' +
        'Replace this with the context your forged agents need: who you are, what\n' +
        'you build, your customers, the inputs/outputs your agents work with, and\n' +
        "any hard rules (\"never fabricate numbers\").\n\n" +
        'Injected into every forged agent wherever the `{{CONTEXT}}` token appears.\n'
    );
  }
}

function install({ force }) {
  console.log(c.bold('\n🔨 tq-forge installer\n'));

  console.log('Checking dependencies:');
  if (!checkDeps()) {
    console.log(
      c.r('\n✗ Missing bash or python3.') +
        ' tq-forge needs both at runtime. Install them and re-run.\n'
    );
    process.exit(1);
  }

  // 1. scripts + templates -> ~/.tq-forge/install/
  console.log(`\nInstalling support files → ${c.dim(INSTALL_DIR)}`);
  fs.mkdirSync(INSTALL_DIR, { recursive: true });
  for (const sub of ['scripts', 'templates']) {
    const src = path.join(PKG_ROOT, sub);
    const dst = path.join(INSTALL_DIR, sub);
    fs.rmSync(dst, { recursive: true, force: true });
    fs.cpSync(src, dst, { recursive: true });
  }
  // make scripts executable
  for (const f of fs.readdirSync(path.join(INSTALL_DIR, 'scripts'))) {
    if (f.endsWith('.sh')) {
      try {
        fs.chmodSync(path.join(INSTALL_DIR, 'scripts', f), 0o755);
      } catch {}
    }
  }
  console.log(`  ${c.g('✓')} scripts + templates`);

  // 2. skills -> ~/.claude/skills/
  console.log(`\nInstalling skills → ${c.dim(SKILLS_DIR)}`);
  fs.mkdirSync(SKILLS_DIR, { recursive: true });
  const skills = listSkillDirs();
  let installed = 0,
    skipped = 0;
  for (const name of skills) {
    const dst = path.join(SKILLS_DIR, name);
    if (fs.existsSync(dst) && !force) {
      console.log(`  ${c.y('•')} ${name} ${c.dim('(exists — skipped, use --force to overwrite)')}`);
      skipped++;
      continue;
    }
    fs.rmSync(dst, { recursive: true, force: true });
    fs.cpSync(path.join(PKG_ROOT, 'skills', name), dst, { recursive: true });
    installed++;
  }
  console.log(`  ${c.g('✓')} ${installed} installed${skipped ? c.dim(`, ${skipped} skipped`) : ''}`);

  // 3. seed state home
  console.log(`\nSeeding state → ${c.dim(TQ_HOME)}`);
  seedState();
  console.log(`  ${c.g('✓')} sandbox, skill-log.json, forge-queue.json, context.md`);

  console.log(c.g('\n✓ Installed.\n'));
  console.log('Next steps:');
  console.log(`  1. ${c.b('Restart Claude Code')} (or reload skills) so it picks up the new commands.`);
  console.log(`  2. Edit ${c.dim(path.join(TQ_HOME, 'context.md'))} with your domain (used by agents).`);
  console.log(`  3. In Claude Code, run ${c.b('/tq-forge a skill that <does something>')}.`);
  console.log(`\nVerify any time with: ${c.b('npx tq-forge doctor')}\n`);
}

function uninstall() {
  console.log(c.bold('\n🧹 tq-forge uninstall\n'));
  const skills = listSkillDirs();
  let removed = 0;
  for (const name of skills) {
    const dst = path.join(SKILLS_DIR, name);
    if (fs.existsSync(dst)) {
      fs.rmSync(dst, { recursive: true, force: true });
      removed++;
    }
  }
  fs.rmSync(INSTALL_DIR, { recursive: true, force: true });
  console.log(`  ${c.g('✓')} removed ${removed} skills and support files`);
  console.log(
    `\n${c.y('Note:')} your data in ${c.dim(TQ_HOME)} (sandbox, logs, context.md) was kept.`
  );
  console.log(`Delete it manually if you want a clean slate: ${c.dim(`rm -rf ${TQ_HOME}`)}\n`);
}

function doctor() {
  console.log(c.bold('\n🩺 tq-forge doctor\n'));
  console.log('Dependencies:');
  const deps = checkDeps();

  console.log('\nInstall locations:');
  const scriptsOk = fs.existsSync(path.join(INSTALL_DIR, 'scripts', 'common.sh'));
  const skills = listSkillDirs();
  const present = skills.filter((n) => fs.existsSync(path.join(SKILLS_DIR, n, 'SKILL.md')));
  console.log(`  ${scriptsOk ? c.g('✓') : c.r('✗')} support scripts at ${c.dim(INSTALL_DIR)}`);
  console.log(
    `  ${present.length === skills.length ? c.g('✓') : c.y('•')} ${present.length}/${skills.length} skills in ${c.dim(SKILLS_DIR)}`
  );

  // functional smoke test: score one bundled skill
  let scorerOk = false;
  try {
    const out = execSync(
      `bash ${JSON.stringify(path.join(INSTALL_DIR, 'scripts', 'quality-score.sh'))} --json ${JSON.stringify(path.join(SKILLS_DIR, 'tq-forge'))}`,
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }
    );
    scorerOk = JSON.parse(out).average >= 7;
  } catch {}
  console.log(`  ${scorerOk ? c.g('✓') : c.y('•')} scorer runs (scored bundled /tq-forge)`);

  const healthy = deps && scriptsOk && present.length === skills.length && scorerOk;
  console.log(
    healthy
      ? c.g('\n✓ Healthy. Run /tq-forge inside Claude Code.\n')
      : c.y('\n• Not fully installed. Run: npx tq-forge install\n')
  );
  process.exit(healthy ? 0 : 1);
}

function help() {
  console.log(`
${c.bold('tq-forge')} — autonomous skill + agent factory for Claude Code
${c.dim('v' + pkg.version)}

${c.bold('Usage')}
  npx tq-forge <command>

${c.bold('Commands')}
  install     Install skills + scripts and seed state ${c.dim('(default)')}
  uninstall   Remove installed skills + scripts ${c.dim('(keeps your data)')}
  doctor      Verify the install and dependencies
  help        Show this help

${c.bold('Options')}
  --force     Overwrite skills that already exist (install)

${c.bold('Env')}
  TQ_FORGE_HOME      State home   ${c.dim('(default ~/.tq-forge)')}
  CLAUDE_SKILLS_DIR  Skills dir   ${c.dim('(default ~/.claude/skills)')}

${c.dim('https://github.com/tanishq286/tq-forge')}
`);
}

function main() {
  const args = process.argv.slice(2);
  const cmd = args.find((a) => !a.startsWith('-')) || 'install';
  const force = args.includes('--force') || args.includes('-f');

  if (args.includes('--version') || args.includes('-v') || cmd === 'version') {
    console.log(pkg.version);
    return;
  }
  if (args.includes('--help') || args.includes('-h') || cmd === 'help') return help();

  switch (cmd) {
    case 'install':
      return install({ force });
    case 'uninstall':
    case 'remove':
      return uninstall();
    case 'doctor':
    case 'check':
      return doctor();
    default:
      console.log(c.r(`Unknown command: ${cmd}`));
      help();
      process.exit(1);
  }
}

main();
