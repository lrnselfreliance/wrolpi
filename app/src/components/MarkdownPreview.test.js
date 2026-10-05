import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {isMarkdownFile, MarkdownPreview, renderMarkdown} from './MarkdownPreview';
import {renderUI} from '../test-utils';

const FILE_URL = '/media/notes/water/storage.md';

/** Render markdown into a detached element so assertions read the DOM, not the HTML string. */
const renderToDOM = (text, fileURL = FILE_URL) => {
    const div = document.createElement('div');
    div.innerHTML = renderMarkdown(text, fileURL);
    return div;
};

describe('renderMarkdown', () => {
    test('formats headings, emphasis, lists, code, and tables', () => {
        const div = renderToDOM([
            '# Water',
            '',
            'Rotate *every* barrel.',
            '',
            '- one',
            '- two',
            '',
            '```',
            'boil 1 minute',
            '```',
            '',
            '| a | b |',
            '|---|---|',
            '| 1 | 2 |',
        ].join('\n'));

        expect(div.querySelector('h1').textContent).toBe('Water');
        expect(div.querySelector('em').textContent).toBe('every');
        expect(div.querySelectorAll('ul li')).toHaveLength(2);
        expect(div.querySelector('pre code').textContent).toBe('boil 1 minute\n');
        expect(div.querySelectorAll('table td')).toHaveLength(2);
    });

    test('raw HTML in the file is shown as text, never parsed', () => {
        const div = renderToDOM('<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">');

        expect(div.querySelector('script')).toBeNull();
        expect(div.querySelector('img')).toBeNull();
        expect(div.textContent).toContain('<script>alert(1)</script>');
    });

    test('script URLs are not turned into links', () => {
        const div = renderToDOM('[click](javascript:alert(1))');

        expect(div.querySelector('a')).toBeNull();
    });

    test('relative images resolve against the markdown file directory', () => {
        const div = renderToDOM('![pump](images/hand%20pump.png)\n\n![tank](../tank.jpg)');

        const [pump, tank] = div.querySelectorAll('img');
        expect(pump.getAttribute('src')).toBe('/media/notes/water/images/hand%20pump.png');
        expect(tank.getAttribute('src')).toBe('/media/notes/tank.jpg');
    });

    test('relative links resolve against the markdown file directory and open a new tab', () => {
        const a = renderToDOM('[filters](filters.md#ceramic)').querySelector('a');

        expect(a.getAttribute('href')).toBe('/media/notes/water/filters.md#ceramic');
        expect(a.getAttribute('target')).toBe('_blank');
    });

    test('a relative URL that climbs out of the media directory is dropped', () => {
        const div = renderToDOM('[api](../../../api/status)\n\n![x](../../../../x.png)');

        expect(div.querySelector('a').hasAttribute('href')).toBe(false);
        expect(div.querySelector('img').hasAttribute('src')).toBe(false);
    });

    test.each([
        ['https://tracker.example/pixel.gif'],
        ['http://tracker.example/pixel.gif'],
        // Protocol-relative: starts with a slash, but loads from another host.
        ['//tracker.example/pixel.gif'],
    ])('an image from another site (%s) is not loaded, it becomes a link', (src) => {
        const div = renderToDOM(`![pixel](${src})`);

        expect(div.querySelector('img')).toBeNull();
        const a = div.querySelector('a');
        expect(a.getAttribute('href')).toBe(src);
        expect(a.textContent).toBe('pixel');
        expect(a.getAttribute('target')).toBe('_blank');
        expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    });

    test('an image from another site with no alt text is labeled by its URL', () => {
        const a = renderToDOM('![](https://example.com/a.png)').querySelector('a');

        expect(a.textContent).toBe('https://example.com/a.png');
    });

    test('an image from another site inside a link becomes the link text, not a nested link', () => {
        // The badge pattern common in READMEs.
        const div = renderToDOM('[![build status](https://ci.example/badge.svg)](https://ci.example/project)');

        expect(div.querySelector('img')).toBeNull();
        const links = div.querySelectorAll('a');
        expect(links).toHaveLength(1);
        expect(links[0].getAttribute('href')).toBe('https://ci.example/project');
        expect(links[0].textContent).toBe('build status');
    });

    test('media and embedded data images still load', () => {
        const [media, data] = renderToDOM('![a](/media/x/a.png)\n\n![b](data:image/png;base64,AAAA)')
            .querySelectorAll('img');

        expect(media.getAttribute('src')).toBe('/media/x/a.png');
        expect(data.getAttribute('src')).toBe('data:image/png;base64,AAAA');
    });

    test('external links open in a new tab without an opener', () => {
        const a = renderToDOM('<https://example.com/page>').querySelector('a');

        expect(a.getAttribute('href')).toBe('https://example.com/page');
        expect(a.getAttribute('target')).toBe('_blank');
        expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    });

    test('absolute and fragment URLs are left alone', () => {
        const [root, fragment] = renderToDOM('[root](/files)\n\n[top](#top)').querySelectorAll('a');

        expect(root.getAttribute('href')).toBe('/files');
        expect(fragment.getAttribute('href')).toBe('#top');
        expect(fragment.hasAttribute('target')).toBe(false);
    });
});

describe('MarkdownPreview', () => {
    const SOURCE = '# Water storage\n\nRotate *every* six months.\n';

    beforeEach(() => {
        window.localStorage.clear();
        global.fetch = jest.fn(() => Promise.resolve({
            ok: true,
            text: () => Promise.resolve(SOURCE),
        }));
    });

    afterEach(() => {
        delete global.fetch;
    });

    test('fetches the file and shows it formatted', async () => {
        renderUI(<MarkdownPreview url={FILE_URL}/>);

        const heading = await screen.findByRole('heading', {name: 'Water storage'});
        expect(heading.tagName).toBe('H1');
        expect(global.fetch).toHaveBeenCalledWith(FILE_URL, expect.anything());
    });

    test('Raw shows the unformatted source, and the choice is remembered', async () => {
        const {unmount} = renderUI(<MarkdownPreview url={FILE_URL}/>);
        await screen.findByRole('heading', {name: 'Water storage'});

        fireEvent.click(screen.getByRole('button', {name: 'Raw'}));

        expect(screen.queryByRole('heading')).toBeNull();
        expect(screen.getByTestId('markdown-raw').textContent).toBe(SOURCE);

        // The next preview opens in the mode the reader chose last.
        unmount();
        renderUI(<MarkdownPreview url={FILE_URL}/>);
        await waitFor(() => expect(screen.getByTestId('markdown-raw').textContent).toBe(SOURCE));
        expect(screen.queryByRole('heading')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Formatted'}));
        expect(screen.getByRole('heading', {name: 'Water storage'})).toBeTruthy();
    });

    test('a failed fetch shows an error instead of loading forever', async () => {
        global.fetch = jest.fn(() => Promise.resolve({ok: false, status: 404, statusText: 'Not Found'}));

        renderUI(<MarkdownPreview url={FILE_URL}/>);

        expect(await screen.findByText(/404 Not Found/)).toBeTruthy();
    });
});

describe('isMarkdownFile', () => {
    test.each([
        ['text/markdown', 'notes/a.md', true],
        // A stored type from before text/markdown existed; refresh does not retag unchanged files.
        ['text/plain', 'notes/a.md', true],
        ['text/plain', 'notes/a.markdown', true],
        ['text/plain', 'notes/a.txt', false],
        // A suffix alone is not enough; a binary file named .md is not markdown.
        ['application/octet-stream', 'notes/a.md', false],
    ])('%s %s -> %s', (mimetype, lowerPath, expected) => {
        expect(isMarkdownFile(mimetype, lowerPath)).toBe(expected);
    });
});
