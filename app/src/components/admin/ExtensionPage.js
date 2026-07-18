import React from "react";
import {Button, Header, Icon, Segment} from "../Theme";
import {Input, Message} from "semantic-ui-react";
import {ThemeContext} from "../../contexts/contexts";
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
    return <Segment style={{marginBottom: '1em'}}>
        <Header as='h4'>
            <Icon name='globe'/>
            This WROLPi's URL
        </Header>
        <p style={{color: 'grey'}}>
            After installing the extension, paste this URL into the
            destination field on the extension's options page.
        </p>
        <Input
            fluid
            readOnly
            value={origin}
            action={
                <Button
                    icon={copied ? 'check' : 'copy'}
                    color={copied ? 'green' : null}
                    content={copied ? 'Copied' : 'Copy'}
                    onClick={onCopy}
                />
            }
        />
    </Segment>;
}

function FirefoxCard({metadata, version}) {
    const file = (metadata && metadata.files && metadata.files['wrolpi-firefox.xpi']) || {};
    const available = !!file.available;
    return <Segment>
        <Header as='h3'>
            <Icon name='firefox'/>
            Firefox{version ? ` — v${version}` : ''}
        </Header>
        <p>One-click install. Mozilla has signed this build.</p>
        <Button
            primary
            as='a'
            href={FIREFOX_XPI_PATH}
            disabled={!available}
            icon='download'
            content={available ? `Install for Firefox (${formatSize(file.size_bytes)})` : 'Not yet available'}
        />
        <p style={{marginTop: '1em', color: 'grey'}}>
            Firefox will ask you to confirm the install. Accept the prompt.
        </p>
        <Header as='h4' style={{marginTop: '1.5em'}}>After installing</Header>
        <ol style={{lineHeight: 1.7, paddingLeft: '1.2em'}}>
            <li>Open the extension's <strong>Options</strong> page (right-click the toolbar icon &rarr; Manage Extension &rarr; Options) and add this WROLPi as a destination. Click <strong>Test</strong> to grant API access.</li>
            <li>Click the extension icon in the toolbar &rarr; the permission dropdown &rarr; <strong>Always Allow on this site</strong>. Firefox requires this second click in addition to the Test grant — without it, the extension can talk to your WROLPi but can't mark its tabs as connected.</li>
        </ol>
    </Segment>;
}

function ChromiumCard({metadata, version}) {
    const file = (metadata && metadata.files && metadata.files['wrolpi-chrome.zip']) || {};
    const available = !!file.available;
    return <Segment>
        <Header as='h3'>
            <Icon name='chrome'/>
            Chrome / Brave / Edge{version ? ` — v${version}` : ''}
        </Header>
        <p>
            Chromium-based browsers don't allow one-click extension installs from
            outside the Web Store, so we sideload via the built-in developer flow.
        </p>
        <Button
            primary
            as='a'
            href={CHROME_ZIP_PATH}
            disabled={!available}
            icon='download'
            content={available ? `Download .zip (${formatSize(file.size_bytes)})` : 'Not yet available'}
            download
        />
        <Header as='h4' style={{marginTop: '1.5em'}}>Install steps</Header>
        <ol style={{lineHeight: 1.7, paddingLeft: '1.2em'}}>
            <li>Download the <code>.zip</code> above and extract it to a folder you'll keep around.</li>
            <li>Open <code>chrome://extensions</code> (or <code>brave://extensions</code> / <code>edge://extensions</code>).</li>
            <li>Toggle <strong>Developer mode</strong> on (top-right).</li>
            <li>Click <strong>Load unpacked</strong> and pick the extracted folder.</li>
        </ol>
        <p style={{color: 'grey'}}>
            The extension stays installed across browser restarts. Don't delete the
            extracted folder — the browser loads from it directly.
        </p>
    </Segment>;
}

function UnknownCard() {
    return <Segment>
        <Header as='h3'>Unsupported browser</Header>
        <p>
            The WROLPi extension supports Chrome, Brave, Edge, and Firefox. Open
            this page in one of those browsers to install.
        </p>
    </Segment>;
}

export function ExtensionPage() {
    const [metadata, setMetadata] = React.useState(null);
    const [error, setError] = React.useState(null);
    const browser = detectBrowser();
    const {s} = React.useContext(ThemeContext);

    React.useEffect(() => {
        let cancelled = false;
        fetch('/api/extensions')
            .then(res => res.json())
            .then(body => { if (!cancelled) setMetadata(body); })
            .catch(err => { if (!cancelled) setError(String(err)); });
        return () => { cancelled = true; };
    }, []);

    if (error) {
        return <Segment>
            <Message negative>
                <Message.Header>Couldn't load extension info</Message.Header>
                <p>{error}</p>
            </Message>
        </Segment>;
    }

    const versions = (metadata && metadata.versions) || {};
    const anyAvailable = metadata && Object.values(metadata.files || {}).some(f => f.available);

    return <>
        <Header as='h1'>Browser Extension</Header>
        <p {...s}>
            Install the WROLPi browser extension to send pages, videos, and feeds to
            this WROLPi from any tab. The extension is open-source and not distributed
            via official browser stores — it ships with each WROLPi release.
        </p>

        <DestinationHint/>

        {metadata && !anyAvailable && <Message warning>
            <Message.Header>Extension binaries not yet installed</Message.Header>
            <p>
                The extension binaries aren't on this WROLPi yet. They ship with the
                next release; pull the latest and they'll appear here.
            </p>
        </Message>}

        {browser === 'firefox' && <FirefoxCard metadata={metadata} version={versions.firefox}/>}
        {browser === 'chromium' && <ChromiumCard metadata={metadata} version={versions.chrome}/>}
        {browser === 'unknown' && <UnknownCard/>}

        <Segment basic style={{marginTop: '2em'}}>
            <Header as='h4'>Both browsers, just in case</Header>
            <p style={{color: 'grey'}}>
                You can install for a different browser too — useful if you sync
                between machines.
            </p>
            {browser !== 'firefox' && <FirefoxCard metadata={metadata} version={versions.firefox}/>}
            {browser !== 'chromium' && <ChromiumCard metadata={metadata} version={versions.chrome}/>}
        </Segment>
    </>;
}
