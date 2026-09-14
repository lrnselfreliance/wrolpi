describe('Speed Test calculator', () => {
    beforeEach(() => {
        // The byte streams themselves are not worth driving from Cypress; this is a render
        // smoke test.  Mock the endpoints the page calls on load so it renders without an API.
        cy.intercept('GET', '/api/status', {statusCode: 200, body: {version: '1.0.0', flags: {}}}).as('getStatus');
        cy.intercept('GET', '/api/settings', {statusCode: 200, body: {settings: {}}}).as('getSettings');
        cy.intercept('GET', '/api/tag*', {statusCode: 200, body: {tags: []}});
        cy.intercept('GET', '/api/events/feed*', {statusCode: 200, body: {events: []}});
    });

    it('is listed under Tools & Reference and renders idle', () => {
        cy.visit('/more/calculators');
        cy.contains('h3', 'Tools & Reference').should('be.visible');
        cy.contains('a', 'Speed Test').click();
        cy.url().should('include', 'calc=speedtest');
        cy.contains('button', 'Start test').should('be.visible');
        cy.get('[data-testid="speedtest-phase"]').should('contain', 'Ready');
        cy.get('[data-testid="speedtest-results"]').should('not.exist');
    });
});
