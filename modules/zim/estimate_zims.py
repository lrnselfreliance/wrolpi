#!/usr/bin/env python3
"""Count the entries of Zim files that match a search string.

Run by `modules.zim.lib.estimate_zims` as a separate process: python-libzim never releases the GIL, and merely
opening a large Zim whose pages are not cached takes seconds (ten for a 75 GB Zim), so doing this in the API
worker would freeze every other request that worker is handling.

Reads `{"paths": [...], "search_str": "..."}` from stdin, writes the list of counts (in order) to stdout.  A Zim
that cannot be opened or searched counts as null, with the error on stderr, so one bad file does not hide the
rest.  Imports only the standard library and libzim; it is run with `python -I` from any working directory.
"""
import json
import sys

from libzim.reader import Archive
from libzim.search import Query, Searcher


def main():
    request = json.load(sys.stdin)
    query = Query().set_query(request['search_str'])
    counts = []
    for path in request['paths']:
        try:
            counts.append(Searcher(Archive(path)).search(query).getEstimatedMatches())
        except Exception as e:
            print(f'{path}: {e}', file=sys.stderr)
            counts.append(None)
    json.dump(counts, sys.stdout)


if __name__ == '__main__':
    main()
