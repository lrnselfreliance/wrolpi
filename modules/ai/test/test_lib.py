"""Tests for the /api/ai formatting helpers."""
from modules.ai import lib


def test_wrolpi_link_video():
    fg = dict(id=123, model='video', video=dict(), mimetype='video/mp4')
    assert lib.wrolpi_link(fg) == '/videos/123'


def test_wrolpi_link_doc():
    fg = dict(id=5, model='doc', mimetype='application/pdf')
    assert lib.wrolpi_link(fg) == '/docs/5'


def test_wrolpi_link_archive():
    fg = dict(id=7, model='archive', mimetype='text/html')
    assert lib.wrolpi_link(fg) == '/archives/7'


def test_wrolpi_link_epub(test_directory):
    fg = dict(id=9, mimetype='application/epub+zip', primary_path=test_directory / 'books/foo.epub')
    assert lib.wrolpi_link(fg) == '/epub/epub.html?url=/download/books/foo.epub'


def test_wrolpi_link_mobi(test_directory):
    fg = dict(id=9, mimetype='application/x-mobipocket-ebook', primary_path=test_directory / 'books/foo.mobi')
    assert lib.wrolpi_link(fg) == '/download/books/foo.mobi'


def test_wrolpi_link_media_fallback(test_directory):
    fg = dict(id=2, mimetype='image/png', primary_path=test_directory / 'photos/a.png')
    assert lib.wrolpi_link(fg) == '/media/photos/a.png'


def test_wrolpi_link_no_path():
    assert lib.wrolpi_link(dict(mimetype='image/png')) is None


def test_format_file_group_video():
    fg = dict(
        id=42,
        model='video',
        title='Canning Basics',
        mimetype='video/mp4',
        size=1000,
        length=4021,
        published_datetime='2024-01-02',
        tags=['food'],
        video=dict(channel=dict(id=1, name='Homesteading'), description='x' * 500),
        d_headline='pressure <b>canning</b>',
    )
    result = lib.format_file_group(fg)
    assert result['id'] == 42
    assert result['kind'] == 'video'
    assert result['link'] == '/videos/42'
    assert result['captions_link'] == '/api/ai/videos/42/captions'
    assert result['channel'] == 'Homesteading'
    assert result['duration'] == 4021
    assert result['headline'] == 'pressure <b>canning</b>'
    assert result['tags'] == ['food']
    # Listing descriptions are truncated.
    assert len(result['description']) == lib.LISTING_DESCRIPTION_LENGTH + 1
    # Empty fields are omitted.
    assert 'author' not in result and 'url' not in result


def test_format_file_group_archive():
    fg = dict(id=8, model='archive', title='Some Page', mimetype='text/html', url='https://example.com/a')
    result = lib.format_file_group(fg)
    assert result['kind'] == 'archive'
    assert result['link'] == '/archives/8'
    assert result['text_link'] == '/api/ai/archives/8/text'
    assert result['url'] == 'https://example.com/a'


def test_format_file_groups_total():
    result = lib.format_file_groups([dict(id=1, model='archive')], 55)
    assert result['total'] == 55
    assert len(result['results']) == 1


def test_paginate_text():
    text = 'a' * (lib.PAGE_SIZE + 100)
    page = lib.paginate_text(text, 0)
    assert len(page['content']) == lib.PAGE_SIZE
    assert page['next_offset'] == lib.PAGE_SIZE
    assert page['total_chars'] == lib.PAGE_SIZE + 100

    page = lib.paginate_text(text, page['next_offset'])
    assert len(page['content']) == 100
    assert page['next_offset'] is None

    # Exact boundary has no next page.
    page = lib.paginate_text('a' * lib.PAGE_SIZE, 0)
    assert page['next_offset'] is None

    # Empty text.
    page = lib.paginate_text(None, 0)
    assert page == dict(content='', next_offset=None, total_chars=0)


def test_html_to_text():
    html = '<html><head><style>.x{}</style><script>evil()</script></head>' \
           '<body><nav>menu</nav><p>Hello</p><p></p><p>World</p></body></html>'
    text = lib.html_to_text(html)
    assert 'Hello' in text and 'World' in text
    assert 'evil' not in text and 'menu' not in text and '.x{}' not in text


def test_format_caption_chunks():
    chunks = [dict(start_seconds=0, text='hello'), dict(start_seconds=3671, text='goodbye')]
    text = lib.format_caption_chunks(chunks)
    assert text == '[00:00:00] hello\n[01:01:11] goodbye'
    assert lib.format_caption_chunks(None) == ''


def test_format_zim_search():
    zim_results = [dict(
        metadata=dict(title='Test Zim'),
        estimate=2,
        search=[
            dict(zim_id=1, path='one', title='One', headline='the first', rank=1),
            dict(zim_id=1, path='two', title='Two', headline=None, rank=1),
        ],
    )]
    result = lib.format_zim_search(zim_results)
    assert result['total'] == 2
    assert result['results'][0]['link'] == '/api/zim/1/entry/one'
    assert result['results'][0]['zim'] == 'Test Zim'
    assert 'headline' not in result['results'][1]
