#!/usr/bin/env python3
"""
Benchmark the read-only WROLPi API endpoints, hot and cold.

Read-only here means "does not mutate the library": every GET endpoint, plus the POST
`.../search` and `.../estimates` endpoints the React UI uses to render its pages (the Videos
page, for example, is rendered from `POST /api/videos/search`).

Usage examples:

    # Hot only (no SSH needed), 3 passes, against a host profile from scripts/api_perf_hosts.json
    # (copy scripts/api_perf_hosts.example.json to create it).
    python3 scripts/api_perf.py --host docker

    # Cold pass (restart the API over SSH, then run every endpoint once) followed by 3 hot passes.
    python3 scripts/api_perf.py --host docker --cold

    # Additionally restart before EACH of the "page" endpoints so each gets a truly cold number.
    python3 scripts/api_perf.py --host decay --cold --cold-each

    # Ad-hoc host.
    python3 scripts/api_perf.py --url https://192.0.2.10:8443

Results are written as CSV to ./perf_results/<host>_<timestamp>.csv, one row per request, and a
summary table is printed at the end.  Only the standard library is used so this runs anywhere.
"""
import argparse
import csv
import datetime
import json
import shlex
import ssl
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# ----------------------------------------------------------------------------------------------
# Hosts
# ----------------------------------------------------------------------------------------------

HOSTS_FILE = Path(__file__).with_name('api_perf_hosts.json')  # gitignored; see api_perf_hosts.example.json


def load_hosts() -> dict:
    """Host profiles live in a gitignored JSON file so LAN addresses/usernames stay out of the repo.

    Each profile: url, ssh (user@host or null), ssh_opts (list), restart (shell command run over
    ssh), drop_caches (shell command or null when the ssh user cannot do it)."""
    if not HOSTS_FILE.exists():
        return {}
    return json.loads(HOSTS_FILE.read_text())


HOSTS = load_hosts()

# ----------------------------------------------------------------------------------------------
# Endpoint catalog
# ----------------------------------------------------------------------------------------------
# Each entry: name, method, path, optional json body, optional `page` (which UI page issues it on
# load; used for grouping and for --cold-each), optional `needs` (an id discovered at runtime,
# substituted into the path as {video_id}, etc.).
#
# Deliberately excluded (read-only but not useful to time, or slow by design):
#   GET /api/events/feed (long-poll), GET /api/files/zip/download (streams a zip),
#   GET /api/extensions/<filename> (static file), GET /api/upgrade/check (network),
#   GET /api/ai/services/<name>/logs, GET /api/ai/files/read, GET /api/ai/help/<slug>,
#   GET /api/echo (used as the readiness probe instead).

CATALOG = [
    # --- root ---
    dict(name='echo', method='GET', path='/api/echo'),
    dict(name='settings', method='GET', path='/api/settings', page='app'),
    dict(name='status', method='GET', path='/api/status', page='app'),
    dict(name='statistics', method='GET', path='/api/statistics', page='home'),
    dict(name='downloaders', method='GET', path='/api/downloaders'),
    dict(name='download', method='GET', path='/api/download', page='downloads'),
    dict(name='tag', method='GET', path='/api/tag', page='app'),
    dict(name='tag/recent', method='GET', path='/api/tag/recent'),
    dict(name='extensions', method='GET', path='/api/extensions'),
    dict(name='search_suggestions', method='POST', path='/api/search_suggestions',
         body={'search_str': '{q}'}, page='search'),
    dict(name='search_file_estimates', method='POST', path='/api/search_file_estimates',
         body={'search_str': '{q}'}, page='search'),
    dict(name='search_other_estimates', method='POST', path='/api/search_other_estimates',
         body={'tag_names': []}, page='search'),

    # --- config ---
    dict(name='config', method='GET', path='/api/config/'),
    dict(name='config/backups', method='GET', path='/api/config/backups'),

    # --- files ---
    dict(name='files/refresh_progress', method='GET', path='/api/files/refresh_progress', page='files'),
    dict(name='files/worker_status', method='GET', path='/api/files/worker_status'),
    dict(name='files/bulk_tag/progress', method='GET', path='/api/files/bulk_tag/progress'),
    dict(name='files (root listing)', method='POST', path='/api/files/', body={'directories': []}, page='files'),
    dict(name='files/search (no query)', method='POST', path='/api/files/search',
         body={'offset': 0, 'limit': 20}, page='search'),
    dict(name='files/search (query)', method='POST', path='/api/files/search',
         body={'offset': 0, 'limit': 20, 'search_str': '{q}'}, page='search'),
    dict(name='files/search (common word "the")', method='POST', path='/api/files/search',
         body={'offset': 0, 'limit': 20, 'search_str': 'the'}),
    dict(name='files/search (query, deep)', method='POST', path='/api/files/search',
         body={'offset': 0, 'limit': 20, 'search_str': '{q}', 'deep': True}),
    dict(name='files/search (page 50)', method='POST', path='/api/files/search',
         body={'offset': 1000, 'limit': 20, 'search_str': '{q}'}),
    dict(name='files/search_directories', method='POST', path='/api/files/search_directories',
         body={'path': 'vid'}),

    # --- collections ---
    dict(name='collections', method='GET', path='/api/collections/', page='collections'),
    dict(name='collections/<id>', method='GET', path='/api/collections/{collection_id}', needs='collection_id'),
    dict(name='collections/search', method='POST', path='/api/collections/search', body={}),
    dict(name='collections/reorganize/channels', method='GET', path='/api/collections/reorganize/channels'),
    dict(name='collections/reorganize/domains', method='GET', path='/api/collections/reorganize/domains'),

    # --- videos ---
    dict(name='videos/statistics', method='GET', path='/api/videos/statistics', page='videos-stats'),
    dict(name='videos/download-defaults', method='GET', path='/api/videos/download-defaults'),
    dict(name='videos/cookies/status', method='GET', path='/api/videos/cookies/status'),
    dict(name='videos/suggested-user-agent', method='GET', path='/api/videos/suggested-user-agent'),
    dict(name='videos/channels', method='GET', path='/api/videos/channels', page='videos'),
    dict(name='videos/channels/<id>', method='GET', path='/api/videos/channels/{channel_id}',
         needs='channel_id', page='channel'),
    dict(name='videos/channels/search', method='POST', path='/api/videos/channels/search', body={'tag_names': []}),
    dict(name='videos/search (page 1, newest)', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': '-published_datetime'}, page='videos'),
    dict(name='videos/search (page 1, -view_count)', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': '-view_count'}),
    dict(name='videos/search (page 50, newest)', method='POST', path='/api/videos/search',
         body={'offset': 1176, 'limit': 24, 'order_by': '-published_datetime'}),
    dict(name='videos/search (query, rank)', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': 'rank', 'search_str': '{q}'}, page='videos-search'),
    dict(name='videos/search (common word "the")', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': 'rank', 'search_str': 'the'}),
    dict(name='videos/search (query, deep)', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': 'rank', 'search_str': '{q}', 'deep': True}),
    dict(name='videos/search (channel)', method='POST', path='/api/videos/search',
         body={'offset': 0, 'limit': 24, 'order_by': '-published_datetime', 'channel_id': '{channel_id}'},
         needs='channel_id', page='channel'),
    dict(name='videos/<id>', method='GET', path='/api/videos/{video_id}', needs='video_id', page='video'),
    dict(name='videos/<id>/comments', method='GET', path='/api/videos/{video_id}/comments', needs='video_id',
         page='video'),
    dict(name='videos/<id>/captions', method='GET', path='/api/videos/{video_id}/captions', needs='video_id'),

    # --- archive ---
    dict(name='archive/statistics', method='GET', path='/api/archive/statistics', page='archives-stats'),
    dict(name='archive/browsers', method='GET', path='/api/archive/browsers'),
    dict(name='archive/search (page 1)', method='POST', path='/api/archive/search',
         body={'offset': 0, 'limit': 20, 'order_by': '-published_datetime'}, page='archives'),
    dict(name='archive/search (query)', method='POST', path='/api/archive/search',
         body={'offset': 0, 'limit': 20, 'search_str': '{q}'}, page='archives-search'),
    dict(name='archive/search (query, deep)', method='POST', path='/api/archive/search',
         body={'offset': 0, 'limit': 20, 'search_str': '{q}', 'deep': True}),
    dict(name='archive/<id>', method='GET', path='/api/archive/{archive_id}', needs='archive_id', page='archive'),

    # --- docs ---
    dict(name='docs/statistics', method='GET', path='/api/docs/statistics'),
    dict(name='docs/search (page 1)', method='POST', path='/api/docs/search', body={'limit': 20}, page='docs'),
    dict(name='docs/search (query)', method='POST', path='/api/docs/search', body={'limit': 20, 'search_str': '{q}'}),
    dict(name='docs/<id>', method='GET', path='/api/docs/{doc_id}', needs='doc_id'),

    # --- zim ---
    dict(name='zim', method='GET', path='/api/zim/', page='zim'),
    dict(name='zim/subscribe', method='GET', path='/api/zim/subscribe'),
    dict(name='zim/outdated', method='GET', path='/api/zim/outdated'),
    dict(name='zim/search', method='POST', path='/api/zim/search', body={'search_str': '{q}', 'limit': 10},
         page='search'),
    dict(name='zim/search_estimates', method='POST', path='/api/zim/search_estimates',
         body={'search_str': '{q}'}, page='search'),

    # --- map ---
    dict(name='map/files', method='GET', path='/api/map/files', page='map'),
    dict(name='map/subscribe', method='GET', path='/api/map/subscribe'),
    dict(name='map/pins', method='GET', path='/api/map/pins', page='map'),
    dict(name='map/search', method='GET', path='/api/map/search?q={q}&limit=20&offset=0'),
    dict(name='map/search/estimate', method='GET', path='/api/map/search/estimate?q={q}'),
    dict(name='map/search/status', method='GET', path='/api/map/search/status'),

    # --- inventory ---
    dict(name='inventory', method='GET', path='/api/inventory/', page='inventory'),
    dict(name='inventory/catalog', method='GET', path='/api/inventory/catalog'),

    # --- flasher ---
    dict(name='flasher/configs', method='GET', path='/api/flasher/configs'),
    dict(name='flasher/search', method='POST', path='/api/flasher/search', body={}),

    # --- ai (MCP-facing read endpoints) ---
    dict(name='ai/status', method='GET', path='/api/ai/status'),
    dict(name='ai/services', method='GET', path='/api/ai/services'),
    dict(name='ai/disks', method='GET', path='/api/ai/disks'),
    dict(name='ai/manage/catalog', method='GET', path='/api/ai/manage/catalog'),
    dict(name='ai/collections', method='GET', path='/api/ai/collections'),
    dict(name='ai/inventories', method='GET', path='/api/ai/inventories'),
    dict(name='ai/zims', method='GET', path='/api/ai/zims'),
    dict(name='ai/search', method='POST', path='/api/ai/search', body={'search_str': '{q}', 'limit': 5}),
    dict(name='ai/videos/search', method='POST', path='/api/ai/videos/search', body={'search_str': '{q}', 'limit': 5}),
    dict(name='ai/archives/search', method='POST', path='/api/ai/archives/search',
         body={'search_str': '{q}', 'limit': 5}),
    dict(name='ai/docs/search', method='POST', path='/api/ai/docs/search', body={'search_str': '{q}', 'limit': 5}),
    dict(name='ai/zims/search', method='POST', path='/api/ai/zims/search', body={'search_str': '{q}', 'limit': 5}),
    dict(name='ai/videos/<id>', method='GET', path='/api/ai/videos/{video_id}', needs='video_id'),
    dict(name='ai/archives/<id>', method='GET', path='/api/ai/archives/{archive_id}', needs='archive_id'),
    dict(name='chat/modes', method='GET', path='/api/chat/modes'),
]

# Endpoints that get their own restart when --cold-each is used: what a user hits when they open
# a page.  Keep this short: each entry costs a restart + readiness wait.
COLD_EACH = [
    'videos/search (page 1, newest)',
    'videos/channels',
    'videos/statistics',
    'files/search (no query)',
    'files/search (query)',
    'archive/search (page 1)',
    'statistics',
    'status',
    'settings',
]

# ----------------------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------------------

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # While the API is down, Caddy 302s /api/* to the Controller's fallback UI, which answers 200
    # with HTML.  Following that would make a down API look like a fast one.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=SSL_CTX))


def request(base_url: str, method: str, path: str, body=None, timeout: float = 180.0) -> dict:
    """Perform one request, reading the whole body.  Returns timing + status + size."""
    url = base_url.rstrip('/') + path
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    start = time.perf_counter()
    status, size, error, payload, ctype = None, 0, None, None, ''
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            payload = resp.read()
            status = resp.status
            size = len(payload)
            ctype = resp.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = e.read()
            size = len(payload)
        except Exception:
            pass
        error = f'HTTP {e.code}'
    except Exception as e:  # timeouts, connection refused, etc.
        error = type(e).__name__ + (f': {e}' if str(e) else '')
    elapsed = time.perf_counter() - start
    if status == 200 and 'json' not in ctype:
        # A 200 that is not JSON did not come from the API (fallback UI, proxy page, ...).
        status, error = 'HTML', f'non-JSON 200 ({ctype.split(";")[0] or "no content-type"})'
    return dict(ms=round(elapsed * 1000, 1), status=status, bytes=size, error=error, payload=payload)


def wait_ready(base_url: str, timeout: float = 300.0) -> float:
    """Poll /api/echo until it answers 200.  Returns seconds waited."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        r = request(base_url, 'GET', '/api/echo', timeout=5)
        if r['status'] == 200:
            return round(time.perf_counter() - start, 1)
        time.sleep(1)
    raise TimeoutError(f'{base_url} did not become ready within {timeout}s')


# ----------------------------------------------------------------------------------------------
# SSH / cold
# ----------------------------------------------------------------------------------------------

def ssh(host: dict, cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', *host['ssh_opts'], host['ssh'], cmd]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f'ssh {host["ssh"]} {shlex.quote(cmd)} failed rc={proc.returncode}: {proc.stderr.strip()}')
    return proc


def go_cold(host: dict, log) -> dict:
    """Restart the API (and drop the OS page cache when we can), then wait for readiness."""
    dropped = False
    if host.get('drop_caches'):
        proc = ssh(host, host['drop_caches'], check=False)
        dropped = proc.returncode == 0
        if not dropped:
            log(f'  ! drop_caches failed (continuing, process-cold only): {proc.stderr.strip()}')
    t = time.perf_counter()
    ssh(host, host['restart'])
    # Give the old process a moment to die so we don't get a "ready" from the old process.
    time.sleep(2)
    ready = wait_ready(host['url'])
    total = round(time.perf_counter() - t, 1)
    log(f'  restarted (drop_caches={dropped}); API ready after {ready}s (restart+ready {total}s)')
    return dict(dropped_caches=dropped, ready_seconds=ready)


# ----------------------------------------------------------------------------------------------
# Discovery of ids
# ----------------------------------------------------------------------------------------------

def _first_id(payload: Optional[bytes], *keys) -> Optional[int]:
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
        if data is None:
            return None
    if isinstance(data, list) and data:
        item = data[0]
        return item.get('id') if isinstance(item, dict) else None
    return None


def discover_ids(base_url: str, log) -> dict:
    ids = {}

    def probe(key, method, path, body, *keys):
        r = request(base_url, method, path, body)
        ids[key] = _first_id(r['payload'], *keys)
        log(f'  [discover ] {r["ms"]:9.1f} ms  {r["status"]}  {r["bytes"]:>9} B  {path}'
            + (f'  <-- {r["error"]}' if r['error'] else ''))

    probe('video_id', 'POST', '/api/videos/search', {'offset': 0, 'limit': 1, 'order_by': '-published_datetime'},
          'file_groups')
    probe('archive_id', 'POST', '/api/archive/search', {'offset': 0, 'limit': 1}, 'file_groups')
    probe('doc_id', 'POST', '/api/docs/search', {'limit': 1}, 'file_groups')
    probe('channel_id', 'GET', '/api/videos/channels', None, 'channels')
    probe('collection_id', 'GET', '/api/collections/', None, 'collections')
    log(f'  discovered ids: {ids}')
    return ids


def resolve(entry: dict, ids: dict) -> Optional[dict]:
    """Substitute discovered ids (and the {q} search term) into an entry.
    Returns None when a required id is missing."""
    needs = entry.get('needs')
    if needs and ids.get(needs) is None:
        return None
    e = dict(entry)
    q = ids.get('q', 'solar')
    e['path'] = e['path'].replace('{q}', urllib.parse.quote(q))
    if e.get('body'):
        e['body'] = {bk: (q if bv == '{q}' else bv) for bk, bv in e['body'].items()}
    for k, v in ids.items():
        if v is None or k == 'q':
            continue
        e['path'] = e['path'].replace('{%s}' % k, str(v))
        if e.get('body'):
            e['body'] = {bk: (v if bv == '{%s}' % k else bv) for bk, bv in e['body'].items()}
    return e


# ----------------------------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--host', choices=sorted(HOSTS), help=f'A host profile from {HOSTS_FILE.name}.')
    g.add_argument('--url', help='Ad-hoc base URL, e.g. https://192.0.2.10:8443 (hot only unless --ssh given).')
    ap.add_argument('--cold', action='store_true', help='Restart the API over SSH, run one cold pass first.')
    ap.add_argument('--cold-each', action='store_true',
                    help='Also restart before each COLD_EACH endpoint for per-endpoint cold numbers.')
    ap.add_argument('--hot-passes', type=int, default=3, help='Number of hot passes (default 3).')
    ap.add_argument('--query', default='solar',
                    help='Search term substituted for {q} in the catalog (default "solar"; "the" rows are fixed worst-case).')
    ap.add_argument('--only', help='Substring filter on endpoint names.')
    ap.add_argument('--timeout', type=float, default=180.0, help='Per-request timeout in seconds.')
    ap.add_argument('--out-dir', default='perf_results')
    args = ap.parse_args()

    if args.host:
        host = dict(HOSTS[args.host], name=args.host)
    else:
        host = dict(url=args.url, name=args.url.replace('https://', '').replace('http://', '').replace(':', '_'),
                    ssh=None, ssh_opts=[], restart=None, drop_caches=None)
    if args.cold and not host.get('ssh'):
        ap.error('--cold requires a --host profile with SSH access')
    host.setdefault('ssh_opts', [])

    base = host['url']
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    out_csv = out_dir / f'{host["name"]}_{stamp}.csv'
    log_path = out_dir / f'{host["name"]}_{stamp}.log'
    log_file = open(log_path, 'w')

    def log(msg=''):
        print(msg, flush=True)
        log_file.write(msg + '\n')
        log_file.flush()

    log(f'== WROLPi API perf: {host["name"]} ({base}) at {stamp}')
    ready = wait_ready(base, timeout=30)
    log(f'  reachable (echo answered after {ready}s)')

    ids = discover_ids(base, log)
    ids['q'] = args.query
    log(f'  query term: {args.query!r}')
    catalog = [e for e in (resolve(e, ids) for e in CATALOG) if e]
    skipped = [e['name'] for e in CATALOG if not resolve(e, ids)]
    if args.only:
        catalog = [e for e in catalog if args.only in e['name']]
    if skipped:
        log(f'  skipped (no id on this host): {skipped}')
    log(f'  {len(catalog)} endpoints')

    rows = []
    writer = csv.DictWriter(open(out_csv, 'w', newline=''),
                            fieldnames=['host', 'phase', 'pass', 'name', 'method', 'path', 'ms', 'status', 'bytes',
                                        'error', 'dropped_caches', 'ready_seconds'])
    writer.writeheader()

    def run_pass(phase: str, pass_no: int, entries, extra=None):
        for e in entries:
            r = request(base, e['method'], e['path'], e.get('body'), timeout=args.timeout)
            row = dict(host=host['name'], phase=phase, **{'pass': pass_no}, name=e['name'], method=e['method'],
                       path=e['path'], ms=r['ms'], status=r['status'], bytes=r['bytes'], error=r['error'] or '',
                       **(extra or {}))
            rows.append(row)
            writer.writerow(row)
            flag = '' if r['status'] == 200 else f'  <-- {r["error"]}'
            log(f'  [{phase:9}] {r["ms"]:9.1f} ms  {r["status"]}  {r["bytes"]:>9} B  {e["name"]}{flag}')

    # --- cold-each: restart before each key endpoint ---
    if args.cold and args.cold_each:
        log('\n-- cold-each: restart before each page endpoint')
        by_name = {e['name']: e for e in catalog}
        for name in COLD_EACH:
            if name not in by_name:
                continue
            info = go_cold(host, log)
            run_pass('cold-each', 0, [by_name[name]], extra=info)

    # --- cold pass: one restart, then every endpoint once, in catalog order ---
    if args.cold:
        log('\n-- cold pass: restart, then every endpoint once')
        info = go_cold(host, log)
        run_pass('cold', 0, catalog, extra=info)

    # --- hot passes ---
    for i in range(1, args.hot_passes + 1):
        log(f'\n-- hot pass {i}/{args.hot_passes}')
        run_pass('hot', i, catalog)

    # --- summary ---
    log(f'\n== Summary for {host["name"]} ({base})  [ms]')
    header = f'{"endpoint":42} {"cold-each":>9} {"cold":>9} {"hot min":>9} {"hot med":>9} {"hot max":>9} {"status":>6} {"bytes":>9}'
    log(header)
    log('-' * len(header))
    summary = []
    for e in catalog:
        name = e['name']
        ce = [r['ms'] for r in rows if r['name'] == name and r['phase'] == 'cold-each']
        cold = [r['ms'] for r in rows if r['name'] == name and r['phase'] == 'cold']
        hot = [r['ms'] for r in rows if r['name'] == name and r['phase'] == 'hot']
        statuses = {r['status'] for r in rows if r['name'] == name}
        size = max((r['bytes'] for r in rows if r['name'] == name), default=0)
        fmt = lambda v: f'{v:9.0f}' if v is not None else f'{"-":>9}'
        hot_min = min(hot) if hot else None
        hot_med = statistics.median(hot) if hot else None
        hot_max = max(hot) if hot else None
        summary.append(dict(name=name, cold_each=ce[0] if ce else None, cold=cold[0] if cold else None,
                            hot_min=hot_min, hot_med=hot_med, hot_max=hot_max, status=statuses, bytes=size))
        st = ','.join(str(s) for s in sorted(statuses, key=str))
        log(f'{name:42} {fmt(ce[0] if ce else None)} {fmt(cold[0] if cold else None)} {fmt(hot_min)} '
            f'{fmt(hot_med)} {fmt(hot_max)} {st:>6} {size:>9}')

    # Slowest endpoints, by hot median and by cold.
    def top(key, n=10):
        vals = [s for s in summary if s[key] is not None]
        return sorted(vals, key=lambda s: -s[key])[:n]

    log('\n-- slowest by hot median')
    for s in top('hot_med'):
        log(f'  {s["hot_med"]:9.0f} ms  {s["name"]}')
    if any(s['cold'] is not None for s in summary):
        log('\n-- slowest cold')
        for s in top('cold'):
            log(f'  {s["cold"]:9.0f} ms  {s["name"]}')

    # Page-load view: sum of the endpoints a page fires when opened (they run in parallel in the
    # browser, so the max is the floor and the sum is the ceiling of what the user waits).
    pages = {}
    for e in catalog:
        if e.get('page'):
            pages.setdefault(e['page'], []).append(e['name'])
    log('\n-- page load (hot median / cold): max = parallel floor, sum = serial ceiling')
    for page, names in sorted(pages.items()):
        ss = [s for s in summary if s['name'] in names]
        hm = [s['hot_med'] for s in ss if s['hot_med'] is not None]
        cd = [s['cold'] for s in ss if s['cold'] is not None]
        hot_txt = f'hot max {max(hm):7.0f} sum {sum(hm):7.0f}' if hm else 'hot -'
        cold_txt = f'cold max {max(cd):7.0f} sum {sum(cd):7.0f}' if cd else ''
        log(f'  {page:16} {hot_txt}   {cold_txt}   ({len(names)} calls)')

    log(f'\nrows: {out_csv}\nlog:  {log_path}')


if __name__ == '__main__':
    sys.exit(main())
