import {mount} from 'cypress/react'

// Cypress 14 dropped the separate cypress/react18 entry point; cypress/react mounts React 18 itself.
Cypress.Commands.add('mount', mount);

/*
 * Waiting on WROLPi background work.
 *
 * Most mutating file endpoints only QUEUE a job for the background file worker (move, refresh),
 * and /api/files/worker_status reads 'idle' while jobs are still waiting in its queue, so
 * neither the response nor the status endpoint says anything about completion.  The reliable
 * signal is the completion event on /api/events/feed.  The pattern: capture the server's clock
 * BEFORE starting the work, then poll the feed for a matching event newer than that timestamp.
 *
 * If the timeout expires the test FAILS -- historically that has meant the file worker was
 * wedged and the api service needed a restart (fixed since, but fail loudly regardless).
 */

// The API decides what time it is (the frontend does the same, in case of clock drift).
Cypress.Commands.add('serverNow', () =>
    cy.request('/api/events/feed').its('body.now'));

/*
 * cy.waitForEvent({since, event, message?, messagePrefix?, failureEvent?, timeout?})
 *
 * Poll the events feed until an event newer than `since` matches.  `event` is a name or a
 * list of names; narrow further with an exact `message` or a `messagePrefix`.  If a
 * `failureEvent` (name or list) shows up first, fail immediately with its message instead
 * of timing out.
 *
 *   cy.serverNow().then((since) => {
 *       // ...start the background work...
 *       cy.waitForEvent({since, event: 'file_move_completed', failureEvent: 'file_move_failed'});
 *   });
 */
Cypress.Commands.add('waitForEvent', ({since, event, message, messagePrefix, failureEvent, timeout = 60000}) => {
    const wanted = [].concat(event);
    const failures = failureEvent ? [].concat(failureEvent) : [];
    const matches = (e) => {
        if (!wanted.includes(e.event)) return false;
        if (message) return e.message === message;
        if (messagePrefix) return (e.message || '').startsWith(messagePrefix);
        return true;
    };

    const deadline = Date.now() + timeout;
    const poll = () => {
        cy.request(`/api/events/feed?after=${encodeURIComponent(since)}`).then(({body}) => {
            const events = body.events || [];
            const failed = events.find((e) => failures.includes(e.event));
            expect(failed, failed && `${failed.event}: ${failed.message}`).to.be.undefined;
            if (events.some(matches)) return;
            expect(Date.now(), `event '${wanted}' not seen within ${timeout}ms -- `
                + 'the file worker may be wedged (restart the api service)').to.be.lessThan(deadline);
            cy.wait(1000);
            poll();
        });
    };
    poll();
});

/*
 * cy.refreshFiles(paths, options) -- refresh files on the live stack and wait for completion.
 *
 *   cy.refreshFiles(['cypress-fb']);                  // refresh one directory
 *   cy.refreshFiles([], {timeout: 300000});           // global refresh, longer timeout
 */
Cypress.Commands.add('refreshFiles', (paths = [], {timeout = 60000} = {}) => {
    // Refresh-completed event names, by scope (wrolpi/files/worker.py).
    const completionEvents = ['directory_refresh', 'files_refreshed', 'global_after_refresh_completed'];
    // A single directory announces itself by name; match exactly so another test's refresh
    // finishing at the same moment cannot satisfy this wait.
    const singleDirectory = paths.length === 1 && !/\.[^/]+$/.test(paths[0]);
    const message = singleDirectory ? `Refreshed: ${paths[0].replace(/\/$/, '')}` : undefined;

    cy.serverNow().then((since) => {
        const body = paths.length ? {paths} : undefined;
        cy.request('POST', '/api/files/refresh', body);
        cy.waitForEvent({since, event: completionEvents, message, timeout});
    });
});
