#!/usr/bin/env python3
"""
Fail when vulture finds dead code that is not in scripts/vulture_baseline.txt.

vulture's 60% hits are mostly dataclass/schema fields and attributes set on library objects, which
nothing in Python reads by name, so this reports only what is worth acting on: unused functions,
methods, classes, properties, imports, unreachable code, unused arguments (100% confidence), and
unused module-level variables.  Class fields, attributes, and variables in tests are not reported.

The baseline is keyed by file and name, not line number, so editing a file does not invalidate it.

Usage:

    pip install vulture
    python3 scripts/check_dead_code.py           # Exits 1 if anything new is found.
    python3 scripts/check_dead_code.py --update  # Rewrite the baseline with the current findings.

Delete the dead code when you can.  Add it to the baseline (--update) only when vulture is wrong,
for example when the name is used dynamically.
"""
import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BASELINE = PROJECT_DIR / 'scripts/vulture_baseline.txt'

# Tests and migrations are scanned so their uses count; anything they call is not dead.
PATHS = ['wrolpi', 'modules', 'controller', 'alembic', 'main.py', 'conftest.py']
EXCLUDE = ['*/venv/*', '*/.venv/*', '*/node_modules/*']
# These register the function somewhere vulture cannot see, so their functions are never called by name.
IGNORE_DECORATORS = [
    '@*.get', '@*.post', '@*.put', '@*.patch', '@*.delete', '@*.route', '@*.websocket', '@*.signal',
    '@*.listener', '@*.middleware', '@*.on_request', '@*.on_response', '@*.exception',
    '@*.main_process_start', '@*.main_process_ready', '@*.reload_process_start',
    '@*.before_server_start', '@*.after_server_start', '@*.before_server_stop', '@*.after_server_stop',
    '@*.on_event', '@*.exception_handler', '@*.validator', '@*.field_validator', '@*.model_validator',
    '@register_switch_handler', '@register_job', '@register_indexer', '@register_refresh_cleanup',
    '@register_modeler', '@perpetual_signal', '@event.listens_for', '@serializer', '@pytest.fixture',
]
# Alembic reads these from every migration.
IGNORE_NAMES = ['revision', 'down_revision', 'branch_labels', 'depends_on']
# Tests request fixtures as arguments for their side effects, so unused test arguments are expected.
TEST_FILE_PATTERN = re.compile(r'(^|/)(test/|test_[^/]*\.py$|conftest\.py$)')

LINE_PATTERN = re.compile(r'^(?P<path>.+?):(?P<line>\d+): (?P<message>.+) \((?P<confidence>\d+)% confidence.*\)$')
UNUSED_PATTERN = re.compile(r"^unused (?P<kind>[a-z]+) '(?P<name>[^']+)'$")


def run_vulture() -> list[str]:
    cmd = [sys.executable, '-m', 'vulture', *PATHS, '--min-confidence', '60',
           '--exclude', ','.join(EXCLUDE), '--ignore-decorators', ','.join(IGNORE_DECORATORS),
           '--ignore-names', ','.join(IGNORE_NAMES)]
    proc = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
    # 0 = nothing found, 3 = dead code found; anything else is a vulture error (bad input, syntax error).
    if proc.returncode not in (0, 3):
        sys.stderr.write(proc.stderr or proc.stdout)
        if 'No module named vulture' in proc.stderr:
            sys.stderr.write('Install vulture: pip install vulture\n')
        sys.exit(2)
    return proc.stdout.splitlines()


def is_module_level(path: str, line: int) -> bool:
    lines = (PROJECT_DIR / path).read_text().splitlines()
    return line <= len(lines) and lines[line - 1][:1] not in ('', ' ', '\t')


def findings() -> dict[str, list[str]]:
    """Map each reportable finding's baseline key to the vulture lines that produced it."""
    found = {}
    for output in run_vulture():
        if not (match := LINE_PATTERN.match(output)):
            continue
        path, line, message = match['path'], int(match['line']), match['message']
        confidence = int(match['confidence'])
        if unused := UNUSED_PATTERN.match(message):
            kind, name = unused['kind'], unused['name']
            if kind == 'attribute':
                continue
            if kind == 'variable' and TEST_FILE_PATTERN.search(path):
                continue
            if kind == 'variable' and confidence < 100 and not is_module_level(path, line):
                continue
            key = f'{path}: unused {kind} {name!r}'
        else:
            # Unreachable code and redundant conditions are keyed by their (unique enough) message.
            key = f'{path}: {message}'
        found.setdefault(key, []).append(output)
    return found


def read_baseline() -> Counter:
    if not BASELINE.is_file():
        return Counter()
    lines = (i.strip() for i in BASELINE.read_text().splitlines())
    return Counter(i for i in lines if i and not i.startswith('#'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--update', action='store_true', help='Rewrite the baseline with the current findings.')
    args = parser.parse_args()

    found = findings()
    current = Counter({key: len(outputs) for key, outputs in found.items()})

    if args.update:
        header = '# Known vulture findings, see scripts/check_dead_code.py.  Regenerate with --update.\n'
        BASELINE.write_text(header + ''.join(f'{key}\n' for key in sorted(current.elements())))
        print(f'Wrote {sum(current.values())} findings to {BASELINE.relative_to(PROJECT_DIR)}')
        return

    baseline = read_baseline()
    new = current - baseline
    stale = baseline - current

    if stale:
        print('These baseline entries are no longer found; remove them with --update:')
        for key in sorted(stale):
            print(f'  {key}')
        print()

    if new:
        print('vulture found dead code that is not in scripts/vulture_baseline.txt:')
        for key in sorted(new):
            for output in found[key]:
                print(f'  {output}')
        print('\nDelete the dead code.  If vulture is wrong (the name is used dynamically, for example), run\n'
              '`python3 scripts/check_dead_code.py --update` and commit the baseline.')
        sys.exit(1)

    print(f'No new dead code ({sum(current.values())} known findings in the baseline).')


if __name__ == '__main__':
    main()
