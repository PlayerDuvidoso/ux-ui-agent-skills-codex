import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

test('gate entrypoint runs from paths containing spaces and non-ASCII characters', () => {
  const root = mkdtempSync(join(tmpdir(), 'codex gate 한글 '));
  try {
    const scripts = join(root, 'scripts');
    mkdirSync(scripts);
    for (const name of ['gate.mjs', 'check_no_emoji.py']) {
      copyFileSync(fileURLToPath(new URL(`../../scripts/${name}`, import.meta.url)), join(scripts, name));
    }
    const file = join(root, 'page.html');
    writeFileSync(file, '<button>Save</button>');
    const run = (...args) => spawnSync(process.execPath, [join(scripts, 'gate.mjs'), ...args], {
      cwd: root, encoding: 'utf8', env: { ...process.env, CLAUDE_PLUGIN_DATA: join(root, 'data'), CLAUDE_SESSION_ID: 'entrypoint-test' },
    });
    assert.equal(run('--check', file).status, 1, 'must not silently succeed before verification');
    const measured = run('check_no_emoji.py', file);
    assert.equal(measured.status, 0, measured.stdout + measured.stderr);
    assert.match(run('--check', file).stdout, /OK:/);
    writeFileSync(file, '<button>Continue</button>');
    const stale = run('--check', file);
    assert.equal(stale.status, 1);
    assert.match(stale.stdout, /EXPIRED/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('eval runner finds briefs under paths containing spaces and non-ASCII characters', () => {
  const root = mkdtempSync(join(tmpdir(), 'codex eval 한글 '));
  try {
    mkdirSync(join(root, 'evals', 'briefs'), { recursive: true });
    copyFileSync(fileURLToPath(new URL('../../evals/run.mjs', import.meta.url)), join(root, 'evals', 'run.mjs'));
    writeFileSync(join(root, 'evals', 'briefs', '01-probe.md'), '# Portable path probe\n');
    const result = spawnSync(process.execPath, [join(root, 'evals', 'run.mjs'), '--list'], { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Portable path probe/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
