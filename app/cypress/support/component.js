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
import 'semantic-ui-offline/semantic.min.css';
import {MemoryRouter, Route, Routes} from "react-router-dom";
import {QueryProvider} from "../../src/hooks/customHooks";
import {TagsProvider} from "../../src/Tags";
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
    return cy.mount(
        <MemoryRouter initialEntries={initialEntries}>
            <QueryProvider>
                <Routes>
                    <Route path='/videos/channels/new' element={component}/>
                    <Route path='/videos/channels/:channelId' element={component}/>
                    <Route path='*' element={component}/>
                </Routes>
            </QueryProvider>
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
