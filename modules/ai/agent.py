"""Tool definitions and tool execution for the agent loop.

The /api/ai blueprint IS the tool catalog: tool definitions are generated from the blueprint's
own OpenAPI operations (in-process — the spec endpoint is not proxied by Caddy), so there is no
separate registry to drift.  operationIds are the tool names; @openapi.description strings are
the tool descriptions; @validate dataclasses and @openapi.parameter declarations become the
JSON-schema parameters."""
import dataclasses
import json
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

from sanic_ext.extensions.openapi.builders import OperationStore, SpecificationBuilder
from sanic_ext.utils.route import get_all_routes

from wrolpi.api_utils import api_app
from wrolpi.common import aiohttp_get, aiohttp_post, logger
from wrolpi.vars import API_PORT

from .lib import PAGE_SIZE

logger = logger.getChild(__name__)

AI_PATH_PREFIX = '/api/ai/'
# Manage endpoints are for the Manage tab, never the model.
EXCLUDED_PREFIX = '/api/ai/manage'

# Tool results are capped so one result cannot blow a small context; content endpoints page.
TOOL_RESULT_MAX_CHARS = PAGE_SIZE + 1_000

_TYPE_MAP = {'integer': int, 'number': float, 'boolean': bool, 'string': str}


@dataclasses.dataclass
class ToolDefinition:
    name: str
    description: str
    method: str  # 'get' or 'post'
    path: str  # e.g. '/api/ai/videos/{file_group_id}/captions'
    path_params: Dict[str, dict]  # name -> JSON schema
    query_params: Dict[str, dict]
    body_params: Dict[str, dict]

    def parameters_schema(self) -> dict:
        """One flat JSON-schema object; the executor routes each arg to its place."""
        properties = {**self.body_params, **self.query_params, **self.path_params}
        required = sorted(self.path_params)
        schema = dict(type='object', properties=properties)
        if required:
            schema['required'] = required
        return schema

    def as_openai_tool(self) -> dict:
        return dict(type='function', function=dict(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema(),
        ))


def _build_ai_spec() -> dict:
    """Populate and serialize the OpenAPI spec for the AI blueprint.

    Replicates sanic-ext's build_spec startup hook (sanic_ext/extensions/openapi/blueprint.py) for
    just our routes, so tool definitions work identically in production and under pytest."""
    spec = SpecificationBuilder()
    store = OperationStore()
    for uri, route_name, route_parameters, method_handlers, host in get_all_routes(api_app, '/docs'):
        if not uri.startswith(AI_PATH_PREFIX):
            continue
        for method, handler in method_handlers:
            if method in ('OPTIONS', 'HEAD', 'TRACE'):
                continue
            if handler not in store and (func := getattr(handler, '__func__', None)) and func in store:
                handler = func
            operation = store[handler]
            if operation._exclude:
                continue
            operation._default['operationId'] = f'{method.lower()}~{route_name}'
            for parameter in route_parameters:
                if not any(p.fields['name'] == parameter.name for p in operation.parameters):
                    operation.parameter(parameter.name, parameter.cast, 'path')
            operation._app = api_app
            spec.operation(uri, method, operation)
    return spec.build(api_app).serialize()


def _resolve_ref(spec: dict, schema: Optional[dict]) -> dict:
    if not schema:
        return {}
    if ref := schema.get('$ref'):
        name = ref.rsplit('/', 1)[-1]
        return (spec.get('components', {}).get('schemas', {}) or {}).get(name, {})
    return schema


def _clean_property(schema: dict) -> dict:
    """A lean JSON-schema property for the model: type (+items), nothing else."""
    schema = schema or {}
    cleaned = {}
    if type_ := schema.get('type'):
        cleaned['type'] = type_
    if items := schema.get('items'):
        cleaned['items'] = _clean_property(items)
    return cleaned or {'type': 'string'}


_TOOL_DEFINITIONS: Optional[Dict[str, ToolDefinition]] = None


def get_ai_tool_definitions(refresh: bool = False) -> Dict[str, ToolDefinition]:
    """All tools the agent loop can ever execute, keyed by name.  Built lazily, cached.

    This map is also the hard allowlist: the executor can only reach /api/ai endpoints that
    appear here, and manage endpoints never do."""
    global _TOOL_DEFINITIONS
    if _TOOL_DEFINITIONS is not None and not refresh:
        return _TOOL_DEFINITIONS

    spec = _build_ai_spec()
    tools = {}
    for path, operations in (spec.get('paths') or {}).items():
        if not path.startswith(AI_PATH_PREFIX) or path.startswith(EXCLUDED_PREFIX):
            continue
        for method, operation in operations.items():
            if method not in ('get', 'post'):
                continue
            name = operation.get('operationId')
            description = operation.get('description') or operation.get('summary') or ''
            if not name or '~' in name:
                # Every tool endpoint must declare a deliberate @openapi.operation name.
                logger.warning(f'AI endpoint without an operation name is not a tool: {method} {path}')
                continue

            path_params, query_params = {}, {}
            for parameter in operation.get('parameters') or []:
                cleaned = _clean_property(parameter.get('schema'))
                if parameter.get('in') == 'path':
                    path_params[parameter['name']] = cleaned
                elif parameter.get('in') == 'query':
                    query_params[parameter['name']] = cleaned

            body_params = {}
            content = (operation.get('requestBody') or {}).get('content') or {}
            # sanic-ext serializes dataclass bodies under '*/*'.
            body_schema = (content.get('application/json') or content.get('*/*') or {}).get('schema')
            body_schema = _resolve_ref(spec, body_schema)
            for prop_name, prop_schema in (body_schema.get('properties') or {}).items():
                body_params[prop_name] = _clean_property(_resolve_ref(spec, prop_schema))

            tools[name] = ToolDefinition(
                name=name, description=description, method=method, path=path,
                path_params=path_params, query_params=query_params, body_params=body_params,
            )

    _TOOL_DEFINITIONS = tools
    return tools


def get_mode_tools(mode_tools: tuple) -> List[dict]:
    """OpenAI-format tool definitions for one mode's allowlist."""
    definitions = get_ai_tool_definitions()
    return [definitions[name].as_openai_tool() for name in mode_tools if name in definitions]


async def call_ai_endpoint(method: str, path: str, query: dict, body: Optional[dict]) -> Tuple[int, dict]:
    """Execute one blueprint endpoint over localhost.  Patched in tests."""
    url = f'http://127.0.0.1:{API_PORT}{path}'
    if query:
        url = f'{url}?{urlencode(query)}'
    if method == 'post':
        async with aiohttp_post(url, json_=body or {}, timeout=60) as response:
            return response.status, await response.json()
    async with aiohttp_get(url, timeout=60) as response:
        return response.status, await response.json()


def _validate_args(tool: ToolDefinition, args: dict) -> Optional[str]:
    """Return a crisp, instructive error string for the model, or None when the args are usable."""
    known = {**tool.path_params, **tool.query_params, **tool.body_params}
    if unknown := sorted(set(args) - set(known)):
        return f'Unknown arguments {unknown}.  {tool.name} accepts: {sorted(known)}.'
    if missing := sorted(set(tool.path_params) - set(args)):
        return f'Missing required arguments {missing} for {tool.name}.'
    for name, value in args.items():
        expected = _TYPE_MAP.get(known[name].get('type'))
        if expected in (int, float) and value is not None and not isinstance(value, (int, float)) \
                and not (isinstance(value, str) and value.lstrip('-').isdigit()):
            return f'Argument {name} must be a {known[name]["type"]}, got {value!r}.'
        # Path parameters land in the request URL; refuse anything that could escape the
        # endpoint's own path (the allowlist must hold even against a crafted value).
        if name in tool.path_params and isinstance(value, str):
            segments = value.split('/')
            if value.startswith('/') or '' in segments or '.' in segments or '..' in segments:
                return f'Argument {name} must not contain path traversal.'
    return None


async def execute_tool(mode_tools: tuple, name: str, args: dict) -> Tuple[bool, str]:
    """Validate and execute one tool call.  Returns (success, result text for the model).

    Every failure is a plain-language error string — small models retry well on crisp errors."""
    definitions = get_ai_tool_definitions()
    if name not in definitions or name not in mode_tools:
        available = sorted(set(mode_tools) & set(definitions))
        return False, f'Unknown tool {name!r}.  Available tools: {available}.'
    tool = definitions[name]

    args = args or {}
    if error := _validate_args(tool, args):
        return False, error

    path = tool.path
    for param in tool.path_params:
        # Encode everything but '/' (help-doc slugs contain it); traversal was rejected above.
        path = path.replace(f'{{{param}}}', quote(str(args[param]), safe='/'))
    # The substituted path must still be inside the endpoint the tool declares.
    static_prefix = tool.path.split('{', 1)[0]
    if not path.startswith(static_prefix) or '..' in path.split('/'):
        return False, f'Arguments produced an invalid path for {tool.name}.'
    query = {k: v for k, v in args.items() if k in tool.query_params and v is not None}
    body = {k: v for k, v in args.items() if k in tool.body_params} if tool.method == 'post' else None

    try:
        status, response = await call_ai_endpoint(tool.method, path, query, body)
    except Exception as e:
        logger.error(f'Tool {name} failed', exc_info=e)
        return False, f'Tool {name} failed to execute; try different arguments or another tool.'

    text = json.dumps(response, default=str)
    if len(text) > TOOL_RESULT_MAX_CHARS:
        text = text[:TOOL_RESULT_MAX_CHARS] + '… (result truncated; use limit/offset to get less at a time)'
    if status >= 400:
        message = response.get('message') or response.get('error') or f'HTTP {status}'
        return False, f'{tool.name} returned an error: {message}'
    return True, text
