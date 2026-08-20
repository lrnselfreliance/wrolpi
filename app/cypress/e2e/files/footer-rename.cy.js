/*
 * The Rename button in the FileBrowser's sticky footer, exercised against the live stack.
 *
 * No API mocking: the fb:* tasks (cypress.config.js) seed real files into the media
 * directory's `cypress-fb/` sandbox, the UI renames them through the real API, and the
 * assertions check the disk as well as the table.  The browse endpoint lists the real
 * filesystem, so seeded files appear without waiting for any refresh/indexing.
 */
import {
    assertWROLModeOff,
    deselectRow,
    dialog,
    footerButton,
    row,
    selectRow,
    setupFileBrowser,
    teardownFileBrowser,
} from '../../support/file-browser';

// Requires the full stack (API + real media directory); CI runs only the React dev server.
(Cypress.env('CI') ? describe.skip : describe)('FileBrowser footer: Rename', () => {

    // Distinctive names so cy.contains cannot match the shared fixtures in the media directory.
    const seedFiles = {
        'fb-notes.txt': 'rename me',
        'fb-other.txt': 'leave me alone',
        'fb-alpha/fb-one.txt': 'child one',
        'fb-alpha/fb-two.txt': 'child two',
    };

    before(assertWROLModeOff);

    beforeEach(() => setupFileBrowser(seedFiles, 'fb-notes.txt'));

    after(teardownFileBrowser);

    it('is enabled only when exactly one row is selected', () => {
        footerButton('Rename').should('be.disabled');

        selectRow('fb-notes.txt');
        footerButton('Rename').should('be.enabled');

        selectRow('fb-other.txt');
        footerButton('Rename').should('be.disabled');

        deselectRow('fb-other.txt');
        footerButton('Rename').should('be.enabled');
    });

    it('opens prefilled, only enables Rename once the name changes, and Reset restores it', () => {
        selectRow('fb-notes.txt');
        footerButton('Rename').click();

        dialog().should('be.visible').within(() => {
            cy.contains('Rename: fb-notes.txt');
            cy.get('input').should('have.value', 'fb-notes.txt');
            // The preview shows where the renamed file will live.
            cy.get('pre').should('contain.text', 'cypress-fb/fb-notes.txt');

            cy.contains('button', 'Rename').should('be.disabled');
            cy.get('input').type('2');
            cy.contains('button', 'Rename').should('be.enabled');
            cy.get('pre').should('contain.text', 'cypress-fb/fb-notes.txt2');

            cy.contains('button', 'Reset').click();
            cy.get('input').should('have.value', 'fb-notes.txt');
            cy.contains('button', 'Rename').should('be.disabled');
        });

        // Escape closes the modal without renaming anything.
        cy.get('body').type('{esc}');
        dialog().should('not.exist');
        cy.task('fb:exists', 'fb-notes.txt').should('be.true');
    });

    // A rename queues a refresh of the parent directory AFTER responding.  Events carry no
    // job id, so a test must not leave that refresh in flight: the next test's own refresh
    // wait could be satisfied by this straggler while the DB still reflects the old tree.
    const drainQueuedRefresh = (act) => {
        cy.serverNow().then((since) => {
            act();
            cy.waitForEvent({since, event: 'directory_refresh', message: 'Refreshed: cypress-fb'});
        });
    };

    it('renames a file on disk', () => {
        selectRow('fb-notes.txt');
        footerButton('Rename').click();

        drainQueuedRefresh(() => {
            dialog().within(() => {
                cy.get('input').clear().type('fb-renamed.txt');
                cy.contains('button', 'Rename').click();
            });

            dialog().should('not.exist');
            row('fb-renamed.txt').should('be.visible');
            cy.contains('tr', 'fb-notes.txt').should('not.exist');

            cy.task('fb:exists', 'fb-renamed.txt').should('be.true');
            cy.task('fb:exists', 'fb-notes.txt').should('be.false');
            // The neighboring file was not touched.
            cy.task('fb:exists', 'fb-other.txt').should('be.true');
        });
    });

    it('renames a directory and its children move with it on disk', () => {
        selectRow('fb-alpha');
        footerButton('Rename').click();

        drainQueuedRefresh(() => {
            dialog().within(() => {
                cy.get('input').clear().type('fb-alpha-renamed');
                cy.contains('button', 'Rename').click();
            });

            // A directory rename runs as a file-worker move job; the modal stays open until
            // the job finishes, which takes longer than the default timeout.
            cy.get('[role="dialog"]', {timeout: 30000}).should('not.exist');
            row('fb-alpha-renamed').should('be.visible');
            // The folder row's text is just the name, so anchoring excludes 'fb-alpha-renamed'.
            cy.contains('tr', /fb-alpha$/).should('not.exist');

            cy.task('fb:readdir', 'fb-alpha-renamed')
                .should('deep.equal', ['fb-one.txt', 'fb-two.txt']);
            cy.task('fb:exists', 'fb-alpha').should('be.false');
        });
    });
});
