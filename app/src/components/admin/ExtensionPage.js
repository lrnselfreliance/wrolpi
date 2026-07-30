import React from "react";
import {ActionInput, Button, Header, Message, Panel, Stack} from "../ui";
import {detectBrowser} from "./browserDetect";

// The WROLPi browser extension is distributed off-store: Chrome users
// sideload the unpacked .zip; Firefox users get a Mozilla-signed .xpi that
// installs in one click. Both binaries are served by the local WROLPi
// backend so this page works on a fully air-gapped install.

const CHROME_ZIP_PATH = '/api/extensions/wrolpi-chrome.zip';
const FIREFOX_XPI_PATH = '/api/extensions/wrolpi-firefox.xpi';

function formatSize(bytes) {
    if (!bytes) return '';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(0)} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
}

function DestinationHint() {
    // The user is currently viewing this WROLPi at exactly window.location.origin.
    // That's the URL they need to paste into the extension's destination field.
    const origin = (typeof window !== 'undefined' && window.location && window.location.origin) || '';
    const [copied, setCopied] = React.useState(false);
    const onCopy = async () => {
        try {
            await navigator.clipboard.writeText(origin);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            // Older / non-secure contexts may block the clipboard API.
            // Fall through silently — the user can still copy manually.
        }
    };
    return <Panel style={{marginBottom: '1em'}}>
        <Header as='h4' icon='globe'>This WROLPi's URL</Header>
        <p style={{color: 'var(--muted)'}}>
            After installing the extension, paste this URL into the
            destination field on the extension's options page.
        </p>
        <ActionInput
            readOnly
            value={origin}
            action={
                <Button
                    icon={copied ? 'check' : 'copy'}
                    role={copied ? 'save' : 'cancel'}
                    onClick={onCopy}
                >
                    {copied ? 'Copied' : 'Copy'}
                </Button>
            }
        />
    </Panel>;
}

function FirefoxCard({metadata, version}) {
    const file = (metadata && metadata.files && metadata.files['wrolpi-firefox.xpi']) || {};
    const available = !!file.available;
    return <Panel>
        <Header as='h3' icon='firefox'>
            Firefox{version ? ` — v${version}` : ''}
        </Header>
        <p>One-click install. Mozilla has signed this build.</p>
        <Button
            role='primary'
            component='a'
            href={FIREFOX_XPI_PATH}
            disabled={!available}
            icon='download'
        >
            {available ? `Install for Firefox (${formatSize(file.size_bytes)})` : 'Not yet available'}
        </Button>
        <p style={{marginTop: '1em', color: 'var(--muted)'}}>
            Firefox will ask you to confirm the install. Accept the prompt.
        </p>
        <Header as='h4' style={{marginTop: '1.5em'}}>After installing</Header>
        <ol style={{lineHeight: 1.7, paddingLeft: '1.2em'}}>
            <li>Open the extension's <strong>Options</strong> page (right-click the toolbar icon &rarr; Manage Extension &rarr; Options) and add this WROLPi as a destination. Click <strong>Test</strong> to grant API access.</li>
            <li>Click the extension icon in the toolbar &rarr; the permission dropdown &rarr; <strong>Always Allow on this site</strong>. Firefox requires this second click in addition to the Test grant — without it, the extension can talk to your WROLPi but can't mark its tabs as connected.</li>
        </ol>
    </Panel>;
}

function ChromiumCard({metadata, version}) {
    const file = (metadata && metadata.files && metadata.files['wrolpi-chrome.zip']) || {};
    const available = !!file.available;
    return <Panel>
        <Header as='h3' icon='chrome'>
            Chrome / Brave / Edge{version ? ` — v${version}` : ''}
        </Header>
        <p>
            Chromium-based browsers don't allow one-click extension installs from
            outside the Web Store, so we sideload via the built-in developer flow.
        </p>
        <Button
            role='primary'
            component='a'
            href={CHROME_ZIP_PATH}
            disabled={!available}
            icon='download'
            download
        >
            {available ? `Download .zip (${formatSize(file.size_bytes)})` : 'Not yet available'}
        </Button>
        <Header as='h4' style={{marginTop: '1.5em'}}>Install steps</Header>
        <ol style={{lineHeight: 1.7, paddingLeft: '1.2em'}}>
            <li>Download the <code>.zip</code> above and extract it to a folder you'll keep around.</li>
            <li>Open <code>chrome://extensions</code> (or <code>brave://extensions</code> / <code>edge://extensions</code>).</li>
            <li>Toggle <strong>Developer mode</strong> on (top-right).</li>
            <li>Click <strong>Load unpacked</strong> and pick the extracted folder.</li>
        </ol>
        <p style={{color: 'var(--muted)'}}>
            The extension stays installed across browser restarts. Don't delete the
            extracted folder — the browser loads from it directly.
        </p>
    </Panel>;
}

function UnknownCard() {
    return <Panel>
        <Header as='h3'>Unsupported browser</Header>
        <p>
            The WROLPi extension supports Chrome, Brave, Edge, and Firefox. Open
            this page in one of those browsers to install.
        </p>
    </Panel>;
}

export function ExtensionPage() {
    const [metadata, setMetadata] = React.useState(null);
    const [error, setError] = React.useState(null);
    const browser = detectBrowser();

    React.useEffect(() => {
        let cancelled = false;
        fetch('/api/extensions')
            .then(res => res.json())
            .then(body => { if (!cancelled) setMetadata(body); })
            .catch(err => { if (!cancelled) setError(String(err)); });
        return () => { cancelled = true; };
    }, []);

    if (error) {
        return <Message kind='error' title="Couldn't load extension info">{error}</Message>;
    }

    const versions = (metadata && metadata.versions) || {};
    const anyAvailable = metadata && Object.values(metadata.files || {}).some(f => f.available);

    return <Stack gap='md'>
        <div>
            <Header as='h1'>Browser Extension</Header>
            <p>
                Install the WROLPi browser extension to send pages, videos, and feeds to
                this WROLPi from any tab. The extension is open-source and not distributed
                via official browser stores — it ships with each WROLPi release.
            </p>
        </div>

        <DestinationHint/>

        {metadata && !anyAvailable && <Message kind='warning' title='Extension binaries not yet installed'>
            The extension binaries aren't on this WROLPi yet. They ship with the
            next release; pull the latest and they'll appear here.
        </Message>}

        {browser === 'firefox' && <FirefoxCard metadata={metadata} version={versions.firefox}/>}
        {browser === 'chromium' && <ChromiumCard metadata={metadata} version={versions.chrome}/>}
        {browser === 'unknown' && <UnknownCard/>}

        <Stack gap='sm' style={{marginTop: '1em'}}>
            <div>
                <Header as='h4' dividing>Both browsers, just in case</Header>
                <p style={{color: 'var(--muted)'}}>
                    You can install for a different browser too — useful if you sync
                    between machines.
                </p>
            </div>
            {browser !== 'firefox' && <FirefoxCard metadata={metadata} version={versions.firefox}/>}
            {browser !== 'chromium' && <ChromiumCard metadata={metadata} version={versions.chrome}/>}
        </Stack>
    </Stack>;
}
