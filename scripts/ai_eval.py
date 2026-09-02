#!/usr/bin/env python3
"""Evaluate the AI assistant against a live WROLPi.

Prompt and mode changes have so far been validated by anecdote; this scores every answer on
mechanical properties that do not need a judge:

  - the stream finished with `done` (no error, no timeout)
  - at least one tool was called, and the FIRST tool was one the question expects
  - the answer contains a relative WROLPi link when one is expected
  - the answer contains no external URLs (the modes forbid them)

Run it before and after any prompt/tool change:

    python3 scripts/ai_eval.py --base https://localhost:8443 [--mode research] [--timeout 600]

Exit code 1 when any question errors out; the score table is the real output.  Requires only
`requests` (in WROLPi's requirements).  The suite reads the library map's world: questions are
library-agnostic (browse/status/help) so they work on any WROLPi with some content."""
import argparse
import json
import re
import sys
import time

import requests

requests.packages.urllib3.disable_warnings()  # noqa  Self-signed certs.

# (mode, question, expected first tools (any of), expect a WROLPi link in the answer)
QUESTIONS = [
    ('help', 'How do I download videos?', {'search_help'}, True),
    ('help', 'What are Tags?', {'search_help'}, True),
    ('help', 'How do I add my own files to WROLPi?', {'search_help'}, True),
    ('research', 'What are my three newest archives?', {'search_archives'}, True),
    ('research', 'What video channels do I have?', {'list_collections', 'search_videos'}, False),
    ('research', 'Find videos about cooking', {'search_videos', 'search_all'}, False),
    ('research', 'Summarize my newest videos', {'search_videos'}, True),
    ('system', 'Is everything running?', {'get_system_status', 'list_services'}, False),
    ('system', 'How full are my drives?', {'get_system_status', 'list_disks'}, False),
    ('system', 'Why would downloads fail?', {'get_system_status', 'search_help'}, False),
]

EXTERNAL_URL = re.compile(r'https?://(?!localhost|127\.0\.0\.1)')
RELATIVE_LINK = re.compile(r'(^|[\s(\[])/(videos|archives|docs|epub|media|download|system|modules)[/\w]')


def run_question(base: str, mode: str, question: str, timeout: int) -> dict:
    started = time.time()
    tools, answer, error = [], None, None
    try:
        response = requests.post(f'{base}/api/chat/', verify=False, stream=True, timeout=timeout,
                                 json=dict(mode=mode, messages=[dict(role='user', content=question)]))
        if response.status_code != 200:
            return dict(error=f'HTTP {response.status_code}', tools=tools, elapsed=time.time() - started)
        event = None
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line.startswith('event:'):
                event = raw_line[6:].strip()
            elif raw_line.startswith('data:'):
                data = json.loads(raw_line[5:].strip())
                if event == 'tool_call':
                    tools.append(data.get('tool'))
                elif event == 'done':
                    answer = data.get('content')
                elif event == 'error':
                    error = data.get('message')
    except Exception as e:
        error = str(e)[:120]
    return dict(answer=answer, error=error, tools=tools, elapsed=time.time() - started)


def score(result: dict, expected_tools: set, expect_link: bool) -> dict:
    answer = result.get('answer') or ''
    checks = {
        'done': result.get('error') is None and bool(answer),
        'used_tool': bool(result['tools']),
        'right_tool': bool(result['tools']) and result['tools'][0] in expected_tools,
        'no_external_urls': not EXTERNAL_URL.search(answer),
    }
    if expect_link:
        checks['has_link'] = bool(RELATIVE_LINK.search(answer))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='https://localhost:8443')
    parser.add_argument('--mode', help='Only run one mode')
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()

    questions = [q for q in QUESTIONS if not args.mode or q[0] == args.mode]
    passed = total = errors = 0
    for mode, question, expected_tools, expect_link in questions:
        result = run_question(args.base, mode, question, args.timeout)
        checks = score(result, expected_tools, expect_link)
        passed += sum(checks.values())
        total += len(checks)
        if result.get('error'):
            errors += 1
        flags = ' '.join(f'{name}={"Y" if ok else "N"}' for name, ok in checks.items())
        print(f'[{mode:8}] {result["elapsed"]:6.1f}s  {flags}  {question}')
        if not all(checks.values()):
            print(f'           tools={result["tools"]}')
            detail = result.get('error') or (result.get('answer') or '')[:200]
            print(f'           {detail}')

    print(f'\nScore: {passed}/{total} checks passed across {len(questions)} questions; {errors} hard errors.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
