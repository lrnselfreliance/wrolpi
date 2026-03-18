from modules.docs.models import Doc, DOC_MIMETYPES, mimetype_is_doc


def test_doc_mimetypes():
    """All expected mimetypes are included."""
    assert 'application/epub+zip' in DOC_MIMETYPES
    assert 'application/x-mobipocket-ebook' in DOC_MIMETYPES
    assert 'application/pdf' in DOC_MIMETYPES
    assert 'application/msword' in DOC_MIMETYPES
    assert 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in DOC_MIMETYPES
    assert 'application/vnd.oasis.opendocument.text' in DOC_MIMETYPES
    assert 'application/x-cbz' in DOC_MIMETYPES
    assert 'application/x-cbr' in DOC_MIMETYPES


def test_mimetype_is_doc():
    """mimetype_is_doc correctly identifies doc mimetypes."""
    assert mimetype_is_doc('application/pdf')
    assert mimetype_is_doc('application/epub+zip')
    assert mimetype_is_doc('application/x-mobipocket-ebook')
    assert mimetype_is_doc('application/msword')
    assert not mimetype_is_doc('video/mp4')
    assert not mimetype_is_doc('text/plain')
    assert not mimetype_is_doc('image/jpeg')


def test_doc_model(test_session, doc_factory):
    """Doc model can be created and queried."""
    doc = doc_factory(size=1024, publisher='Test Publisher', language='en', subject='Testing')
    assert doc.id
    assert doc.size == 1024
    assert doc.publisher == 'Test Publisher'
    assert doc.language == 'en'
    assert doc.subject == 'Testing'
    assert doc.file_group is not None

    queried = test_session.query(Doc).filter_by(id=doc.id).one()
    assert queried.publisher == 'Test Publisher'


def test_doc_can_model(test_session, test_directory):
    """Doc.can_model identifies correct FileGroups."""
    from wrolpi.files.models import FileGroup

    pdf_path = test_directory / 'test.pdf'
    pdf_path.write_bytes(b'%PDF-1.4 test')
    fg = FileGroup.from_paths(test_session, pdf_path)
    test_session.flush()
    assert Doc.can_model(fg)

    # Video should not be modeled as a doc.
    video_path = test_directory / 'test.mp4'
    video_path.write_bytes(b'\x00\x00\x00\x1cftypisom')
    fg2 = FileGroup.from_paths(test_session, video_path)
    test_session.flush()
    assert not Doc.can_model(fg2)
