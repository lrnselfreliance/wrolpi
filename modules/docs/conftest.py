import pytest

from modules.docs.models import Doc


@pytest.fixture
def doc_factory(test_session, test_directory):
    """Factory for creating Doc records for testing."""
    count = 0

    def factory(file_group=None, **kwargs):
        nonlocal count
        count += 1
        if file_group is None:
            from wrolpi.files.models import FileGroup
            path = test_directory / f'test_doc_{count}.pdf'
            path.write_bytes(b'%PDF-1.4 test')
            file_group = FileGroup.from_paths(test_session, path)
            test_session.flush()

        doc = Doc(file_group=file_group, **kwargs)
        test_session.add(doc)
        test_session.flush()
        return doc

    return factory
