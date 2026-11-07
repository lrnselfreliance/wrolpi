/*
 * Previewing STL files, exercised against the live stack in a real browser (WebGL).
 *
 * An STL is either ASCII text or binary.  Both must load in the preview: the dimensions line
 * is only shown after the model has been parsed and framed, and a load failure is shown as an
 * error (or thrown, which fails the test).
 */
import {assertWROLModeOff, SANDBOX, teardownFileBrowser} from '../../support/file-browser';

// One right triangle, legs of 2 along X and 1 along Y.
const ASCII_STL = `solid ASCII
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 2 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid
`;

function binaryStlBase64() {
    // 80-byte header, uint32 triangle count, then one 50-byte triangle: normal, three vertices.
    const buffer = new ArrayBuffer(84 + 50);
    const view = new DataView(buffer);
    view.setUint32(80, 1, true);
    const floats = [0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0];
    floats.forEach((value, i) => view.setFloat32(84 + i * 4, value, true));
    return Cypress.Buffer.from(buffer).toString('base64');
}

// Requires the full stack (API + real media directory); CI runs only the React dev server.
(Cypress.env('CI') ? describe.skip : describe)('STL preview', () => {

    before(() => {
        assertWROLModeOff();
        cy.task('fb:reset', {
            files: {
                'ascii.stl': ASCII_STL,
                'binary.stl': {base64: binaryStlBase64()},
            },
        });
        cy.refreshFiles([SANDBOX]);
    });

    after(() => {
        teardownFileBrowser();
    });

    const openPreview = (name) => {
        const params = new URLSearchParams({folders: `${SANDBOX}/`, preview: `${SANDBOX}/${name}`});
        cy.visit(`/files?${params}`);
        cy.get('[role="dialog"]').should('contain', name);
    };

    const expectTriangleDimensions = () => {
        // The triangle is 2 wide along X, which only a parsed model can report.  Which axis
        // reads as Height or Length depends on how the viewer orients the model, so only
        // Width is asserted.
        cy.get('[role="dialog"]').contains('Width:', {timeout: 20000}).parent()
            .should('contain', 'Width: 2.00');
        cy.get('[role="dialog"]').should('not.contain', 'Failed to');
    };

    it('previews an ASCII STL file', () => {
        openPreview('ascii.stl');
        expectTriangleDimensions();
    });

    it('previews a binary STL file', () => {
        openPreview('binary.stl');
        expectTriangleDimensions();
    });
});
