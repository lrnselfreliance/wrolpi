import React from 'react';
import {render, screen, waitFor} from '../../test-utils';
import {ExtensionInstallSuggestion} from './ExtensionInstallSuggestion';

const CHROME_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36';
const CHROMIUM_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chromium/147.0.0.0 Safari/537.36';
const FIREFOX_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0';
const SAFARI_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';

const setUserAgent = (ua) => {
    Object.defineProperty(window.navigator, 'userAgent', {value: ua, configurable: true});
};

const setMeta = (version) => {
    const existing = document.querySelector('meta[name="wrolpi-extension"]');
    if (existing) existing.remove();
    if (version === undefined) return;
    const meta = document.createElement('meta');
    meta.name = 'wrolpi-extension';
    meta.content = String(version);
    document.head.appendChild(meta);
};

describe('ExtensionInstallSuggestion', () => {
    beforeEach(() => {
        setMeta(undefined);
        setUserAgent(CHROME_UA);
        window.localStorage.removeItem('wrolpi-extension-banner-dismissed');
    });

    it('renders nothing when the extension marker meta is present', async () => {
        setMeta('0.2.2');
        render(<ExtensionInstallSuggestion/>);
        // Give the hook a moment in case its initial detect() races; should
        // still find the marker on first render.
        await waitFor(() => {
            expect(screen.queryByText(/Install the WROLPi browser extension/i)).toBeNull();
        });
    });

    it('renders the install message when the marker is absent', async () => {
        render(<ExtensionInstallSuggestion/>);
        // The hook re-checks once at 500ms before deciding "not installed".
        // Wait the recheck out, then assert.
        await waitFor(
            () => expect(screen.getByText(/Install the WROLPi browser extension/i)).toBeInTheDocument(),
            {timeout: 1500},
        );
        expect(screen.getByText(/Open install page/i)).toBeInTheDocument();
    });

    it('renders the install message on Firefox when the marker is absent', async () => {
        setUserAgent(FIREFOX_UA);
        render(<ExtensionInstallSuggestion/>);
        await waitFor(
            () => expect(screen.getByText(/Install the WROLPi browser extension/i)).toBeInTheDocument(),
            {timeout: 1500},
        );
    });

    it('renders the install message on pure Chromium (Chromium/ without Chrome/)', async () => {
        setUserAgent(CHROMIUM_UA);
        render(<ExtensionInstallSuggestion/>);
        await waitFor(
            () => expect(screen.getByText(/Install the WROLPi browser extension/i)).toBeInTheDocument(),
            {timeout: 1500},
        );
    });

    it('renders nothing on Safari even when the marker is absent', async () => {
        setUserAgent(SAFARI_UA);
        render(<ExtensionInstallSuggestion/>);
        await new Promise(r => setTimeout(r, 600));
        expect(screen.queryByText(/Install the WROLPi browser extension/i)).toBeNull();
    });

    it('renders nothing when the user has dismissed the banner', async () => {
        window.localStorage.setItem('wrolpi-extension-banner-dismissed', 'true');
        render(<ExtensionInstallSuggestion/>);
        await new Promise(r => setTimeout(r, 600));
        expect(screen.queryByText(/Install the WROLPi browser extension/i)).toBeNull();
    });
});
