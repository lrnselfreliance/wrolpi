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
// react-router v7 ships these directly; `react-router-dom` is not installed.
import {MemoryRouter, Route, Routes} from "react-router";
import {QueryProvider} from "../../src/hooks/customHooks";
import {TagsProvider} from "../../src/Tags";
import {MantineProvider} from "@mantine/core";
import {cssVariablesResolver, mantineTheme} from "../../src/themes/mantine";
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
