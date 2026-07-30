import {settingsFixture, statusFixture} from '../../../src/test-fixtures';

describe('Download Window Settings', () => {

    beforeEach(() => {
        cy.intercept('GET', '/api/status', {statusCode: 200, body: statusFixture()}).as('getStatus');

        cy.intercept('GET', '/api/tags', {
            statusCode: 200,
            body: {tags: []}
        }).as('getTags');

        cy.intercept('GET', '/api/events', {
            statusCode: 200,
            body: {events: []}
        }).as('getEvents');

        cy.intercept('POST', '/api/search/suggestions', {
            statusCode: 200,
            body: {fileGroups: 0, zimsEstimates: [], channels: [], domains: []}
        }).as('getSuggestions');
    });

    it('time inputs are empty when no window is configured', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: settingsFixture(),
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').should('have.length', 2);
        cy.get('input[type="time"]').first().should('have.value', '');
        cy.get('input[type="time"]').last().should('have.value', '');
    });

    it('displays saved download window values from API', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {
                ...settingsFixture(),
                download_window_start: '08:00',
                download_window_end: '17:00',
            },
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').should('have.length', 2);
        cy.get('input[type="time"]').first().should('have.value', '08:00');
        cy.get('input[type="time"]').last().should('have.value', '17:00');
    });

    it('can set download window values', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: settingsFixture(),
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').first().type('08:00');
        cy.get('input[type="time"]').first().should('have.value', '08:00');

        cy.get('input[type="time"]').last().type('17:00');
        cy.get('input[type="time"]').last().should('have.value', '17:00');
    });

    it('displays overnight window values from API', () => {
        cy.intercept('GET', '/api/settings', {
            statusCode: 200,
            body: {
                ...settingsFixture(),
                download_window_start: '22:00',
                download_window_end: '06:00',
            },
        }).as('getSettings');

        cy.visit('/admin/settings');
        cy.wait('@getSettings');

        cy.get('input[type="time"]').first().should('have.value', '22:00');
        cy.get('input[type="time"]').last().should('have.value', '06:00');
    });
});
