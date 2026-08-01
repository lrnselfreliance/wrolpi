import React from 'react';
import {notifications} from '@mantine/notifications';

/*
 * Toasts.
 *
 * Keeps the react-semantic-toasts-2 call signature so the ~19 call sites migrate
 * by changing their import, not their code.  The container is mounted by
 * ThemeProvider.
 */

export type ToastType = 'info' | 'success' | 'warning' | 'error';

export interface ToastOptions {
    type?: ToastType;
    title?: string;
    description?: string;
    /** Milliseconds before auto-dismiss.  0 keeps it until dismissed. */
    time?: number;
    /**
     * Makes the whole toast activate this — Semantic's behaviour, which `Events.js` still
     * relies on for the three events that carry a URL: a page shared from the browser
     * extension, a finished archive upload, and a generated screenshot.
     */
    onClick?: () => void;
}

const toastColors: Record<ToastType, string> = {
    info: 'blue',
    success: 'green',
    warning: 'yellow',
    error: 'red',
};

/**
 * The props that make a toast followable.
 *
 * `tabIndex` and the key handler are not decoration: WROLPi runs on devices with a keyboard
 * and no mouse, and a toast only a pointer can follow is a feature half the deployments
 * cannot use.  There is deliberately no `role` — a `button` or `link` role may not contain
 * interactive content, and the dismiss button lives inside.
 */
const followable = (onClick: () => void) => ({
    style: {cursor: 'pointer'},
    tabIndex: 0,
    onClick: (event: React.MouseEvent) => {
        // The dismiss button is inside the toast, so its click reaches here too.  Closing a
        // notification is not following it, and for these three that would be a navigation
        // the user did not ask for.
        if ((event.target as HTMLElement).closest('button')) {
            return;
        }
        onClick();
    },
    onKeyDown: (event: React.KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onClick();
        }
    },
});

export function toast({type = 'info', title, description, time = 5000, onClick}: ToastOptions = {}) {
    notifications.show({
        title,
        message: description,
        color: toastColors[type],
        // Semantic treated 0 as "stay up"; Mantine wants false for that.  Its `getAutoClose`
        // returns any number as given and the container then calls `setTimeout(hide, 0)`, so
        // passing the 0 through dismisses the toast on the next tick.
        autoClose: time === 0 ? false : time,
        withBorder: true,
        // Mantine leaves its close button unnamed, which a screen reader reads as "button".
        closeButtonProps: {'aria-label': 'Dismiss notification'},
        ...(onClick ? followable(onClick) : {}),
    });
}

/** Dismiss every visible toast.  Useful when navigating away from a failed action. */
export const clearToasts = () => notifications.clean();
