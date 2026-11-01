#!/usr/bin/env python3
"""Run libzim jobs (estimate, search, fetch entries) for the API.

Run by `modules.zim.lib.run_libzim_jobs` as a separate process: python-libzim never releases the GIL, and merely
opening a large Zim whose pages are not cached takes seconds (ten for a 75 GB Zim), so doing this in the API
worker would freeze every other request that worker is handling.

Reads `{"jobs": [...]}` from stdin and writes one result per job, in order, to stdout.  Every job names the Zim
`path` and an `op`:

    {"op": "estimate", "search_str": ...}            -> {"estimate": int}
    {"op": "search", "search_str": ..., "offset": ..., "limit": ...}
                                                      -> {"estimate": int, "entries": [{"path", "title", "content"}]}
    {"op": "entries", "paths": [...]}                 -> {"entries": [{"path", "title", "content"}]}
    {"op": "metadata"}                                -> {} (with the metadata below)

Any job may add `"metadata": true` to also get the Zim's metadata.  A job that fails returns `{"error": str}`
so one bad Zim does not hide the rest.  Imports only the standard library and libzim; it is run with
`python -I` from any working directory.
"""
import json
import sys

from libzim.reader import Archive
from libzim.search import Query, Searcher
from libzim.suggestion import SuggestionSearcher

METADATA_KEYS = ('Date', 'Creator', 'Description', 'Name', 'Publisher', 'Tags', 'Title')


def get_metadata(archive: Archive) -> dict:
    metadata = dict()
    for key in METADATA_KEYS:
        try:
            metadata[key.lower()] = archive.get_metadata(key).decode()
        except RuntimeError:
            metadata[key.lower()] = None
    return metadata


def unique_paths(*paths: str) -> list:
    """The first of any paths that differ only in case, dashes, underscores or slashes (disambiguation or
    redirect entries)."""
    seen, unique = set(), list()
    for path in paths:
        key = path.replace('-', '').replace('_', '').replace('/', '').lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def entry_dict(archive: Archive, path: str) -> dict:
    entry = archive.get_entry_by_path(path)
    return dict(path=entry.path, title=entry.title, content=bytes(entry.get_item().content).decode('UTF-8'))


def run_job(job: dict) -> dict:
    archive = Archive(job['path'])
    op = job['op']
    result = dict()
    if op == 'estimate':
        query = Query().set_query(job['search_str'])
        result['estimate'] = Searcher(archive).search(query).getEstimatedMatches()
    elif op == 'search':
        search_str, offset, limit = job['search_str'], job['offset'], job['limit']
        query = Query().set_query(search_str)
        # Suggestions search the titles.
        suggested = list(SuggestionSearcher(archive).suggest(search_str).getResults(offset, limit))
        search = Searcher(archive).search(query)
        found = list(search.getResults(offset, limit))
        paths = unique_paths(*suggested, *found)[:limit]
        result['estimate'] = search.getEstimatedMatches()
        result['entries'] = [entry_dict(archive, i) for i in paths]
    elif op == 'entries':
        result['entries'] = [entry_dict(archive, i) for i in job['paths']]
    elif op == 'metadata':
        job['metadata'] = True
    else:
        raise ValueError(f'Unknown op {op!r}')
    if job.get('metadata'):
        result['metadata'] = get_metadata(archive)
    return result


def main():
    request = json.load(sys.stdin)
    results = list()
    for job in request['jobs']:
        try:
            results.append(run_job(job))
        except Exception as e:
            print(f'{job.get("path")}: {e}', file=sys.stderr)
            results.append(dict(error=str(e)))
    json.dump(results, sys.stdout)


if __name__ == '__main__':
    main()
