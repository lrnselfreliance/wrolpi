import io
import json
import tarfile
import zipfile
from http import HTTPStatus

import pytest


@pytest.mark.asyncio
async def test_list_zip_contents(test_session, async_client, test_directory):
    """Zip archive contents can be listed as a tree."""
    archive_path = test_directory / 'test.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('file1.txt', 'hello')
        zf.writestr('dir1/file2.txt', 'world')
        zf.writestr('dir1/file3.txt', 'foo')

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'test.zip'}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 3
    assert contents['total_size'] == len(b'hello') + len(b'world') + len(b'foo')
    # Should have file1.txt at root and dir1/ with 2 children.
    entry_names = [e['name'] for e in contents['entries']]
    assert 'file1.txt' in entry_names
    assert 'dir1' in entry_names
    dir1 = [e for e in contents['entries'] if e['name'] == 'dir1'][0]
    assert dir1['is_dir'] is True
    assert len(dir1['children']) == 2


@pytest.mark.asyncio
async def test_list_tar_gz_contents(test_session, async_client, test_directory):
    """Tar.gz archive contents can be listed."""
    archive_path = test_directory / 'test.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as tf:
        data = b'hello tar'
        info = tarfile.TarInfo(name='readme.txt')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

        data2 = b'nested file'
        info2 = tarfile.TarInfo(name='subdir/nested.txt')
        info2.size = len(data2)
        tf.addfile(info2, io.BytesIO(data2))

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'test.tar.gz'}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 2
    assert contents['total_size'] == len(b'hello tar') + len(b'nested file')


@pytest.mark.asyncio
async def test_list_tar_xz_contents(test_session, async_client, test_directory):
    """Tar.xz archive contents can be listed."""
    archive_path = test_directory / 'test.tar.xz'
    with tarfile.open(archive_path, 'w:xz') as tf:
        data = b'xz content'
        info = tarfile.TarInfo(name='data.bin')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'test.tar.xz'}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 1


@pytest.mark.asyncio
async def test_list_tar_contents(test_session, async_client, test_directory):
    """Plain tar archive contents can be listed."""
    archive_path = test_directory / 'test.tar'
    with tarfile.open(archive_path, 'w') as tf:
        data = b'plain tar'
        info = tarfile.TarInfo(name='plain.txt')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'test.tar'}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 1
    assert contents['total_size'] == len(b'plain tar')


@pytest.mark.asyncio
async def test_list_tar_bz2_contents(test_session, async_client, test_directory):
    """Tar.bz2 archive contents can be listed."""
    archive_path = test_directory / 'test.tar.bz2'
    with tarfile.open(archive_path, 'w:bz2') as tf:
        data = b'bz2 content'
        info = tarfile.TarInfo(name='bz2file.txt')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'test.tar.bz2'}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 1
    assert contents['total_size'] == len(b'bz2 content')


@pytest.mark.asyncio
async def test_list_contents_unsupported(test_session, async_client, test_directory):
    """Non-archive file returns an error."""
    txt_path = test_directory / 'readme.txt'
    txt_path.write_text('not an archive')

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'readme.txt'}))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'UNSUPPORTED_ARCHIVE' in response.text


@pytest.mark.asyncio
async def test_list_contents_corrupted(test_session, async_client, test_directory):
    """Corrupted archive returns an error."""
    archive_path = test_directory / 'bad.zip'
    archive_path.write_bytes(b'this is not a zip file')

    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': 'bad.zip'}))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'UNSUPPORTED_ARCHIVE' in response.text


@pytest.mark.asyncio
async def test_download_single_member_zip(test_session, async_client, test_directory):
    """A single file can be streamed from a zip archive."""
    archive_path = test_directory / 'test.zip'
    file_content = b'download me'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('docs/readme.txt', file_content)

    _, response = await async_client.get('/api/files/zip/download?path=test.zip&member=docs/readme.txt')
    assert response.status_code == HTTPStatus.OK
    assert response.body == file_content
    assert 'readme.txt' in response.headers.get('Content-Disposition', '')


@pytest.mark.asyncio
async def test_download_single_member_tar(test_session, async_client, test_directory):
    """A single file can be streamed from a tar archive."""
    archive_path = test_directory / 'test.tar.gz'
    file_content = b'tar member content'
    with tarfile.open(archive_path, 'w:gz') as tf:
        info = tarfile.TarInfo(name='data/file.dat')
        info.size = len(file_content)
        tf.addfile(info, io.BytesIO(file_content))

    _, response = await async_client.get('/api/files/zip/download?path=test.tar.gz&member=data/file.dat')
    assert response.status_code == HTTPStatus.OK
    assert response.body == file_content


@pytest.mark.asyncio
async def test_download_single_member_tar_plain(test_session, async_client, test_directory):
    """A single file can be streamed from a plain tar archive."""
    archive_path = test_directory / 'test.tar'
    file_content = b'plain tar member'
    with tarfile.open(archive_path, 'w') as tf:
        info = tarfile.TarInfo(name='doc.txt')
        info.size = len(file_content)
        tf.addfile(info, io.BytesIO(file_content))

    _, response = await async_client.get('/api/files/zip/download?path=test.tar&member=doc.txt')
    assert response.status_code == HTTPStatus.OK
    assert response.body == file_content


@pytest.mark.asyncio
async def test_download_single_member_tar_bz2(test_session, async_client, test_directory):
    """A single file can be streamed from a tar.bz2 archive."""
    archive_path = test_directory / 'test.tar.bz2'
    file_content = b'bz2 member content'
    with tarfile.open(archive_path, 'w:bz2') as tf:
        info = tarfile.TarInfo(name='data/info.txt')
        info.size = len(file_content)
        tf.addfile(info, io.BytesIO(file_content))

    _, response = await async_client.get('/api/files/zip/download?path=test.tar.bz2&member=data/info.txt')
    assert response.status_code == HTTPStatus.OK
    assert response.body == file_content


@pytest.mark.asyncio
async def test_download_single_member_tar_xz(test_session, async_client, test_directory):
    """A single file can be streamed from a tar.xz archive."""
    archive_path = test_directory / 'test.tar.xz'
    file_content = b'xz member content'
    with tarfile.open(archive_path, 'w:xz') as tf:
        info = tarfile.TarInfo(name='notes/readme.md')
        info.size = len(file_content)
        tf.addfile(info, io.BytesIO(file_content))

    _, response = await async_client.get('/api/files/zip/download?path=test.tar.xz&member=notes/readme.md')
    assert response.status_code == HTTPStatus.OK
    assert response.body == file_content


@pytest.mark.asyncio
async def test_download_nonexistent_member(test_session, async_client, test_directory):
    """Requesting a non-existent member returns an error."""
    archive_path = test_directory / 'test.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('exists.txt', 'data')

    _, response = await async_client.get('/api/files/zip/download?path=test.zip&member=nope.txt')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'INVALID_ARCHIVE_MEMBER' in response.text


@pytest.mark.asyncio
async def test_download_directory_member(test_session, async_client, test_directory):
    """Attempting to download a directory entry returns an error."""
    archive_path = test_directory / 'test.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('mydir/', '')
        zf.writestr('mydir/file.txt', 'content')

    _, response = await async_client.get('/api/files/zip/download?path=test.zip&member=mydir/')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'INVALID_ARCHIVE_MEMBER' in response.text


@pytest.mark.asyncio
async def test_download_traversal_attack(test_session, async_client, test_directory):
    """Member path with '../' is rejected."""
    archive_path = test_directory / 'test.zip'
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('file.txt', 'safe')

    _, response = await async_client.get('/api/files/zip/download?path=test.zip&member=../../../etc/passwd')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'INVALID_ARCHIVE_MEMBER' in response.text


# ---- Comic book archive format tests using real sample files ----


@pytest.mark.asyncio
async def test_list_cbt_contents(test_session, async_client, test_directory, example_cbt):
    """CBT (TAR) archive contents can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cbt.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4


@pytest.mark.asyncio
async def test_list_cbt_dir_contents(test_session, async_client, test_directory, example_cbt_dir):
    """CBT (TAR) archive with nested directories can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cbt_dir.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4
    # Files are in a nested directory.
    entry_names = [e['name'] for e in contents['entries']]
    assert 'images' in entry_names


@pytest.mark.asyncio
async def test_download_cbt_member(test_session, async_client, test_directory, example_cbt):
    """A single image can be downloaded from a CBT archive."""
    _, response = await async_client.get(
        f'/api/files/zip/download?path={example_cbt.name}&member=Bobby-Make-Believe_1915__0.jpg')
    assert response.status_code == HTTPStatus.OK
    assert len(response.body) > 0
    assert response.body[:2] == b'\xff\xd8'  # JPEG magic bytes


@pytest.mark.asyncio
async def test_list_cbr_contents(test_session, async_client, test_directory, example_cbr):
    """CBR (RAR) archive contents can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cbr.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4


@pytest.mark.asyncio
async def test_download_cbr_member(test_session, async_client, test_directory, example_cbr):
    """A single image can be downloaded from a CBR archive."""
    _, response = await async_client.get(
        f'/api/files/zip/download?path={example_cbr.name}&member=Bobby-Make-Believe_1915__0.jpg')
    assert response.status_code == HTTPStatus.OK
    assert len(response.body) > 0
    assert response.body[:2] == b'\xff\xd8'  # JPEG magic bytes


@pytest.mark.asyncio
async def test_list_cb7_contents(test_session, async_client, test_directory, example_cb7):
    """CB7 (7z) archive contents can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cb7.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4


@pytest.mark.asyncio
async def test_list_cb7_dir_contents(test_session, async_client, test_directory, example_cb7_dir):
    """CB7 (7z) archive with nested directories can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cb7_dir.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4
    entry_names = [e['name'] for e in contents['entries']]
    assert 'images' in entry_names


@pytest.mark.asyncio
async def test_download_cb7_member(test_session, async_client, test_directory, example_cb7):
    """A single image can be downloaded from a CB7 archive."""
    _, response = await async_client.get(
        f'/api/files/zip/download?path={example_cb7.name}&member=Bobby-Make-Believe_1915__0.jpg')
    assert response.status_code == HTTPStatus.OK
    assert len(response.body) > 0
    assert response.body[:2] == b'\xff\xd8'  # JPEG magic bytes


@pytest.mark.asyncio
async def test_list_cbz_dir_contents(test_session, async_client, test_directory, example_cbz_dir):
    """CBZ (ZIP) archive with nested directories can be listed."""
    _, response = await async_client.post('/api/files/zip/contents',
                                          content=json.dumps({'path': example_cbz_dir.name}))
    assert response.status_code == HTTPStatus.OK
    contents = response.json['contents']
    assert contents['total_files'] == 4
    entry_names = [e['name'] for e in contents['entries']]
    assert 'images' in entry_names
