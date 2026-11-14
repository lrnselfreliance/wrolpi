/*
 * The standalone map viewer (port 8084) and overlays: map files which are not a basemap.
 *
 * The standalone viewer is plain HTML with no build step; it loads copies of the map viewer's
 * overlay modules.  This runs against the live stack with a real map file: the map:* tasks write
 * a small overlay (no tiles) and a style beside it into the media directory's map directory.
 */

const VIEWER = 'https://localhost:8084/';
const LABEL = 'Cypress Overlay';

const METADATA = {
    name: LABEL,
    description: 'An overlay for the standalone viewer test',
    type: 'overlay',
    vector_layers: [
        {id: 'towers', fields: {name: 'String'}, minzoom: 0, maxzoom: 8},
        {id: 'power_lines', fields: {}, minzoom: 0, maxzoom: 8},
        {id: 'parks', fields: {}, minzoom: 0, maxzoom: 8},
    ],
    tilestats: {
        layers: [
            {layer: 'towers', geometry: 'Point', count: 1},
            {layer: 'power_lines', geometry: 'LineString', count: 1},
            {layer: 'parks', geometry: 'Polygon', count: 1},
        ],
    },
};

// Written for some other map: its own source name and URL, and one layer MapLibre cannot draw.
const STYLE = {
    version: 8,
    sources: {features: {type: 'vector', url: 'https://example.com/features.json'}},
    layers: [
        {id: 'background', type: 'background'},
        {id: 'lines', type: 'line', source: 'features', 'source-layer': 'power_lines', paint: {'line-color': '#c60'}},
        {id: 'bad', type: 'line', source: 'features', 'source-layer': 'parks', paint: {'line-width': 'wide'}},
        {
            id: 'towers', type: 'symbol', source: 'features', 'source-layer': 'towers',
            layout: {'text-field': ['get', 'name'], 'text-font': ['Roboto Bold']},
        },
    ],
};

const overlayRow = () => cy.contains('.overlay-file', LABEL);
const overlayBox = () => overlayRow().find('input[type=checkbox]');
const layerBox = (name) => cy.contains('.overlay-layer', name).find('input[type=checkbox]');
const openPanel = () => cy.get('#overlay-section', {timeout: 20000}).should('be.visible');

// Requires the full stack (API, Caddy on 8084, real media directory); CI runs only the React dev server.
(Cypress.env('CI') ? describe.skip : describe)('Standalone map viewer: overlays', () => {

    afterEach(() => {
        cy.task('map:cleanup');
    });

    it('offers an overlay by its own name, hidden, with a checkbox per layer', () => {
        cy.task('map:seed-overlay', {name: 'generic', metadata: METADATA});
        cy.visit(VIEWER);
        openPanel();

        overlayBox().should('not.be.checked');
        overlayRow().find('.overlay-zooms').should('have.text', 'z0\u20138');

        overlayRow().find('.overlay-expand').click();
        // Every layer of the file, each with the color it is drawn in.
        cy.get('.overlay-layer').should('have.length', 3);
        cy.get('.overlay-swatch').should('have.length', 3);
        // The layers cannot be chosen while the file is off.
        layerBox('towers').should('be.disabled');

        overlayBox().check();
        layerBox('towers').should('be.enabled').and('be.checked');
        layerBox('towers').uncheck();
        cy.contains('.overlay-all-none button', 'None').click();
        layerBox('power_lines').should('not.be.checked');
        cy.contains('.overlay-all-none button', 'All').click();
        layerBox('power_lines').should('be.checked');
        layerBox('towers').should('be.checked');
    });

    it('remembers what was turned on', () => {
        cy.task('map:seed-overlay', {name: 'remembered', metadata: METADATA});
        cy.visit(VIEWER);
        openPanel();
        overlayBox().check();
        overlayRow().find('.overlay-expand').click();
        layerBox('parks').uncheck();

        cy.reload();
        openPanel();
        overlayBox().should('be.checked');
        overlayRow().find('.overlay-expand').click();
        layerBox('parks').should('not.be.checked');
        layerBox('towers').should('be.checked');
    });

    it('draws an overlay with the style beside it, without the layer MapLibre refuses', () => {
        cy.intercept('GET', '**/data/cypress-map/styled.style.json').as('style');
        cy.intercept('GET', '**/sprites/overlay-icons*.json').as('icons');
        cy.task('map:seed-overlay', {name: 'styled', metadata: METADATA, style: STYLE});
        cy.visit(VIEWER);
        // The style is fetched from the map directory this viewer is served.
        cy.wait('@style').its('response.statusCode').should('eq', 200);
        openPanel();

        overlayRow().find('.overlay-expand').click();
        // Only the layers the style draws, and no generic colors.
        cy.get('.overlay-layer').should('have.length', 3);
        cy.get('.overlay-swatch').should('have.length', 0);
        // This viewer cannot check a layer before MapLibre does: the bad one is refused there.
        cy.contains('.overlay-note', '1 style layer skipped');
        // The panel is rebuilt by a change, so the checkbox is found again.
        overlayBox().check();
        overlayBox().should('be.checked');
        // A style names icons: the map's own, a sprite of this viewer's.  Its index has a name a
        // style may use for an icon, beside the icon's own.
        cy.wait('@icons').then(({response}) => {
            expect(response.statusCode).to.eq(200);
            expect(response.body).to.have.property('ham_radio');
            expect(response.body.ham_radio).to.deep.eq(response.body.antenna);
            expect(response.body.hospital.sdf).to.eq(true);
        });
    });

    it('does not offer an ignored file', () => {
        cy.task('map:seed-overlay', {name: 'ignored', metadata: METADATA}).then((mapPath) => {
            cy.request('POST', 'https://localhost:8084/api/map/files/visible', {map_path: mapPath, visible: false});
            cy.visit(VIEWER);
            cy.get('#layer-content', {timeout: 20000}).contains('Labels');
            cy.contains('.overlay-file', LABEL).should('not.exist');
            // Deleting the file forgets that it was ignored.
            cy.request('DELETE', `https://localhost:8084/api/map/files/${mapPath}`);
        });
    });
});
