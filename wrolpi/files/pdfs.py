import pathlib
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from wrolpi.common import register_modeler, logger
from wrolpi.files.models import File

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

logger = logger.getChild(__name__)


def get_pdf_title(path: pathlib.Path) -> Optional[str]:
    reader = PdfReader(path)
    if reader.metadata and reader.metadata.title:
        return reader.metadata.title.strip()


@register_modeler
def pdf_modeler(groups: Dict[str, List[File]], _: Session):
    """Reads the contents of a PDF and extracts the title, attaches the title to the File.

    This modeler does not claim any groups passed to it.  Does NOT mark the PDFs as indexed."""
    if not PdfReader:
        logger.warning(f'Cannot get title from PDF without PyPDF2')
        return

    pdf_files = (file for group in groups.values() for file in group if
                 file.indexed is not True and file.mimetype == 'application/pdf')

    for file in pdf_files:
        path: pathlib.Path = file.path.path if hasattr(file.path, 'path') else file.path
        if title := get_pdf_title(path):
            file.title = title
