/*
 * The Ignore, Upload, and Refresh buttons in the FileBrowser's sticky footer, against the
 * live stack.  Ignore/Upload only make sense with a single directory selected, so this spec
 * also carries their enable-state rules.
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
(Cypress.env('CI') ? describe.skip : describe)('FileBrowser footer: Ignore, Upload, Refresh', () => {

    const seedFiles = {
        'fb-notes.txt': 'a file',
        'fb-beta/fb-inside.txt': 'inside the directory',
    };

    const IGNORED_DIR = 'cypress-fb/fb-beta';

    before(assertWROLModeOff);

    beforeEach(() => setupFileBrowser(seedFiles, 'fb-notes.txt'));

    after(() => {
        // Un-ignore unconditionally: a failed test must not leave the sandbox in the
        // ignored_directories config (it would confuse later runs and the user's stack).
        cy.request({
            method: 'POST',
            url: '/api/files/unignore_directory',
            body: {path: `/media/wrolpi/${IGNORED_DIR}`},
            failOnStatusCode: false,
        });
        teardownFileBrowser();
    });

    // cy.task has no built-in retry; background work (uploads) lands on disk asynchronously.
    const waitForDisk = (relativePath, timeout = 30000) => {
        const deadline = Date.now() + timeout;
        const poll = () => {
            cy.task('fb:exists', relativePath).then((exists) => {
                if (exists) return;
                expect(Date.now(), `${relativePath} did not appear on disk within ${timeout}ms`)
                    .to.be.lessThan(deadline);
                cy.wait(500);
                poll();
            });
        };
        poll();
    };

    it('Upload and Ignore require a single directory selection', () => {
        // Nothing selected: Upload targets the media directory, Ignore has no directory.
        footerButton('Upload').should('be.enabled');
        footerButton('Ignore').should('be.disabled');

        selectRow('fb-notes.txt');
        footerButton('Upload').should('be.disabled');
        footerButton('Ignore').should('be.disabled');
        deselectRow('fb-notes.txt');

        selectRow('fb-beta');
        footerButton('Upload').should('be.enabled');
        footerButton('Ignore').should('be.enabled');

        selectRow('fb-notes.txt');
        footerButton('Upload').should('be.disabled');
        footerButton('Ignore').should('be.disabled');
    });

    it('ignores and un-ignores a directory through the config', () => {
        selectRow('fb-beta');
        footerButton('Ignore').click();

        dialog().should('contain.text', 'Ignore Directory')
            .should('contain.text', `/media/wrolpi/${IGNORED_DIR}`);
        dialog().contains('button', 'Ignore').click();

        // The directory lands in the settings config.
        cy.request('/api/settings').its('body.ignored_directories')
            .should('include', IGNORED_DIR);

        // With the settings reloaded the same button now offers the reverse action.
        footerButton('Unignore').should('be.enabled').click();
        dialog().should('contain.text', 'Remove Ignore Directory');
        dialog().contains('button', 'Un-ignore').click();

        cy.request('/api/settings').its('body.ignored_directories')
            .should('not.include', IGNORED_DIR);
        footerButton('Ignore').should('be.enabled');
    });

    it('uploads a file into the selected directory', () => {
        selectRow('fb-beta');
        footerButton('Upload').click();

        dialog().should('contain.text', `Upload to: /media/wrolpi/${IGNORED_DIR}`);
        dialog().find('input[type="file"]').selectFile({
            contents: Cypress.Buffer.from('uploaded by cypress'),
            fileName: 'fb-uploaded.txt',
        }, {force: true});

        waitForDisk('fb-beta/fb-uploaded.txt');
        dialog().contains('button', 'Close').click();
        dialog().should('not.exist');

        // The upload landed exactly where the selection pointed.
        cy.task('fb:readdir', 'fb-beta').should('deep.equal', ['fb-inside.txt', 'fb-uploaded.txt']);
    });

    it('Refresh with a selection runs a scoped refresh end-to-end', () => {
        // Drop a file behind the UI's back; only a refresh makes the backend index it.
        cy.task('fb:seed', {files: {'fb-sneaky.txt': 'added behind the UI'}});

        selectRow('cypress-fb');
        cy.serverNow().then((since) => {
            footerButton('Refresh').click();
            // The button's refresh is scoped to the selection -- the completion event
            // names the sandbox, a global refresh would say 'Global refresh completed'.
            cy.waitForEvent({
                since,
                event: 'directory_refresh',
                message: 'Refreshed: cypress-fb',
                timeout: 30000,
            });
        });

        // The table does NOT refetch itself after a refresh (useBrowseFiles only fetches on
        // mount and folder toggles) -- the user must reload or toggle a folder to see what
        // the refresh found.  Assert the current behavior; if this later starts auto-updating,
        // the reload can be dropped.
        // The open folders live in the ?folders= query, so the sandbox is still open
        // after the reload -- clicking it again would close it.
        cy.reload();
        row('fb-sneaky.txt').should('be.visible');
    });
});
