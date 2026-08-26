"""Tests for tool-definition generation and tool execution."""
import json
from unittest import mock
from urllib.parse import urlencode

import pytest

from modules.ai import agent
from modules.ai.modes import MODES


@pytest.fixture
async def tool_definitions(async_client):
    # Any request finalizes the router, which the spec builder requires.
    await async_client.get('/api/ai/zims')
    return agent.get_ai_tool_definitions(refresh=True)


@pytest.mark.asyncio
async def test_tool_definitions_from_spec(tool_definitions):
    """Tool definitions are generated from the blueprint's own OpenAPI operations."""
    tools = tool_definitions
    # Every tool any mode allowlists must exist — this guards allowlists against drift.
    for mode_name, mode in MODES.items():
        for tool_name in mode['tools']:
            assert tool_name in tools, f'Mode {mode_name} allowlists missing tool {tool_name}'

    # Every tool has a model-facing description.
    for name, tool in tools.items():
        assert tool.description, f'Tool {name} has no description'

    # Manage endpoints are never tools.
    assert not any(t.path.startswith('/api/ai/manage') for t in tools.values())
    assert 'manage_catalog' not in tools and 'manage_settings' not in tools
    # The chat endpoint itself is not a tool.
    assert not any(t.path.startswith('/api/chat') for t in tools.values())

    # Body, query, and path parameters all appear in the flat schema.
    schema = tools['search_videos'].parameters_schema()
    assert schema['properties']['search_str'] == {'type': 'string'}
    assert schema['properties']['tag_names'] == {'type': 'array', 'items': {'type': 'string'}}
    schema = tools['get_video_captions'].parameters_schema()
    assert schema['required'] == ['file_group_id']
    assert schema['properties']['offset'] == {'type': 'integer'}

    # OpenAI tool format.
    openai_tool = tools['search_all'].as_openai_tool()
    assert openai_tool['type'] == 'function'
    assert openai_tool['function']['name'] == 'search_all'


def _endpoint_shim(async_client):
    async def shim(method, path, query, body):
        url = f'{path}?{urlencode(query)}' if query else path
        if method == 'post':
            request, response = await async_client.post(url, content=json.dumps(body or {}))
        else:
            request, response = await async_client.get(url)
        return response.status_code, response.json

    return mock.patch('modules.ai.agent.call_ai_endpoint', side_effect=shim)


@pytest.mark.asyncio
async def test_execute_tool(async_client, tool_definitions, video_factory, test_session):
    """Tools execute against the blueprint; every failure is an instructive error string."""
    video_factory(title='pressure canning')
    test_session.commit()
    research_tools = MODES['research']['tools']

    with _endpoint_shim(async_client):
        # A real search through the blueprint.
        success, result = await agent.execute_tool(research_tools, 'search_videos',
                                                   dict(search_str='canning'))
        assert success is True
        result = json.loads(result)
        assert result['total'] == 1

        # Unknown tool.
        success, error = await agent.execute_tool(research_tools, 'delete_everything', {})
        assert success is False and 'Unknown tool' in error

        # Mode allowlist: research mode cannot read service logs even though the tool exists.
        success, error = await agent.execute_tool(research_tools, 'get_service_logs',
                                                  dict(name='wrolpi-api'))
        assert success is False and 'Unknown tool' in error

        # Unknown argument names the accepted ones.
        success, error = await agent.execute_tool(research_tools, 'search_videos', dict(query='x'))
        assert success is False and 'accepts' in error and 'search_str' in error

        # Missing required path parameter.
        success, error = await agent.execute_tool(research_tools, 'get_video_captions', {})
        assert success is False and 'Missing required' in error

        # Wrong type.
        success, error = await agent.execute_tool(research_tools, 'get_video_captions',
                                                  dict(file_group_id='banana'))
        assert success is False and 'must be a integer' in error

        # An endpoint error comes back as a message, not an exception.
        success, error = await agent.execute_tool(research_tools, 'get_video_captions',
                                                  dict(file_group_id=123456))
        assert success is False and 'error' in error.lower()


@pytest.mark.asyncio
async def test_execute_tool_path_traversal(async_client, tool_definitions):
    """A crafted path parameter cannot escape the tool's endpoint (allowlist bypass)."""
    help_tools = MODES['help']['tools']
    with _endpoint_shim(async_client):
        for slug in ('../../manage/catalog', '../manage/settings', '/etc/passwd',
                     'a/../../files/refresh', 'a//b', 'a/./b'):
            success, error = await agent.execute_tool(help_tools, 'get_help_doc', dict(slug=slug))
            assert success is False, f'traversal not refused: {slug}'
            assert 'traversal' in error or 'invalid path' in error

        # Legitimate nested slugs keep working (404 from the endpoint is fine, no traversal error).
        success, error = await agent.execute_tool(help_tools, 'get_help_doc', dict(slug='system/logs'))
        assert 'traversal' not in error and 'invalid path' not in (error or '')


@pytest.mark.asyncio
async def test_execute_tool_result_truncated(async_client, tool_definitions, archive_factory, test_session):
    """A huge tool result is capped with a paging hint."""
    archive_factory(domain='example.com', title='big page', contents='word ' * 5_000)
    test_session.commit()
    from modules.archive.models import Archive
    archive = test_session.query(Archive).one()

    with _endpoint_shim(async_client):
        success, result = await agent.execute_tool(MODES['research']['tools'], 'get_archive_text',
                                                   dict(file_group_id=archive.file_group_id))
        assert success is True
        assert len(result) <= agent.TOOL_RESULT_MAX_CHARS + 100
