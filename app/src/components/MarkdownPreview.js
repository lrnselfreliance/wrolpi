import React from "react";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import {useLocalStorage} from "./Common";
import {Button, ButtonGroup, Loading, Message} from "./ui";

/*
 * Raw HTML in the file is escaped, not parsed: markdown files arrive with downloads, and the preview
 * renders on the API's origin.  `validateLink` (on by default) refuses javascript:, vbscript:, file:,
 * and non-image data: URLs.  DOMPurify runs anyway, so neither guard is the only one.
 */
const markdown = new MarkdownIt({html: false, linkify: true});

// A URL with a scheme (https:, mailto:, ...) points somewhere other than the media directory.
const URL_WITH_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

/**
 * Resolve a URL written in a markdown file against the file's own media URL, the way a browser
 * would resolve it against a document in that directory.
 *
 * Returns the URL unchanged if it is not relative, or null if it climbs out of the media directory;
 * only media is served relative to a file.
 */
function resolveRelativeURL(url, fileURL) {
    if (!url || URL_WITH_SCHEME.test(url) || url.startsWith('/') || url.startsWith('#')) {
        return url;
    }
    const resolved = new URL(url, new URL(fileURL, window.location.origin));
    if (!resolved.pathname.startsWith('/media/')) {
        return null;
    }
    return resolved.pathname + resolved.search + resolved.hash;
}

function rewriteURL(token, attr, fileURL) {
    const url = token.attrGet(attr);
    if (url === null) {
        return;
    }
    const resolved = resolveRelativeURL(url, fileURL);
    if (resolved === null) {
        token.attrs = token.attrs.filter(([name]) => name !== attr);
    } else {
        token.attrSet(attr, resolved);
    }
}

markdown.core.ruler.push('wrolpi_media_urls', (state) => {
    const {fileURL} = state.env;
    for (const token of state.tokens) {
        for (const child of token.children || []) {
            if (child.type === 'image') {
                rewriteURL(child, 'src', fileURL);
            } else if (child.type === 'link_open') {
                rewriteURL(child, 'href', fileURL);
                const href = child.attrGet('href');
                // Following a link would close the preview; a fragment stays within the document.
                if (href && !href.startsWith('#')) {
                    child.attrSet('target', '_blank');
                    child.attrSet('rel', 'noopener noreferrer');
                }
            }
        }
    }
});

/** Render markdown to sanitized HTML.  Relative URLs resolve against `fileURL`, the file's /media/ URL. */
export function renderMarkdown(text, fileURL) {
    const html = markdown.render(text, {fileURL});
    return DOMPurify.sanitize(html, {ADD_ATTR: ['target']});
}

export function isMarkdownFile(mimetype, lowerPath) {
    // Files indexed before text/markdown existed stay text/plain until their next refresh.
    return mimetype.startsWith('text/markdown')
        || (mimetype.startsWith('text/') && (lowerPath.endsWith('.md') || lowerPath.endsWith('.markdown')));
}

/** Preview a markdown file, formatted or as its raw source. */
export function MarkdownPreview({url}) {
    const [formatted, setFormatted] = useLocalStorage('markdownPreviewFormatted', true);
    const [text, setText] = React.useState(null);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
        const controller = new AbortController();
        setText(null);
        setError(null);
        fetch(url, {signal: controller.signal})
            .then(response => {
                if (!response.ok) {
                    throw new Error(`${response.status} ${response.statusText}`);
                }
                return response.text();
            })
            .then(setText)
            .catch(e => {
                if (e.name !== 'AbortError') {
                    console.error(e);
                    setError(e.message);
                }
            });
        return () => controller.abort();
    }, [url]);

    const html = React.useMemo(() => text === null ? null : renderMarkdown(text, url), [text, url]);

    let body;
    if (error) {
        body = <Message kind='error' title='Could not load file'>{error}</Message>;
    } else if (text === null) {
        body = <Loading/>;
    } else if (formatted) {
        body = <div className='markdown-body' dangerouslySetInnerHTML={{__html: html}}/>;
    } else {
        body = <pre className='markdown-raw' data-testid='markdown-raw'>{text}</pre>;
    }

    return <>
        <ButtonGroup>
            <Button size='small' variant={formatted ? 'filled' : 'default'} onClick={() => setFormatted(true)}>
                Formatted
            </Button>
            <Button size='small' variant={formatted ? 'default' : 'filled'} onClick={() => setFormatted(false)}>
                Raw
            </Button>
        </ButtonGroup>
        <div className='markdown-preview'>
            {body}
        </div>
    </>
}
