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
}

const toastColors: Record<ToastType, string> = {
    info: 'blue',
    success: 'green',
    warning: 'yellow',
    error: 'red',
};

export function toast({type = 'info', title, description, time = 5000}: ToastOptions = {}) {
    notifications.show({
        title,
        message: description,
        color: toastColors[type],
        // Semantic treated 0 as "stay up"; Mantine wants false for that.
        autoClose: time === 0 ? false : time,
        withBorder: true,
    });
}

/** Dismiss every visible toast.  Useful when navigating away from a failed action. */
export const clearToasts = () => notifications.clean();
