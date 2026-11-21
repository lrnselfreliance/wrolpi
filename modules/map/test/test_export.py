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
from wrolpi.jobs import wait_for_job

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
    ], WIDTH, HEIGHT, dpi=300, title='40°15′N 105°07′30″W')

    doc = pymupdf.open(stream=pdf, filetype='pdf')
    assert doc.page_count == 1
    page = doc[0]
    # 60x90 pixels at 300 DPI is 0.2x0.3 inches: 14.4x21.6 points.
    assert (round(page.rect.width, 3), round(page.rect.height, 3)) == (14.4, 21.6)
    assert layer_names(pdf) == ['Background', 'Water', 'Satellite']
    assert all(i['on'] for i in doc.get_ocgs().values())
    assert doc.metadata['title'] == '40°15′N 105°07′30″W'

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


async def api_export(async_client, images, **meta):
    """Export a map through the API, as the browser does: describe it, send the image of each layer, have the PDF
    made, and fetch it.  Returns the response which ended it (the PDF's, or the first to refuse) and the Job's
    record (None when it did not get as far as a Job)."""
    meta = dict(dict(width=WIDTH, height=HEIGHT, dpi=300, layers=[name for name, _ in images]), **meta)
    request, response = await async_client.post('/api/map/export', json=meta)
    if response.status_code != HTTPStatus.CREATED:
        return response, None
    export_id = response.json['export_id']
    for index, (_, image) in enumerate(images):
        request, response = await async_client.post(f'/api/map/export/{export_id}/layer/{index}', content=image)
        if response.status_code != HTTPStatus.NO_CONTENT:
            return response, None
    request, response = await async_client.post(f'/api/map/export/{export_id}/start')
    if response.status_code != HTTPStatus.ACCEPTED:
        return response, None
    job = await wait_for_job(response.json['job_id'], timeout=60)
    request, response = await async_client.get(f'/api/map/export/{export_id}/pdf')
    return response, job


@pytest.mark.asyncio
async def test_api_export_pdf(async_client):
    """The images of a map's layers are sent, a Job makes the PDF of them, and the PDF is fetched."""
    response, job = await api_export(async_client, [
        ('Background', make_image((240, 240, 230, 255))),
        ('Roads - Tunnels', BLANK),
        ('Water', make_image((60, 120, 220, 255), box=(0, 0, 30, 90))),
    ], title='A quadrangle')
    assert job['status'] == 'complete', job
    assert job['progress'] == 100
    assert job['description'] == 'Map PDF: A quadrangle'
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF-')
    assert layer_names(response.content) == ['Background', 'Water']
    assert pymupdf.open(stream=response.content, filetype='pdf').metadata['title'] == 'A quadrangle'


@pytest.mark.asyncio
async def test_api_export_pdf_invalid(async_client):
    """What is not a map is refused before any image is sent, and why is said."""
    # No description of the map.
    request, response = await async_client.post('/api/map/export', content=b'not json')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'description of the map' in response.json['error']
    request, response = await async_client.post('/api/map/export', json=['a', 'list'])
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # A description which is not of a map.
    response, _ = await api_export(async_client, [('A', make_image())], width='wide')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # More than a PDF is made of: said at once, with nothing sent.
    response, _ = await api_export(async_client, [('A', make_image())], width=10000, height=10000)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert '10000x10000' in response.json['error']
    response, _ = await api_export(async_client, [], layers=[])
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'no layers' in response.json['error']


@pytest.mark.asyncio
async def test_api_export_layers(async_client):
    """Only the images of the map's own layers are taken, and the PDF is not made until all of them are sent."""
    meta = dict(width=WIDTH, height=HEIGHT, dpi=300, layers=['A', 'B'])
    request, response = await async_client.post('/api/map/export', json=meta)
    export_id = response.json['export_id']
    layer, start = f'/api/map/export/{export_id}/layer', f'/api/map/export/{export_id}/start'

    for index, content, error in (
            (2, make_image(), 'no layer 2'),
            (0, b'', 'empty'),
            (0, b'not an image', 'not a PNG or JPEG'),
            (0, make_image(image_format='GIF'), 'not a PNG or JPEG'),
    ):
        request, response = await async_client.post(f'{layer}/{index}', content=content)
        assert response.status_code == HTTPStatus.BAD_REQUEST, error
        assert error in response.json['error']

    # One of two layers.
    request, response = await async_client.post(f'{layer}/0', content=make_image())
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.post(start)
    assert response.status_code == HTTPStatus.CONFLICT
    assert '1 layers have not been sent: B' in response.json['error']
    request, response = await async_client.get(f'/api/map/export/{export_id}/pdf')
    assert response.status_code == HTTPStatus.CONFLICT
    assert 'not started' in response.json['error']

    request, response = await async_client.post(f'{layer}/1', content=make_image(image_format='JPEG'))
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.post(start)
    assert response.status_code == HTTPStatus.ACCEPTED
    job_id = response.json['job_id']
    # Asked again, it is the same Job; and no more images are taken.
    request, response = await async_client.post(start)
    assert response.json['job_id'] == job_id
    request, response = await async_client.post(f'{layer}/0', content=make_image())
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'already being made' in response.json['error']

    # Until the Job is done there is no PDF.
    request, response = await async_client.get(f'/api/map/export/{export_id}/pdf')
    assert response.status_code == HTTPStatus.CONFLICT
    assert (await wait_for_job(job_id, timeout=60))['status'] == 'complete'
    request, response = await async_client.get(f'/api/map/export/{export_id}/pdf')
    assert response.status_code == HTTPStatus.OK
    assert layer_names(response.content) == ['A', 'B']


@pytest.mark.asyncio
async def test_api_export_unknown(async_client):
    """An export which there is not, and an id which is not one."""
    for export_id in ('0' * 32, 'nothing', '..%2F..%2Fetc'):
        for method, url in (('post', f'/api/map/export/{export_id}/layer/0'),
                            ('post', f'/api/map/export/{export_id}/start'),
                            ('get', f'/api/map/export/{export_id}/pdf')):
            request, response = await getattr(async_client, method)(url)
            assert response.status_code == HTTPStatus.NOT_FOUND, url


@pytest.mark.asyncio
async def test_api_export_job_fails(async_client):
    """An image which is not of the map fails the Job, which says why; there is no PDF."""
    response, job = await api_export(async_client, [('A', make_image()), ('B', make_image(size=(10, 10)))])
    assert job['status'] == 'failed'
    assert '10x10' in job['error']
    assert response.status_code == HTTPStatus.CONFLICT
    assert 'failed' in response.json['error']


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
    export._insert_layer(doc, page, page.rect, ExportLayer('Satellite', make_image(image_format='JPEG')), {})
    export._insert_layer(doc, page, page.rect, ExportLayer('Water', make_image((0, 0, 255, 200), box=(0, 0, 30, 90))), {})

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
    """With the edges of the map, the page has a geospatial viewport: all of the page, with the latitude and
    longitude of each of its corners, in a projection every reader knows."""
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
    # Mercator on the ellipsoid, in Esri's words: Adobe Acrobat puts every place of a page said to be in Web
    # Mercator at 0, 0.
    assert '/Type/PROJCS' in text.replace(' ', '') and '/EPSG 3395' in text
    assert 'PROJCS["WGS_1984_World_Mercator"' in text and 'PROJECTION["Mercator"]' in text
    assert '3857' not in text and 'Auxiliary_Sphere' not in text and 'Mercator_1SP' not in text

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
    [179.875, 0, 180.00001, 0.125],  # Across the antimeridian, if not by much.
    [179.9, 0, 180.1, 0.125],
    [-180.00001, 0, -179.875, 0.125],
    [-150, 61.125, -149.875, 89],  # Further north than the map goes.
    [-150, float('nan'), -149.875, 61.25],
])
def test_invalid_bounds(bounds):
    with pytest.raises(InvalidExport, match='edges'):
        build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72, bounds=bounds)


@pytest.mark.parametrize('bounds,expected', [
    # The map's own arithmetic puts the edge of the world a hair past where it is.
    ([179.875, 0, 180.00000000000125, 0.125], [179.875, 0, 180, 0.125]),
    ([-180.00000000000125, 0, -179.875, 0.125], [-180, 0, -179.875, 0.125]),
    ([-180, 0, -179.875, 0.125], [-180, 0, -179.875, 0.125]),
])
def test_bounds_at_the_antimeridian(bounds, expected):
    """A map whose edge is the antimeridian is exported, with that edge at 180 degrees and not at -180."""
    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72, bounds=bounds)
    west, south, east, north = expected
    assert read_viewport(pdf)['gpts'] == [north, west, south, west, south, east, north, east]


@pytest.mark.asyncio
async def test_api_export_pdf_georeferenced(async_client):
    """The edges of the map are sent with its description, and the PDF says where it is."""
    images = [('Background', make_image())]
    response, job = await api_export(async_client, images, bounds=ANCHORAGE)
    assert response.status_code == HTTPStatus.OK, response.text
    assert read_viewport(response.content)['gpts'] == [61.25, -150, 61.125, -150, 61.125, -149.875, 61.25, -149.875]

    # Without them it is a PDF all the same.
    response, job = await api_export(async_client, images)
    assert response.status_code == HTTPStatus.OK

    # Edges which are not those of a map are refused.
    response, job = await api_export(async_client, images, bounds=[0, 0, 0, 0])
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'edges' in response.json['error']


@pytest.mark.asyncio
async def test_api_export_text_which_is_not_text(async_client):
    """What is sent as the title of a map, or the name of a layer, may have in it what is no character (half of
    a pair, a NUL).  It is taken out when the export begins: the Job, after every image is sent, is too late to
    find that a PDF can not have it."""
    body = json.dumps(dict(width=WIDTH, height=HEIGHT, dpi=300, title='A \ud800 map\x00', layers=['Ro\x00ads \ud800']))
    request, response = await async_client.post('/api/map/export', content=body)
    assert response.status_code == HTTPStatus.CREATED, response.json
    export_id = response.json['export_id']
    request, response = await async_client.post(f'/api/map/export/{export_id}/layer/0', content=make_image())
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.post(f'/api/map/export/{export_id}/start')
    job = await wait_for_job(response.json['job_id'], timeout=60)
    assert job['status'] == 'complete', job
    request, response = await async_client.get(f'/api/map/export/{export_id}/pdf')
    assert layer_names(response.content) == ['Roads ?']
    assert pymupdf.open(stream=response.content).metadata['title'] == 'A ? map'


def test_images_of_one_name_are_one_pdf_layer():
    """A layer of the map may be several images, with other layers drawn between them (the parks of the land
    are under the water, and its piers are over it).  They are one layer of the PDF, and each is drawn where it
    was given: turning the layer off hides them all."""
    pdf = build_layered_pdf([
        ExportLayer('Land Cover', make_image((0, 200, 0, 255))),
        ExportLayer('Water', make_image((0, 0, 255, 255), box=(0, 0, 30, 90))),
        ExportLayer('Land Cover', make_image((90, 90, 90, 255), box=(0, 0, 10, 90))),
    ], WIDTH, HEIGHT, dpi=300)
    assert layer_names(pdf) == ['Land Cover', 'Water']
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    page = doc[0]
    assert len(page.get_images()) == 3

    def color(x):
        pixmap = page.get_pixmap(dpi=300)
        return pixmap.pixel(x, 45)

    # From the left: the pier over the water, the water over the park, the park.
    assert [color(x) for x in (5, 20, 50)] == [(90, 90, 90), (0, 0, 255), (0, 200, 0)]


def _wkt_parameter(wkt: str, name: str) -> float:
    return float(re.search(rf'PARAMETER\["{name}",([-0-9.]+)]', wkt).group(1))


def _read_as_a_reader_does(viewport: dict, wkt: str, latitude: float, longitude: float):
    """Where on the page (across and up, 0 to 1) a reader of the PDF puts a place: it projects the corners it
    is given (/GPTS) in the projection it is told of (the WKT: Mercator on its spheroid), and the place, and puts
    the place between the corners as they are on the page (/LPTS)."""
    assert 'PROJECTION["Mercator"]' in wkt
    a, inverse_flattening = [float(i) for i in re.search(r'SPHEROID\["[^"]*",([0-9.]+),([0-9.]+)]', wkt).groups()]
    f = 1 / inverse_flattening
    e = math.sqrt(f * (2 - f))
    meridian = _wkt_parameter(wkt, 'Central_Meridian')
    # Mercator of one standard parallel: the scale is that of the parallel.
    parallel = math.radians(_wkt_parameter(wkt, 'Standard_Parallel_1'))
    k = math.cos(parallel) / math.sqrt(1 - (e * math.sin(parallel)) ** 2)

    def project(lat, lon):
        phi = math.radians(lat)
        y = math.log(math.tan(math.pi / 4 + phi / 2) * ((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2))
        return (a * k * math.radians(lon - meridian) + _wkt_parameter(wkt, 'False_Easting'),
                a * k * y + _wkt_parameter(wkt, 'False_Northing'))

    gpts, lpts = viewport['gpts'], viewport['lpts']
    corners = [(project(gpts[i], gpts[i + 1]), (lpts[i], lpts[i + 1])) for i in range(0, 8, 2)]
    # The page is a rectangle of the projection, so three corners say where the rest of it is.
    (upper_left, page_ul), (lower_left, page_ll), (lower_right, page_lr), _ = corners
    x, y = project(latitude, longitude)
    across = (x - lower_left[0]) / (lower_right[0] - lower_left[0])
    up = (y - lower_left[1]) / (upper_left[1] - lower_left[1])
    return (page_ll[0] + across * (page_lr[0] - page_ll[0]), page_ll[1] + up * (page_ul[1] - page_ll[1]))


def _drawn(bounds, latitude: float, longitude: float):
    """Where on the page (across and up, 0 to 1) the map has a place: it is drawn in Web Mercator."""
    west, south, east, north = bounds

    def y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    return (longitude - west) / (east - west), (y(latitude) - y(south)) / (y(north) - y(south))


@pytest.mark.parametrize('west,south', [(-78.5, 0), (-100, 20), (-105.125, 40.25), (-149.625, 61.25), (-156.75, 71.25),
                                        (151.125, -33.875), (10, 84.875), (-0.0625, -0.0625)])
def test_page_is_where_the_projection_it_is_said_to_be_in_puts_it(west, south):
    """The page is drawn in Web Mercator (a sphere), and a reader is told it is Mercator on the ellipsoid, with
    the latitude and longitude of its corners.  A reader puts a place on the page by where that projection has
    it between the corners: that is within 5 centimeters on the ground of where the map drew it, anywhere on a
    quadrangle, at any latitude.  What the reader is told is what the PDF says: its corners and its WKT."""
    bounds = [west, south, west + 0.125, south + 0.125]
    pdf = build_layered_pdf([ExportLayer('Background', make_image())], WIDTH, HEIGHT, dpi=72, bounds=bounds)
    viewport = read_viewport(pdf)
    wkt = re.search(r'/WKT\s*\((.*)\)\s*>>', viewport['text'], re.S).group(1)

    # The page is this wide and this tall on the ground.
    height = 6378137 * math.radians(0.125)
    width = height * math.cos(math.radians(south + 0.0625))
    worst = 0
    for i in range(21):
        for j in range(21):
            lat, lon = south + 0.125 * i / 20, west + 0.125 * j / 20
            read = _read_as_a_reader_does(viewport, wkt, lat, lon)
            drawn = _drawn(bounds, lat, lon)
            worst = max(worst, math.hypot((read[0] - drawn[0]) * width, (read[1] - drawn[1]) * height))
    assert worst < 0.05

    # The same sum finds a page whose corners are not where they are said to be: here, a second of arc south.
    moved = dict(viewport, gpts=[v - 1 / 3600 if index % 2 == 0 else v for index, v in enumerate(viewport['gpts'])])
    middle = (south + 0.0625, west + 0.0625)
    off = _read_as_a_reader_does(moved, wkt, *middle)[1] - _drawn(bounds, *middle)[1]
    assert abs(off) * height == pytest.approx(31, abs=1)


def test_page_taller_than_a_quadrangle_is_less_well_said():
    """What is left between the two projections grows with the square of how tall the page is: centimeters on a
    quadrangle, more than a meter on a page a degree tall.  (A page that tall is not exported yet.)"""
    def worst(tall):
        bounds = [-150, 61, -149, 61 + tall]
        viewport = dict(gpts=[bounds[3], bounds[0], bounds[1], bounds[0], bounds[1], bounds[2], bounds[3], bounds[2]],
                        lpts=[0, 1, 0, 0, 1, 0, 1, 1])
        height = 6378137 * math.radians(tall)
        return max(abs(_read_as_a_reader_does(viewport, export.PAGE_PROJECTION_WKT, 61 + tall * i / 40, -149.5)[1]
                       - _drawn(bounds, 61 + tall * i / 40, -149.5)[1]) * height for i in range(41))

    assert worst(0.125) < 0.05
    assert 1 < worst(1) < 2
