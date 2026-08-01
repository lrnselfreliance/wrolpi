// ***********************************************************
// This example support/component.js is processed and
// loaded automatically before your test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
//
// You can read more here:
// https://on.cypress.io/configuration
// ***********************************************************

import './commands'
// Component tests mount real components, so they need the same styles the app loads.
import '../../src/index.css';
import '../../src/themes/fonts.css';
import '../../src/themes/tokens.css';
import '@mantine/core/styles.css';
// App.js loads this too.  Without it a Notification renders unstyled here, so a toast had no
// surface and no title colour of Mantine's -- and its contrast test could not fail.
import '@mantine/notifications/styles.css';
// react-router v7 ships these directly; `react-router-dom` is not installed.
import {MemoryRouter, Route, Routes} from "react-router";
import {QueryProvider} from "../../src/hooks/customHooks";
import {TagsProvider} from "../../src/Tags";
import {MantineProvider} from "@mantine/core";
import {cssVariablesResolver, mantineTheme} from "../../src/themes/mantine";
import {isDarkTheme} from "../../src/themes/names";
import {MediaFilterDefs} from "../../src/themes/MediaFilterDefs";
import React from "react";

Cypress.on('uncaught:exception', (err, runnable) => {
    if (err.message.includes('ChunkLoadError')) {
        return false; // Ignore this error which happens after CircleCI tests.
    }
    // Otherwise, fail like normal
    return true;
});

Cypress.Commands.add('mountWithRouter', (component, options) => {
    options = options || {};
    const initialEntries = options?.initialEntries || ['/'];
    /*
     * MantineProvider, configured exactly as ThemeProvider configures it.  Every component
     * in src/components/ui renders Mantine internals and throws without it -- the same
     * thing that had to be added to test-utils.js for jest.
     */
    return cy.mount(
        <MemoryRouter initialEntries={initialEntries}>
            <MantineProvider theme={mantineTheme} cssVariablesResolver={cssVariablesResolver}>
            <QueryProvider>
                <Routes>
                    <Route path='/videos/channels/new' element={component}/>
                    <Route path='/videos/channel/:channelId/edit' element={component}/>
                    <Route path='/videos/channels/:channelId' element={component}/>
                    <Route path='*' element={component}/>
                </Routes>
            </QueryProvider>
            </MantineProvider>
        </MemoryRouter>,
        options
    );
});

/*
 * Mount a component from src/components/ui with nothing but Mantine's provider and the
 * theme stamped on <html> -- no router, no query client, no tag fixtures.
 *
 * That spartan setup is the whole point.  These components take props and read no ambient
 * state, so a real browser can render one in isolation, which is what lets a spec assert
 * things jsdom cannot compute: whether two boxes overlap, whether text is clipped, whether
 * a token actually resolved.  The Settings page shipped five unreadable inputs because
 * `padding-inline-start: auto` silently became zero, and no jsdom test could have seen it --
 * getBoundingClientRect() returns zeros there.
 *
 * `theme` stamps data-theme the way ThemeProvider does; `mediaFilter` stamps
 * data-media-filter and mounts the SVG filter definitions, since a filter referenced but
 * never defined silently does nothing.
 *
 * `forceColorScheme` matters as much as the token table, and was missing.  Mantine keys its
 * own rules on data-mantine-color-scheme, which ThemeProvider sets from the theme -- night and
 * amber ride on dark.  Without it every theme rendered against Mantine's LIGHT scheme here, so
 * a per-theme test could pass on a page that was broken in the app: the toast title, which
 * Mantine paints with `--mantine-color-white` in dark scheme only, resolved correctly by
 * accident and its contrast test could not fail.
 */
Cypress.Commands.add('mountUI', (component, options = {}) => {
    const {theme = 'light', mediaFilter, ...mountOptions} = options;

    const html = document.documentElement;
    html.dataset.theme = theme;
    if (mediaFilter) html.dataset.mediaFilter = mediaFilter;
    else delete html.dataset.mediaFilter;

    return cy.mount(
        <MantineProvider
            theme={mantineTheme}
            cssVariablesResolver={cssVariablesResolver}
            forceColorScheme={isDarkTheme(theme) ? 'dark' : 'light'}
        >
            {mediaFilter ? <MediaFilterDefs/> : null}
            {component}
        </MantineProvider>,
        mountOptions
    );
});

/**
 * Fail unless two elements are laid out side by side.
 *
 * Reads real geometry, so it catches an element painted over another regardless of how the
 * overlap came about -- an invalid length, a collapsed flex row, a stale absolute position.
 */
Cypress.Commands.add('shouldNotOverlap', {prevSubject: false}, (firstSelector, secondSelector) => {
    cy.get(firstSelector).then(($first) => {
        cy.get(secondSelector).then(($second) => {
            const a = $first[0].getBoundingClientRect();
            const b = $second[0].getBoundingClientRect();
            const overlapsHorizontally = (a.right > b.left + 0.5) && (b.right > a.left + 0.5);
            const overlapsVertically = (a.bottom > b.top + 0.5) && (b.bottom > a.top + 0.5);
            const overlaps = overlapsHorizontally && overlapsVertically;
            expect(
                overlaps,
                `${firstSelector} [${a.left}, ${a.right}] must not overlap `
                + `${secondSelector} [${b.left}, ${b.right}]`,
            ).to.equal(false);
        });
    });
});

/**
 * Contrast ratio between an element's text and the surface actually behind it, per WCAG.
 *
 * "The surface actually behind it" is the point.  A transparent element -- which is what a
 * tag becomes in night mode -- has no background of its own to compare against, so a naive
 * check reads `rgba(0,0,0,0)` and concludes anything is legible.  This walks up to the first
 * ancestor that paints something, which is what the eye sees.
 */
const parseRgb = (value) => {
    const parts = (value.match(/[\d.]+/g) || []).map(Number);
    return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
};

const relativeLuminance = ({r, g, b}) => {
    const channel = (v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
};

const effectiveBackground = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
        const bg = parseRgb(getComputedStyle(node).backgroundColor);
        if (bg.a > 0) return bg;
        node = node.parentElement;
    }
    return parseRgb(getComputedStyle(document.documentElement).backgroundColor);
};

Cypress.Commands.add('contrastRatio', {prevSubject: false}, (selector) => {
    return cy.get(selector).then(($el) => {
        const el = $el[0];
        const text = relativeLuminance(parseRgb(getComputedStyle(el).color));
        const behind = relativeLuminance(effectiveBackground(el));
        const lighter = Math.max(text, behind);
        const darker = Math.min(text, behind);
        return (lighter + 0.05) / (darker + 0.05);
    });
});

Cypress.Commands.add('mountWithTags', (component, options) => {
    cy.fixture('tagsMock.json').then((mockTags) => {
        cy.intercept('GET', '**/api/tag', {
            statusCode: 200,
            body: mockTags
        }).as('getTags');
    });
    return cy.mountWithRouter(
        <TagsProvider>
            {component}
        </TagsProvider>,
        options
    );
});
