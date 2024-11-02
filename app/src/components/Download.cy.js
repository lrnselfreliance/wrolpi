import React from 'react';
import {ArchiveDownloadForm, ChannelDownloadForm} from './Download';
import 'semantic-ui-offline/semantic.min.css';

describe('<ArchiveDownloadForm />', () => {
    beforeEach(() => {
        cy.mountWithTags(<ArchiveDownloadForm/>);
    });

    it('displays error for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');
    });

    it('enables download button for valid URL', () => {
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        cy.get('#urls_textarea').should('not.have.attr', 'error');
        cy.get('#download_form_download_button').should('be.visible').and('not.have.attr', 'disabled');
    });

    it('disables download button for invalid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('initially has download button disabled', () => {
        cy.get('#download_form_download_button').should('be.visible').and('have.attr', 'disabled');
    });

    it('clears error when switching from invalid to valid URL', () => {
        cy.get('#urls_textarea').type('invalid-url').wait(500);
        cy.get('#urls_textarea').should('have.attr', 'error');

        cy.get('#urls_textarea').clear();
        cy.get('#urls_textarea').type('https://wrolpi.org').wait(500);
        cy.get('#urls_textarea').should('not.have.attr', 'error');
    });
});

describe('<ChannelDownloadForm/>', () => {
    beforeEach(() => {
        // Do not return directories for these tests.
        cy.intercept('POST', '**/api/files/search_directories', {
            statusCode: 200,
            body: {
                is_dir: true, channel_directories: [], domain_directories: [],
                directories: [{path: "some directory", name: "some directory"}],
            },
        }).as('searchDirectories');

        cy.mountWithTags(<ChannelDownloadForm/>);
    });

    it('displays error for invalid URL', () => {
        cy.get('#url_input').type('invalid-url').wait(500);
        cy.get('#url_input').should('have.attr', 'error');
    });

    it('Can choose different options', () => {
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('Once').click();
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('Daily').click();
        cy.get('#download_frequency_selector').click()
            .get('.item').contains('180 Days').click();
    });
});
