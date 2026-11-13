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
const { execSync, execFileSync, spawnSync } = require('child_process');

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

  // 1. scripts + templates + model registry -> ~/.tq-forge/install/
  console.log(`\nInstalling support files → ${c.dim(INSTALL_DIR)}`);
  fs.mkdirSync(INSTALL_DIR, { recursive: true });
  for (const sub of ['scripts', 'templates', 'config']) {
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
    // Argument array, no shell: paths with spaces or shell characters stay literal.
    const out = execFileSync(
      'bash',
      [path.join(INSTALL_DIR, 'scripts', 'quality-score.sh'), '--json', path.join(SKILLS_DIR, 'tq-forge')],
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

${c.bold('Forge and score')} ${c.dim('(each takes --help)')}
  scaffold    Deterministic scaffolds: skill, agent, hooks, mcp, list
  score       0-100 quality score with model-compat lint
  validate    Structural check of a skill, subagent, .mcp.json or settings.json

${c.bold('Context optimizer')} ${c.dim('(dry run unless --apply; restore undoes it)')}
  measure       Estimate the always-loaded context of the current project
  optimize      Lossless: keep MCP servers with deferred tools, move long skill bodies and
                CLAUDE.md prose to on-demand files ${c.dim('(--isolate-mcp, --description-limit 160 trade capability)')}
  optimize-mcp / optimize-skills   Run one part of optimize
  auto-improve  optimize, plus usage- and score-driven fixes ${c.dim('(--root ~ for your user setup)')}
  shield        claudeMdExcludes, soaker subagents and a one-line hygiene note
  restore       Put back the files an --apply run changed ${c.dim('(--outside, --discard-edits)')}

${c.bold('Mods')} ${c.dim('(signal-driven hooks; install is a dry run unless --apply)')}
  mods install  Install the hooks, /savings, /switchboard, /handoff, /keep-warm ${c.dim('(--root ~)')}
  mods status | savings            What is on, and what each mod has saved
  mods toggle <mod> <on|off|haiku|sonnet>
  keep-warm     When the prompt cache goes cold ${c.dim('(--ttl 55m|4m, --wait)')}
  retrieve <ccr_id>   The full text behind a CCR id ${c.dim('(--lines A:B, --search KW)')}

${c.bold('Learn')} ${c.dim('(sandbox only unless --apply)')}
  learn <url-or-query>   Turn a video, repository or page into a skill
  scout <topic>          Research a topic ${c.dim('(--sources youtube,github,social,web)')}

${c.bold('Models')} ${c.dim('(dry run unless --apply)')}
  sync-models   Detect new Claude models; update the registry and pinned model ids

${c.bold('Options')}
  --force     Overwrite skills that already exist (install)

${c.bold('Env')}
  TQ_FORGE_HOME      State home   ${c.dim('(default ~/.tq-forge)')}
  CLAUDE_SKILLS_DIR  Skills dir   ${c.dim('(default ~/.claude/skills)')}

${c.dim('https://github.com/tanishq286/tq-forge')}
`);
}

// Subcommands that hand their arguments to a bundled script unchanged.
// Each entry: [script in scripts/, arguments placed before the user's].
const PASS_THROUGH = {
  scaffold: ['scaffold.sh', []],
  score: ['quality-score.sh', []],
  validate: ['dry-test.sh', []],
  measure: ['optimize.sh', ['measure']],
  optimize: ['optimize.sh', ['optimize']],
  'optimize-mcp': ['optimize.sh', ['optimize', '--only', 'mcp']],
  'optimize-skills': ['optimize.sh', ['optimize', '--only', 'skills,rules']],
  shield: ['optimize.sh', ['shield']],
  restore: ['optimize.sh', ['restore']],
  'auto-improve': ['auto-improve.sh', []],
  'sync-models': ['sync-models.sh', []],
  mods: ['mods.sh', []],
  'keep-warm': ['mods.sh', ['keep-warm']],
  learn: ['learn.sh', ['learn']],
  scout: ['learn.sh', ['scout']],
};

function runScript(script, scriptArgs) {
  // spawnSync with an argument array: nothing the user typed reaches a shell.
  const result = spawnSync('bash', [path.join(PKG_ROOT, 'scripts', script), ...scriptArgs], {
    stdio: 'inherit',
  });
  if (result.error) {
    console.error(c.r(`Could not run ${script}: ${result.error.message}`));
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

const CCR_ID = /^[a-f0-9]{12}$/;
const LINE_RANGE = /^\d+:\d+$/;
const RETRIEVE_USAGE = 'Usage: tq-forge retrieve <ccr_id> [--lines A:B] [--search KW]';
const EXIT_USAGE = 2;

/**
 * Parse `retrieve` arguments. Returns { id, lines, search } or { error }.
 * @param {string[]} args
 * @returns {{ id?: string, lines?: string, search?: string, error?: string }}
 */
function parseRetrieveArgs(args) {
  const parsed = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--lines' || arg === '--search') {
      const value = args[++i];
      if (value === undefined) return { error: `${arg} needs a value` };
      parsed[arg.slice(2)] = value;
    } else if (arg.startsWith('--lines=') || arg.startsWith('--search=')) {
      const cut = arg.indexOf('=');
      parsed[arg.slice(2, cut)] = arg.slice(cut + 1);
    } else if (arg.startsWith('-')) {
      return { error: `unknown option ${arg}` };
    } else if (parsed.id !== undefined) {
      return { error: 'only one CCR id is accepted' };
    } else {
      parsed.id = arg;
    }
  }
  if (parsed.id === undefined) return { error: 'a CCR id is required' };
  if (!CCR_ID.test(parsed.id)) return { error: 'a CCR id is 12 lowercase hex characters' };
  if (parsed.lines !== undefined && !LINE_RANGE.test(parsed.lines)) {
    return { error: '--lines takes START:END, for example 10:40' };
  }
  return parsed;
}

function retrieve(args) {
  if (args.includes('--help') || args.includes('-h')) {
    console.log(`${RETRIEVE_USAGE}\n\nPrint the full text behind a CCR id that the input-router left in a tool result.`);
    return;
  }
  const parsed = parseRetrieveArgs(args);
  if (parsed.error) {
    console.error(c.r(`retrieve: ${parsed.error}`));
    console.error(RETRIEVE_USAGE);
    process.exit(EXIT_USAGE);
  }
  // Validated values in an argument array: nothing the user typed reaches a shell or a file path.
  const scriptArgs = [path.join(PKG_ROOT, 'scripts', 'lib', 'ccr_engine.py'), parsed.id];
  if (parsed.lines !== undefined) scriptArgs.push('--lines', parsed.lines);
  if (parsed.search !== undefined) scriptArgs.push(`--search=${parsed.search}`);
  const result = spawnSync(have('python3') ? 'python3' : 'python', scriptArgs, {
    stdio: 'inherit',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  });
  if (result.error) {
    console.error(c.r(`Could not run python3: ${result.error.message}`));
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

function main() {
  const args = process.argv.slice(2);
  if (args[0] === 'retrieve') return retrieve(args.slice(1));
  if (Object.prototype.hasOwnProperty.call(PASS_THROUGH, args[0])) {
    const [script, prefix] = PASS_THROUGH[args[0]];
    return runScript(script, [...prefix, ...args.slice(1)]);
  }
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
