import React from 'react';
import {Button} from './Button';
import {Message} from './Feedback';

/*
 * A gate for media the theme's filter cannot reach.
 *
 * Night and amber pass media through an SVG color matrix so nothing a user opens costs them
 * their dark adaptation.  That filter reaches everything drawn in our own document -- images,
 * video, canvases, and same-origin iframes such as the EPUB viewer.
 *
 * It does not reach a PDF.  Chrome renders PDFs in its own out-of-process viewer, which the
 * compositor paints outside the parent's filter: the computed style on the iframe really does
 * say `filter: url(#wrolpi-night-red)`, and the page still arrives in full color.  Measured on
 * a device in night mode, a PDF covered 55% of the viewport in non-red pixels while the chrome
 * around it was correctly red.
 *
 * Tinting it from outside does not work either.  A red `mix-blend-mode: multiply` overlay above
 * the iframe cannot see the plugin's pixels, so it stops blending and paints flat opaque red:
 * the measurement reports zero non-red pixels while the document is entirely obliterated.
 *
 * So the options are to render PDFs ourselves or to not show one unasked.  This is the second:
 * the reader is told why, and chooses.  Nothing renders until they do -- hiding it with CSS
 * would still load and paint the viewer, which is the whole thing being avoided.
 *
 * `gated` is a prop rather than something read from ThemeContext, so this stays a component of
 * the library like any other: it is told whether to gate, it does not decide.  Call sites pass
 * `isPdf && mediaFilterEnabled`.
 */

export interface MediaGateProps {
    /** Whether to withhold `children` until the reader asks for them. */
    gated: boolean;
    /** What is being withheld, named in the reader's terms: "PDF", "document". */
    kind?: string;
    children: React.ReactNode;
}

export function MediaGate({gated, kind = 'PDF', children}: MediaGateProps) {
    const [revealed, setRevealed] = React.useState(false);

    // Re-gate when filtering comes back on, so revealing one document does not leave every
    // later one unguarded.
    React.useEffect(() => {
        if (!gated) setRevealed(false);
    }, [gated]);

    if (!gated) return <>{children}</>

    if (revealed) {
        /*
         * The control goes ABOVE the media, not after it.  A preview fills
         * `calc(100dvh - 18.75rem)`, a height calibrated with no room for a trailing button
         * row, so a control placed after it lands below the fold of a full-screen modal --
         * leaving the reader who just lit up their eyes scrolling to find the way to undo it.
         */
        return <>
            <div className='wrolpi-button-row'>
                <Button role='cancel' icon='eye slash' onClick={() => setRevealed(false)}>
                    Hide the {kind} again
                </Button>
            </div>
            {children}
        </>
    }

    return <Message kind='warning' icon='eye slash' title={`${kind} hidden`}>
        <p>
            This {kind} cannot be tinted to match the theme, so it would be shown in full color
            and at full brightness.
        </p>
        <Button role='primary' onClick={() => setRevealed(true)}>
            Show the full-color {kind}
        </Button>
    </Message>
}
