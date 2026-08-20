/*
 * Shared helpers for the FileBrowser e2e specs (cypress/e2e/files/).
 *
 * These specs run against the live stack with real files: the fb:* tasks
 * (cypress.config.js) seed a `cypress-fb/` sandbox inside the media directory,
 * and cy.refreshFiles (support/commands.js) keeps the DB in sync with it.
 */

export const SANDBOX = 'cypress-fb';

export const footerButton = (label) => cy.get('.sticky-footer').contains('button', label);
export const row = (name) => cy.contains('tr', name);
export const selectRow = (name) => row(name).find('input[type="checkbox"]').check({force: true});
export const deselectRow = (name) => row(name).find('input[type="checkbox"]').uncheck({force: true});
export const dialog = () => cy.get('[role="dialog"]');

// WROL mode silently disables most footer buttons; fail loudly instead of reporting
// false failures.  Call once from a spec's before().
export const assertWROLModeOff = () => {
    cy.request('/api/settings').its('body.wrol_mode').then((wrolMode) => {
        expect(wrolMode, 'WROL mode must be OFF for FileBrowser e2e tests (Admin > Settings)')
            .to.be.false;
    });
};

/*
 * Seed the sandbox, sync the DB, open /files, and open the sandbox folder.
 * `firstRow` should be a seeded name that proves the folder's children rendered.
 */
export const setupFileBrowser = (seedFiles, firstRow) => {
    cy.task('fb:reset', {files: seedFiles});
    cy.refreshFiles([SANDBOX]);
    // The footer shows labeled buttons only when it is at least 1050px wide.
    cy.viewport(1280, 800);
    cy.visit('/files');
    // A fresh page load replays recent events as toasts (each test run adds more), and
    // they stack over the sticky footer, making cy.click() refuse the buttons.  These
    // specs assert on the disk and the table, not toasts, so hide the notification layer.
    cy.document().then((doc) => {
        const style = doc.createElement('style');
        style.textContent = '.mantine-Notifications-root { display: none !important; }';
        doc.head.appendChild(style);
    });
    cy.contains('.file-path', SANDBOX).click();
    row(firstRow).should('be.visible');
};

// Empty the sandbox on disk, let a refresh purge its rows from the DB, then remove the
// empty directory itself so nothing stale survives into the next run.  Call from after().
//
// The refresh is best-effort and never fails: a failed command aborts the rest of its hook,
// and the disk wipe below must always run.  The next run's setup refresh repairs the DB
// even when this purge is missed.
export const teardownFileBrowser = () => {
    cy.task('fb:reset', {files: {}});
    cy.serverNow().then((since) => {
        cy.request({
            method: 'POST',
            url: '/api/files/refresh',
            body: {paths: [SANDBOX]},
            failOnStatusCode: false,
        });
        const deadline = Date.now() + 30000;
        const poll = () => {
            cy.request({
                url: `/api/events/feed?after=${encodeURIComponent(since)}`,
                failOnStatusCode: false,
            }).then(({body}) => {
                const done = ((body && body.events) || []).some((e) =>
                    e.event === 'directory_refresh' && e.message === `Refreshed: ${SANDBOX}`);
                if (done || Date.now() > deadline) return;
                cy.wait(1000);
                poll();
            });
        };
        poll();
    });
    cy.task('fb:cleanup');
};
