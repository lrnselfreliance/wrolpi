import React from 'react';
import {render, screen, waitFor} from '../../test-utils';
import {ExtensionInstallSuggestion} from './ExtensionInstallSuggestion';

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

    it('renders nothing when the user has dismissed the banner', async () => {
        window.localStorage.setItem('wrolpi-extension-banner-dismissed', 'true');
        render(<ExtensionInstallSuggestion/>);
        await new Promise(r => setTimeout(r, 600));
        expect(screen.queryByText(/Install the WROLPi browser extension/i)).toBeNull();
    });
});
