#!/usr/bin/env python3
"""Install namespaced Codex skills and opt-in lifecycle hooks from this clone."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ('SessionStart', 'PreToolUse', 'PostToolUse', 'Stop')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('This adapter requires macOS/Linux (POSIX file locking).')
    if sys.version_info < (3, 9):
        parser.error('Python 3.9+ is required.')
    if not shutil.which('rg'):
        parser.error('Install ripgrep (rg) first.')
    home = args.codex_home.expanduser().resolve()
    config_path = home / 'hooks.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {'hooks': {}}
    manifest_path = home / 'ux-ui-codex-install.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    sources = sorted((ROOT / '.claude/skills').glob('*/SKILL.md'))
    names = {p.parent.name: 'ux-ui-' + p.parent.name for p in sources}
    owned = set(previous.get('skills', []))
    # Do not overwrite similarly named skills installed by another tool/person.
    for name in names.values():
        if (home / 'skills' / name).exists() and name not in owned:
            parser.error(f'Existing unmanaged skill: {name}; move it or choose another --codex-home.')
    hooks = config.setdefault('hooks', {})
    if not isinstance(hooks, dict) or any(not isinstance(hooks.get(e, []), list) for e in EVENTS):
        parser.error('Unsupported hooks.json shape; existing configuration was left unchanged.')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / 'backups' / ('ux-ui-codex-' + stamp)
    backup.mkdir(parents=True)
    for p in [config_path, manifest_path]:
        if p.exists():
            shutil.copy2(p, backup / p.name)
    for source in sources:
        name = names[source.parent.name]
        dest = home / 'skills' / name
        if dest.exists():
            shutil.move(str(dest), str(backup / name))
        shutil.copytree(source.parent, dest)
        for md in dest.rglob('*.md'):
            text = md.read_text()
            text = text.replace('${CLAUDE_SKILL_DIR}/../../..', str(ROOT)).replace('${CLAUDE_SKILL_DIR}', str(source.parent))
            # Rename skill references without changing kit paths or ordinary prose.
            text = re.sub(r'(?<![\w/])/(\w[\w-]*)(?![\w/.-])', lambda m: '/' + names.get(m[1], m[1]), text)
            text = re.sub(r'`([a-z][a-z-]+)`', lambda m: '`' + names.get(m[1], m[1]) + '`', text)
            if md.name == 'SKILL.md':
                text = re.sub(r'^name: .+$', 'name: ' + name, text, count=1, flags=re.M)
                text += f'\n## Codex paths\n\nResolve kit-relative references from `{ROOT}`. Keep the clone at this location. Run kit self-tests from that directory; project gates must target the user project. Follow the active Codex hook instructions to record verification.\n'
            md.write_text(text)
    command = shlex.join([sys.executable, str(ROOT / 'codex/enforce.py')])
    previous_command = previous.get('command')
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if previous_command:
            for group in groups:
                group['hooks'] = [h for h in group.get('hooks', []) if h.get('command') != previous_command]
            groups[:] = [g for g in groups if g.get('hooks')]
        groups.append({'hooks': [{'type': 'command', 'command': command, 'timeout': 120 if event == 'PostToolUse' else 30}]})
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    manifest_path.write_text(json.dumps({'repository': str(ROOT), 'command': command, 'skills': sorted(names.values()), 'backup': str(backup)}, indent=2) + '\n')
    print(f'Installed {len(names)} namespaced skills and {len(EVENTS)} hooks in {home}.')
    print(f'Backup: {backup}')
    print('Open Codex CLI /hooks and review/trust these four hook definitions. Restart Codex.')
    print('Hooks are not automatically trusted. Keep this clone at its current path.')

if __name__ == '__main__':
    main()
