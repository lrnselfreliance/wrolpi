import React from "react";
import {TagsDashboard} from "./Tags";

// Mock data for tags

describe('Tags', () => {
    beforeEach(() => {
        cy.mountWithTags(<TagsDashboard/>, {});
    });

    it('Tags Dashboard displays Tags.', () => {
        cy.wait('@getTags');
        // `.wrolpi-tag` is what a tag chip is now.  `div.ui.label.large` named the old
        // framework's markup, and has matched nothing since its stylesheet stopped loading.
        cy.get('.wrolpi-tag').contains('Automotive').should('be.visible');
    });
});
