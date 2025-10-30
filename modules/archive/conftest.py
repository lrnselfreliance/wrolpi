import datetime
import json
import pathlib
from typing import List
from uuid import uuid4

import pytest
import pytz

from modules.archive.lib import archive_strftime
from modules.archive.models import Archive
from wrolpi.collections import Collection


@pytest.fixture
def archive_directory(test_directory) -> pathlib.Path:
    path = test_directory / 'archive'
    path.mkdir()
    return path


@pytest.fixture
def archive_factory(test_session, archive_directory, make_files_structure, image_bytes_factory):
    def time_generator():
        timestamp = datetime.datetime(2000, 1, 1, 0, 0, 0).astimezone(pytz.UTC)
        while True:
            timestamp += datetime.timedelta(seconds=1)
            yield timestamp

    now = time_generator()

    def _(domain: str = None, url: str = None, title: str = 'NA', contents: str = None,
          singlefile_contents: str = None, tag_names: List[str] = None, screenshot: bool = True) -> Archive:
        if domain:
            assert '/' not in domain

        tag_names = tag_names or list()

        title = title or str(uuid4())
        domain_dir = domain or title
        domain_dir = archive_directory / domain_dir
        domain_dir.mkdir(exist_ok=True)

        download_datetime = next(now)
        timestamp = archive_strftime(download_datetime)

        json_contents = {}
        if title != 'NA':
            json_contents['title'] = title
        if url:
            json_contents['url'] = url
        json_contents = json.dumps(json_contents)
        singlefile_path, readability_path, readability_txt_path, readability_json_path = \
            make_files_structure({
                str(domain_dir / f'{timestamp}_{title}.html'): singlefile_contents or '<html></html>',
                str(domain_dir / f'{timestamp}_{title}.readability.html'): '<html></html>',
                str(domain_dir / f'{timestamp}_{title}.readability.txt'): contents,
                str(domain_dir / f'{timestamp}_{title}.readability.json'): json_contents,
            })

        if domain:
            # Find or create domain collection
            collection = test_session.query(Collection).filter_by(
                name=domain,
                kind='domain'
            ).one_or_none()
            if not collection:
                collection = Collection(
                    name=domain,
                    kind='domain',
                    directory=None,  # Domain collections are unrestricted
                )
                test_session.add(collection)
                test_session.flush([collection])
        else:
            collection = None

        screenshot_path = None
        if screenshot:
            screenshot_path = domain_dir / f'{timestamp}_{title}.png'
            screenshot_path.write_bytes(image_bytes_factory())

        # Only add files that were created.
        files = (readability_path, readability_json_path, readability_txt_path, screenshot_path, singlefile_path)
        files = list(filter(None, files))

        archive = Archive.from_paths(test_session, *files)
        archive.url = url
        archive.title = title
        archive.file_group.download_datetime = archive.file_group.published_datetime = next(now)
        archive.file_group.modification_datetime = next(now)
        archive.collection = collection
        archive.validate()

        for tag_name in tag_names:
            archive.add_tag(tag_name, test_session)

        return archive

    return _
