import unittest

from wrolpi.common import get_db_context
from wrolpi.plugins.videos import captions
from wrolpi.test.common import test_db_wrapper


class TestCaption(unittest.TestCase):
    vtt_path1 = 'test/example1.en.vtt'
    vtt_path2 = 'test/example2.en.vtt'

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

    @test_db_wrapper
    def test_process_captions(self):
        with get_db_context() as (db_conn, db):
            Video = db['video']
            video1 = Video(title='scream', caption_path=self.vtt_path1).flush()
            captions.process_captions(video1)
            video2 = Video(title='bar', caption_path=self.vtt_path2).flush()
            captions.process_captions(video2)

            # Get the video from the DB
            video1 = Video.get_one(id=video1['id'])
            self.assertIsNotNone(video1['caption'])
            video2 = Video.get_one(id=video2['id'])
            self.assertIsNotNone(video2['caption'])

            # Search using the tsvector, "sessions" never actually appears in the text, but "session" does
            curs = db_conn.cursor()
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('sessions',))
            self.assertEqual(curs.fetchall(), [(1,)])
            # Matches video1.title and video2.caption
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('scream',))
            self.assertEqual(curs.fetchall(), [(1,), (2,)])
            # Matches video1.title and video2.caption
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('scream | sessions',))
            self.assertEqual(curs.fetchall(), [(1,), (2,)])
            # Only matches video1.title
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('scream & sessions',))
            self.assertEqual(curs.fetchall(), [(1,)])
            # Matches neither
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('scream & sess',))
            self.assertEqual(curs.fetchall(), [])
            # Matches video2.caption
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('yawn | sess',))
            self.assertEqual(curs.fetchall(), [(2,)])
            # Matches video2.caption
            curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s)', ('yawn',))
            self.assertEqual(curs.fetchall(), [(2,)])
