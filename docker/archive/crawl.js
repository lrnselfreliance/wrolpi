#!/usr/bin/env node
/*
 * WROLPi real-browser crawler for the Scrape Downloader.
 *
 * Drives a headless Chromium (via puppeteer-core) to discover downloadable files that a raw-HTML
 * scrape cannot see: files referenced only by JavaScript, fetched via XHR/fetch, or listed inside
 * JSON manifests.  Discovery is read-only -- this never downloads the files, it only finds their
 * URLs and prints them.  The Python Scrape Downloader hands the result to the existing aria2c
 * sub-downloader.
 *
 * Invocation:
 *   node crawl.js '<json-args>'
 * where <json-args> is:
 *   {
 *     "url": "https://example.com/",   // seed URL
 *     "depth": 1,                       // number of link levels to fetch (1 == seed only)
 *     "suffix": ".mp4",                 // file suffix to collect (case-insensitive)
 *     "max_pages": 100,                 // hard cap on pages fetched
 *     "user_agent": "WROLPi/...",       // optional UA string
 *     "executable_path": "/usr/bin/google-chrome"  // required: path to Chrome/Chromium
 *   }
 *
 * Output (stdout, a single JSON object):
 *   {"found_urls": [...], "pages_visited": N, "capped": false}
 * Diagnostics go to stderr.
 */
'use strict';

const puppeteer = require('puppeteer-core');

// Content types whose bodies we scan for file references.  Sites stash file URLs in different
// places: JSON manifests (the real ben.kahn.studio), or inlined in JS bundles (some SPAs).  We scan
// JSON, HTML, plain text, AND JavaScript; the path-like (slash-required) regex in scanBody is what
// keeps JS-bundle noise such as the literal ".pdf,.mp4" out of the results.  CSS is excluded.
const SCANNABLE_CT = /^(application\/(json|xml|xhtml\+xml|javascript)|.*\+json|text\/(html|plain|xml|javascript))/i;
// Don't read enormous bodies into memory -- protect the Pi.
const MAX_BODY_BYTES = 5 * 1024 * 1024;
const PAGE_TIMEOUT_MS = 3 * 60 * 1000; // Matches the SingleFile per-page budget.

function parseArgs() {
    const raw = process.argv[2];
    if (!raw) {
        throw new Error('Missing JSON argument');
    }
    const args = JSON.parse(raw);
    if (!args.url) throw new Error('url is required');
    if (!args.suffix) throw new Error('suffix is required');
    if (!args.executable_path) throw new Error('executable_path is required');
    args.depth = args.depth || 1;
    args.max_pages = args.max_pages || 100;
    args.suffix = String(args.suffix).toLowerCase();
    return args;
}

// True if the URL's path (ignoring any query/fragment) ends with the requested suffix.
function matchesSuffix(url, suffix) {
    try {
        const u = new URL(url);
        return u.pathname.toLowerCase().endsWith(suffix);
    } catch (e) {
        return false;
    }
}

function sameHost(url, seedHost) {
    try {
        return new URL(url).host === seedHost;
    } catch (e) {
        return false;
    }
}

// Resolve a possibly-relative reference against a base, returning an absolute URL or null.
function resolve(ref, base) {
    try {
        return new URL(ref, base).href;
    } catch (e) {
        return null;
    }
}

// Scan a text body (e.g. JSON manifest) for tokens that look like a path/URL ending in the suffix.
// This is what finds files that never appear in the DOM (e.g. ben.kahn.studio/manifest.json).
function scanBody(body, suffix, baseUrl, found) {
    // Escape regex metacharacters in the suffix (the leading dot, etc.).
    const escaped = suffix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // Match a path-like token ending in the suffix: it must contain a "/" (a real path or URL) and
    // must not span commas/quotes/brackets.  Requiring a slash rejects bare suffix-list tokens like
    // ".pdf,.mp4" that appear in config blobs.  Real manifest references are always paths.
    const tok = '[^\\s"\'`()<>,\\[\\]{}]';
    const re = new RegExp(tok + '*/' + tok + '*' + escaped + '(?:\\?' + tok + '*)?', 'gi');
    const matches = body.match(re) || [];
    for (const m of matches) {
        const abs = resolve(m, baseUrl);
        if (abs && matchesSuffix(abs, suffix)) {
            found.add(abs);
        }
    }
}

async function autoScroll(page) {
    // Trigger lazy-loaded content by scrolling to the bottom in steps.
    await page.evaluate(async () => {
        await new Promise((resolve) => {
            let total = 0;
            const step = 600;
            const timer = setInterval(() => {
                window.scrollBy(0, step);
                total += step;
                if (total >= document.body.scrollHeight || total > 50000) {
                    clearInterval(timer);
                    resolve();
                }
            }, 100);
        });
    });
}

async function main() {
    const args = parseArgs();
    const seedHost = new URL(args.url).host;
    const found = new Set();      // absolute file URLs matching the suffix
    const visited = new Set();    // pages already fetched
    let pagesVisited = 0;
    let capped = false;

    const browser = await puppeteer.launch({
        executablePath: args.executable_path,
        headless: 'new',
        // Accept self-signed/invalid certs: WROLPi runs on its own self-signed Root CA, and an
        // offline archiving crawler should fetch content regardless of TLS validation.
        ignoreHTTPSErrors: true,
        args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--ignore-certificate-errors'],
    });

    try {
        // BFS queue of {url, level}; level 0 is the seed.  A page is fetched while level < depth.
        let queue = [{url: args.url, level: 0}];

        while (queue.length > 0) {
            if (pagesVisited >= args.max_pages) {
                capped = true;
                console.error('Reached max page count.');
                break;
            }

            const {url, level} = queue.shift();
            if (visited.has(url)) continue;
            visited.add(url);

            const page = await browser.newPage();
            if (args.user_agent) await page.setUserAgent(args.user_agent);

            // Capture files from every response: by URL, by content-type, and by scanning bodies.
            page.on('response', async (resp) => {
                try {
                    const respUrl = resp.url();
                    const ct = (resp.headers()['content-type'] || '').toLowerCase();

                    if (matchesSuffix(respUrl, args.suffix) || ct.startsWith('video/')) {
                        found.add(respUrl);
                    }

                    if (SCANNABLE_CT.test(ct)) {
                        const len = Number(resp.headers()['content-length'] || 0);
                        if (len && len > MAX_BODY_BYTES) return;
                        const buf = await resp.buffer();
                        if (buf.length > MAX_BODY_BYTES) return;
                        scanBody(buf.toString('utf8'), args.suffix, respUrl, found);
                    }
                } catch (e) {
                    // Responses can be unreadable (redirects, aborted, no body) -- ignore.
                }
            });

            try {
                await page.goto(url, {waitUntil: 'networkidle2', timeout: PAGE_TIMEOUT_MS});
                await autoScroll(page);

                // Harvest links and media from the rendered DOM.
                const hrefs = await page.evaluate(() => {
                    const out = [];
                    document.querySelectorAll('a[href]').forEach((a) => out.push(a.href));
                    document.querySelectorAll('video[src], source[src]').forEach((v) => out.push(v.src));
                    return out;
                });

                for (const href of hrefs) {
                    const abs = resolve(href, url);
                    if (!abs) continue;
                    if (matchesSuffix(abs, args.suffix)) {
                        found.add(abs);
                    } else if (level + 1 < args.depth && sameHost(abs, seedHost) && !visited.has(abs)) {
                        queue.push({url: abs, level: level + 1});
                    }
                }
            } catch (e) {
                console.error(`Failed to crawl ${url}: ${e.message}`);
            } finally {
                pagesVisited += 1;
                await page.close();
            }
        }
    } finally {
        await browser.close();
    }

    process.stdout.write(JSON.stringify({
        found_urls: Array.from(found),
        pages_visited: pagesVisited,
        capped: capped,
    }));
}

main().catch((e) => {
    console.error(e && e.stack ? e.stack : String(e));
    process.exit(1);
});
