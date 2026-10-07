import json
import sqlite3
import time
from http import HTTPStatus

import pytest

from modules.repos import lib
from modules.repos.models import Repository


def set_readme(session, repo: Repository, readme_text: str):
    repo.readme_text = readme_text
    session.commit()


@pytest.mark.asyncio
async def test_search_repos(test_session, async_client, test_wrolpi_config):
    """Repos are found by their name, owner, and README; a name match outranks a README mention."""
    kiwix = lib.create_repository(test_session, 'https://github.com/kiwix/kiwix-tools', tag_name='software')
    maps = lib.create_repository(test_session, 'https://github.com/protomaps/basemaps')
    set_readme(test_session, kiwix, 'Kiwix tools serve Zim files offline.')
    set_readme(test_session, maps, 'Vector basemaps.  Works with kiwix-tools and offline maps.')

    def names(search_str=None, tag_names=None):
        repos, total = lib.search_repos(test_session, search_str, tag_names)
        assert total == len(repos)
        return [i['name'] for i in repos]

    assert names('kiwix') == ['kiwix-tools', 'basemaps']
    assert names('protomaps') == ['basemaps']  # The owner.
    assert names('vector') == ['basemaps']
    assert set(names('offline')) == {'kiwix-tools', 'basemaps'}
    assert names('zim -vector') == ['kiwix-tools']
    assert names('nothing') == []

    repos, _ = lib.search_repos(test_session, 'vector')
    assert repos[0]['readme_headline'] == '<b>Vector</b> basemaps.  Works with kiwix-tools and offline maps.'

    # Tags.
    assert names('offline', ['software']) == ['kiwix-tools']
    assert names(tag_names=['software']) == ['kiwix-tools']
    assert names('offline', ['software', 'other']) == []
    assert names('offline', ['other']) == []

    # Nothing to search.
    assert names() == []
    assert names('!!!') == []

    assert lib.count_repos(test_session, 'offline') == 2
    assert lib.count_repos(test_session, 'offline', ['software']) == 1
    assert lib.count_repos(test_session) == 0


@pytest.mark.asyncio
async def test_search_index_follows_changes(test_session, test_directory, async_client, test_wrolpi_config):
    """The search index follows README changes, renames from the config, and deletes."""
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    set_readme(test_session, repo, 'first readme')
    assert lib.count_repos(test_session, 'first') == 1

    set_readme(test_session, repo, 'second readme')
    assert lib.count_repos(test_session, 'first') == 0
    assert lib.count_repos(test_session, 'second') == 1

    lib.ReposConfig._import_repo(test_session, dict(url='https://github.com/a/b', name='renamed'))
    test_session.commit()
    assert lib.count_repos(test_session, 'renamed') == 1

    await lib.delete_repository(test_session, repo.id)
    assert lib.count_repos(test_session, 'second') == 0
    assert lib.count_repos(test_session, 'renamed') == 0

    # The index matches its content.
    with sqlite3.connect(test_directory / 'config/wrolpi.db') as conn:
        conn.execute("INSERT INTO repository_fts(repository_fts, rank) VALUES('integrity-check', 1)")


@pytest.mark.asyncio
async def test_downloader_indexes_readme(test_session, git_remote_factory, repos_download_manager):
    """The downloader stores the README as plain text, and keeps it current."""
    readme = '# Example\n\n[![CI](https://ci/badge.svg)](https://ci) An **offline** [library](https://docs).\n'
    remote = git_remote_factory(files={'README.md': readme})
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    assert repo.readme_text == 'Example\nCI An offline library.'
    assert lib.count_repos(test_session, 'library') == 1

    remote.git('rm', '--quiet', 'README.md')
    remote.commit({'readme.txt': 'Plain *text*'}, 'Plain README')
    download = repo.download
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    assert repo.readme_path == 'readme.txt'
    assert repo.readme_text == 'Plain *text*'
    assert lib.count_repos(test_session, 'library') == 0


@pytest.mark.asyncio
async def test_search_api(test_session, async_client, test_wrolpi_config):
    kiwix = lib.create_repository(test_session, 'https://github.com/kiwix/kiwix-tools', tag_name='software')
    set_readme(test_session, kiwix, 'Serve Zim files offline.')
    lib.create_repository(test_session, 'https://github.com/a/b')

    body = dict(search_str='zim')
    request, response = await async_client.post('/api/repos/search', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json['totals'] == dict(repos=1)
    repo, = response.json['repos']
    assert repo['name'] == 'kiwix-tools'
    assert repo['readme_headline'] == 'Serve <b>Zim</b> files offline.'
    assert 'readme_text' not in repo

    # The global search's "Other" estimate counts Repos by the search, and by Tag.
    request, response = await async_client.post('/api/search_other_estimates', content=json.dumps(body))
    assert response.json['others'] == dict(channel_count=0, domain_count=0, repo_count=1)
    body = dict(tag_names=['software'])
    request, response = await async_client.post('/api/search_other_estimates', content=json.dumps(body))
    assert response.json['others'] == dict(channel_count=0, domain_count=0, repo_count=1)
    body = dict(tag_names=['software'], search_str='nothing')
    request, response = await async_client.post('/api/search_other_estimates', content=json.dumps(body))
    assert response.json['others'] == dict(channel_count=0, domain_count=0, repo_count=0)

    # Repos are suggested by name.
    request, response = await async_client.post('/api/search_suggestions', content=json.dumps(dict(search_str='kiw')))
    assert response.json['repos'] == [
        dict(id=kiwix.id, name='kiwix-tools', tag_name='software', location=f'/repos/{kiwix.id}')]


@pytest.mark.asyncio
async def test_readme_headline_is_escaped(test_session, async_client, test_wrolpi_config):
    """A README comes from an untrusted remote; its headline is rendered as HTML, so only the highlight is markup."""
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    set_readme(test_session, repo, 'zim <img src=x onerror="alert(1)"> &amp; <b>bold</b>')

    repos, _ = lib.search_repos(test_session, 'zim')
    assert repos[0]['readme_headline'] == \
           '<b>zim</b> &lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp;amp; &lt;b&gt;bold&lt;/b&gt;'


def test_read_readme_text_refuses_symlinks(tmp_path):
    secret = tmp_path / 'secret.txt'
    secret.write_text('secret')
    readme = tmp_path / 'README.md'
    readme.symlink_to(secret)
    assert lib.read_readme_text(readme) is None
    assert lib.find_readme(tmp_path) is None


@pytest.mark.parametrize('text', [
    pytest.param('|' + ' ' * 100_000 + 'x', id='table-spaces'),
    pytest.param('-' * 100_000 + 'x', id='dashes'),
    pytest.param('<!--' * 25_000, id='unclosed-comments'),
    pytest.param('![' * 50_000, id='image-brackets'),
    pytest.param('[' * 50_000 + '(' * 50_000, id='link-brackets'),
    pytest.param('<' * 100_000, id='angles'),
    pytest.param('\n' + ' \n' * 50_000 + 'x', id='blank-lines'),
    pytest.param('#' * 100_000, id='hashes'),
    pytest.param('> ' * 50_000, id='quotes'),
])
def test_markdown_to_text_is_linear(text):
    """A README is untrusted; converting the largest README must never take long.

    Each case takes milliseconds; the patterns this replaced took minutes.  The bound is loose so a busy machine
    does not fail it."""
    start = time.monotonic()
    lib.markdown_to_text(text)
    assert time.monotonic() - start < 5


def test_markdown_to_text():
    readme = '''# Kiwix Tools <!-- hidden
comment -->

[![CI](https://x/badge.svg)](https://ci) **Kiwix** is an *offline* reader. See [the docs](https://docs).

| a | b |
|---|---|
| 1 | 2 |

```bash
kiwix-serve --port 80
```
> quoted
[ref]: https://example.com
---
#hashtag
'''
    assert lib.markdown_to_text(readme) == ('Kiwix Tools\nCI Kiwix is an offline reader. See the docs.'
                                            '\na b\n1 2\nkiwix-serve --port 80\nquoted\n#hashtag')
