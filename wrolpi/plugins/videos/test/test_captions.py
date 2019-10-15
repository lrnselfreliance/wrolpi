import unittest

from wrolpi.plugins.videos import captions


class TestCaption(unittest.TestCase):

    def test_example_en_vtt(self):
        vtt_path = 'test/example.en.vtt'

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
        self.assertEqual(list(captions.get_caption_text(vtt_path)), expected)

        expected = ['okay welcome to this session this is',
                    'called the kinetic bunny need to meet',
                    'the virtual bonnie emilio stop this is',
                    'jana car who just to give a little bit',
                    'of background information we come from a',
                    'company called le code from finland and']
        self.assertEqual(list(captions.get_unique_caption_lines(vtt_path)), expected)
