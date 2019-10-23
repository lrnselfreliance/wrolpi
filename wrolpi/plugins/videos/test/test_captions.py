import unittest
from pathlib import Path

import mock

from wrolpi.plugins.videos import captions
from wrolpi.test.common import test_db_wrapper
from wrolpi.tools import get_db_context


class TestCaption(unittest.TestCase):
    vtt_path1 = Path('test/example1.en.vtt').absolute()
    vtt_path2 = Path('test/example2.en.vtt').absolute()

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
            video1 = Video(title='scream', caption_path=str(self.vtt_path1)).flush()
            with mock.patch('wrolpi.plugins.videos.captions.get_absolute_video_caption', lambda *a: self.vtt_path1):
                captions.process_captions(video1)
            video2 = Video(title='bar', caption_path=str(self.vtt_path2)).flush()
            with mock.patch('wrolpi.plugins.videos.captions.get_absolute_video_caption', lambda *a: self.vtt_path2):
                captions.process_captions(video2)

            v1_id = video1['id']
            v2_id = video2['id']

            # Get the video from the DB
            video1 = Video.get_one(id=video1['id'])
            self.assertIsNotNone(video1['caption'])
            video2 = Video.get_one(id=video2['id'])
            self.assertIsNotNone(video2['caption'])

            # Search using the tsvector, "sessions" never actually appears in the text, but "session" does
            curs = db_conn.cursor()

            def select_textsearch(*args):
                curs.execute('SELECT id FROM video WHERE textsearch @@ to_tsquery(%s) ORDER BY id', args)

            select_textsearch('sessions')
            self.assertEqual(curs.fetchall(), [(v1_id,)])
            # Matches video1.title and video2.caption
            select_textsearch('scream')
            self.assertEqual(curs.fetchall(), [(v1_id,), (v2_id,)])
            # Matches video1.title and video2.caption
            select_textsearch('scream | sessions')
            self.assertEqual(curs.fetchall(), [(v1_id,), (v2_id,)])
            # Only matches video1.title
            select_textsearch('scream & sessions')
            self.assertEqual(curs.fetchall(), [(v1_id,)])
            # Matches neither
            select_textsearch('scream & sess')
            self.assertEqual(curs.fetchall(), [])
            # Matches video2.caption
            select_textsearch('yawn | sess')
            self.assertEqual(curs.fetchall(), [(v2_id,)])
            # Matches video2.caption
            select_textsearch('yawn')
            self.assertEqual(curs.fetchall(), [(v2_id,)])
            # Matches video2.title
            select_textsearch('bar')
            self.assertEqual(curs.fetchall(), [(v2_id,)])
