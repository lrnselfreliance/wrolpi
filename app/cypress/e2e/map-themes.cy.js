/*
 * The map basemap has a "flavor" of its own, and MapViewer used to hand protomaps the WROLPi
 * theme name.  That worked while the only themes were `light` and `dark`, and broke when
 * night and amber arrived: protomaps looks the flavor up in a record and dereferences the
 * result without checking, so an unknown name throws
 * `Cannot read properties of undefined (reading 'background')` before the first tile and the
 * viewer renders nothing at all.
 *
 * Driven through the real page in every theme, because the unit test can only check that the
 * mapping returns something valid -- it cannot see whether MapViewer USES it, which is the
 * half that was broken.
 */
const THEMES = ['light', 'dark', 'night', 'amber'];

describe('the map viewer builds a basemap in every theme', () => {
    THEMES.forEach((theme) => {
        it(`initialises MapLibre in ${theme}`, () => {
            const errors = [];
            cy.visit('/map', {
                onBeforeLoad(win) {
                    // Set the theme before the app boots, so the viewer builds its style once
                    // with the theme under test rather than rebuilding after a switch.
                    win.localStorage.setItem('color-scheme', theme);
                    // MapViewer reports a failed init through console.error and then renders
                    // nothing, so the console is where the defect is visible.
                    const original = win.console.error;
                    win.console.error = (...args) => {
                        errors.push(args.map(String).join(' '));
                        original(...args);
                    };
                },
            });

            // The canvas only exists once MapLibre constructed a style successfully.
            cy.get('canvas.maplibregl-canvas', {timeout: 40000}).should('exist');

            cy.then(() => {
                const failures = errors.filter(message =>
                    /MapLibre failed to initialize|reading 'background'/.test(message));
                expect(failures.join('\n')).to.equal('');
            });
        });
    });
});
