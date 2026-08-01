import React from 'react';
import {act, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MantineProvider} from '@mantine/core';
import {Notifications} from '@mantine/notifications';
import {cssVariablesResolver, mantineTheme} from '../../themes/mantine';
import {notificationsStore} from '@mantine/notifications';
import {clearToasts, toast} from './toast';

/*
 * Tests for toasts.
 *
 * `toast` has thirteen call sites and had no test at all, having already failed once in the
 * way that is hardest to notice: App.js dropped Semantic's toast container while seven pages
 * were still importing the old helper, so every notification in the app silently went
 * nowhere.  Nothing threw, and nothing looked wrong until somebody expected a message.
 *
 * The container is mounted here the way ThemeProvider mounts it, because a toast with no
 * container is exactly the failure worth covering.
 */

const withToasts = () => render(
    <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
        <Notifications position='top-right' limit={5}/>
    </MantineProvider>
);

const showToast = (options) => act(() => {
    toast(options);
});

const visibleToasts = () =>
    document.querySelectorAll('[class*="mantine-Notification-root"]');

afterEach(() => {
    act(() => clearToasts());
});

describe('toast', () => {
    it('shows a title and its description', async () => {
        withToasts();

        showToast({type: 'success', title: 'Saved', description: 'Channel settings written.'});

        expect(await screen.findByText('Saved')).toBeInTheDocument();
        expect(screen.getByText('Channel settings written.')).toBeInTheDocument();
    });

    it('shows a description on its own', async () => {
        // Several call sites send no title.
        withToasts();

        showToast({description: 'Nothing to download.'});

        expect(await screen.findByText('Nothing to download.')).toBeInTheDocument();
    });

    it('stacks, rather than replacing what is already up', async () => {
        /*
         * The behaviour that matters when a background task reports repeatedly -- three
         * downloads finishing should be three messages, not one that keeps being overwritten.
         * Mantine replaces a notification when it is given an `id` it has already seen, so
         * this would break the moment somebody added one to dedupe.
         */
        withToasts();

        showToast({title: 'First'});
        showToast({title: 'Second'});
        showToast({title: 'Third'});

        await waitFor(() => expect(visibleToasts()).toHaveLength(3));
        expect(screen.getByText('First')).toBeInTheDocument();
        expect(screen.getByText('Third')).toBeInTheDocument();
    });

    it('stacks two identical toasts as two', async () => {
        // Same title and description twice over: still two messages.
        withToasts();

        showToast({title: 'Download failed', description: 'HTTP 403'});
        showToast({title: 'Download failed', description: 'HTTP 403'});

        await waitFor(() => expect(visibleToasts()).toHaveLength(2));
    });

    it('holds no more than the container allows', async () => {
        // Five at once, so the sixth waits rather than the stack growing without limit.
        withToasts();

        for (let i = 1; i <= 7; i += 1) {
            showToast({title: `Toast ${i}`});
        }

        await waitFor(() => expect(visibleToasts()).toHaveLength(5));
    });

    it('clears everything on request', async () => {
        // Used when navigating away from a failed action, so its errors do not follow you.
        withToasts();
        showToast({title: 'One'});
        showToast({title: 'Two'});
        await waitFor(() => expect(visibleToasts()).toHaveLength(2));

        act(() => clearToasts());

        await waitFor(() => expect(visibleToasts()).toHaveLength(0));
    });

    it('carries the ROLE its type maps to, never a hue', async () => {
        withToasts();

        showToast({type: 'error', title: 'Download failed'});

        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        /*
         * The whole custom property, not a substring: `toContain('danger')` would also be
         * satisfied by any other declaration that happens to carry those letters.
         *
         * A hue here is the bug, not a detail.  `red` resolves per theme, but in night
         * `--yellow` and `--amber` are the same value and `--orange` is `--text`, so hue
         * names cannot keep four kinds of toast apart there.  The role can.
         */
        expect(visibleToasts()[0].getAttribute('style'))
            .toMatch(/--notification-color:\s*var\(--mantine-color-danger-/);
    });

    it('accepts `danger` as well as `error`, so new code can use the token name', async () => {
        // `error` is what 26 call sites already write; both must reach the same role.
        withToasts();

        showToast({type: 'danger', title: 'Download failed'});

        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        expect(visibleToasts()[0].getAttribute('style'))
            .toMatch(/--notification-color:\s*var\(--mantine-color-danger-/);
    });

    it('gives each type a colour of its own', async () => {
        /*
         * Four types that must not collapse into one in light and dark.  Night and amber are
         * the deliberate exception -- they have no second hue to spend -- but that is decided
         * by the token tables, not here, and here they have to differ.
         */
        withToasts();

        const colours = new Set();
        for (const type of ['info', 'success', 'warning', 'error']) {
            showToast({type, title: `A ${type}`});
        }
        await waitFor(() => expect(visibleToasts()).toHaveLength(4));
        for (const notification of visibleToasts()) {
            colours.add((notification.getAttribute('style') || '').match(/--notification-color:[^;]*/)?.[0]);
        }

        expect(colours.size).toBe(4);
    });

    it('defaults to info when given no type', async () => {
        withToasts();

        showToast({title: 'Refresh started'});

        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        expect(visibleToasts()[0].getAttribute('style'))
            .toMatch(/--notification-color:\s*var\(--mantine-color-info-/);
    });

    it('survives being called with nothing at all', () => {
        // Defensive: a call site building options from an API response can end up with none.
        withToasts();

        expect(() => showToast()).not.toThrow();
    });
});

describe('a toast that can be clicked', () => {
    /*
     * Semantic's toast took an `onClick` in its options and made the whole toast activate it.
     * `Events.js` still passes one -- it did before the migration and was never changed -- for
     * three events that each open a URL: a shared page pushed from the browser extension, a
     * finished archive upload, and a generated screenshot.  The migrated helper destructured
     * four keys and dropped the rest, so all three became dead toasts.  The first of them
     * renders the description "Click here to view the shared page", which it was not.
     */

    it('runs the handler when the toast is clicked', async () => {
        const onClick = jest.fn();
        withToasts();

        showToast({title: 'Archive Uploaded', description: 'example.com', onClick});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        await userEvent.click(screen.getByText('Archive Uploaded'));

        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('does not run the handler when the toast is dismissed', async () => {
        // The close button sits inside the toast, so its click reaches the root too.  Dismissing
        // a notification is not the same as following it, and for these three that difference is
        // a page navigation the user did not ask for.
        const onClick = jest.fn();
        withToasts();

        showToast({title: 'Archive Uploaded', onClick});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        await userEvent.click(screen.getByRole('button', {name: 'Dismiss notification'}));

        expect(onClick).not.toHaveBeenCalled();
    });

    it('can be reached and activated from the keyboard', async () => {
        // WROLPi runs on devices with a keyboard and no mouse.  A toast that only a pointer can
        // follow is a feature half the deployments cannot use.
        const onClick = jest.fn();
        withToasts();

        showToast({title: 'Screenshot Generated', onClick});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        visibleToasts()[0].focus();
        expect(visibleToasts()[0]).toHaveFocus();
        await userEvent.keyboard('{Enter}');

        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('can also be activated with Space', async () => {
        // `toast.ts` handles Enter and Space; only Enter was covered, so dropping the Space
        // branch -- or switching to `event.code` -- would have stayed green.
        const onClick = jest.fn();
        withToasts();

        showToast({title: 'Screenshot Generated', onClick});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));
        visibleToasts()[0].focus();
        await userEvent.keyboard(' ');

        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('looks clickable only when it is', async () => {
        withToasts();

        showToast({title: 'Plain'});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));

        const plain = visibleToasts()[0];
        expect(plain.style.cursor).not.toBe('pointer');
        expect(plain).not.toHaveAttribute('tabindex');
    });

    it('marks a clickable toast as clickable', async () => {
        const onClick = jest.fn();
        withToasts();

        showToast({title: 'Follow me', onClick});
        await waitFor(() => expect(visibleToasts()).toHaveLength(1));

        expect(visibleToasts()[0].style.cursor).toBe('pointer');
        expect(visibleToasts()[0]).toHaveAttribute('tabindex', '0');
    });
});

describe('how long a toast stays up', () => {
    /*
     * Real timers, with short durations chosen by the caller.
     *
     * Fake timers do not work here.  Hiding a notification runs an exit transition -- a timer
     * plus a state update plus a transition end -- and advancing the clock, even awaited inside
     * `act`, never gets the element removed from the DOM.  Both the assertion and its control
     * then read the same whatever the code does, which is a test that cannot fail.  It read
     * green against a deliberately planted `autoClose: 0` before this was rewritten.
     */

    it('goes away on its own', async () => {
        withToasts();
        showToast({title: 'Saved', time: 60});

        await waitFor(() => expect(screen.queryByText('Saved')).not.toBeInTheDocument());
    });

    /*
     * The dismissal deadline `toast()` hands Mantine, read back off its store.
     *
     * Waiting is no good for this.  Sleeping 150ms and finding the toast still there catches
     * "vanishes on the next tick" and nothing else -- it passes just as happily for a 200ms
     * default, a 1000ms one, `false`, or Mantine's own container default of 4000ms.  Waiting
     * the full five seconds instead would put five seconds into every run.  The store holds
     * exactly what was passed, which is the thing worth asserting.
     */
    const autoCloseOf = (options) => {
        showToast(options);
        const [notification] = notificationsStore.getState().notifications;
        return notification.autoClose;
    };

    it('gives a toast five seconds when the caller names no time', () => {
        withToasts();

        expect(autoCloseOf({title: 'Refresh started'})).toBe(5000);
    });

    it('passes a time the caller chose straight through', () => {
        withToasts();

        expect(autoCloseOf({title: 'Brief', time: 250})).toBe(250);
    });

    it('turns time 0 into no deadline at all', () => {
        // Not 0.  Mantine reads a number as a delay, so a literal 0 dismisses on the next tick.
        withToasts();

        expect(autoCloseOf({title: 'Download failed', time: 0})).toBe(false);
    });

    it('stays until dismissed when the caller asks for time 0', async () => {
        /*
         * Semantic treated `time: 0` as "stay up".  Mantine wants `autoClose: false`: its
         * `getAutoClose` returns any number as given, and the container then calls
         * `setTimeout(hide, 0)` -- so passing the 0 straight through dismisses the toast on the
         * next tick.  Call sites use 0 for errors the user must actually see, so getting this
         * backwards would throw away precisely the messages that matter most.
         *
         * A toast that expires normally goes up alongside it as a control.  Waiting for that one
         * to disappear proves dismissal is working, which is what makes the survivor a fact
         * about `time: 0` rather than about how long the test happened to wait.
         */
        withToasts();
        showToast({title: 'Expires normally', time: 60});
        showToast({title: 'Download failed', time: 0});

        await waitFor(() => expect(screen.queryByText('Expires normally')).not.toBeInTheDocument());

        expect(screen.getByText('Download failed')).toBeInTheDocument();
    });
});
