import React from 'react';
import {Button, Modal} from './index';
import {openModalCount} from './Overlays';

/*
 * Nested modals: only the one on top answers the keyboard, and the one underneath stays on
 * screen behind it.
 *
 * Mantine binds a window-level `keydown` listener per open modal, gated only on whether that
 * modal is open -- nothing checks which one the user is looking at.  Two open modals meant
 * two listeners, so one Escape closed both: opening the search modal over the dashboard's
 * download modal and pressing Escape once left you on the dashboard.  Reproduced in the
 * running app before this was written.
 *
 * A real browser, because none of it is visible to jsdom: the listener is on `window` with
 * `capture: true`, the stacking is z-index, and "still visible behind" is geometry.
 */

const Nested = ({onParentClose, onChildClose}) => {
    const [parent, setParent] = React.useState(false);
    const [child, setChild] = React.useState(false);
    return <>
        <Button data-testid='open-parent' onClick={() => setParent(true)}>Open parent</Button>
        <Modal open={parent} size='large'
               onClose={() => {
                   setParent(false);
                   onParentClose?.();
               }}>
            <Modal.Header>Parent</Modal.Header>
            <Modal.Content>
                <p data-testid='parent-body'>The parent's own content.</p>
                <Button data-testid='open-child' onClick={() => setChild(true)}>Open child</Button>
            </Modal.Content>
        </Modal>
        {/*
          * A SIBLING of the parent in the JSX, not a descendant.  This is the shape the bug
          * actually took -- the search modal is rendered by KeyboardShortcutsProvider near
          * the app root while the download modal is rendered by the dashboard -- and it is
          * why the register is module-level rather than a React context, which could not
          * relate these two at all.
          */}
        <Modal open={child} size='small'
               onClose={() => {
                   setChild(false);
                   onChildClose?.();
               }}>
            <Modal.Header>Child</Modal.Header>
            <Modal.Content><p data-testid='child-body'>The child's own content.</p></Modal.Content>
        </Modal>
    </>
};

const openBoth = () => {
    cy.mountUI(<Nested/>);
    cy.get('[data-testid="open-parent"]').click();
    cy.contains('.mantine-Modal-title', 'Parent').should('exist');
    cy.get('[data-testid="open-child"]').click();
    cy.contains('.mantine-Modal-title', 'Child').should('exist');
};

// Escape has to come from a real element: Mantine's handler calls
// `event.target.getAttribute(...)`, which throws if the event was dispatched on `document`.
const pressEscape = () => cy.get('body').trigger('keydown', {key: 'Escape', bubbles: true});

describe('a modal opened over another', () => {
    it('closes only itself on Escape, leaving the one underneath open', () => {
        // The bug, exactly: one press used to take both.
        openBoth();

        pressEscape();

        cy.contains('.mantine-Modal-title', 'Child').should('not.exist');
        cy.contains('.mantine-Modal-title', 'Parent').should('exist');
    });

    it('lets the next Escape close the one underneath', () => {
        // The other half: suppressing Escape on the parent must be temporary, or the parent
        // becomes unclosable by keyboard for the rest of its life.
        openBoth();

        pressEscape();
        cy.contains('.mantine-Modal-title', 'Child').should('not.exist');
        pressEscape();

        cy.contains('.mantine-Modal-title', 'Parent').should('not.exist');
    });

    it('keeps the parent on screen behind the child, not hidden', () => {
        /*
         * Mantine's own Modal.Stack sets `__hidden` on everything below the top, so the
         * parent vanishes while the child is open.  That is the behaviour this deliberately
         * does not use -- the parent should be dimmed and still there.
         *
         * Not `should('be.visible')`: that is an occlusion check, and a child drawn over its
         * parent trips it by definition -- at the default component viewport the 440px child
         * covers the 620px parent completely and the assertion fails on correct behaviour.
         * A wide viewport instead, where the parent is genuinely broader than the child, and
         * the claim is stated as what it is: the parent is rendered, and some of it is not
         * behind the child.
         */
        cy.viewport(1200, 800);
        openBoth();

        cy.get('.mantine-Modal-content').should(($contents) => {
            expect($contents, 'both modals are rendered').to.have.length(2);

            const boxes = [...$contents].map(content => ({
                el: content, box: content.getBoundingClientRect(),
                display: getComputedStyle(content).display,
                visibility: getComputedStyle(content).visibility,
            }));
            const [child, parent] = [...boxes].sort((a, b) => a.box.width - b.box.width);

            // `__hidden` would show up as either of these.
            expect(parent.display, 'the parent is not display:none').to.not.equal('none');
            expect(parent.visibility, 'the parent is not hidden').to.equal('visible');
            expect(parent.box.height, 'the parent still has a box').to.be.greaterThan(0);

            // And it is wider than the child on both sides, so it is actually seen.
            expect(parent.box.left, 'parent shows to the left of the child')
                .to.be.lessThan(child.box.left - 1);
            expect(parent.box.right, 'parent shows to the right of the child')
                .to.be.greaterThan(child.box.right + 1);
        });
    });

    it('draws the child above the parent', () => {
        // Both modals used to sit at z-index 200, so which one won was DOM order rather than
        // which one the user opened.
        openBoth();

        cy.get('.mantine-Modal-inner').should(($inners) => {
            const zIndexes = [...$inners].map(inner =>
                parseInt(getComputedStyle(inner).zIndex, 10));

            expect(zIndexes, 'two modals are stacked').to.have.length(2);
            expect(Math.max(...zIndexes), 'the child clears the parent')
                .to.be.greaterThan(Math.min(...zIndexes));
        });
    });

    it('keeps the stack below the popovers that open inside it', () => {
        /*
         * A Select or date picker inside a modal renders at Mantine's popover z-index of 300.
         * A stack that climbed past that would paint over the dropdowns in its own form,
         * which is a worse bug than the one being fixed.
         */
        openBoth();

        cy.get('.mantine-Modal-inner').should(($inners) => {
            const highest = Math.max(...[...$inners]
                .map(inner => parseInt(getComputedStyle(inner).zIndex, 10)));
            expect(highest, 'top modal stays under the popover layer').to.be.lessThan(300);
        });
    });
});

describe('the register of open modals', () => {
    it('empties as they close', () => {
        /*
         * The failure mode of keeping a module-level list: a modal that unmounts without
         * deregistering leaves a ghost on top forever, and then NOTHING closes on Escape --
         * every real modal believes something else is above it.  Silent, permanent, and
         * invisible to a test that only ever opens one modal.
         */
        openBoth();
        cy.then(() => expect(openModalCount(), 'both registered').to.equal(2));

        pressEscape();
        cy.contains('.mantine-Modal-title', 'Child').should('not.exist');
        cy.then(() => expect(openModalCount(), 'child deregistered').to.equal(1));

        pressEscape();
        cy.contains('.mantine-Modal-title', 'Parent').should('not.exist');
        cy.then(() => expect(openModalCount(), 'register is empty').to.equal(0));
    });

    it('is empty before anything opens, so the counts above mean something', () => {
        cy.mountUI(<Nested/>);
        cy.then(() => expect(openModalCount()).to.equal(0));
    });
});

describe('a single modal', () => {
    it('still closes on Escape', () => {
        // The premise for every case above.  Suppressing Escape on all but the top is
        // worthless if the top does not respond either.
        cy.mountUI(<Nested/>);
        cy.get('[data-testid="open-parent"]').click();
        cy.contains('.mantine-Modal-title', 'Parent').should('exist');

        pressEscape();

        cy.contains('.mantine-Modal-title', 'Parent').should('not.exist');
    });
});

describe('a parent that disables Escape while it is busy', () => {
    /*
     * Three call sites pass `closeOnEscape` of their own: CollectionReorganizeModal and
     * BatchReorganizeModal disable it while a reorganize runs, Flasher while it writes an
     * image.  The stack props were set BEFORE the `{...props}` spread, so those call sites
     * overwrote the stack's decision and re-armed Mantine's window-level listener on a modal
     * that is not on top.
     *
     * The concrete breakage: ConflictResolutionModal opens as a sibling above the reorganize
     * modal, so as soon as the reorganize finished and `closeOnEscape` went back to true, one
     * Escape closed both again -- the original bug, in the one place the app really does
     * stack two modals.
     *
     * "Only the top modal answers Escape" and "do not dismiss me while I am busy" are both
     * true; they compose with AND.
     */
    const Busy = ({busy}) => {
        const [parent, setParent] = React.useState(true);
        const [child, setChild] = React.useState(true);
        return <>
            <Modal open={parent} size='large' closeOnEscape={!busy}
                   onClose={() => setParent(false)}>
                <Modal.Header>Reorganize</Modal.Header>
                <Modal.Content><p>working</p></Modal.Content>
            </Modal>
            <Modal open={child} size='small' onClose={() => setChild(false)}>
                <Modal.Header>Conflicts</Modal.Header>
                <Modal.Content><p>resolve these</p></Modal.Content>
            </Modal>
        </>
    };

    it('still closes only the child when the parent has re-enabled Escape', () => {
        cy.mountUI(<Busy busy={false}/>);
        cy.contains('.mantine-Modal-title', 'Conflicts').should('exist');

        pressEscape();

        cy.contains('.mantine-Modal-title', 'Conflicts').should('not.exist');
        cy.contains('.mantine-Modal-title', 'Reorganize').should('exist');
    });

    it('honours the parent\'s own refusal once it is on top again', () => {
        /*
         * The other direction, and the reason the two are composed rather than the stack
         * simply winning: a busy parent must stay put even when nothing is above it.
         */
        cy.mountUI(<Busy busy/>);
        cy.contains('.mantine-Modal-title', 'Conflicts').should('exist');

        pressEscape();
        cy.contains('.mantine-Modal-title', 'Conflicts').should('not.exist');
        pressEscape();

        cy.contains('.mantine-Modal-title', 'Reorganize')
            .should('exist');
    });
});
