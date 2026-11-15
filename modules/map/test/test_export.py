import io
import json
import math
import re
import subprocess
import sys
from http import HTTPStatus
from unittest import mock

import pymupdf
import pytest
from PIL import Image

from modules.map import export
from modules.map.export import ExportLayer, InvalidExport, build_layered_pdf

WIDTH, HEIGHT = 60, 90


def make_image(color=(200, 80, 20, 255), size=(WIDTH, HEIGHT), image_format='PNG', box=None) -> bytes:
    """An image of a layer: transparent, with `color` in `box` (all of it by default)."""
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    image.paste(color, box or (0, 0, *size))
    if image_format == 'JPEG':
        image = image.convert('RGB')
    data = io.BytesIO()
    image.save(data, image_format)
    return data.getvalue()


BLANK = make_image(color=(0, 0, 0, 0))


def layer_names(pdf: bytes) -> list:
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    return [i['name'] for _, i in sorted(doc.get_ocgs().items())]


def test_layers_are_pdf_layers():
    """Each image of the map is in a PDF layer of its own, named and in the order given, on one page the size
    the map is at its DPI."""
    pdf = build_layered_pdf([
        ExportLayer('Background', make_image((240, 240, 230, 255))),
        ExportLayer('Water', make_image((60, 120, 220, 255), box=(0, 0, 30, 90))),
        ExportLayer('Satellite', make_image(image_format='JPEG')),
    ], WIDTH, HEIGHT, dpi=300, title='40°15′N 112°00′W')

    doc = pymupdf.open(stream=pdf, filetype='pdf')
    assert doc.page_count == 1
    page = doc[0]
    # 60x90 pixels at 300 DPI is 0.2x0.3 inches: 14.4x21.6 points.
    assert (round(page.rect.width, 3), round(page.rect.height, 3)) == (14.4, 21.6)
    assert layer_names(pdf) == ['Background', 'Water', 'Satellite']
    assert all(i['on'] for i in doc.get_ocgs().values())
    assert doc.metadata['title'] == '40°15′N 112°00′W'

    # Every image fills the page, and is the picture it was given.
    images = page.get_image_info(xrefs=True)
    assert len(images) == 3
    for image in images:
        assert (image['width'], image['height']) == (WIDTH, HEIGHT)
        assert pymupdf.Rect(image['bbox']) == page.rect

    # The page looks like the layers stacked: water over the background on the left... but the satellite image
    # is on top of both, and is all one color.
    pixmap = page.get_pixmap(dpi=300)
    assert pixmap.pixel(5, 5)[:3] == pixmap.pixel(55, 85)[:3]


def test_layers_are_stacked_in_order():
    """The first layer is at the bottom: what is above it covers it, and shows it where it is transparent."""
    pdf = build_layered_pdf([
        ExportLayer('Background', make_image((255, 255, 255, 255))),
        ExportLayer('Water', make_image((0, 0, 255, 255), box=(0, 0, 30, 90))),
    ], WIDTH, HEIGHT, dpi=72)
    pixmap = pymupdf.open(stream=pdf, filetype='pdf')[0].get_pixmap(dpi=72)
    assert pixmap.pixel(10, 45) == (0, 0, 255)
    assert pixmap.pixel(50, 45) == (255, 255, 255)


def test_hidden_layer_is_not_drawn():
    """A layer of the PDF can be turned off, which is the point of there being layers."""
    pdf = build_layered_pdf([
        ExportLayer('Background', make_image((255, 255, 255, 255))),
        ExportLayer('Water', make_image((0, 0, 255, 255))),
    ], WIDTH, HEIGHT, dpi=72)
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    assert doc[0].get_pixmap(dpi=72).pixel(10, 45) == (0, 0, 255)

    # As a reader does it: clear the layer's box in the list of layers.
    water, = [i['number'] for i in doc.layer_ui_configs() if i['text'] == 'Water']
    doc.set_layer_ui_config(water, action=2)
    assert doc[0].get_pixmap(dpi=72).pixel(10, 45) == (255, 255, 255)


def test_blank_layer_is_left_out():
    """A layer in which nothing was drawn (no tunnels in this quadrangle) is not a layer of the PDF."""
    pdf = build_layered_pdf([
        ExportLayer('Background', make_image()),
        ExportLayer('Roads - Tunnels', BLANK),
        ExportLayer('Labels', make_image(box=(1, 1, 2, 2))),
    ], WIDTH, HEIGHT, dpi=300)
    assert layer_names(pdf) == ['Background', 'Labels']

    with pytest.raises(InvalidExport, match='Nothing is drawn'):
        build_layered_pdf([ExportLayer('Roads - Tunnels', BLANK)], WIDTH, HEIGHT, dpi=300)


@pytest.mark.parametrize('layers,width,height,dpi,error', [
    ([], WIDTH, HEIGHT, 300, 'no layers'),
    ([ExportLayer('A', make_image())] * (export.MAX_LAYERS + 1), WIDTH, HEIGHT, 300, 'more than'),
    # Not the size the map is said to be.
    ([ExportLayer('A', make_image(size=(61, 90)))], WIDTH, HEIGHT, 300, '61x90'),
    # Not an image, and not a kind of image the map is drawn as.
    ([ExportLayer('A', b'not an image')], WIDTH, HEIGHT, 300, 'not a readable image'),
    ([ExportLayer('A', make_image(image_format='GIF'))], WIDTH, HEIGHT, 300, 'not a PNG or JPEG'),
    # Sizes no map is.
    ([ExportLayer('A', make_image())], 0, HEIGHT, 300, '0x90'),
    ([ExportLayer('A', make_image())], export.MAX_SIDE + 1, 10, 300, 'can not be exported'),
    ([ExportLayer('A', make_image())], 10000, 10000, 300, 'can not be exported'),
    # Each layer is a size a map is, but all of them together are more than there is memory for.
    ([ExportLayer('A', b'never decoded')] * 30, 6000, 8000, 300, 'too large to export'),
    ([ExportLayer('A', make_image())], WIDTH, HEIGHT, 0, 'DPI'),
    ([ExportLayer('A', make_image())], WIDTH, HEIGHT, 5000, 'DPI'),
])
def test_invalid_export(layers, width, height, dpi, error):
    with pytest.raises(InvalidExport, match=error):
        build_layered_pdf(layers, width, height, dpi)


MULTIPART = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}


def export_form(make_multipart_form, images, **meta):
    meta = dict(dict(width=WIDTH, height=HEIGHT, dpi=300, layers=[name for name, _ in images]), **meta)
    return make_multipart_form([
        dict(name='meta', value=json.dumps(meta)),
        *[dict(name='layer', value=image, filename=f'{index}.png') for index, (_, image) in enumerate(images)],
    ])


@pytest.mark.asyncio
async def test_api_export_pdf(async_client, make_multipart_form):
    """The images of a map's layers are sent, and the PDF of them comes back."""
    body = export_form(make_multipart_form, [
        ('Background', make_image((240, 240, 230, 255))),
        ('Roads - Tunnels', BLANK),
        ('Water', make_image((60, 120, 220, 255), box=(0, 0, 30, 90))),
    ], title='A quadrangle')
    request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF-')
    assert layer_names(response.content) == ['Background', 'Water']
    assert pymupdf.open(stream=response.content, filetype='pdf').metadata['title'] == 'A quadrangle'


@pytest.mark.asyncio
async def test_api_export_pdf_invalid(async_client, make_multipart_form):
    """What is not a map is refused, and why is said."""
    def post(body):
        return async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)

    # No description of the map.
    request, response = await post(make_multipart_form([dict(name='layer', value=make_image(), filename='0.png')]))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'description of the map' in response.json['error']

    # A description which is not of a map.
    request, response = await post(export_form(make_multipart_form, [('A', make_image())], width='wide'))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # More names than images.
    request, response = await post(export_form(make_multipart_form, [('A', make_image())], layers=['A', 'B']))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert '2 layers, but 1 images' in response.json['error']

    # An image which is not of the map.
    request, response = await post(export_form(make_multipart_form, [('A', make_image(size=(10, 10)))]))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert '10x10' in response.json['error']


def test_total_pixels_are_limited_before_decoding():
    """The memory an export needs is the pixels of all its layers, which a small upload can be a great many of:
    it is refused without any image being opened."""
    with mock.patch('modules.map.export.Image.open') as image_open:
        with pytest.raises(InvalidExport, match='too large to export'):
            build_layered_pdf([ExportLayer(str(i), BLANK) for i in range(export.MAX_LAYERS)],
                              export.MAX_SIDE // 4, export.MAX_SIDE // 4, dpi=300)
    image_open.assert_not_called()

    # A quadrangle at 300 DPI near the equator, with every layer of a full layer control on, is within it.
    assert 24 * 5300 * 6900 <= export.MAX_TOTAL_PIXELS


def test_pymupdf_is_not_imported_with_the_module():
    """pymupdf is slow to import, and the API imports this module when it starts."""
    code = 'import sys, modules.map.api; print("pymupdf" in sys.modules)'
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == 'False'


def test_images_are_compressed_as_they_are_added():
    """The pixels of a layer are compressed in the PDF when the layer is added, not kept until it is written:
    kept, the layers of a quadrangle are more memory than a Raspberry Pi has to spare."""
    doc = pymupdf.open()
    page = doc.new_page(width=WIDTH, height=HEIGHT)
    export._insert_layer(doc, page, ExportLayer('Satellite', make_image(image_format='JPEG')))
    export._insert_layer(doc, page, ExportLayer('Water', make_image((0, 0, 255, 200), box=(0, 0, 30, 90))))

    streams = [xref for xref in range(1, doc.xref_length()) if doc.xref_is_stream(xref)]
    images = [xref for xref in streams if doc.xref_get_key(xref, 'Subtype')[1] == '/Image']
    # The picture and its transparency, and the photograph.
    assert len(images) == 3
    assert sorted(doc.xref_get_key(xref, 'Filter')[1] for xref in images) \
        == ['/DCTDecode', '/FlateDecode', '/FlateDecode']

    # And it is still the picture: blue, mostly opaque, over the left of the photograph.
    pixmap = page.get_pixmap(dpi=72, alpha=False)
    assert pixmap.pixel(50, 45) != pixmap.pixel(10, 45)


# A quadrangle at Anchorage: west, south, east, north.
ANCHORAGE = [-150.0, 61.125, -149.875, 61.25]


def read_viewport(pdf: bytes) -> dict:
    """What the first page of a PDF says of where it is: its /VP, as the text of each part."""
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    page = doc[0]
    kind, viewports = doc.xref_get_key(page.xref, 'VP')
    assert kind == 'array', f'The page has no /VP: {kind} {viewports}'

    def numbers(key):
        return [float(i) for i in re.search(rf'/{key}\s*\[([^]]*)]', viewports).group(1).split()]

    return dict(
        text=viewports,
        bbox=numbers('BBox'), bounds=numbers('Bounds'), gpts=numbers('GPTS'), lpts=numbers('LPTS'),
        page=(page.rect.width, page.rect.height),
    )


def test_pdf_says_where_it_is():
    """With the edges of the map, the page has a geospatial viewport: all of the page, in Web Mercator, with the
    latitude and longitude of each of its corners."""
    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72,
                            title='1:24,000 61°07′30″N 150°00′W', bounds=ANCHORAGE)
    viewport = read_viewport(pdf)

    # All of the page.
    assert viewport['bbox'] == [0, 0, WIDTH, HEIGHT]
    # The corners, from the lower left of the page: upper left, lower left, lower right, upper right...
    assert viewport['lpts'] == viewport['bounds'] == [0, 1, 0, 0, 1, 0, 1, 1]
    # ...and where each is: latitude, then longitude.
    assert viewport['gpts'] == [61.25, -150, 61.125, -150, 61.125, -149.875, 61.25, -149.875]

    text = viewport['text']
    assert '/Type/Viewport' in text.replace(' ', '') and '/Subtype/GEO' in text.replace(' ', '')
    assert '/EPSG 3857' in text
    assert 'PROJCS["WGS 84 / Pseudo-Mercator"' in text and 'AUTHORITY["EPSG","3857"]' in text

    # It is still the PDF it was.
    assert layer_names(pdf) == ['Background']
    assert pymupdf.open(stream=pdf, filetype='pdf')[0].get_pixmap(dpi=72).pixel(5, 5) == (200, 80, 20)


def test_corner_of_page_is_corner_of_map():
    """A reader finds where a point of the page is from the corners: here, as a reader does it, in the
    projection the page says it is in."""
    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72, bounds=ANCHORAGE)
    viewport = read_viewport(pdf)

    def mercator(latitude, longitude):
        return (math.radians(longitude) * 6378137,
                math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)) * 6378137)

    def unmercator(x, y):
        return math.degrees(2 * math.atan(math.exp(y / 6378137)) - math.pi / 2), math.degrees(x / 6378137)

    lpts, gpts = viewport['lpts'], viewport['gpts']
    corners = {(lpts[i], lpts[i + 1]): mercator(gpts[i], gpts[i + 1]) for i in range(0, 8, 2)}

    def where(across, up):
        """The latitude and longitude of a point of the page (0 to 1 from its lower left)."""
        (x0, y0), (x1, y1) = corners[(0, 0)], corners[(1, 1)]
        return unmercator(x0 + across * (x1 - x0), y0 + up * (y1 - y0))

    assert where(0, 0) == pytest.approx((61.125, -150))
    assert where(1, 1) == pytest.approx((61.25, -149.875))
    # The middle of the page is the middle of the map in longitude, and north of its middle in latitude: the
    # further north, the more of the page a degree is.
    latitude, longitude = where(0.5, 0.5)
    assert longitude == pytest.approx(-149.9375)
    assert 61.1875 < latitude < 61.1877
    # The other two corners are the corners of the same rectangle.
    assert corners[(0, 1)] == pytest.approx((corners[(0, 0)][0], corners[(1, 1)][1]))
    assert corners[(1, 0)] == pytest.approx((corners[(1, 1)][0], corners[(0, 0)][1]))


def test_pdf_without_edges_says_nothing_of_where_it_is():
    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72)
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    assert doc.xref_get_key(doc[0].xref, 'VP')[0] == 'null'


def test_viewport_name():
    """The viewport is named as the map is; a name which is not ASCII is written so a PDF can hold it."""
    viewport = export.geospatial_viewport(10, 10, ANCHORAGE, 'A quadrangle (of a map)')
    assert '/Name (A quadrangle \\(of a map\\))' in viewport
    assert '/Name' not in export.geospatial_viewport(10, 10, ANCHORAGE)

    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72,
                            title='61°07′30″N', bounds=ANCHORAGE)
    name = re.search(r'/Name\s*<([0-9A-Fa-f]+)>', read_viewport(pdf)['text']).group(1)
    assert bytes.fromhex(name).decode('utf-16') == '61°07′30″N'


@pytest.mark.parametrize('bounds', [
    [-150, 61.125, -149.875],  # Three edges.
    'here',
    [-150, 61.125, -149.875, 'north'],
    [-149.875, 61.125, -150, 61.25],  # East of its east.
    [-150, 61.25, -149.875, 61.125],  # North of its north.
    [-150, 61.125, -150, 61.25],  # No width.
    [-190, 61.125, -149.875, 61.25],  # Off the world.
    [-150, 61.125, -149.875, 89],  # Further north than the map goes.
    [-150, float('nan'), -149.875, 61.25],
])
def test_invalid_bounds(bounds):
    with pytest.raises(InvalidExport, match='edges'):
        build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72, bounds=bounds)


@pytest.mark.asyncio
async def test_api_export_pdf_georeferenced(async_client, make_multipart_form):
    """The edges of the map are sent with its images, and the PDF says where it is."""
    images = [('Background', make_image())]
    body = export_form(make_multipart_form, images, bounds=ANCHORAGE)
    request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
    assert response.status_code == HTTPStatus.OK, response.text
    assert read_viewport(response.content)['gpts'] == [61.25, -150, 61.125, -150, 61.125, -149.875, 61.25, -149.875]

    # Without them it is a PDF all the same.
    request, response = await async_client.post(
        '/api/map/export/pdf', content=export_form(make_multipart_form, images), headers=MULTIPART)
    assert response.status_code == HTTPStatus.OK

    # Edges which are not those of a map are refused.
    body = export_form(make_multipart_form, images, bounds=[0, 0, 0, 0])
    request, response = await async_client.post('/api/map/export/pdf', content=body, headers=MULTIPART)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'edges' in response.json['error']
