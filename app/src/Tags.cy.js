import React from "react";
import {TagsDashboard} from "./Tags";

// Mock data for tags

describe('Tags', () => {
    beforeEach(() => {
        cy.mountWithTags(<TagsDashboard/>, {});
    });

    it('Tags Dashboard displays Tags.', () => {
        cy.wait('@getTags');
        cy.get('div.ui.label.large').contains('Automotive').should('be.visible');
    });
});
