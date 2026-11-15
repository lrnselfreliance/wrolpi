import json
import math
import re
from http import HTTPStatus

import pymupdf
import pytest

from modules.map import export, magnetic, sheet
from modules.map.export import ExportLayer, InvalidExport, Sheet, build_layered_pdf
from modules.map.test.test_export import MULTIPART, export_form, layer_names, make_image, read_viewport

# A quadrangle of Anchorage, and the size of its image: 11 by 22.9 inches of paper at 36 DPI.
ANCHORAGE = [-150, 61.125, -149.875, 61.25]
WIDTH, HEIGHT, DPI = 397, 824, 36
MAP_WIDTH, MAP_HEIGHT = WIDTH * 72 / DPI, HEIGHT * 72 / DPI
SHEET = Sheet(name='61°07′30″N 150°00′W', credits=['© OpenStreetMap contributors', 'Protomaps'],
              date='2026-11-15')


def build(bounds=None, sheet_=SHEET, **kwargs) -> bytes:
    return build_layered_pdf([ExportLayer('Background', make_image(size=(WIDTH, HEIGHT)))], WIDTH, HEIGHT, DPI,
                             bounds=bounds or ANCHORAGE, sheet=sheet_, **kwargs)


def page_text(pdf: bytes) -> str:
    return pymupdf.open(stream=pdf, filetype='pdf')[0].get_text()


@pytest.mark.parametrize('latitude,longitude,zone,south,easting,northing', [
    # As PROJ has them (gdaltransform, EPSG:326xx and 327xx).
    (61.2181, -149.9003, 6, False, 344247.206470396, 6790536.87132859),
    (61.125, -150, 6, False, 338419.895396155, 6780416.03492079),
    (40.2802, -111.9345, 12, False, 420557.776669581, 4459276.30827112),
    (-33.87, 151.21, 56, True, 334435.70614183, 6250816.39780466),
])
def test_utm(latitude, longitude, zone, south, easting, northing):
    """A place has the UTM coordinates PROJ gives it, to a millimeter, and they are of that place."""
    assert sheet.utm_zone(longitude) == zone
    assert sheet.to_utm(latitude, longitude, zone, south) == pytest.approx((easting, northing), abs=0.001)
    assert sheet.from_utm(easting, northing, zone, south) == pytest.approx((latitude, longitude), abs=1e-8)


def test_utm_zone():
    assert [sheet.utm_zone(i) for i in (-180, -174.001, -174, 0, 179.999, 180)] == [1, 1, 2, 31, 60, 60]


def test_format_angle():
    assert sheet.format_angle(61.125, 'N', 'S') == '61°07\'30"N'
    assert sheet.format_angle(-150, 'E', 'W') == "150°00'W"
    assert sheet.format_angle(-33.875, 'N', 'S') == '33°52\'30"S'
    assert sheet.format_angle(61.125, short=True) == '07\'30"'
    assert sheet.format_angle(-149.9166666667, short=True) == "55'"
    # Seconds which round up to a minute.
    assert sheet.format_angle(2.9999999) == "3°00'"


def test_graticule_interval():
    """A 7.5 minute map has a tick every 2.5 minutes; a larger map has them further apart."""
    assert sheet.graticule_interval(0.125) == pytest.approx(2.5 / 60)
    assert sheet.graticule_interval(0.25) == pytest.approx(5 / 60)
    assert sheet.graticule_interval(1) == pytest.approx(15 / 60)
    assert sheet.graticule_interval(1e-9) == pytest.approx(1 / 3600)


def test_map_scale():
    """The quadrangle the browser draws for a 1:24,000 sheet is 1:24,000."""
    assert sheet.map_scale(MAP_WIDTH, ANCHORAGE) == pytest.approx(24000, rel=0.005)
    assert sheet.map_scale(MAP_WIDTH * 2, ANCHORAGE) == pytest.approx(12000, rel=0.005)


def test_plan():
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, SHEET)
    x0, y0, x1, y1 = plan.map_rect
    assert (x1 - x0, y1 - y0) == pytest.approx((MAP_WIDTH, MAP_HEIGHT))
    # There is a margin on every side, and the most of it is under the map.
    assert x0 > 36 and y0 > 36 and plan.width - x1 > 36
    assert plan.height - y1 > y0
    assert plan.zone == 6 and not plan.south_hemisphere
    # The corners of the map are the corners of its rectangle.
    assert plan.point(61.25, -150) == pytest.approx((x0, y0))
    assert plan.point(61.125, -149.875) == pytest.approx((x1, y1))
    notes = ' '.join(plan.notes)
    assert 'Scale 1:24,000' in notes
    assert 'zone 6N' in notes and 'west of true north' in notes
    assert 'Map data: © OpenStreetMap contributors; Protomaps' in notes
    assert 'Made with WROLPi, 2026-11-15.' in notes


def test_plan_notes_fit_the_map():
    """Notes too long for the map are on more lines, and the page is longer for them."""
    short = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, Sheet())
    long = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, Sheet(credits=['Somebody who made a map'] * 20))
    assert len(long.notes) > len(short.notes)
    assert long.height > short.height
    assert all(pymupdf.get_text_length(i, fontsize=sheet.NOTE_SIZE) <= MAP_WIDTH for i in long.notes)


class FakePen:
    def __init__(self):
        self.lines, self.texts = [], []

    def line(self, points, **kwargs):
        self.lines.append(list(points))

    def text(self, x, y, text, **kwargs):
        self.texts.append((x, y, text, kwargs.get('align', 'left')))


def place_at(plan, x, y):
    """The latitude and longitude of a point of the page."""
    x0, y0, x1, y1 = plan.map_rect
    west, south, east, north = plan.bounds
    top, bottom = (math.log(math.tan(math.pi / 4 + math.radians(i) / 2)) for i in (north, south))
    mercator = top - (y - y0) / (y1 - y0) * (top - bottom)
    return math.degrees(2 * math.atan(math.exp(mercator)) - math.pi / 2), west + (x - x0) / (x1 - x0) * (east - west)


@pytest.mark.parametrize('bounds,zone,south', [
    (ANCHORAGE, 6, False),
    ([151.125, -33.875, 151.25, -33.75], 56, True),
    ([0, 0, 0.125, 0.125], 31, False),
])
def test_grid_lines_are_where_they_say(bounds, zone, south):
    """Every line of the grid is on a whole kilometer of UTM along all of it, and is nowhere off the map."""
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, bounds, Sheet())
    assert (plan.zone, plan.south_hemisphere) == (zone, south)
    pen = FakePen()
    sheet._draw_grid(pen, plan)
    x0, y0, x1, y1 = plan.map_rect
    eastings, northings = set(), set()
    for line in pen.lines:
        places = [sheet.to_utm(*place_at(plan, x, y), zone, south) for x, y in line]
        for x, y in line:
            assert x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6
        spread_e = max(i[0] for i in places) - min(i[0] for i in places)
        value = places[0][0] if spread_e < 1 else places[0][1]
        assert value == pytest.approx(round(value / 1000) * 1000, abs=0.5)
        for easting, northing in places:
            assert (easting if spread_e < 1 else northing) == pytest.approx(value, abs=0.5)
        (eastings if spread_e < 1 else northings).add(round(value))
    # A quadrangle is several kilometers each way, and every kilometer has its line.
    for values in (eastings, northings):
        assert len(values) >= 5
        assert sorted(values) == list(range(min(values), max(values) + 1, 1000))

    # Each line is named in the margin: the first in full, the others by their kilometers.
    labels = [text for _, _, text, _ in pen.texts]
    for letter in ('mE', 'mN'):
        assert len([i for i in labels if i.endswith(letter)]) == 2, labels
    assert len([i for i in labels if i.isdigit()]) >= 12, labels
    # And where the line meets the edge of the map.
    for x, y, text, align in pen.texts:
        if align == 'center':
            edge = y0 if y < y0 else y1
            meters = int(text[:-2]) if text.endswith('mE') else int(text) * 1000
            assert sheet.to_utm(*place_at(plan, x, edge), zone, south)[0] == pytest.approx(meters, abs=0.5)


def test_grid_labels_keep_clear_of_coordinates():
    """A line of the grid which meets the edge where a coordinate is written is not named there."""
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, Sheet())
    pen = FakePen()
    sheet._draw_grid(pen, plan)
    across, up = sheet._graticule_labels(plan)
    for x, y, text, align in pen.texts:
        if align == 'center':
            assert all(not low < x < high for low, high in across), text
        else:
            assert all(not low < y - sheet.LABEL_SIZE * 0.35 < high for low, high in up), text


def test_clip():
    rect = (0, 0, 10, 10)
    assert sheet._clip([(-5, 5), (15, 5)], rect) == [[(0, 5), (10, 5)]]
    assert sheet._clip([(2, 2), (4, 4), (6, 2)], rect) == [[(2, 2), (4, 4), (6, 2)]]
    # Out of the rectangle and in again is two lines.
    assert sheet._clip([(2, 5), (5, 15), (8, 5)], rect) == [[(2, 5), (3.5, 10)], [(6.5, 10), (8, 5)]]
    assert sheet._clip([(-5, -5), (-1, 20)], rect) == []
    assert sheet._clip([(5, 5)], rect) == []


def test_sheet_pdf():
    """A map on a sheet is in the middle of a larger page, with its grid and its margin in layers of their own."""
    plain = build_layered_pdf([ExportLayer('Background', make_image(size=(WIDTH, HEIGHT)))], WIDTH, HEIGHT, DPI,
                              bounds=ANCHORAGE)
    pdf = build()
    assert layer_names(plain) == ['Background']
    assert layer_names(pdf) == ['Background', 'UTM grid', 'Sheet']

    doc = pymupdf.open(stream=pdf, filetype='pdf')
    page = doc[0]
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, SHEET)
    assert (page.rect.width, page.rect.height) == pytest.approx((plan.width, plan.height), abs=0.01)
    # The map is as large as it is without the sheet.
    image = page.get_image_rects(page.get_images()[0][0])[0]
    assert tuple(image) == pytest.approx(plan.map_rect, abs=0.01)

    text = page.get_text()
    # The name and the scale, the corners, the ticks between them, the grid, the bars and the notes.
    for expected in ('61°07\'30"N 150°00\'W', '1:24,000', "150°00'W", '149°52\'30"W', "61°15'N", '61°07\'30"N',
                     "55'", '57\'30"', "10'", '12\'30"', '6790', '342', 'mE', 'mN', 'SCALE 1:24,000', 'KILOMETERS',
                     'MILES', 'FEET', '7000', 'zone 6N', '© OpenStreetMap contributors; Protomaps',
                     'Made with WROLPi, 2026-11-15.'):
        assert expected in text, expected


def test_sheet_layers_can_be_hidden():
    """The grid and the margin are drawn only in their own layers."""
    doc = pymupdf.open(stream=build(), filetype='pdf')
    full = doc[0].get_pixmap(dpi=36)
    for config in doc.layer_ui_configs():
        if config['text'] in ('UTM grid', 'Sheet'):
            doc.set_layer_ui_config(config['number'], action=2)
    hidden = doc[0].get_pixmap(dpi=36)
    assert full.samples != hidden.samples
    # Only the map is left: the margin is as white as paper.
    assert hidden.pixel(5, 5) == (255, 255, 255)
    assert hidden.color_count() == 2


def test_sheet_georeference_is_of_the_map():
    """The PDF says where the map is, not where the page is."""
    pdf = build()
    viewport = read_viewport(pdf)
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, SHEET)
    x0, y0, x1, y1 = plan.map_rect
    assert viewport['bbox'] == pytest.approx([x0, plan.height - y1, x1, plan.height - y0], abs=0.01)
    assert viewport['lpts'] == [0, 1, 0, 0, 1, 0, 1, 1]
    assert viewport['gpts'] == [61.25, -150, 61.125, -150, 61.125, -149.875, 61.25, -149.875]


def test_sheet_near_a_pole_has_no_grid():
    """UTM stops at 84 degrees north and 80 south."""
    pdf = build(bounds=[0, 84.5, 0.125, 84.625])
    assert layer_names(pdf) == ['Background', 'Sheet']
    assert 'Universal Transverse Mercator' not in page_text(pdf)
    assert 'UTM grid' in layer_names(build(bounds=[0, -80, 0.125, -79.875]))


def test_sheet_of_a_narrow_map():
    """A map too narrow for a scale bar goes without it."""
    narrow = build_layered_pdf([ExportLayer('Background', make_image(size=(90, 400)))], 90, 400, DPI,
                               bounds=[0, 84.5, 0.125, 84.625], sheet=Sheet())
    assert 'MILES' not in page_text(narrow)


@pytest.mark.parametrize('bounds,name', [
    # The narrowest quadrangles there are, with the longest names.
    ([-179.875, 84.875, -179.75, 85], '84°52′30″N 179°52′30″W'),
    ([-179.875, -84.875, -179.75, -84.75], '84°52′30″S 179°52′30″W'),
    ([10, 84.875, 10.125, 85], '84°52′30″N 10°00′E'),
    (ANCHORAGE, '61°07′30″N 150°00′W'),
])
def test_sheet_title_of_a_narrow_map(bounds, name):
    """The name of a map and its scale are not written over each other, however narrow the map is."""
    # As wide as the paper of a 1:24,000 sheet is.
    map_width = sheet.map_scale(1, bounds) / 24000
    width, height = round(map_width * DPI / 72), 400
    pdf = build_layered_pdf([ExportLayer('Background', make_image(size=(width, height)))], width, height, DPI,
                            bounds=bounds, sheet=Sheet(name=name))
    page = pymupdf.open(stream=pdf, filetype='pdf')[0]
    titles = [pymupdf.Rect(span['bbox']) for block in page.get_text('dict')['blocks'] for line in block.get('lines', [])
              for span in line['spans'] if span['size'] == pytest.approx(sheet.TITLE_SIZE)]
    assert len(titles) == 2, titles
    assert not titles[0].intersects(titles[1]), titles
    # Both are on the page, above the map and what is written along its top edge.
    top = sheet.plan_sheet(map_width, height * 72 / DPI, bounds, Sheet(name=name)).map_rect[1]
    for title in titles:
        assert title in page.rect
        assert title.y1 <= top - sheet.LABEL_SIZE


def test_plan_norths():
    """A sheet says how far the grid's north and a compass's north are from true north, at the middle of it."""
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, SHEET)
    # West of the middle of its zone the grid leans west; a compass in Alaska points well east.
    assert plan.grid_north == pytest.approx(-2.571, abs=0.001)
    assert plan.magnetic_north == pytest.approx(magnetic.declination(61.1875, -149.9375, 2026 + 318 / 365), abs=0.01)
    assert 13 < plan.magnetic_north < 15
    notes = ' '.join(plan.notes)
    assert "Grid north is 2°34' west of true north" in notes
    assert re.search(r"Magnetic north is 13°5\d' east of true north at the middle of the map on 2026-11-15,"
                     r" and moves about 0°1\d' west each year \(WMM-2025\)\.", notes), notes


@pytest.mark.parametrize('date', [None, 'yesterday', '', '2024-12-31', '2030-01-01', '2026-13-45'])
def test_plan_without_a_compass(date):
    """Where a compass points is not said when the day is not known, or is not one the model is of."""
    plan = sheet.plan_sheet(MAP_WIDTH, MAP_HEIGHT, ANCHORAGE, Sheet(date=date))
    assert plan.magnetic_north is None
    assert 'Magnetic' not in ' '.join(plan.notes)
    assert plan.grid_north is not None


def test_decimal_year():
    assert sheet._decimal_year('2026-01-01') == 2026
    assert sheet._decimal_year('2026-07-02') == pytest.approx(2026.4986, abs=0.0001)
    assert sheet._decimal_year('2028-12-31T10:00:00') == pytest.approx(2028 + 365 / 366)


def test_norths_are_on_their_own_sides():
    """In the diagram a north is drawn on the side of true north it is on, and apart from it however near it
    is."""
    assert sheet._north_tip(0, 0, 14, 50)[0] > 0 > sheet._north_tip(0, 0, -2.5, 50)[0]
    # A north a tenth of a degree off, and one eighty off, are both drawn where they can be seen.
    near, far = sheet._north_tip(0, 0, 0.1, 50), sheet._north_tip(0, 0, -80, 50)
    assert near[0] == pytest.approx(50 * math.sin(math.radians(7)))
    assert far == pytest.approx((-25, -50 * math.cos(math.radians(30))))


def test_sheet_norths_diagram():
    """The diagram of the norths is beside the scale bars, with each angle written; a sheet too narrow for it,
    or with nothing to put in it, goes without."""
    text = page_text(build())
    assert 'MN 13°' in text and 'E\n' in text
    assert 'GN 2°34\' W' in text

    # No compass: the grid's north is still drawn.
    text = page_text(build(sheet_=Sheet()))
    assert 'GN 2°34\' W' in text and 'MN' not in text

    # No grid near a pole, but a compass points somewhere; the quadrangle is too narrow for the diagram.
    narrow = build_layered_pdf([ExportLayer('Background', make_image(size=(90, 400)))], 90, 400, DPI,
                               bounds=[0, 84.5, 0.125, 84.625], sheet=Sheet(date='2026-11-15'))
    text = page_text(narrow)
    assert 'Magnetic north is' in text
    assert 'MN ' not in text and 'GN ' not in text


def test_sheet_text_which_the_font_can_not_write():
    pdf = build(sheet_=Sheet(name='Карта “map” – 地図', credits=['<b>© Somebody</b>\n\nelse']))
    text = page_text(pdf)
    assert '"map" -' in text
    assert '<b>© Somebody</b> else' in text


def test_sheet_needs_bounds():
    with pytest.raises(InvalidExport, match='edges of the map are needed'):
        build_layered_pdf([ExportLayer('Background', make_image())], 60, 90, 72, sheet=Sheet())


@pytest.mark.asyncio
async def test_api_export_pdf_sheet(async_client, make_multipart_form):
    images = [('Background', make_image(size=(WIDTH, HEIGHT)))]
    body = export_form(make_multipart_form, images, width=WIDTH, height=HEIGHT, dpi=DPI, bounds=ANCHORAGE,
                       sheet=dict(name='A quadrangle', credits=['Somebody', 'x' * 500] + ['More'] * 50,
                                  date='2026-11-15'))
    request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
    assert response.status_code == HTTPStatus.OK, response.text
    assert layer_names(response.content) == ['Background', 'UTM grid', 'Sheet']
    text = page_text(response.content)
    assert 'A quadrangle' in text and 'Somebody' in text
    # What is written on a sheet is limited.
    assert len(re.findall('More', text)) == 18
    assert 'x' * 201 not in text.replace('\n', '')

    # An empty sheet is a sheet.
    body = export_form(make_multipart_form, images, width=WIDTH, height=HEIGHT, dpi=DPI, bounds=ANCHORAGE, sheet={})
    request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
    assert response.status_code == HTTPStatus.OK, response.text
    assert 'Sheet' in layer_names(response.content)

    # A sheet which is not one, and a sheet of a map which is nowhere.
    for meta in (dict(bounds=ANCHORAGE, sheet='yes'), dict(sheet={})):
        body = export_form(make_multipart_form, images, width=WIDTH, height=HEIGHT, dpi=DPI, **meta)
        request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
        assert response.status_code == HTTPStatus.BAD_REQUEST, json.dumps(meta)
