"""The MapLibre style the tiles are drawn with: the web map's basemap (MapViewer's `buildStyle`) for map files on
the disk.

`basemap-light.json` is the layers of the web map's light basemap, written from protomaps-themes-base (see
app/src/components/mapTileStyle.test.js), for a source named `protomaps`.  Each map file gets a source and the
layers of its own.  As on the web map: the first file's layers are as they are, every later file's are renamed
and leave out the background and the earth (which would cover the files before it), and every label is over the
ground of every file.
"""
import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

LAYERS_FILE = Path(__file__).with_name('basemap-light.json')
STATIC = Path(__file__).resolve().parents[1] / 'modules/map/static'
TEMPLATE_SOURCE = 'protomaps'
SKIP_SECONDARY = frozenset({'background', 'earth'})


@lru_cache
def _template() -> str:
    return LAYERS_FILE.read_text()


def basemap_layers(source: str) -> List[dict]:
    layers = json.loads(_template())
    for layer in layers:
        if layer.get('source') == TEMPLATE_SOURCE:
            layer['source'] = source
    return layers


def has_fonts(static: Path = STATIC) -> bool:
    """Whether the map's fonts are installed (unpacked from a blob, not in the repository)."""
    return any((static / 'fonts').glob('*/0-255.pbf'))


def build_style(maps: List[Path], static: Path = STATIC) -> dict:
    """The style which draws these PMTiles files, the first under the rest.

    Without the map's fonts a label cannot be drawn, and MapLibre fails the whole tile; the labels are left out."""
    sources = dict()
    layers = []
    for index, path in enumerate(maps):
        name = f'{index}-{path.stem}'
        sources[name] = dict(type='vector', url=f'pmtiles://file://{path}')
        for layer in basemap_layers(name):
            if index == 0:
                layers.append(layer)
            elif layer['id'] not in SKIP_SECONDARY:
                layers.append(dict(layer, id=f'{name}:{layer["id"]}'))
    if not sources:
        # No map files: the background alone, which every tile is drawn as.
        layers = [i for i in basemap_layers(TEMPLATE_SOURCE) if i['type'] == 'background']
    labels = [i for i in layers if i['type'] == 'symbol']
    layers = [i for i in layers if i['type'] != 'symbol']
    style = dict(version=8, sprite=f'file://{static}/sprites/light', sources=sources)
    if has_fonts(static):
        style['glyphs'] = f'file://{static}/fonts/{{fontstack}}/{{range}}.pbf'
        layers += labels  # over the ground of every file
    elif labels:
        logger.warning(f'The map fonts are not in {static / "fonts"}: tiles are drawn without labels')
    style['layers'] = layers
    return style


def style_id(style: dict, signature) -> str:
    """Names a style and the map files it draws: tiles drawn with one are never served for another."""
    digest = hashlib.sha256(json.dumps([style, signature], sort_keys=True).encode()).hexdigest()
    return digest[:16]


def background_color(style: dict) -> str:
    """The color of a tile of nowhere the map files have anything (`#rrggbb`)."""
    for layer in style['layers']:
        if layer['type'] == 'background':
            color = layer.get('paint', {}).get('background-color')
            if isinstance(color, str) and color.startswith('#') and len(color) in (4, 7):
                return color
    return '#cccccc'
