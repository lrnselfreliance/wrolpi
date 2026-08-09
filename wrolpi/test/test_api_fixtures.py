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


def json_kind(value) -> str:
    """The OpenAPI `type` a Python value corresponds to."""
    # bool before int: bool is a subclass of int, so the order matters.
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    return 'null'


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/api/settings', '/api/status'])
async def test_the_spec_declares_the_right_types(async_client, test_directory, path):
    """Matching names is not matching shapes.

    `StatusResponse` declared `downloads: int` while the handler has long sent the download
    manager's summary object, and `wrol_mode: str` where it sends a boolean.  The published
    contract was telling a generated client to expect a number where it will receive a dict.  A
    name-only comparison passes straight over both, which is what the first version of this file
    did.

    Only the pairs the spec gives a `type` for and the handler actually sent are compared; a
    `null` from an optional field says nothing about its declared type.
    """
    spec = await get_spec(async_client)
    properties = spec['paths'][path]['get']['responses']['default'] \
        ['content']['*/*']['schema']['properties']

    request, response = await async_client.get(path)
    assert response.status == 200

    mismatches = []
    for name, value in response.json.items():
        declared = properties.get(name, {}).get('type')
        if not declared or value is None:
            continue
        actual = json_kind(value)
        if declared != actual:
            mismatches.append(f'{name}: spec says {declared}, handler sent {actual}')

    assert not mismatches, f'the OpenAPI spec declares the wrong type for {path}:\n  ' \
                           + '\n  '.join(mismatches)


@pytest.mark.asyncio
async def test_downloads_summary_fixture_matches_the_download_manager(async_client, test_session):
    """The one nested object worth checking by hand.

    `/api/status` returns an empty `downloads` while the database is down, which it is for much
    of the test suite, so the endpoint's own response cannot vouch for the shape.  The download
    manager's summary is the authority instead -- and statusFixture was missing
    `daily_limit_reached` from it, a field the API has always sent.
    """
    from wrolpi.downloader import download_manager

    declared = set(download_manager.get_summary())

    source = TEST_FIXTURES_JS.read_text()
    block = re.search(r'^    downloads: \{(.*?)\n    },', source, re.S | re.M)
    assert block, 'statusFixture no longer has a `downloads` object in the expected form'
    fixture = set(re.findall(r'^        ([a-z0-9_]+):', block.group(1), re.M))
    assert fixture, 'the downloads block appears to have no keys'

    assert declared == fixture, (
        "statusFixture's downloads has drifted from DownloadManager.get_summary().\n"
        f'  manager reports, fixture omits: {sorted(declared - fixture)}\n'
        f'  fixture invents:                {sorted(fixture - declared)}'
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
