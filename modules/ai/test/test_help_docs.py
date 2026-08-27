"""Tests for the help-docs search (Help mode).  Uses a fixture corpus, never the real submodule."""
import json
from http import HTTPStatus

import pytest

from modules.ai import help_docs, lib


@pytest.fixture
def help_corpus(test_directory, monkeypatch):
    """A small help-docs corpus in a temporary directory."""
    docs = test_directory / 'help-docs'
    (docs / 'system').mkdir(parents=True)
    (docs / 'modules').mkdir()
    (docs / 'index.md').write_text('# Home\n\nWelcome to WROLPi help.\n')
    (docs / 'system/logs.md').write_text(
        '# Logs\n\n## Reading logs\n\nUse journalctl to read service logs on a WROLPi.\n')
    (docs / 'modules/videos.md').write_text(
        '# Videos\n\n## Downloading\n\nVideos are downloaded with yt-dlp into channels.\n'
        + ('More text about videos. ' * 400))  # > one page
    monkeypatch.setenv('HELP_DOCS_DIR', str(docs))
    help_docs._CACHE.clear()
    try:
        yield docs
    finally:
        help_docs._CACHE.clear()


def test_search_help_scoring(help_corpus):
    """Title matches outrank body matches; snippets show context."""
    results, total = help_docs.search_help('logs')
    assert total == 1
    assert results[0]['slug'] == 'system/logs'
    assert results[0]['title'] == 'Logs'
    assert results[0]['link'] == '/system/logs/'
    assert 'journalctl' in results[0]['snippet'] or 'Logs' in results[0]['snippet']

    # 'videos' matches the videos doc far better than any other.
    results, _ = help_docs.search_help('downloading videos')
    assert results[0]['slug'] == 'modules/videos'

    # No matches.
    results, total = help_docs.search_help('xyzzy')
    assert results == [] and total == 0


def test_help_doc_cache_invalidation(help_corpus):
    """Edited files are re-parsed; deleted files leave the corpus."""
    results, _ = help_docs.search_help('welcome')
    assert results[0]['slug'] == 'index'
    assert results[0]['link'] == '/'

    (help_corpus / 'index.md').write_text('# Home\n\nGreetings, traveler.\n')
    import os
    os.utime(help_corpus / 'index.md', (0, 0))  # force a distinct mtime
    results, total = help_docs.search_help('welcome')
    assert total == 0
    results, _ = help_docs.search_help('greetings')
    assert results[0]['slug'] == 'index'

    (help_corpus / 'system/logs.md').unlink()
    _, total = help_docs.search_help('logs')
    assert total == 0


def test_get_help_doc_refuses_traversal(help_corpus):
    assert help_docs.get_help_doc('../secrets') is None
    assert help_docs.get_help_doc('system/logs') is not None


@pytest.mark.asyncio
async def test_ai_help_endpoints(async_client, help_corpus):
    """Help can be searched and pages read as paged markdown."""
    content = dict(search_str='logs')
    request, response = await async_client.post('/api/ai/help/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    result = response.json['results'][0]
    assert result['slug'] == 'system/logs'

    request, response = await async_client.get(f'/api/ai/help/{result["slug"]}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['title'] == 'Logs'
    assert 'journalctl' in response.json['content']

    # Long pages are paged.
    request, response = await async_client.get('/api/ai/help/modules/videos')
    assert response.status_code == HTTPStatus.OK
    assert response.json['next_offset'] == lib.PAGE_SIZE

    # Unknown page.
    request, response = await async_client.get('/api/ai/help/no/such/page')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Empty search is a clear error.
    request, response = await async_client.post('/api/ai/help/search', content=json.dumps(dict()))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_ai_help_not_installed(async_client, monkeypatch, test_directory):
    """A missing help directory returns empty results with a message, never a 500."""
    monkeypatch.setenv('HELP_DOCS_DIR', str(test_directory / 'nope'))
    help_docs._CACHE.clear()

    content = dict(search_str='logs')
    request, response = await async_client.post('/api/ai/help/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['results'] == []
    assert 'not installed' in response.json['message']

    request, response = await async_client.get('/api/ai/help/system/logs')
    assert response.status_code == HTTPStatus.NOT_FOUND
