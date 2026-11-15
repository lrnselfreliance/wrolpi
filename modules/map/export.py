"""Build the PDF of an exported map.

The map is drawn by the browser, which is the only thing that draws it as the user sees it: one image for each
layer the user has turned on, all of the same area and size.  Here they become one page, each image in a PDF
layer (an "optional content group") of its own, so a reader can show and hide them as the map can.

The page is also told where on the Earth it is (a "geospatial PDF", ISO 32000-2 section 12.10), so a reader which
knows how can show coordinates, measure, and put a GPS position on the map.

The map can be put on a sheet (see `modules.map.sheet`): a margin around it with what a printed map has there, and
a grid over it.
"""
import io
import math
import zlib
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PIL import Image

from modules.map.sheet import Sheet, draw_sheet, plan_sheet
from wrolpi.common import logger

logger = logger.getChild(__name__)

__all__ = ['ExportLayer', 'InvalidExport', 'Sheet', 'build_layered_pdf', 'geospatial_viewport', 'MAX_LAYERS',
           'MAX_SIDE', 'MAX_PIXELS', 'MAX_TOTAL_PIXELS', 'MIN_DPI', 'MAX_DPI']

# What the browser may ask for.  Every image is decoded, so what an export costs is its pixels, whatever the size
# of the upload (an image of one color is a few kilobytes however large it is).
MAX_LAYERS = 64
MAX_SIDE = 16384
# The pixels of one layer, which are in memory together (a few bytes each) while it is put in the PDF.  A 1:24,000
# quadrangle at 300 DPI is 23 to 36 megapixels, more the nearer it is to the equator.
MAX_PIXELS = 64_000_000
# The pixels of every layer of a map together, which is the work an export is.  A quadrangle of 36 megapixels with
# 24 layers on is about 860 million.
MAX_TOTAL_PIXELS = 1_000_000_000
# How hard an image is compressed in the PDF (zlib, 1 to 9).  Less is a few seconds faster and a much larger file.
COMPRESSION_LEVEL = 6
MIN_DPI = 36
MAX_DPI = 1200
IMAGE_FORMATS = ('PNG', 'JPEG')

POINTS_PER_INCH = 72


# The map is drawn in Web Mercator, in which the area between two meridians and two parallels is a rectangle: the
# page.  So the page is said to be in that projection, and its four corners are all a reader needs.
#
# Web Mercator is Mercator on a sphere the size of the WGS 84 equator, with WGS 84 latitudes and longitudes.  The
# EXTENSION says so to a reader which knows PROJ; one which does not takes it for Mercator on the ellipsoid, which
# across a page of a map is the same to well within a meter (the corners are given in latitude and longitude, so
# such a reader only stretches the page a little differently between them).
WEB_MERCATOR_EPSG = 3857
WEB_MERCATOR_WKT = (
    'PROJCS["WGS 84 / Pseudo-Mercator",'
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Mercator_1SP"],'
    'PARAMETER["central_meridian",0],PARAMETER["scale_factor",1],'
    'PARAMETER["false_easting",0],PARAMETER["false_northing",0],'
    'UNIT["metre",1],'
    'EXTENSION["PROJ4","+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m'
    ' +nadgrids=@null +wktext +no_defs"],'
    'AUTHORITY["EPSG","3857"]]'
)
# Web Mercator has no poles: this is as far north or south as it goes.
MAX_LATITUDE = 85.06
# The browser's arithmetic can put the edge of the world a hair past where it is (180.00000000000125 degrees).  An
# edge within this of 180 degrees is at 180 degrees; one further past it is of a map which crosses the antimeridian.
LONGITUDE_SLIVER = 1e-8


class InvalidExport(ValueError):
    """The layers sent can not be made into a map."""


@dataclass
class ExportLayer:
    # What the layer is called in the reader's list of layers.
    name: str
    # A PNG or JPEG image.
    image: bytes


def _is_blank(image: Image.Image) -> bool:
    """True when nothing was drawn: every pixel of the image is transparent."""
    if image.mode in ('RGBA', 'LA'):
        return image.getchannel('A').getextrema()[1] == 0
    if image.mode == 'P' and 'transparency' in image.info:
        return image.convert('RGBA').getchannel('A').getextrema()[1] == 0
    return False


def _check_layer(layer: ExportLayer, width: int, height: int) -> bool:
    """Raises InvalidExport when the layer is not an image of the map.  Returns whether there is anything in it."""
    try:
        image = Image.open(io.BytesIO(layer.image))
        if image.format not in IMAGE_FORMATS:
            raise InvalidExport(f'The layer {layer.name!r} is not a PNG or JPEG image')
        if image.size != (width, height):
            raise InvalidExport(f'The layer {layer.name!r} is {image.size[0]}x{image.size[1]},'
                                f' but the map is {width}x{height}')
        return not _is_blank(image)
    except InvalidExport:
        raise
    except Exception as e:
        # Whatever Pillow makes of something which is not an image.
        raise InvalidExport(f'The layer {layer.name!r} is not a readable image') from e


def _edge_longitude(longitude: float) -> float:
    """A longitude which is a rounding error past the edge of the world, put on it.  It is not wrapped: the east
    edge of the last map before the antimeridian is at 180 degrees, not at -180."""
    if 180 < abs(longitude) < 180 + LONGITUDE_SLIVER:
        return math.copysign(180.0, longitude)
    return longitude


def _check_bounds(bounds: Sequence[float]) -> List[float]:
    """The west, south, east and north edges of a map, in degrees.  Raises InvalidExport when they are not."""
    try:
        west, south, east, north = (float(i) for i in bounds)
    except (TypeError, ValueError) as e:
        raise InvalidExport('The edges of the map are not four numbers') from e
    west, east = _edge_longitude(west), _edge_longitude(east)
    edges = [west, south, east, north]
    if not all(math.isfinite(i) for i in edges) or not (-180 <= west < east <= 180) \
            or not (-MAX_LATITUDE <= south < north <= MAX_LATITUDE):
        raise InvalidExport(f'A map with the edges {edges} can not be exported')
    return edges


def _pdf_string(text: str) -> str:
    """A string as it is written in a PDF: as it is when it is ASCII, else in UTF-16."""
    if text.isascii():
        return '(' + text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'
    return '<' + (b'\xfe\xff' + text.encode('utf-16-be')).hex().upper() + '>'


def geospatial_viewport(width: float, height: float, bounds: Sequence[float], name: str = None,
                        origin: Sequence[float] = (0, 0)) -> str:
    """The value of a page's `/VP`: a viewport which covers the map (`width` by `height` points, its lower left
    corner at `origin`: so far right of, and up from, the page's), and says it is the map between `bounds` (west,
    south, east, north; degrees of WGS 84) in Web Mercator.

    A point of the map is given as a part of the way across and up it (0 to 1, from the lower left), and the
    corners are listed as GDAL and the readers which follow it expect: upper left, lower left, lower right,
    upper right.  The coordinates of each are its latitude, then its longitude.
    """
    west, south, east, north = _check_bounds(bounds)
    corners = '0 1 0 0 1 0 1 1'
    points = ' '.join(f'{lat:.9f} {lon:.9f}' for lat, lon in ((north, west), (south, west), (south, east),
                                                              (north, east)))
    name = f' /Name {_pdf_string(name)}' if name else ''
    return (
        f'[<< /Type /Viewport{name}'
        f' /BBox [{origin[0]:.3f} {origin[1]:.3f} {origin[0] + width:.3f} {origin[1] + height:.3f}]'
        f' /Measure << /Type /Measure /Subtype /GEO'
        f' /Bounds [{corners}] /GPTS [{points}] /LPTS [{corners}]'
        f' /GCS << /Type /PROJCS /EPSG {WEB_MERCATOR_EPSG} /WKT {_pdf_string(WEB_MERCATOR_WKT)} >>'
        f' /PDU [/M /SQM /DEG] >> >>]'
    )


def _compress_stream(doc, xref: int):
    """Compress the stream of an object of the PDF, when it is not already."""
    if doc.xref_get_key(xref, 'Filter')[0] != 'null':
        return
    doc.update_stream(xref, zlib.compress(doc.xref_stream_raw(xref), COMPRESSION_LEVEL), compress=False)
    doc.xref_set_key(xref, 'Filter', '/FlateDecode')


def _insert_layer(doc, page, rect, layer: ExportLayer):
    """Put the image of a layer in a rectangle of the page, in a PDF layer of its own.

    PyMuPDF keeps the pixels of an image uncompressed until the PDF is written: about 90 MB for each layer of a
    quadrangle, all of them at once.  They are compressed here instead, so only one layer's are ever in memory."""
    group = doc.add_ocg(layer.name, on=True)
    xref = page.insert_image(rect, stream=layer.image, oc=group)
    _compress_stream(doc, xref)
    # The transparency of a PNG is an image of its own.
    kind, mask = doc.xref_get_key(xref, 'SMask')
    if kind == 'xref':
        _compress_stream(doc, int(mask.split()[0]))


def build_layered_pdf(layers: List[ExportLayer], width: int, height: int, dpi: float, title: str = None,
                      bounds: Optional[Sequence[float]] = None, sheet: Optional[Sheet] = None) -> bytes:
    """A one page PDF of the layers, the first at the bottom, each in a PDF layer of its own.

    A layer in which nothing was drawn is left out.

    @param layers: The images of the map, all `width` by `height` pixels.
    @param dpi: How many of those pixels are an inch of the page.
    @param bounds: The west, south, east and north edges of the images, in degrees.  With them the PDF says where
        it is on the Earth; the images must be Web Mercator, and all of the map between those edges.
    @param sheet: With this the map is on a sheet, which says this of it.  The sheet needs `bounds`.
    @raise InvalidExport: When the layers are not of one map.
    """
    if not layers:
        raise InvalidExport('There are no layers to export')
    if len(layers) > MAX_LAYERS:
        raise InvalidExport(f'A map of more than {MAX_LAYERS} layers can not be exported')
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE) or width * height > MAX_PIXELS:
        raise InvalidExport(f'A map of {width}x{height} pixels can not be exported')
    if len(layers) * width * height > MAX_TOTAL_PIXELS:
        # Before any image is decoded.
        raise InvalidExport(f'A map of {len(layers)} layers of {width}x{height} pixels is too large to export;'
                            f' turn some layers off')
    if not MIN_DPI <= dpi <= MAX_DPI:
        raise InvalidExport(f'A map can not be exported at {dpi} DPI')
    if bounds is not None:
        bounds = _check_bounds(bounds)
    elif sheet is not None:
        raise InvalidExport('The edges of the map are needed to put it on a sheet')

    drawn = [layer for layer in layers if _check_layer(layer, width, height)]
    if not drawn:
        raise InvalidExport('Nothing is drawn in any layer of the map')

    # Not imported at module level: pymupdf also imports onnxruntime (~2s on a Pi 4), which the API must not pay
    # for at startup.
    import pymupdf

    doc = pymupdf.open()
    try:
        map_width, map_height = width * POINTS_PER_INCH / dpi, height * POINTS_PER_INCH / dpi
        if sheet is not None:
            plan = plan_sheet(map_width, map_height, bounds, sheet)
            page = doc.new_page(width=plan.width, height=plan.height)
            rect = pymupdf.Rect(plan.map_rect)
        else:
            plan = None
            page = doc.new_page(width=map_width, height=map_height)
            rect = page.rect
        for layer in drawn:
            _insert_layer(doc, page, rect, layer)
        if plan is not None:
            draw_sheet(doc, page, plan)
        if bounds is not None:
            # A PDF measures up from the bottom of the page.
            origin = (rect.x0, page.rect.height - rect.y1)
            doc.xref_set_key(page.xref, 'VP', geospatial_viewport(rect.width, rect.height, bounds, title, origin))
        doc.set_metadata(dict(title=title or 'Map', creator='WROLPi', producer='WROLPi'))
        return doc.tobytes(garbage=3)
    finally:
        doc.close()
