import mock

from api.db import get_db_context, get_db_curs
from api.test.common import wrap_test_db, TestAPI
from api.vars import PROJECT_DIR
from api.videos import captions
from api.videos.models import Video


class TestCaption(TestAPI):
    vtt_path1 = (PROJECT_DIR / 'test/example1.en.vtt').absolute()
    vtt_path2 = (PROJECT_DIR / 'test/example2.en.vtt').absolute()

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
        with get_db_context(commit=True) as (engine, session):
            video1 = Video(title='scream', caption_path=str(self.vtt_path1))
            session.add(video1)
            with mock.patch('api.videos.captions.get_absolute_video_caption', lambda *a: self.vtt_path1):
                captions.process_captions(video1)
            video2 = Video(title='bar', caption_path=str(self.vtt_path2))
            session.add(video2)
            with mock.patch('api.videos.captions.get_absolute_video_caption', lambda *a: self.vtt_path2):
                captions.process_captions(video2)

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
