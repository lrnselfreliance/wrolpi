from wrolpi import captions


def test_get_caption_text(vtt_file1, srt_file3):
    expected = ['okay welcome to this session this is',
                'okay welcome to this session this is\ncalled the kinetic bunny need to meet',
                'called the kinetic bunny need to meet',
                'called the kinetic bunny need to meet\nthe virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is\njana car who just to give a little bit',
                'jana car who just to give a little bit',
                'jana car who just to give a little bit\nof background information we come from a',
                'of background information we come from a',
                'of background information we come from a\ncompany called le code from finland and']
    assert list(captions.get_caption_text(vtt_file1)) == expected

    expected = ['okay welcome to this session this is',
                'okay welcome to this session this is\ncalled the kinetic bunny need to meet',
                'called the kinetic bunny need to meet',
                'called the kinetic bunny need to meet\n'
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is',
                'the virtual bonnie emilio stop this is\n'
                'jana car who just to give a little bit',
                'jana car who just to give a little bit',
                'jana car who just to give a little bit\n'
                'of background information we come from a',
                'of background information we come from a',
                'of background information we come from a\n'
                'company called le code from finland and']
    assert list(captions.get_caption_text(srt_file3)) == expected


def test_get_unique_caption_lines(vtt_file1, srt_file3):
    expected = ['okay welcome to this session this is',
                'called the kinetic bunny need to meet',
                'the virtual bonnie emilio stop this is',
                'jana car who just to give a little bit',
                'of background information we come from a',
                'company called le code from finland and']
    assert list(captions.get_unique_caption_lines(vtt_file1)) == expected

    expected = ['okay welcome to this session this is',
                'called the kinetic bunny need to meet',
                'the virtual bonnie emilio stop this is',
                'jana car who just to give a little bit',
                'of background information we come from a',
                'company called le code from finland and']
    assert list(captions.get_unique_caption_lines(srt_file3)) == expected
