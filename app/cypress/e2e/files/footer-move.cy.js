/*
 * The Move button in the FileBrowser's sticky footer, exercised against the live stack.
 *
 * Real files: the fb:* tasks seed a `cypress-fb/` sandbox in the media directory and the
 * UI moves them through the real API.  Unlike rename, POST /api/files/move only QUEUES a
 * background job and returns immediately -- the modal closes before anything moved -- so
 * each move waits on the `file_move_completed` event before asserting the disk.
 */
import {
    assertWROLModeOff,
    dialog,
    footerButton,
    row,
    selectRow,
    setupFileBrowser,
    teardownFileBrowser,
} from '../../support/file-browser';

// Requires the full stack (API + real media directory); CI runs only the React dev server.
(Cypress.env('CI') ? describe.skip : describe)('FileBrowser footer: Move', () => {

    const seedFiles = {
        'fb-notes.txt': 'move me',
        'fb-other.txt': 'leave me alone',
        'fb-alpha/fb-one.txt': 'child one',
        'fb-alpha/fb-two.txt': 'child two',
        'fb-beta/': null,
    };

    before(assertWROLModeOff);

    beforeEach(() => setupFileBrowser(seedFiles, 'fb-notes.txt'));

    after(teardownFileBrowser);

    // Type a destination into the MoveModal's DirectorySearch and pick it from the results.
    const chooseDestination = (destination) => {
        dialog().find('.wrolpi-searchbox-input').type(destination);
        dialog().find('[role="listbox"] [role="option"]')
            .contains('.wrolpi-searchbox-result-title', destination)
            .click();
    };

    // Start the clock, run the move via `act`, then wait for the background job to finish.
    const moveAndWait = (act) => {
        cy.serverNow().then((since) => {
            act();
            dialog().should('not.exist');
            cy.waitForEvent({
                since,
                event: 'file_move_completed',
                failureEvent: 'file_move_failed',
                timeout: 30000,
            });
        });
    };

    it('is enabled for any selection, disabled for none', () => {
        footerButton('Move').should('be.disabled');
        selectRow('fb-notes.txt');
        footerButton('Move').should('be.enabled');
        selectRow('fb-other.txt');
        footerButton('Move').should('be.enabled');
    });

    it('moves one file into a sibling directory on disk', () => {
        selectRow('fb-notes.txt');
        footerButton('Move').click();

        dialog().should('be.visible').within(() => {
            // The source column lists the path being moved.
            cy.contains('pre', 'cypress-fb/fb-notes.txt');
        });
        chooseDestination('cypress-fb/fb-beta');
        // The destination column previews where the file will land.
        dialog().contains('pre', 'cypress-fb/fb-beta/fb-notes.txt');

        moveAndWait(() => dialog().contains('button', 'Move').click());

        cy.task('fb:exists', 'fb-beta/fb-notes.txt').should('be.true');
        cy.task('fb:exists', 'fb-notes.txt').should('be.false');
        cy.task('fb:exists', 'fb-other.txt').should('be.true');

        // The table catches up: the file now lists under fb-beta.
        cy.reload();
        cy.contains('.file-path', 'fb-beta').click();
        row('fb-notes.txt').should('be.visible');
    });

    it('moves several selected files in one operation', () => {
        cy.contains('.file-path', 'fb-alpha').click();
        row('fb-one.txt').should('be.visible');
        selectRow('fb-one.txt');
        selectRow('fb-two.txt');

        footerButton('Move').click();
        dialog().within(() => {
            cy.contains('pre', 'cypress-fb/fb-alpha/fb-one.txt');
            cy.contains('pre', 'cypress-fb/fb-alpha/fb-two.txt');
        });
        chooseDestination('cypress-fb/fb-beta');

        moveAndWait(() => dialog().contains('button', 'Move').click());

        cy.task('fb:readdir', 'fb-beta').should('deep.equal', ['fb-one.txt', 'fb-two.txt']);
        cy.task('fb:readdir', 'fb-alpha').should('deep.equal', []);
    });

    it('Reset clears the chosen destination, and closing moves nothing', () => {
        selectRow('fb-notes.txt');
        footerButton('Move').click();

        chooseDestination('cypress-fb/fb-beta');
        dialog().contains('pre', 'cypress-fb/fb-beta/fb-notes.txt');

        dialog().contains('button', 'Reset').click();
        // Without a destination the second column falls back to the bare file name.
        dialog().contains('pre', 'cypress-fb/fb-beta/fb-notes.txt').should('not.exist');

        cy.get('body').type('{esc}');
        dialog().should('not.exist');
        cy.task('fb:exists', 'fb-notes.txt').should('be.true');
        cy.task('fb:exists', 'fb-beta/fb-notes.txt').should('be.false');
    });
});
