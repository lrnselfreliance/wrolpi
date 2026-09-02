"""End-to-end tests for /api/chat: SSE framing, the agent loop, and its guardrails.

llama-server is scripted (llama_chat_stream is patched); tool calls execute against the real
/api/ai blueprint through the test client."""
import json
from http import HTTPStatus
from unittest import mock
from urllib.parse import urlencode

import pytest

from modules.ai.config import get_ai_config


@pytest.fixture
async def ai_enabled(async_client, test_ai_config, test_directory):
    """AI enabled with a (fake) downloaded model, llama-server 'healthy'."""
    models_dir = test_directory / 'ai/models'
    models_dir.mkdir(parents=True)
    (models_dir / 'test.gguf').write_bytes(b'GGUF')
    config = get_ai_config()
    config.active_model = 'test.gguf'
    config.enabled = True

    with mock.patch('modules.ai.service.llama_healthy', return_value=True), \
            mock.patch('modules.ai.chat.service.ensure_llama_running', return_value=True):
        yield config


def _llama_script(*turns):
    """Patch llama_chat_stream with scripted turns.

    Each turn is a list of events ({'type': 'token'|'stop', ...}); turn N answers call N."""
    calls = dict(count=0, messages=[])

    def factory(messages, tools):
        calls['messages'].append(messages)
        turn = turns[min(calls['count'], len(turns) - 1)]
        calls['count'] += 1

        async def generator():
            for event in turn:
                yield event

        return generator()

    return mock.patch('modules.ai.chat.llama_chat_stream', side_effect=factory), calls


def _endpoint_shim(async_client):
    async def shim(method, path, query, body):
        url = f'{path}?{urlencode(query)}' if query else path
        if method == 'post':
            request, response = await async_client.post(url, content=json.dumps(body or {}))
        else:
            request, response = await async_client.get(url)
        return response.status_code, response.json

    return mock.patch('modules.ai.agent.call_ai_endpoint', side_effect=shim)


def _parse_sse(text):
    """[(event, data_dict), ...] from an SSE body."""
    events = []
    for block in text.split('\n\n'):
        event = data = None
        for line in block.splitlines():
            if line.startswith('event:'):
                event = line[6:].strip()
            elif line.startswith('data:'):
                data = json.loads(line[5:].strip())
        if event:
            events.append((event, data))
    return events


@pytest.mark.asyncio
async def test_chat_tool_call_then_answer(async_client, ai_enabled, video_factory, test_session):
    """The loop executes a tool call against the blueprint, then streams the final answer."""
    video_factory(title='pressure canning')
    test_session.commit()

    patch, calls = _llama_script(
        [dict(type='stop', tool_calls=[
            dict(id='call_1', name='search_videos', arguments='{"search_str": "canning"}')])],
        [dict(type='token', content='Found '), dict(type='token', content='one video.'),
         dict(type='stop', tool_calls=[])],
    )
    body = dict(mode='research', messages=[dict(role='user', content='Find videos about canning')])
    with patch, _endpoint_shim(async_client):
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK

    events = _parse_sse(response.text)
    # A status event precedes every model call so slow CPUs never leave the stream silent.
    names = [e for e, _ in events if e != 'status']
    assert names == ['tool_call', 'tool_result', 'token', 'token', 'done']
    tool_call = dict(events)['tool_call']
    assert tool_call == dict(tool='search_videos', args=dict(search_str='canning'))
    assert dict(events)['tool_result'] == dict(tool='search_videos', success=True)
    assert dict(events)['done'] == dict(content='Found one video.')

    # The second llama call saw the system prompt (with the live library map), the mode's
    # worked example, the user message, and the tool result.
    second_call_messages = calls['messages'][1]
    assert second_call_messages[0]['role'] == 'system'
    assert 'librarian' in second_call_messages[0]['content']
    assert 'Today is' in second_call_messages[0]['content']
    assert "library contains" in second_call_messages[0]['content']
    example = [m for m in second_call_messages if m.get('content') and 'Bakehouse' in str(m.get('content'))]
    assert example, 'the research few-shot example is in context'
    assert second_call_messages[-1]['role'] == 'tool'
    assert 'pressure canning' in second_call_messages[-1]['content']


@pytest.mark.asyncio
async def test_chat_plain_answer(async_client, ai_enabled):
    """A toolless answer streams tokens then done."""
    patch, _ = _llama_script(
        [dict(type='token', content='Hello!'), dict(type='stop', tool_calls=[])],
    )
    body = dict(mode='help', messages=[dict(role='user', content='hi')])
    with patch:
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    events = [e for e in _parse_sse(response.text) if e[0] != 'status']
    assert events == [('token', dict(content='Hello!')), ('done', dict(content='Hello!'))]


@pytest.mark.asyncio
async def test_chat_tool_loop_bounded(async_client, ai_enabled):
    """A model that never stops calling tools hits max_tool_calls and gets the fallback."""
    get_ai_config().max_tool_calls = 2
    patch, calls = _llama_script(
        [dict(type='stop', tool_calls=[dict(id='x', name='search_help', arguments='{"search_str": "a"}')])],
    )
    body = dict(mode='help', messages=[dict(role='user', content='loop forever')])
    with patch, _endpoint_shim(async_client):
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    events = _parse_sse(response.text)
    assert events[-1][0] == 'error'
    assert calls['count'] == 3  # initial + max_tool_calls


@pytest.mark.asyncio
async def test_chat_invalid_tool_args(async_client, ai_enabled):
    """Bad tool JSON and disallowed tools come back to the model as errors, not crashes."""
    patch, calls = _llama_script(
        [dict(type='stop', tool_calls=[dict(id='x', name='search_help', arguments='{not json')])],
        [dict(type='stop', tool_calls=[dict(id='y', name='list_disks', arguments='{}')])],
        [dict(type='token', content='Sorry.'), dict(type='stop', tool_calls=[])],
    )
    body = dict(mode='help', messages=[dict(role='user', content='hi')])
    with patch, _endpoint_shim(async_client):
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    events = _parse_sse(response.text)
    results = [d for e, d in events if e == 'tool_result']
    assert results[0]['success'] is False  # invalid JSON arguments
    assert results[1]['success'] is False  # list_disks is not a help-mode tool
    assert events[-1] == ('done', dict(content='Sorry.'))
    # The model saw instructive errors (skip the few-shot example's tool messages).
    tool_messages = [m for m in calls['messages'][-1]
                     if m['role'] == 'tool' and not str(m.get('tool_call_id', '')).startswith('ex_')]
    assert 'not valid JSON' in tool_messages[0]['content']
    assert 'Unknown tool' in tool_messages[1]['content']


@pytest.mark.asyncio
async def test_chat_validation(async_client, ai_enabled):
    """Bad requests are refused before the stream starts."""
    request, response = await async_client.post(
        '/api/chat/', content=json.dumps(dict(mode='nope', messages=[dict(role='user', content='x')])))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    request, response = await async_client.post(
        '/api/chat/', content=json.dumps(dict(mode='help', messages=[])))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_chat_disabled(async_client, test_ai_config):
    """Chat refuses when AI is disabled or no model is selected."""
    body = dict(mode='help', messages=[dict(role='user', content='x')])
    request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json['code'] == 'AI_DISABLED'


@pytest.mark.asyncio
async def test_chat_modes_endpoint(async_client):
    """The Chat tab can list modes and their suggestion chips."""
    request, response = await async_client.get('/api/chat/modes')
    assert response.status_code == HTTPStatus.OK
    modes = {m['name']: m for m in response.json['modes']}
    assert set(modes) == {'help', 'research', 'system'}
    assert modes['research']['suggestions']


def test_trim_history():
    """Old turns are dropped first; fixed messages and the current turn are never trimmed."""
    from modules.ai import chat
    fixed = [dict(role='system', content='s' * 400), dict(role='user', content='current')]
    history = [dict(role='user', content=f'old {i} ' + 'x' * 400) for i in range(10)]

    # A huge budget keeps everything.
    assert chat.trim_history(history, fixed, [], budget=10_000) == history

    # A small budget drops the OLDEST turns.
    trimmed = chat.trim_history(history, fixed, [], budget=400)
    assert len(trimmed) < len(history)
    assert trimmed == history[len(history) - len(trimmed):]

    # A budget the fixed messages alone exceed empties the history without crashing.
    assert chat.trim_history(history, fixed, [], budget=1) == []


@pytest.mark.asyncio
async def test_chat_context_full(async_client, ai_enabled):
    """A conversation that cannot fit the model context gets a clear error, not a bad answer."""
    from modules.ai import chat
    get_ai_config().context_size = 1  # far below the reply reserve

    patch, calls = _llama_script([dict(type='token', content='hi'), dict(type='stop', tool_calls=[])])
    body = dict(mode='help', messages=[dict(role='user', content='hello')])
    with patch:
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    events = _parse_sse(response.text)
    assert events[-1][0] == 'error'
    assert 'no longer fits' in events[-1][1]['message']
    assert calls['count'] == 0  # the model was never called


@pytest.mark.asyncio
async def test_chat_history_trimmed(async_client, ai_enabled):
    """Old turns are dropped to fit the context; the current question always survives."""
    get_ai_config().context_size = 4_096

    patch, calls = _llama_script([dict(type='token', content='ok'), dict(type='stop', tool_calls=[])])
    old_turns = []
    for i in range(6):
        old_turns += [dict(role='user', content=f'old question {i} ' + 'pad ' * 500),
                      dict(role='assistant', content=f'old answer {i} ' + 'pad ' * 500)]
    body = dict(mode='help', messages=old_turns + [dict(role='user', content='the current question')])
    with patch:
        request, response = await async_client.post('/api/chat/', content=json.dumps(body))
    assert _parse_sse(response.text)[-1][0] == 'done'

    sent = calls['messages'][0]
    contents = [str(m.get('content')) for m in sent]
    assert any('the current question' in c for c in contents)
    assert not any('old question 0' in c for c in contents)  # oldest turn was trimmed
