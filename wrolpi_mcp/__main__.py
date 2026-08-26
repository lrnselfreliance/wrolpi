"""Entry point: python -m wrolpi_mcp, or python wrolpi_mcp/__main__.py"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so wrolpi_mcp is importable
# regardless of the working directory or how this script is invoked.
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from wrolpi_mcp.server import mcp

mcp.run(transport="stdio")
