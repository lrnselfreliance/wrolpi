import shutil
from pathlib import Path

from modules.videos import captions
from modules.videos.models import Video
from wrolpi.db import get_db_curs, get_db_context
from wrolpi.test.common import wrap_test_db, TestAPI
from wrolpi.vars import PROJECT_DIR


class TestCaption(TestAPI):

    def setUp(self) -> None:
        super().setUp()
        self.vtt_path1 = Path(self.tmp_dir.name) / 'example1.en.vtt'
        self.vtt_path1.touch()
        self.vtt_path1.write_text((PROJECT_DIR / 'test/example1.en.vtt').read_text())
        self.vtt_path2 = Path(self.tmp_dir.name) / 'example2.en.vtt'
        self.vtt_path2.touch()
        self.vtt_path2.write_text((PROJECT_DIR / 'test/example2.en.vtt').read_text())

    def test_example_en_vtt(self):
        expected = ['okay welcome to this session this is',
                    'okay welcome to this session this is',
                    'okay welcome to this session this is\ncalled the kinetic bunny need to meet',
                    'called the kinetic bunny need to meet',
                    'called the kinetic bunny need to meet\nthe virtual bonnie emilio stop this is',
                    'the virtual bonnie emilio stop this is',
                    'the virtual bonnie emilio stop this is\njana car who just to give a little bit',
                    'jana car who just to give a little bit',
                    'jana car who just to give a little bit\nof background information we come from a',
                    'of background information we come from a',
                    'of background information we come from a\ncompany called le code from finland and']
        self.assertEqual(list(captions.get_caption_text(self.vtt_path1)), expected)

        expected = ['okay welcome to this session this is',
                    'called the kinetic bunny need to meet',
                    'the virtual bonnie emilio stop this is',
                    'jana car who just to give a little bit',
                    'of background information we come from a',
                    'company called le code from finland and']
        self.assertEqual(list(captions.get_unique_caption_lines(self.vtt_path1)), expected)

    @wrap_test_db
    def test_process_captions(self):
        _, session = get_db_context()
        video1 = Video(title='scream', caption_path=str(self.vtt_path1))
        session.add(video1)
        session.commit()
        video1.caption = captions.get_captions(video1.caption_path.path)
        video2 = Video(title='bar', caption_path=str(self.vtt_path2))
        session.add(video2)
        session.commit()
        video2.caption = captions.get_captions(video2.caption_path.path)

        session.commit()
        session.flush()
        session.refresh(video1)
        session.refresh(video2)

        # Get the video from the DB
        video1 = session.query(Video).filter_by(id=video1.id).one()
        self.assertIsNotNone(video1.caption)
        video2 = session.query(Video).filter_by(id=video2.id).one()
        self.assertIsNotNone(video2.caption)

        # Search using the tsvector, "sessions" never actually appears in the text, but "session" does
        with get_db_curs() as curs:
            def select_textsearch(*args):
                curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s) ORDER BY id', args)

            select_textsearch('sessions')
            self.assertEqual(curs.fetchall(), [[1, ]])
            # Matches video1.title and video2.caption
            select_textsearch('scream')
            self.assertEqual(curs.fetchall(), [[1, ], [2, ]])
            # Matches video1.title and video2.caption
            select_textsearch('scream | sessions')
            self.assertEqual(curs.fetchall(), [[1, ], [2, ]])
            # Only matches video1.title
            select_textsearch('scream & sessions')
            self.assertEqual(curs.fetchall(), [[1, ]])
            # Matches neither
            select_textsearch('scream & sess')
            self.assertEqual(curs.fetchall(), [])
            # Matches video2.caption
            select_textsearch('yawn | sess')
            self.assertEqual(curs.fetchall(), [[2, ]])
            # Matches video2.caption
            select_textsearch('yawn')
            self.assertEqual(curs.fetchall(), [[2, ]])
            # Matches video2.title
            select_textsearch('bar')
            self.assertEqual(curs.fetchall(), [[2, ]])


def test_bad_caption(test_directory):
    """A caption file that cannot be parsed is ignored."""
    bad_caption_file = PROJECT_DIR / 'test/bad_caption.en.vtt'
    test_file = test_directory / 'bad_caption.en.vtt'
    shutil.copy(bad_caption_file, test_file)

    result = captions.get_captions(test_file)
    assert result is None
