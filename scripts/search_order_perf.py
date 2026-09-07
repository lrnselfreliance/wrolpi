#!/usr/bin/env python3
"""Benchmark file-search endpoints across every supported order.

Usage:
    python3 scripts/search_order_perf.py --host decay --label before
    python3 scripts/search_order_perf.py --host decay --label after --passes 3

Writes CSV to ./perf_results/search_order_<host>_<label>_<timestamp>.csv and prints a table.
"""
import argparse
import csv
import datetime
import json
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOSTS_FILE = Path(__file__).with_name('api_perf_hosts.json')

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=SSL_CTX))


def load_hosts() -> dict:
    if not HOSTS_FILE.exists():
        return {}
    return json.loads(HOSTS_FILE.read_text())


# (name, path, base_body, orders)
# orders: None means a single request with whatever base_body already has.
CASES = [
    ('videos', '/api/videos/search',
     {'offset': 0, 'limit': 24, 'tag_names': []},
     [
         'published_datetime', '-published_datetime',
         'download_datetime', '-download_datetime',
         'size', '-size',
         'length', '-length',
         'size_to_duration', '-size_to_duration',
         'viewed', '-viewed',
         'view_count', '-view_count',
     ]),
    ('videos/search', '/api/videos/search',
     {'offset': 0, 'limit': 24, 'tag_names': [], 'search_str': 'the'},
     ['rank', '-rank', '-published_datetime', '-download_datetime', '-size']),
    ('archive', '/api/archive/search',
     {'offset': 0, 'limit': 20},
     [
         'published_datetime', '-published_datetime',
         'download_datetime', '-download_datetime',
         'published_modified_datetime', '-published_modified_datetime',
         'size', '-size',
         'viewed', '-viewed',
     ]),
    ('archive/search', '/api/archive/search',
     {'offset': 0, 'limit': 20, 'search_str': 'the'},
     ['rank', '-rank', '-published_datetime', '-download_datetime', '-size']),
    ('files', '/api/files/search',
     {'offset': 0, 'limit': 20},
     [None, 'viewed', '-viewed']),
    ('files/search', '/api/files/search',
     {'offset': 0, 'limit': 20, 'search_str': 'the'},
     [None, 'viewed', '-viewed']),
    ('docs', '/api/docs/search',
     {'limit': 20, 'offset': 0},
     ['published_datetime', 'size', 'title']),
    ('docs/search', '/api/docs/search',
     {'limit': 20, 'offset': 0, 'search_str': 'the'},
     ['rank', 'published_datetime', 'size', 'title']),
]


def request(base_url: str, path: str, body: dict, timeout: float = 180.0) -> dict:
    url = base_url.rstrip('/') + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method='POST',
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
    )
    start = time.perf_counter()
    status, size, error, total = None, 0, None, None
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            payload = resp.read()
            status = resp.status
            size = len(payload)
            if status == 200:
                try:
                    total = json.loads(payload).get('totals', {}).get('file_groups')
                except Exception:
                    pass
    except urllib.error.HTTPError as e:
        status = e.code
        error = f'HTTP {e.code}'
        try:
            size = len(e.read())
        except Exception:
            pass
    except Exception as e:
        error = type(e).__name__ + (f': {e}' if str(e) else '')
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return dict(ms=elapsed_ms, status=status, bytes=size, error=error, total=total)


def expand_cases():
    rows = []
    for group, path, base, orders in CASES:
        for order in orders:
            body = dict(base)
            label = group
            if order is not None:
                if path == '/api/files/search':
                    body['order'] = order
                else:
                    body['order_by'] = order
                label = f'{group} order={order}'
            else:
                label = f'{group} order=<default>'
            rows.append((label, path, body))
    return rows


def main():
    hosts = load_hosts()
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='decay', choices=sorted(hosts) or ['decay'])
    ap.add_argument('--url', default=None, help='Override host URL')
    ap.add_argument('--label', default='run', help='Tag written into the CSV filename (before/after)')
    ap.add_argument('--passes', type=int, default=3)
    ap.add_argument('--warmup', type=int, default=1)
    ap.add_argument('--out-dir', default='perf_results')
    args = ap.parse_args()

    if args.url:
        base_url = args.url
        host_name = 'adhoc'
    else:
        profile = hosts[args.host]
        base_url = profile['url']
        host_name = args.host

    cases = expand_cases()
    print(f'host={host_name} url={base_url} label={args.label} cases={len(cases)} passes={args.passes}')

    if args.warmup:
        print(f'warmup x{args.warmup}...')
        for _ in range(args.warmup):
            for _, path, body in cases:
                request(base_url, path, body)

    results = []
    for label, path, body in cases:
        times = []
        last = None
        for i in range(args.passes):
            last = request(base_url, path, body)
            times.append(last['ms'])
            status = last['status']
            err = f'  {last["error"]}' if last['error'] else ''
            print(f'  {last["ms"]:8.1f} ms  {status}  {label}{err}')
        med = statistics.median(times)
        results.append(dict(
            label=label,
            path=path,
            order=body.get('order_by') or body.get('order') or '',
            search=bool(body.get('search_str')),
            median_ms=med,
            min_ms=min(times),
            max_ms=max(times),
            status=last['status'] if last else None,
            total=last['total'] if last else None,
            bytes=last['bytes'] if last else None,
            error=last['error'] if last else None,
        ))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out = out_dir / f'search_order_{host_name}_{args.label}_{stamp}.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print()
    print(f'{"median_ms":>10}  {"min":>8}  {"max":>8}  {"total":>8}  case')
    print('-' * 80)
    for r in results:
        total = '' if r['total'] is None else str(r['total'])
        print(f'{r["median_ms"]:10.1f}  {r["min_ms"]:8.1f}  {r["max_ms"]:8.1f}  {total:>8}  {r["label"]}')
    print(f'\nwrote {out}')


if __name__ == '__main__':
    sys.exit(main() or 0)
