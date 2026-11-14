"""Build the PDF of an exported map.

The map is drawn by the browser, which is the only thing that draws it as the user sees it: one image for each
layer the user has turned on, all of the same area and size.  Here they become one page, each image in a PDF
layer (an "optional content group") of its own, so a reader can show and hide them as the map can.
"""
import io
from dataclasses import dataclass
from typing import List

import pymupdf
from PIL import Image

from wrolpi.common import logger

logger = logger.getChild(__name__)

__all__ = ['ExportLayer', 'InvalidExport', 'build_layered_pdf', 'MAX_LAYERS', 'MAX_SIDE', 'MAX_PIXELS', 'MIN_DPI',
           'MAX_DPI']

# What the browser may ask for.  The images are decoded, so their size is what memory the export needs.
MAX_LAYERS = 64
MAX_SIDE = 16384
# A 1:24,000 quadrangle at 300 DPI is about 23 megapixels, and at 400 DPI about 40.
MAX_PIXELS = 64_000_000
MIN_DPI = 36
MAX_DPI = 1200
IMAGE_FORMATS = ('PNG', 'JPEG')

POINTS_PER_INCH = 72


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


def build_layered_pdf(layers: List[ExportLayer], width: int, height: int, dpi: float, title: str = None) -> bytes:
    """A one page PDF of the layers, the first at the bottom, each in a PDF layer of its own.

    A layer in which nothing was drawn is left out.

    @param layers: The images of the map, all `width` by `height` pixels.
    @param dpi: How many of those pixels are an inch of the page.
    @raise InvalidExport: When the layers are not of one map.
    """
    if not layers:
        raise InvalidExport('There are no layers to export')
    if len(layers) > MAX_LAYERS:
        raise InvalidExport(f'A map of more than {MAX_LAYERS} layers can not be exported')
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE) or width * height > MAX_PIXELS:
        raise InvalidExport(f'A map of {width}x{height} pixels can not be exported')
    if not MIN_DPI <= dpi <= MAX_DPI:
        raise InvalidExport(f'A map can not be exported at {dpi} DPI')

    drawn = [layer for layer in layers if _check_layer(layer, width, height)]
    if not drawn:
        raise InvalidExport('Nothing is drawn in any layer of the map')

    doc = pymupdf.open()
    try:
        page = doc.new_page(width=width * POINTS_PER_INCH / dpi, height=height * POINTS_PER_INCH / dpi)
        for layer in drawn:
            group = doc.add_ocg(layer.name, on=True)
            page.insert_image(page.rect, stream=layer.image, oc=group)
        doc.set_metadata(dict(title=title or 'Map', creator='WROLPi', producer='WROLPi'))
        return doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()
