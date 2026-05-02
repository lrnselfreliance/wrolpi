import React from 'react';
import {mockFetch, render, screen, waitFor} from '../../test-utils';
import {ExtensionPage} from './ExtensionPage';

const FIREFOX_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0';
const CHROME_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36';
const SAFARI_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';

const setUserAgent = (ua) => {
    Object.defineProperty(window.navigator, 'userAgent', {value: ua, configurable: true});
};

describe('ExtensionPage', () => {
    let originalFetch;

    beforeEach(() => {
        originalFetch = global.fetch;
    });

    afterEach(() => {
        global.fetch = originalFetch;
    });

    it('shows the Firefox install card when the user agent is Firefox', async () => {
        setUserAgent(FIREFOX_UA);
        global.fetch = mockFetch({
            files: {
                'wrolpi-firefox.xpi': {available: true, size_bytes: 700000},
                'wrolpi-chrome.zip': {available: true, size_bytes: 700000},
            },
            versions: {firefox: '0.1.0', chrome: '0.1.0'},
        });

        render(<ExtensionPage/>);

        const button = await screen.findByText(/Install for Firefox/i);
        expect(button).toBeInTheDocument();
    });

    it('shows the Chromium install card with install steps when the user agent is Chrome', async () => {
        setUserAgent(CHROME_UA);
        global.fetch = mockFetch({
            files: {
                'wrolpi-firefox.xpi': {available: true, size_bytes: 700000},
                'wrolpi-chrome.zip': {available: true, size_bytes: 700000},
            },
            versions: {chrome: '0.1.0', firefox: '0.1.0'},
        });

        render(<ExtensionPage/>);

        expect(await screen.findByText(/Download \.zip/i)).toBeInTheDocument();
        expect(screen.getByText(/Developer mode/i)).toBeInTheDocument();
        expect(screen.getByText(/Load unpacked/i)).toBeInTheDocument();
    });

    it('shows the not-yet-installed warning when no binaries are available', async () => {
        // This test exists specifically to render the <Message warning> block,
        // which catches missing imports from the Theme/Semantic-UI module.
        setUserAgent(CHROME_UA);
        global.fetch = mockFetch({
            files: {
                'wrolpi-firefox.xpi': {available: false, size_bytes: null},
                'wrolpi-chrome.zip': {available: false, size_bytes: null},
            },
            versions: {},
        });

        render(<ExtensionPage/>);

        expect(await screen.findByText(/Extension binaries not yet installed/i)).toBeInTheDocument();
    });

    it('shows the unsupported-browser message for Safari', async () => {
        setUserAgent(SAFARI_UA);
        global.fetch = mockFetch({
            files: {
                'wrolpi-firefox.xpi': {available: true, size_bytes: 700000},
                'wrolpi-chrome.zip': {available: true, size_bytes: 700000},
            },
            versions: {},
        });

        render(<ExtensionPage/>);

        expect(await screen.findByText(/Unsupported browser/i)).toBeInTheDocument();
    });

});
