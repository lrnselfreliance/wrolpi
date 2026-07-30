"""Hold the frontend's test fixtures to the API's OpenAPI spec.

The React specs stub API responses with the fixtures in `app/src/test-fixtures.js`.  Nothing
connected those to the API, so they were a snapshot of what the endpoints returned whenever
each was written, and they drifted silently: a field added to an endpoint simply never appeared
in them, and every frontend test carried on passing against a body the API had stopped
returning.  A fixture that has drifted is worse than none, because the test still passes.

These tests close the loop in two steps, because the spec was not trustworthy either -- it
declared `hotspot_status` and `throttle_status`, which moved to the Controller and which the
handler had long stopped returning, and omitted four fields it did return:

    handler  <->  OpenAPI spec  <->  test-fixtures.js

The first pair keeps the published spec honest about the endpoint (it is what /docs shows a
user, so it is worth being right on its own account).  The second keeps the fixtures honest
about the spec.  Neither can drift without failing here.
"""
import pathlib
import re

import pytest

TEST_FIXTURES_JS = pathlib.Path(__file__).parents[2] / 'app/src/test-fixtures.js'


def spec_properties(spec: dict, path: str, method: str = 'get') -> set:
    """The property names the OpenAPI spec promises for an endpoint's response.

    sanic-ext inlines the response schema under the path rather than naming it in
    components/schemas, so read it from where it actually is.
    """
    try:
        responses = spec['paths'][path][method]['responses']
    except KeyError as e:
        raise AssertionError(f'{method.upper()} {path} is missing from the OpenAPI spec') from e

    # 'default' is what sanic-ext uses when the definition names no status code.
    response = responses.get('default') or responses.get('200')
    assert response, f'{method.upper()} {path} declares no response schema'
    content = response['content']
    schema = (content.get('*/*') or content.get('application/json'))['schema']
    properties = schema.get('properties')
    assert properties, f'{method.upper()} {path} declares a response with no properties'
    return set(properties)


def fixture_keys(name: str) -> set:
    """The top-level keys of a fixture factory in test-fixtures.js.

    Read from source rather than executed: node is not necessarily available where pytest runs,
    and this only needs the shape.  Anchoring on four-space indentation takes the top level
    only, leaving nested objects (statusFixture's `downloads`) out of it.
    """
    source = TEST_FIXTURES_JS.read_text()
    match = re.search(
        rf'export const {name} = \(overrides = {{}}\) => \(\{{(.*?)\n}}\);',
        source,
        re.S,
    )
    assert match, f'{name} is not defined in {TEST_FIXTURES_JS.name} in the expected form'
    body = match.group(1)
    # Drop nested objects so their inner keys are not mistaken for top-level ones.
    body = re.sub(r'\{[^{}]*}', '{}', body)
    # Digits included: `is_rpi4` and `is_rpi5` are real keys, and a reader that skips them
    # reports the fixture as missing fields it actually has.
    keys = set(re.findall(r'^    ([a-z0-9_]+):', body, re.M))
    assert keys, f'{name} appears to have no keys'
    return keys


async def get_spec(async_client) -> dict:
    request, response = await async_client.get('/docs/openapi.json')
    assert response.status == 200, 'the OpenAPI spec is not being served'
    return response.json


@pytest.mark.asyncio
async def test_settings_spec_matches_the_handler(async_client, test_directory):
    """What /api/settings returns is what the spec says it returns."""
    spec = await get_spec(async_client)
    declared = spec_properties(spec, '/api/settings')

    request, response = await async_client.get('/api/settings')
    assert response.status == 200
    returned = set(response.json)

    assert declared == returned, (
        'the OpenAPI spec and /api/settings disagree.\n'
        f'  spec declares, handler omits: {sorted(declared - returned)}\n'
        f'  handler returns, spec omits:  {sorted(returned - declared)}'
    )


@pytest.mark.asyncio
async def test_settings_fixture_matches_the_spec(async_client):
    """app/src/test-fixtures.js settingsFixture() carries every field the API returns.

    A missing field is invisible in the frontend suite: the component reads `undefined` from a
    body the real API would have filled in, and the assertion about everything else still
    passes.
    """
    spec = await get_spec(async_client)
    declared = spec_properties(spec, '/api/settings')
    fixture = fixture_keys('settingsFixture')

    assert declared == fixture, (
        'settingsFixture has drifted from /api/settings.\n'
        f'  API returns, fixture omits: {sorted(declared - fixture)}\n'
        f'  fixture invents:            {sorted(fixture - declared)}'
    )


@pytest.mark.asyncio
async def test_status_spec_matches_the_handler(async_client, test_directory):
    spec = await get_spec(async_client)
    declared = spec_properties(spec, '/api/status')

    request, response = await async_client.get('/api/status')
    assert response.status == 200
    returned = set(response.json)

    assert declared == returned, (
        'the OpenAPI spec and /api/status disagree.\n'
        f'  spec declares, handler omits: {sorted(declared - returned)}\n'
        f'  handler returns, spec omits:  {sorted(returned - declared)}'
    )


@pytest.mark.asyncio
async def test_status_fixture_matches_the_spec(async_client):
    spec = await get_spec(async_client)
    declared = spec_properties(spec, '/api/status')
    fixture = fixture_keys('statusFixture')

    assert declared == fixture, (
        'statusFixture has drifted from /api/status.\n'
        f'  API returns, fixture omits: {sorted(declared - fixture)}\n'
        f'  fixture invents:            {sorted(fixture - declared)}'
    )


@pytest.mark.asyncio
async def test_which_fixtures_the_spec_can_vouch_for(async_client):
    """Name the API-shaped fixtures this file does not cover, and why.

    `domainFixture` and `tagFixture` stand in for endpoint responses too, but the endpoints
    behind them carry an `@openapi.definition` with a description and no `response=`, so the
    spec promises nothing about their bodies and there is nothing to compare against.  They are
    therefore still hand-maintained guesses.

    This is a ratchet: declare a response on one of those endpoints, add its fixture to the
    checks above, and delete its line here.  Without it the gap reads as coverage.
    """
    spec = await get_spec(async_client)

    checked = {'settingsFixture': '/api/settings', 'statusFixture': '/api/status'}
    for name, path in checked.items():
        assert spec_properties(spec, path), f'{name} claims to be checked against {path}'

    unchecked = {
        'domainFixture': 'the domains endpoint declares no response schema',
        'tagFixture': 'GET /api/tag declares no response schema',
        # This one is a provider value rather than an API body, so it does not belong above --
        # but it is unguarded at the other end too.  test-fixtures.test.js compares each
        # context fixture against its `createContext` default, and this context's default is
        # `null` on purpose: `useFileWorkerStatus` relies on that to detect a missing provider.
        # So there is no declared shape at either end.  Naming it beats it looking covered.
        'fileWorkerStatusFixture': 'FileWorkerStatusContext defaults to null, by design',
    }

    source = TEST_FIXTURES_JS.read_text()
    api_fixtures = set(re.findall(r'^export const ([a-zA-Z]+Fixture) =', source, re.M))
    # domainsFixture is a list built from domainFixture, and the *Context* fixtures are held to
    # their React contexts by the frontend's own test-fixtures.test.js.
    api_fixtures -= {'domainsFixture'}
    api_fixtures = {n for n in api_fixtures if 'Context' not in n}

    assert api_fixtures == set(checked) | set(unchecked), (
        'an API-shaped fixture is neither checked against the spec nor listed as uncheckable:\n'
        f'  {sorted(api_fixtures - set(checked) - set(unchecked))}'
    )


def test_the_fixture_reader_actually_reads():
    """Guard the regex above: it silently returning nothing would make every check vacuous."""
    keys = fixture_keys('settingsFixture')

    assert 'media_directory' in keys
    assert len(keys) > 10
    # Nested objects must not leak their keys into the top level.
    assert 'pending' not in fixture_keys('statusFixture')
    # Keys containing digits must be read; missing them reports fields the fixture has as
    # absent, which is exactly what this reader did at first.
    assert {'is_rpi4', 'is_rpi5'}.issubset(fixture_keys('statusFixture'))
