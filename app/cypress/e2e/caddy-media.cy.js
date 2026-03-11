// These tests require Caddy (not available in CI where only React dev server runs)
(Cypress.env('CI') ? describe.skip : describe)('Caddy Media Serving Tests', () => {

    describe('/media/ Content-Disposition inline', () => {
        it('sets Content-Disposition inline on /media/ file requests', () => {
            cy.request('GET', '/media/config/wrolpi.yaml').then((response) => {
                expect(response.status).to.eq(200);
                expect(response.headers['content-disposition']).to.contain('inline');
            });
        });

        it('serves .yaml files with text/yaml Content-Type', () => {
            cy.request('GET', '/media/config/wrolpi.yaml').then((response) => {
                expect(response.status).to.eq(200);
                expect(response.headers['content-type']).to.contain('text/yaml');
            });
        });
    });

    describe('/download/ Content-Disposition attachment', () => {
        it('sets Content-Disposition attachment on /download/ file requests', () => {
            cy.request('GET', '/download/config/wrolpi.yaml').then((response) => {
                expect(response.status).to.eq(200);
                expect(response.headers['content-disposition']).to.contain('attachment');
            });
        });
    });
});
