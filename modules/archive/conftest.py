import copy
import datetime
import json
import pathlib
from uuid import uuid4

import pytest

from modules.archive.lib import archive_strftime
from modules.archive.models import Archive, Domain
from wrolpi.dates import local_timezone
from wrolpi.files.models import File


@pytest.fixture
def archive_directory(test_directory) -> pathlib.Path:
    path = test_directory / 'archive'
    path.mkdir()
    return path


@pytest.fixture
def archive_factory(test_session, archive_directory, make_files_structure):
    def time_generator():
        timestamp = datetime.datetime(2000, 1, 1, 0, 0, 0)
        while True:
            timestamp += datetime.timedelta(seconds=1)
            yield timestamp

    now = time_generator()

    def _(domain: str = None, url: str = None, title: str = 'NA', contents: str = None,
          singlefile_contents: str = None) -> Archive:
        if domain:
            assert '/' not in domain

        title = title or str(uuid4())
        domain_dir = domain or title
        domain_dir = archive_directory / domain_dir
        domain_dir.mkdir(exist_ok=True)

        archive_datetime = local_timezone(next(now))
        timestamp = archive_strftime(archive_datetime)

        json_contents = {}
        if title != 'NA':
            json_contents['title'] = title
        if url:
            json_contents['url'] = url
        json_contents = json.dumps(json_contents)
        singlefile_path, screenshot_path, readability_path, readability_txt_path, readability_json_path = \
            make_files_structure({
                str(domain_dir / f'{timestamp}_{title}.html'): singlefile_contents or '<html></html>',
                str(domain_dir / f'{timestamp}_{title}.png'): None,
                str(domain_dir / f'{timestamp}_{title}.readability.html'): '<html></html>',
                str(domain_dir / f'{timestamp}_{title}.readability.txt'): contents,
                str(domain_dir / f'{timestamp}_{title}.readability.json'): json_contents,
            })

        if domain:
            domain = test_session.query(Domain).filter_by(domain=domain).one_or_none()

        if not domain and domain_dir.name != 'NA':
            domain = Domain(
                domain=domain_dir.name,
                directory=domain_dir,
            )
            test_session.add(domain)
            test_session.flush([domain])

        archive = Archive(
            readability_json_file=File(path=readability_json_path) if readability_json_path else None,
            readability_file=File(path=readability_path) if readability_path else None,
            readability_txt_file=File(path=readability_txt_path) if readability_txt_path else None,
            screenshot_file=File(path=screenshot_path) if screenshot_path else None,
            singlefile_file=File(path=singlefile_path, model='archive'),
            title=title,
            url=url,
            domain_id=domain.id if domain else None,
            archive_datetime=archive_datetime,
        )
        test_session.add(archive)
        archive.singlefile_file.do_index()

        return archive

    return _


SINGLEFILE_CONTENTS = '''<html><!--
 Page saved with SingleFile 
 url: https://example.com 
 saved date: Thu May 12 2022 00:38:02 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">

<meta name="msapplication-TileColor" content="#2d89ef">
<meta name="theme-color" content="#000000">

<title>the title</title>

<body>
some body contents
</body>

</html>
'''


@pytest.fixture
def singlefile_contents() -> str:
    """Return a short HTML string that contains an example Singlefile file."""
    return copy.deepcopy(SINGLEFILE_CONTENTS)
