import React from 'react';
import {notifications} from '@mantine/notifications';
import {RoleName} from '../../themes/mantine';

/*
 * Toasts.
 *
 * One call signature for the ~19 places that raise a toast.  The container is mounted
 * by ThemeProvider, so a caller only says what happened.
 */

/* `error` is the original spelling and stays; `danger` is the token's name for it. */
export type ToastType = 'info' | 'success' | 'warning' | 'error' | 'danger';

export interface ToastOptions {
    type?: ToastType;
    title?: string;
    description?: string;
    /** Milliseconds before auto-dismiss.  0 keeps it until dismissed. */
    time?: number;
    /**
     * Makes the whole toast activate this.  `Events.js` relies on it for the three events
     * that carry a URL: a page shared from the browser extension, a finished archive
     * upload, and a generated screenshot.
     */
    onClick?: () => void;
}

/*
 * Roles, not hues.  With hues, all four kinds were the same pixel in night and amber:
 * `--yellow` there is byte-identical to `--amber`, and `--orange` to `--text`.  An
 * error toast was indistinguishable from an informational one, which is the failure
 * mode a toast exists to avoid.
 */
const toastRoles: Record<ToastType, RoleName> = {
    info: 'info',
    success: 'success',
    warning: 'warning',
    error: 'danger',
    danger: 'danger',
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
        color: toastRoles[type],
        // Callers spell "stay up" as `time: 0`; Mantine wants `false`.  Its `getAutoClose`
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
