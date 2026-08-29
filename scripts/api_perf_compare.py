#!/usr/bin/env python3
"""
Merge the CSVs written by scripts/api_perf.py into one cross-host table.

    python3 scripts/api_perf_compare.py perf_results/*.csv
    python3 scripts/api_perf_compare.py perf_results/*.csv --sort hot --top 25
    python3 scripts/api_perf_compare.py perf_results/*.csv --markdown > perf_results/summary.md

For each endpoint and host prints cold (ms, first request after an API restart) and hot median
(ms, over the hot passes).  When several CSVs exist for the same host the newest one wins.
"""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def load(paths):
    # host -> newest file
    newest = {}
    for p in paths:
        host = p.stem.rsplit('_', 2)[0]
        if host not in newest or p.stat().st_mtime > newest[host].stat().st_mtime:
            newest[host] = p
    data = defaultdict(lambda: defaultdict(lambda: dict(cold=None, cold_each=None, hot=[], status=set())))
    order = []
    for host, p in sorted(newest.items()):
        with open(p) as f:
            for row in csv.DictReader(f):
                d = data[row['name']][host]
                ms = float(row['ms'])
                if row['phase'] == 'cold':
                    d['cold'] = ms
                elif row['phase'] == 'cold-each':
                    d['cold_each'] = ms
                elif row['phase'] == 'hot':
                    d['hot'].append(ms)
                d['status'].add(row['status'])
                if row['name'] not in order:
                    order.append(row['name'])
    return sorted(newest), data, order


def fmt(v):
    if v is None:
        return '-'
    return f'{v:,.0f}'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csvs', nargs='+', type=Path)
    ap.add_argument('--sort', choices=['catalog', 'hot', 'cold'], default='catalog',
                    help='catalog order (default), or by worst hot median / worst cold across hosts.')
    ap.add_argument('--top', type=int, help='Only print the first N rows after sorting.')
    ap.add_argument('--markdown', action='store_true')
    args = ap.parse_args()

    hosts, data, order = load(args.csvs)

    def hot_med(name, host):
        h = data[name][host]['hot']
        return statistics.median(h) if h else None

    def worst(name, key):
        vals = [data[name][h][key] if key == 'cold' else hot_med(name, h) for h in hosts]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else -1

    names = list(order)
    if args.sort == 'hot':
        names.sort(key=lambda n: -worst(n, 'hot'))
    elif args.sort == 'cold':
        names.sort(key=lambda n: -worst(n, 'cold'))
    if args.top:
        names = names[:args.top]

    cols = ['endpoint'] + [f'{h} cold' for h in hosts] + [f'{h} hot' for h in hosts]
    rows = []
    for n in names:
        row = [n]
        for h in hosts:
            d = data[n][h]
            c = d['cold_each'] if d['cold_each'] is not None else d['cold']
            bad = d['status'] and d['status'] != {'200'}
            row.append(fmt(c) + ('*' if d['cold_each'] is not None else '') + (' !' if bad else ''))
        for h in hosts:
            row.append(fmt(hot_med(n, h)))
        rows.append(row)

    if args.markdown:
        print('| ' + ' | '.join(cols) + ' |')
        print('|' + '|'.join(['---'] + ['---:'] * (len(cols) - 1)) + '|')
        for r in rows:
            print('| ' + ' | '.join(r) + ' |')
    else:
        widths = [max(len(str(x)) for x in col) for col in zip(cols, *rows)]
        line = '  '.join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(cols, widths)))
        print(line)
        print('-' * len(line))
        for r in rows:
            print('  '.join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))))
    print('\nms; cold = first request after API restart (* = own restart via --cold-each); hot = median of hot passes;'
          ' ! = non-200 seen')


if __name__ == '__main__':
    main()
