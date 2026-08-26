"""Guards for the wrolpi_mcp thin proxy.

The MCP server's venv (with the `mcp` package) is separate from the API's, so these are source
scans: external clients depend on the tool names, and the proxy must only reach the tested
/api/ai blueprint (plus the two whole-API reads that predate it)."""
import re

from wrolpi.vars import PROJECT_DIR

MCP_SERVER = PROJECT_DIR / 'wrolpi_mcp/server.py'

# The tool names external clients (Claude etc.) already use.  Renaming one breaks them.
EXPECTED_TOOLS = {
    'search', 'search_videos', 'search_archives', 'search_docs',
    'search_zim', 'search_default_zims',
    'get_video', 'get_video_captions', 'get_video_comments',
    'get_archive', 'get_archive_text',
    'get_doc', 'get_zim_entry',
    'list_collections', 'list_zim_files',
    'get_statistics', 'get_inventory', 'get_inventory_items', 'get_status',
}


def test_mcp_tool_names_unchanged():
    text = MCP_SERVER.read_text()
    tools = set(re.findall(r'@mcp\.tool[^\n]*\)\nasync def (\w+)\(', text))
    assert tools == EXPECTED_TOOLS


def test_mcp_is_a_thin_proxy():
    """The MCP calls only /api/ai (and the raw statistics read); the formatting layer is gone."""
    text = MCP_SERVER.read_text()
    endpoints = set(re.findall(r'["\'](/api/[a-z_/{}]+)', text))
    allowed_non_ai = {'/api/statistics'}
    offenders = {e for e in endpoints if not e.startswith('/api/ai') and e not in allowed_non_ai}
    assert not offenders, f'MCP tools must proxy /api/ai, found: {sorted(offenders)}'

    # The formatting/truncation layer moved into modules/ai; it must not come back here.
    for name in ('_wrolpi_link', '_fmt_file_group', 'html_to_text', 'BeautifulSoup'):
        assert name not in text, f'{name} belongs in modules/ai, not the MCP proxy'
