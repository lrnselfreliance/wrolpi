"""POST /api/chat — the agent loop, streamed over SSE.

Events (each `event: <name>` with a JSON `data:` line):
  status       {message}                     e.g. "Loading the model…"
  token        {content}                     one streamed answer fragment
  tool_call    {tool, args}                  the model is using a tool
  tool_result  {tool, success}               the tool finished
  done         {content}                     the complete final answer
  error        {message}

The loop: build the mode's system prompt and tool definitions -> stream from llama-server ->
execute tool calls against /api/ai only (the mode allowlist is enforced server-side) -> repeat,
bounded by ai.yaml's max_tool_calls -> stream the final answer.

A streaming response outlives the request middleware, so nothing here may use
request.ctx.session; tools execute through the blueprint, which manages its own sessions."""
import dataclasses
import json
import time
from http import HTTPStatus
from typing import AsyncGenerator, List, Optional

from sanic import Blueprint, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import aiohttp_post, logger
from wrolpi.errors import APIError, ValidationError

from . import agent, service
from .config import get_ai_config
from .modes import MODE_SUGGESTIONS, MODES

chat_bp = Blueprint('AIChat', url_prefix='/api/chat')

logger = logger.getChild(__name__)

# The whole conversation turn (all tool calls and answers) must finish within this.
CHAT_TIMEOUT_SECONDS = 600
FALLBACK_MESSAGE = "I couldn't complete that request.  Try rephrasing, or a more specific question."


class AIDisabled(APIError):
    code = 'AI_DISABLED'
    summary = 'AI is not enabled.  Enable it and select a model on the AI page.'
    status_code = HTTPStatus.CONFLICT


@dataclasses.dataclass
class ChatRequest:
    mode: str = ''
    messages: List[dict] = dataclasses.field(default_factory=list)
    model: Optional[str] = None  # reserved; llama-server runs the single active model


@chat_bp.get('/modes')
@openapi.description('The available chat modes with their suggestion chips.')
async def get_modes(_: Request):
    from wrolpi.api_utils import json_response
    modes = [dict(name=name, suggestions=MODE_SUGGESTIONS.get(name, [])) for name in MODES]
    return json_response(dict(modes=modes))


async def llama_chat_stream(messages: List[dict], tools: List[dict]) -> AsyncGenerator[dict, None]:
    """Stream one /v1/chat/completions call from llama-server.

    Yields {'type': 'token', 'content': str} for answer fragments, then exactly one
    {'type': 'stop', 'tool_calls': [...]} where tool_calls is empty for a final answer.
    Patched in tests."""
    body = dict(messages=messages, stream=True)
    if tools:
        body['tools'] = tools

    tool_calls = {}  # index -> {id, name, arguments}
    async with aiohttp_post(f'{service.LLAMA_URL}/v1/chat/completions', json_=body,
                            timeout=CHAT_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f'llama-server returned HTTP {response.status}')
        async for raw_line in response.content:
            line = raw_line.decode('UTF-8', errors='replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            choice = (chunk.get('choices') or [{}])[0]
            delta = choice.get('delta') or {}
            if content := delta.get('content'):
                yield dict(type='token', content=content)
            for tool_call in delta.get('tool_calls') or []:
                index = tool_call.get('index', 0)
                entry = tool_calls.setdefault(index, dict(id=None, name='', arguments=''))
                if tool_call.get('id'):
                    entry['id'] = tool_call['id']
                function = tool_call.get('function') or {}
                if function.get('name'):
                    entry['name'] = function['name']
                if function.get('arguments'):
                    entry['arguments'] += function['arguments']

    yield dict(type='stop', tool_calls=[tool_calls[i] for i in sorted(tool_calls)])


async def _send_event(response, event: str, data: dict):
    await response.send(f'event: {event}\ndata: {json.dumps(data, default=str)}\n\n')


@chat_bp.post('/')
@openapi.definition(
    summary='Chat with the local AI assistant (SSE stream)',
    body=ChatRequest,
)
@validate(ChatRequest)
async def post_chat(request: Request, body: ChatRequest):
    if body.mode not in MODES:
        raise ValidationError(f'Unknown mode: {body.mode!r}.  Modes: {sorted(MODES)}')
    if not body.messages:
        raise ValidationError('messages must not be empty')
    config = get_ai_config()
    if not config.enabled or not config.active_model:
        raise AIDisabled()

    mode = MODES[body.mode]
    tools = agent.get_mode_tools(mode['tools'])
    max_tool_calls = config.max_tool_calls
    deadline = time.time() + CHAT_TIMEOUT_SECONDS

    response = await request.respond(content_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        # Ask proxies not to buffer the stream.
        'X-Accel-Buffering': 'no',
    })

    try:
        if not await service.llama_healthy():
            await _send_event(response, 'status', dict(message='Loading the model…'))
        if not await service.ensure_llama_running():
            await _send_event(response, 'error', dict(message='The AI service could not be started.'))
            return

        messages = [dict(role='system', content=mode['system_prompt'])]
        messages += [dict(role=m.get('role', 'user'), content=m.get('content', '')) for m in body.messages]

        final_answer = []
        for _ in range(max_tool_calls + 1):
            if time.time() > deadline:
                await _send_event(response, 'error', dict(message=FALLBACK_MESSAGE))
                return

            service.record_llm_activity()
            tool_calls = []
            final_answer = []
            async for event in llama_chat_stream(messages, tools):
                if event['type'] == 'token':
                    final_answer.append(event['content'])
                    await _send_event(response, 'token', dict(content=event['content']))
                elif event['type'] == 'stop':
                    tool_calls = event['tool_calls']

            if not tool_calls:
                # A final answer.
                content = ''.join(final_answer).strip()
                await _send_event(response, 'done', dict(content=content or FALLBACK_MESSAGE))
                return

            # Execute the tool calls, then loop for the model's next step.
            messages.append(dict(role='assistant', content=''.join(final_answer) or None, tool_calls=[
                dict(id=i['id'] or f'call_{n}', type='function',
                     function=dict(name=i['name'], arguments=i['arguments']))
                for n, i in enumerate(tool_calls)
            ]))
            for n, tool_call in enumerate(tool_calls):
                name = tool_call['name']
                try:
                    args = json.loads(tool_call['arguments']) if tool_call['arguments'] else {}
                except ValueError:
                    args = None
                await _send_event(response, 'tool_call', dict(tool=name, args=args))
                if args is None:
                    success, result = False, 'The tool arguments were not valid JSON.  Try again.'
                else:
                    success, result = await agent.execute_tool(mode['tools'], name, args)
                await _send_event(response, 'tool_result', dict(tool=name, success=success))
                messages.append(dict(role='tool', tool_call_id=tool_call['id'] or f'call_{n}',
                                     content=result))

        # Tool-call budget exhausted without a final answer.
        await _send_event(response, 'error', dict(message=FALLBACK_MESSAGE))
    except Exception as e:
        logger.error('Chat failed', exc_info=e)
        try:
            await _send_event(response, 'error', dict(message='The AI failed to answer.  Check the logs.'))
        except Exception:
            pass
    finally:
        await response.eof()
