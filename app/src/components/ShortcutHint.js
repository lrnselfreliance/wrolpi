import React from "react";
import {useKeyboardDetected, usePlatformModifier} from "../hooks/customHooks";

/**
 * Displays a keyboard shortcut hint that adapts to the user's platform.
 * Shows the correct modifier key (Cmd on macOS, Ctrl on Windows/Linux).
 * Hidden on touch devices until a hardware keyboard is detected via key press.
 *
 * @param {string} shortcutKey - The key part of the shortcut (e.g., "K", "P", "/")
 * @param {object} style - Optional additional styles to apply
 */
export function ShortcutHint({shortcutKey, style = {}}) {
    const {modifierKey} = usePlatformModifier();
    const keyboardDetected = useKeyboardDetected();

    if (!keyboardDetected) {
        return null;
    }

    const defaultStyle = {
        fontSize: '0.75em',
        opacity: 0.7,
        marginLeft: '0.3em',
    };

    return (
        <span style={{...defaultStyle, ...style}}>
            {modifierKey}{shortcutKey}
        </span>
    );
}

/**
 * Displays a simple key hint without a modifier (e.g., for "/" or "?" shortcuts).
 * Hidden on touch devices until a hardware keyboard is detected via key press.
 *
 * @param {string} keyLabel - The key to display (e.g., "?", "/")
 * @param {object} style - Optional additional styles to apply
 */
export function KeyHint({keyLabel, style = {}}) {
    const keyboardDetected = useKeyboardDetected();

    if (!keyboardDetected) {
        return null;
    }

    const defaultStyle = {
        fontSize: '0.75em',
        opacity: 0.7,
        marginLeft: '0.3em',
    };

    return (
        <span style={{...defaultStyle, ...style}}>
            {keyLabel}
        </span>
    );
}
