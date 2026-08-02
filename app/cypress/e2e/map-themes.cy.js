import {mapSprite, themeNames, themeSessionKey} from '../../src/themes/names';

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
 *
 * `themeNames` rather than a list written out here, so a fifth theme is cold-started by this
 * suite the day it is added rather than the day someone remembers to edit it.
 */

describe('the map viewer builds a basemap in every theme', () => {
    themeNames.forEach((theme) => {
        it(`initialises MapLibre in ${theme}`, () => {
            const errors = [];
            /*
             * The sprite is the half no canvas assertion can see: a wrong sprite name 404s
             * the icons and MapLibre carries on, so the map still draws and this test would
             * still pass.  Watching the request is the only way to tell `sprites/dark` from
             * `sprites/black` -- and `black` is exactly the name that would be requested if
             * the flavor and the sprite were ever collapsed back into one variable.
             */
            cy.intercept('GET', '**/map-assets/sprites/**').as('sprite');

            cy.visit('/map', {
                onBeforeLoad(win) {
                    // Set the theme before the app boots, so the viewer builds its style once
                    // with the theme under test rather than rebuilding after a switch.
                    win.localStorage.setItem(themeSessionKey, theme);
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

            cy.wait('@sprite', {timeout: 40000}).then(({request}) => {
                const name = request.url
                    .split('/map-assets/sprites/')[1]
                    .replace(/[?#].*$/, '')
                    .replace(/\.(json|png)$/, '')
                    .replace('@2x', '');
                expect(name, `sprite set requested in ${theme}`).to.equal(mapSprite(theme));
            });

            cy.then(() => {
                const failures = errors.filter(message =>
                    /MapLibre failed to initialize|reading 'background'/.test(message));
                expect(failures.join('\n')).to.equal('');
            });
        });
    });
});
