import json

import pytest

from wrolpi.scripts import build_map_icons

SPRITES = build_map_icons.SPRITES_DIRECTORY
ICONS = build_map_icons.ICONS_DIRECTORY
SHEETS = ((1, ''), (2, '@2x'))


def _index(suffix: str) -> dict:
    return json.loads((SPRITES / f'overlay-icons{suffix}.json').read_text())


@pytest.mark.parametrize('pixel_ratio,suffix', SHEETS)
def test_sprite_index_is_the_icons_and_their_names(pixel_ratio, suffix):
    """The committed sprite index lists every name of every icon; run wrolpi/scripts/build_map_icons.py after
    changing the icons or their aliases."""
    index = _index(suffix)
    names = build_map_icons.find_names()
    assert sorted(index) == sorted(names)

    cells = {name: (i['x'], i['y']) for name, i in index.items()}
    for name, icon in names.items():
        # Every name of an icon is the same pixels.
        assert cells[name] == cells[icon], name
    # Each icon has pixels of its own (but for one whose name an alias gives to another icon).
    icons = [i for i in build_map_icons.find_icons() if names[i] == i]
    assert len({cells[i] for i in icons}) == len(icons)
    for image in index.values():
        assert image['sdf'] is True
        assert image['pixelRatio'] == pixel_ratio
        assert image['width'] == image['height'] == (build_map_icons.ICON_SIZE + 2 * build_map_icons.BUFFER) * pixel_ratio


def test_both_sheets_have_the_same_names():
    assert sorted(_index('')) == sorted(_index('@2x'))
    for suffix in ('', '@2x'):
        assert (SPRITES / f'overlay-icons{suffix}.png').stat().st_size > 10_000


def test_icon_names():
    """A style may spell a name with underscores or hyphens; an alias is what a name means on a map."""
    names = build_map_icons.find_names()
    assert names['hospital'] == 'hospital'
    assert names['fire_station'] == names['fire-station'] == 'fire-station'
    assert names['drinking_water'] == 'drinking-water'
    # Aliases, in both spellings.
    assert names['ham_radio'] == names['ham-radio'] == 'antenna'
    assert names['post_office'] == 'post'
    # An alias comes before the icon which happens to have the name.
    assert 'tower' in build_map_icons.find_icons()
    assert names['tower'] == 'communications-tower'


def test_aliases_are_of_icons_which_exist():
    icons = build_map_icons.find_icons()
    aliases = json.loads((ICONS / 'aliases.json').read_text())
    assert aliases
    assert {k: v for k, v in aliases.items() if v not in icons} == {}


def test_excluded_icons_are_not_shipped():
    """A logo is not an icon of the map."""
    excluded = json.loads((ICONS / 'exclude.json').read_text())
    assert 'temaki' in excluded
    names = build_map_icons.find_names()
    for name in excluded:
        assert name not in names
        assert name not in _index('')


def test_icon_sets_have_their_licenses():
    """The icons are other people's work, given to the public domain; their licenses are shipped with them."""
    assert 'CC0 1.0 Universal' in (ICONS / 'svg/maki/LICENSE.txt').read_text()
    assert 'CC0 1.0 Universal' in (ICONS / 'svg/temaki/LICENSE.md').read_text()
    notices = (SPRITES.parent / 'THIRD_PARTY_LICENSES.md').read_text()
    assert 'Maki' in notices and 'Temaki' in notices


def test_render_sdf(tmp_path):
    """An icon is a signed distance field: three quarters alpha at its edge, full inside, none far outside."""
    svg = tmp_path / 'square.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 15 15"><rect width="15" height="15"/></svg>')
    alpha = build_map_icons.render_sdf(svg, 1)
    cell = build_map_icons.ICON_SIZE + 2 * build_map_icons.BUFFER
    assert alpha.shape == (cell, cell)
    middle = cell // 2
    assert alpha[middle, middle] == 255
    # The corner of the cell is outside of the square, by the buffer.
    assert alpha[0, 0] < 191
    # Alpha falls going out across the edge.
    assert alpha[middle, build_map_icons.BUFFER + 1] > alpha[middle, build_map_icons.BUFFER - 1] > alpha[middle, 0]
    assert 150 < alpha[middle, build_map_icons.BUFFER - 1] < 230
