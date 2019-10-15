import unittest

from wrolpi.common import get_db_context
from wrolpi.plugins.videos import captions
from wrolpi.test.common import test_db_wrapper


class TestCaption(unittest.TestCase):
    vtt_path = 'test/example.en.vtt'

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
        self.assertEqual(list(captions.get_caption_text(self.vtt_path)), expected)

        expected = ['okay welcome to this session this is',
                    'called the kinetic bunny need to meet',
                    'the virtual bonnie emilio stop this is',
                    'jana car who just to give a little bit',
                    'of background information we come from a',
                    'company called le code from finland and']
        self.assertEqual(list(captions.get_unique_caption_lines(self.vtt_path)), expected)

    @test_db_wrapper
    def test_process_captions(self):
        with get_db_context() as (db_conn, db):
            Video = db['video']
            video = Video(name='foo', caption_path=self.vtt_path).flush()
            captions.process_captions(db, video)

            # Get the video from the DB
            video = Video.get_one(id=video['id'])
            self.assertIsNotNone(video['caption_tsvector'])
