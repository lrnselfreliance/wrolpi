/*
 * The Delete button in the FileBrowser's sticky footer, exercised against the live stack.
 *
 * Real files: the fb:* tasks seed a `cypress-fb/` sandbox in the media directory and the UI
 * deletes them through the real API (POST /api/files/delete runs synchronously).  Deleting a
 * TAGGED file is refused with FILE_GROUP_IS_TAGGED, which opens a second confirmation listing
 * the tagged files; confirming there force-deletes.
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
(Cypress.env('CI') ? describe.skip : describe)('FileBrowser footer: Delete', () => {

    const seedFiles = {
        'fb-notes.txt': 'delete me',
        'fb-other.txt': 'leave me alone',
        'fb-alpha/fb-one.txt': 'child one',
        'fb-alpha/fb-two.txt': 'child two',
        'fb-tagged.txt': 'tagged, delete needs force',
    };

    const TAG_NAME = 'CypressFBDelete';

    // Remove the suite's tag wherever a failed run may have left it, along with the
    // tags/<TAG_NAME>/ directory: force-deleting a tagged file strands its hardlink there.
    const deleteTestTag = () => {
        cy.request('/api/tag').its('body.tags').then((tags) => {
            const tag = tags.find((t) => t.name === TAG_NAME);
            if (tag) {
                cy.request('DELETE', `/api/tag/${tag.id}`);
            }
        });
        cy.task('fb:cleanup-tag-dir', TAG_NAME);
    };

    before(() => {
        assertWROLModeOff();
        deleteTestTag();
    });

    beforeEach(() => setupFileBrowser(seedFiles, 'fb-notes.txt'));

    after(() => {
        deleteTestTag();
        teardownFileBrowser();
    });

    // The footer Delete goes through APIButton's confirmation first.
    const confirmDialog = () => {
        dialog().should('be.visible')
            .should('contain.text', 'Are you sure you want to delete these files?');
        return dialog();
    };

    it('cancelling the confirmation deletes nothing', () => {
        selectRow('fb-notes.txt');
        footerButton('Delete').click();

        confirmDialog().contains('button', 'Cancel').click();
        dialog().should('not.exist');

        row('fb-notes.txt').should('be.visible');
        cy.task('fb:exists', 'fb-notes.txt').should('be.true');
    });

    it('deletes one file from disk', () => {
        selectRow('fb-notes.txt');
        footerButton('Delete').click();
        confirmDialog().contains('button', 'Delete').click();

        cy.contains('tr', 'fb-notes.txt').should('not.exist');
        cy.task('fb:exists', 'fb-notes.txt').should('be.false');
        cy.task('fb:exists', 'fb-other.txt').should('be.true');
    });

    it('deletes an open directory recursively without breaking the table', () => {
        // Open the folder first so it is in openFolders; deleting it must also prune it
        // from openFolders or the next fetch requests a directory that no longer exists.
        cy.contains('.file-path', 'fb-alpha').click();
        row('fb-one.txt').should('be.visible');

        selectRow('fb-alpha');
        footerButton('Delete').click();
        confirmDialog().contains('button', 'Delete').click();

        cy.contains('tr', /fb-alpha$/).should('not.exist');
        cy.task('fb:exists', 'fb-alpha').should('be.false');

        // The table still renders the remaining files -- no failed re-fetch.
        row('fb-other.txt').should('be.visible');
    });

    it('a tagged file needs the second, force-delete confirmation', () => {
        // Tag the file through the real API; the FileGroup exists because setup refreshed.
        cy.request('POST', '/api/tag', {name: TAG_NAME, color: '#ff0000'});
        cy.request('POST', '/api/files/tag', {
            tag_name: TAG_NAME,
            file_group_primary_path: 'cypress-fb/fb-tagged.txt',
        });

        // First attempt: cancel at the tagged-files warning; nothing is deleted.
        selectRow('fb-tagged.txt');
        footerButton('Delete').click();
        confirmDialog().contains('button', 'Delete').click();

        dialog().should('contain.text', 'Tagged Files Will Be Deleted')
            .should('contain.text', 'cypress-fb/fb-tagged.txt')
            .should('contain.text', TAG_NAME);
        dialog().contains('button', 'Cancel').click();
        dialog().should('not.exist');
        cy.task('fb:exists', 'fb-tagged.txt').should('be.true');

        // Second attempt: confirm the warning; the file is force-deleted.
        footerButton('Delete').click();
        confirmDialog().contains('button', 'Delete').click();
        dialog().should('contain.text', 'Tagged Files Will Be Deleted');
        dialog().contains('button', 'Delete').click();

        cy.contains('tr', 'fb-tagged.txt').should('not.exist');
        cy.task('fb:exists', 'fb-tagged.txt').should('be.false');
    });
});
