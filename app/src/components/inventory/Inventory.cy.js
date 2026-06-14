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
        // The page loads every inventory in full from one endpoint.
        cy.intercept('GET', '**/api/inventory', {statusCode: 200, body: {inventories: [FOOD_STORAGE]}})
            .as('getInventories');
    });

    it('renders an inventory with its items', () => {
        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        cy.contains('Food Storage').should('be.visible');
        cy.contains('Salt').should('be.visible');
        cy.get('input[name="name"]').should('exist');  // the spreadsheet add row
    });

    it('persists a new item with a whole-inventory PUT', () => {
        cy.intercept('PUT', '**/api/inventory/food-storage', (req) => {
            req.reply({statusCode: 200, body: {inventory: {...FOOD_STORAGE, version: 2, items: req.body.items}}});
        }).as('saveInventory');

        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        cy.get('input[name="name"]').last().type('Rice{enter}');
        cy.wait('@saveInventory').its('request.body.items').should('have.length', 2);
    });

    it('switches to the summary tab', () => {
        cy.mountWithTags(<InventoryRoute/>, {initialEntries: ['/inventory']});
        cy.wait('@getInventories');

        cy.contains('Summary').click();
        cy.contains('Group by').should('be.visible');
    });
});
