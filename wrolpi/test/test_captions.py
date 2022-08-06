import shutil
from pathlib import Path

from wrolpi import captions
from wrolpi.test.common import TestAPI
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


def test_bad_caption(test_directory):
    """A caption file that cannot be parsed is ignored."""
    bad_caption_file = PROJECT_DIR / 'test/bad_caption.en.vtt'
    test_file = test_directory / 'bad_caption.en.vtt'
    shutil.copy(bad_caption_file, test_file)

    result = captions.read_captions(test_file)
    assert result is None
