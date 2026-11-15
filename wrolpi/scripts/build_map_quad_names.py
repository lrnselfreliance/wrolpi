#!/usr/bin/env python3
"""Make the index of the names of the USGS 7.5 minute quadrangles which WROLPi ships
(modules/map/quads/usgs_7_5_minute.tsv.gz).

The names are from the Map Indices of The National Map (U.S. Geological Survey; public domain):

    https://prd-tnm.s3.amazonaws.com/StagedProducts/MapIndices/National/GDB/MapIndices_National_GDB.zip

Its cells are read with GDAL, which WROLPi does not need otherwise, so that is done first and by hand:

    ogr2ogr -f CSV cells.csv MapIndices_National_GDB.gdb -dialect SQLite -sql "SELECT CELL_NAME, PRIMARY_STATE,
        ST_MinX(SHAPE) AS west, ST_MinY(SHAPE) AS south, ST_MaxX(SHAPE) AS east, ST_MaxY(SHAPE) AS north
        FROM CellGrid_7_5Minute"

    python3 wrolpi/scripts/build_map_quad_names.py cells.csv

The index is a line for each quadrangle: its south, west, east and north edges (whole seconds of arc), its name
and its state, between tabs; the lines are in order.
"""
import argparse
import csv
import gzip
import pathlib
import sys

OUTPUT = pathlib.Path(__file__).resolve().parents[2] / 'modules/map/quads/usgs_7_5_minute.tsv.gz'


def seconds(degrees: str) -> int:
    return round(float(degrees) * 3600)


def read_cells(path: pathlib.Path) -> list:
    cells = []
    with path.open(newline='') as fh:
        for row in csv.DictReader(fh):
            name, state = row['CELL_NAME'].strip(), row['PRIMARY_STATE'].strip()
            if not name or not state or state == 'None':
                # A cell which is of no state is of no map.
                continue
            if '\t' in name or '\t' in state:
                raise ValueError(f'A tab in the name of a quadrangle: {name!r} {state!r}')
            south, west, east, north = (seconds(row[i]) for i in ('south', 'west', 'east', 'north'))
            if not (south < north and west < east):
                raise ValueError(f'The quadrangle {name!r} has no size: {row}')
            cells.append((south, west, east, north, name, state))
    return sorted(cells)


def write_index(cells: list, path: pathlib.Path):
    text = ''.join('\t'.join(str(i) for i in cell) + '\n' for cell in cells)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as fh:
        # No name and no time in the file, so the same cells are the same bytes.
        with gzip.GzipFile(filename='', mode='wb', fileobj=fh, mtime=0, compresslevel=9) as gz:
            gz.write(text.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('cells', type=pathlib.Path, help='The CSV of the cells, as ogr2ogr writes it')
    parser.add_argument('--output', type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()
    cells = read_cells(args.cells)
    write_index(cells, args.output)
    print(f'{len(cells)} quadrangles, {args.output.stat().st_size} bytes: {args.output}', file=sys.stderr)


if __name__ == '__main__':
    main()
