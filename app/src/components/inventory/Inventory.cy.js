import React from "react";
import {InventoryRoute} from "./InventoryRoute";

const FIELDS = [
    {key: 'name', label: 'Name', type: 'text', order: 0},
    {key: 'item_size', label: 'Size', type: 'quantity', unit: 'lb', order: 1},
    {key: 'count', label: 'Count', type: 'number', order: 2},
];

const FOOD_STORAGE = {
    slug: 'food-storage', name: 'Food Storage', type: 'food', version: 1, fields: FIELDS,
    items: [{id: 1, name: 'Salt', item_size: '25', item_size_unit: 'lb', count: '8'}],
};

describe('Inventory Page', () => {
    beforeEach(() => {
        /*
         * The page also loads the shared food catalog, from its own endpoint.
         *
         * Unstubbed, that fetch reached the network and rejected -- "Failed to fetch" out of
         * an effect, which Cypress counts as an uncaught application error and fails the
         * running test on, whatever it happened to be asserting.  All three tests here died
         * that way, none of them for a reason to do with their own subject.
         */
        cy.intercept('GET', '**/api/inventory/catalog', {statusCode: 200, body: {catalog: []}})
            .as('getCatalog');
        // The page loads every inventory in full from one endpoint.
        cy.intercept('GET', '**/api/inventory', {statusCode: 200, body: {inventories: [FOOD_STORAGE]}})
            .as('getInventories');
    });

    it('renders an inventory with its items', () => {
        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        /*
         * `:visible` because the page always mounts its printable copy of the inventory, a
         * `.inventory-print` block that is `display: none` on screen and becomes the only
         * visible content when the browser prints.  It carries the same headings and the
         * same item names, and `cy.contains` finds the DEEPEST match -- which was the
         * hidden `<h1>`, so the assertion was reading the print sheet and reporting that
         * the page had not rendered.
         */
        cy.contains(':visible', 'Food Storage').should('be.visible');
        cy.contains(':visible', 'Salt').should('be.visible');
        cy.get('input[name="name"]').should('exist');  // the spreadsheet add row
    });

    it('persists a new item with a whole-inventory PUT', () => {
        /*
         * The request body arrives as a JSON string, so `req.body.items` was undefined --
         * both in the reply built here, which handed the page back an inventory with no
         * items at all, and in the assertion, which waited for a property that could never
         * appear and timed out.  Parsing it once at the top makes both mean what they say.
         */
        const itemsIn = (body) => (typeof body === 'string' ? JSON.parse(body) : body).items;

        cy.intercept('PUT', '**/api/inventory/food-storage', (req) => {
            req.reply({
                statusCode: 200,
                body: {inventory: {...FOOD_STORAGE, version: 2, items: itemsIn(req.body)}},
            });
        }).as('saveInventory');

        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        cy.get('input[name="name"]').last().type('Rice{enter}');
        cy.wait('@saveInventory').its('request.body').then((body) => {
            expect(itemsIn(body), 'the existing item and the new one').to.have.length(2);
        });
    });

    it('switches to the summary tab', () => {
        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        cy.contains('Summary').click();
        cy.contains('Group by').should('be.visible');
    });
});
