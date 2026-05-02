import React from "react";
import {Link} from "react-router";
import {Button, Icon, Message} from "semantic-ui-react";
import {useLocalStorage} from "../Common";
import {useExtensionInstalled} from "../../hooks/customHooks";

// Top-of-dashboard nudge for users who don't yet have the WROLPi browser
// extension installed (or installed but haven't added this WROLPi as a
// destination). Hidden once the user installs+configures, or dismisses it.
//
// Detection is via a meta tag injected by the extension's content script.
// The extension only injects on configured destination origins, so seeing
// the marker here means "extension is installed AND knows about this WROLPi".
export function ExtensionInstallSuggestion() {
    const installed = useExtensionInstalled();
    const [dismissed, setDismissed] = useLocalStorage(
        'wrolpi-extension-banner-dismissed', false,
    );

    // installed === null means "still checking" — render nothing rather
    // than flashing the banner before the content-script race resolves.
    if (installed !== false || dismissed) return null;

    return <Message info icon onDismiss={() => setDismissed(true)}>
        <Icon name='puzzle piece'/>
        <Message.Content>
            <Message.Header>Install the WROLPi browser extension</Message.Header>
            <p>
                Send pages, videos, and feeds to this WROLPi straight from any
                tab. Open-source and not distributed via the official browser
                stores.
            </p>
            <Button as={Link} to='/admin/extension' primary size='small'>
                Open install page
            </Button>
        </Message.Content>
    </Message>;
}
