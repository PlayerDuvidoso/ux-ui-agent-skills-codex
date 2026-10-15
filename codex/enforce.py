#!/usr/bin/env python3
"""Codex UX/UI hooks; no model calls, no project modifications."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
KIT = BASE.parent
DATA = Path(os.environ.get('UX_UI_HOOK_DATA', str(Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'ux-ui-hook-state')))
EXT = {'.html', '.htm', '.css', '.scss', '.tsx', '.jsx', '.vue', '.svelte'}
RG = shutil.which('rg')

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def identity(cwd, session):
    if not session:
        raise ValueError('Missing session_id: cannot isolate UI verification records')
    return hashlib.sha256((str(cwd) + '\0' + session).encode()).hexdigest()

def snapshot(cwd):
    if not RG:
        raise RuntimeError('ripgrep (rg) is required; install it and restart Codex')
    args = [RG, '--files', '--hidden', '-0', '-g', '!.git', '-g', '!node_modules', '-g', '!dist', '-g', '!build', '-g', '!.next', '-g', '!.codex', '-g', '!coverage']
    for ext in sorted(EXT):
        args += ['-g', '*' + ext]
    r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=15)
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr.decode(errors='replace'))
    paths = [cwd / os.fsdecode(p) for p in r.stdout.split(b'\0') if p]
    if len(paths) > 20000:
        raise RuntimeError('UI scan exceeds 20,000 files; use a narrower project root')
    return {str(p.resolve()): digest(p) for p in paths if p.is_file() and not p.is_symlink()}

def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)

def static_checks(files):
    errors = []
    for file in files:
        for gate in ['lint_hardcodes.py', 'check_no_emoji.py', 'lint_native_select.py']:
            r = subprocess.run([sys.executable, str(KIT / 'scripts' / gate), file], capture_output=True, text=True, timeout=20)
            if r.returncode:
                errors.append(f'{file}: {gate}\n{(r.stdout + r.stderr)[-2000:]}')
    return errors

def instruction(session):
    import shlex
    return ('UI changes require successful verification of the current file hashes. '
            'Use the installed UX/UI design-doctrine skill for UI work. Run: ' + shlex.join([sys.executable, str(BASE / 'enforce.py'), 'verify', '--session', session, '--files']) +
            ' <changed UI files...> -- <real validation command and arguments>. '
            'For HTML use the kit render gate (' + shlex.join(['node', str(KIT / 'scripts/gate.mjs')]) +
            ' verify_states.mjs <html>). For component sources use the project build/tests; '
            'these do not prove visual/accessibility quality. Report that limitation. '
            'Receipts require a zero exit, no SKIPPED output, and unchanged hashes. '
            'Do not use dummy success commands or manually edit verification state.')

def verify(argv):
    split = argv.index('--')
    p = argparse.ArgumentParser()
    p.add_argument('--session', required=True)
    p.add_argument('--files', nargs='+', required=True)
    opts = p.parse_args(argv[:split])
    cmd = argv[split + 1:]
    if not cmd:
        raise ValueError('A real validation command is required')
    cwd = Path.cwd().resolve()
    files = [str(Path(f).resolve()) for f in opts.files]
    if any(not Path(f).is_relative_to(cwd) or Path(f).suffix not in EXT for f in files):
        raise ValueError('Verification targets must be UI files inside the current project')
    before = {f: digest(f) for f in files}
    errors = static_checks(files)
    if errors:
        print('\n'.join(errors)); return 1
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, 'DS_REQUIRE_BROWSER': '1'})
    print(r.stdout, end=''); print(r.stderr, end='', file=sys.stderr)
    after = {f: digest(f) for f in files}
    if r.returncode or 'SKIPPED' in (r.stdout + r.stderr).upper() or before != after:
        print('Verification receipt NOT issued: command failed, skipped checks, or changed targets.', file=sys.stderr)
        return 1
    key = identity(cwd, opts.session)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = DATA / (key + '.json')
        state = read(path, {'pending': {}, 'receipts': {}})
        for file, sha in after.items():
            state['receipts'][file] = {'sha256': sha, 'command': cmd, 'at': time.time(), 'output_sha256': hashlib.sha256((r.stdout+r.stderr).encode()).hexdigest()}
        save(path, state)
    print(f'UX/UI: recorded successful verification for {len(files)} file(s).')
    return 0

def hook(payload):
    event = payload['hook_event_name']
    cwd = Path(payload.get('cwd') or os.getcwd()).resolve()
    session = str(payload.get('session_id') or '')
    key = identity(cwd, session)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = DATA / (key + '.json')
        state = read(path, {'pending': {}, 'receipts': {}})
        call = hashlib.sha256(str(payload.get('tool_use_id', '')).encode()).hexdigest()
        snapfile = DATA / (key + '-' + call + '.snapshot.json')
        if event == 'SessionStart':
            return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': instruction(session)}}
        if event == 'PreToolUse':
            save(snapfile, snapshot(cwd))
            return {}
        if event == 'PostToolUse':
            if not snapfile.exists():
                return {'systemMessage': 'UX/UI: no pre-tool snapshot; this tool change could not be tracked.'}
            before = read(snapfile, {})
            after = snapshot(cwd)
            snapfile.unlink()
            changed = [f for f, sha in after.items() if before.get(f) != sha]
            for file in changed:
                state['pending'][file] = after[file]
            save(path, state)
            errors = static_checks(changed)
            if errors:
                return {'decision': 'block', 'reason': 'UX/UI static checks failed:\n' + '\n'.join(errors)[:7000] + '\n' + instruction(session)}
            if changed:
                return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': 'UI changes tracked: ' + ', '.join(changed) + '\n' + instruction(session)}}
            return {}
        if event == 'Stop':
            pending = []
            for file in list(state['pending']):
                if not Path(file).exists():
                    del state['pending'][file]
                elif state['receipts'].get(file, {}).get('sha256') != digest(file):
                    pending.append(file)
            save(path, state)
            if pending:
                return {'decision': 'block', 'reason': 'UX/UI verification is missing or expired for:\n' + '\n'.join(pending) + '\n' + instruction(session)}
            return {}
    return {}

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'verify':
            sys.exit(verify(sys.argv[2:]))
        print(json.dumps(hook(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as e:
        print('UX/UI hook failed: ' + str(e), file=sys.stderr)
        sys.exit(2)
