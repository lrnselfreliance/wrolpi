import React from 'react';
import {
    ActionInput, Button, Card, Header, Icon, IconButton, IconStack, Loading, MultiSelect, Panel, PathInput,
    Group, Message, Pagination, Placeholder, Progress, SearchBox, Statistic, StatisticGroup, Status, TabBar, Table,
    tabClassName, TextInput,
} from './index';
import {MemoryRouter} from 'react-router';
import {VideoCard} from '../Videos';
import {CardPoster, contrastingColor, HelpHeader, LoadStatistic} from '../Common';
import {Notifications} from '@mantine/notifications';
import {clearToasts, toast} from './toast';
import {monochromeThemes, themeNames} from '../../themes/names';
import {navColorNames} from '../../themes/navColors';
import {NavBarSample} from '../ThemeSamplePage';
import {DesktopNav, NavIconWrapper} from '../Nav';
import {APIButton} from '../Common';
import {ShareButton} from '../Share';

/*
 * The interface scale, so a test can express a length the way the stylesheet does.
 *
 * A hardcoded px expectation is a hidden assertion that the scale is 1.  Three tests here
 * carried one -- a container width, a poster cap and a button height -- and all three failed
 * when it became 1.1, in names that said nothing about size.
 */
const uiScale = () => {
    const value = parseFloat(getComputedStyle(document.documentElement)
        .getPropertyValue('--ui-scale'));
    expect(value, 'the interface scale is declared').to.be.within(0.5, 3);
    return value;
};

describe('the interface scale actually reaches what it is supposed to', () => {
    /*
     * Every other check on the scale reads source text, which proves a declaration says `rem`
     * and nothing about whether the browser then paints a larger control.  This is the one
     * that measures, and it is the reason the source guards are worth trusting: it fails if
     * `--ui-scale` stops being applied to the root, if Mantine's `theme.scale` is set and
     * cancels it, or if a rule someone adds later pins a px size over the top.
     */
    /*
     * The root of the application-under-test, not the runner's.  Cypress mounts the
     * component in an iframe and loads the stylesheets there, so `window.top` reads the
     * runner's own document -- where `--ui-scale` is not declared, so it came back NaN.
     * `Cypress.$` is scoped to the AUT.
     */
    const root = () => Cypress.$('html')[0];

    it('makes the root font-size the declared multiple of the browser default', () => {
        cy.mountUI(<Button>Save</Button>);

        cy.get('.mantine-Button-root').should(() => {
            const scale = parseFloat(getComputedStyle(root()).getPropertyValue('--ui-scale'));
            expect(scale, 'the scale is declared').to.be.within(0.5, 3);
            // 16px is the browser default the percentage resolves against.
            expect(parseFloat(getComputedStyle(root()).fontSize), 'root font-size')
                .to.be.closeTo(16 * scale, 0.5);
        });
    });

    it('grows a Mantine control and our own text together when the scale changes', () => {
        /*
         * Both halves in one measurement, because the failure that matters is them
         * DISAGREEING: Mantine's sizes are `calc(Xrem * var(--mantine-scale))` and ours are
         * plain rem, so a `theme.scale` of 1.1 alongside a 110% root would leave Mantine's
         * buttons at the old size beside 10% larger card text.
         */
        cy.mountUI(<Card title='Rainwater Harvesting' meta='engineering775.com'/>);

        /*
         * DOUBLE whatever the scale currently is, rather than setting it to 2.  Setting the
         * literal gave a ratio of 1.818 -- 2 divided by the 1.1 already in effect -- so the
         * first version of this failed against a perfectly working scale.
         */
        const doubled = () => {
            const current = parseFloat(getComputedStyle(root()).getPropertyValue('--ui-scale'));
            root().style.setProperty('--ui-scale', String(current * 2));
        };

        cy.get('.wrolpi-card-title').should(($title) => {
            const before = parseFloat(getComputedStyle($title[0]).fontSize);
            expect(before, 'the card title has a size to grow from').to.be.greaterThan(1);
            doubled();
            const after = parseFloat(getComputedStyle($title[0]).fontSize);
            root().style.removeProperty('--ui-scale');

            // A px declaration would not have moved at all.
            expect(after / before, 'our own text tracks the scale').to.be.closeTo(2, 0.05);
        });

        cy.mountUI(<Button>Save</Button>);
        cy.get('.mantine-Button-root').should(($button) => {
            const before = $button[0].getBoundingClientRect().height;
            doubled();
            const after = $button[0].getBoundingClientRect().height;
            root().style.removeProperty('--ui-scale');

            expect(after / before, "Mantine's controls track it too, by the same factor")
                .to.be.closeTo(2, 0.05);
        });
    });

    it('leaves a hairline a hairline at any scale', () => {
        // The inverse, and the whole reason rem was chosen over `zoom`.
        cy.mountUI(<Panel>Structure</Panel>);

        cy.get('.wrolpi-panel').should(($panel) => {
            const before = parseFloat(getComputedStyle($panel[0]).borderTopWidth);
            root().style.setProperty('--ui-scale', '2');
            const after = parseFloat(getComputedStyle($panel[0]).borderTopWidth);
            root().style.removeProperty('--ui-scale');

            expect(before, 'the panel has a hairline border').to.be.within(0.5, 2);
            expect(after, 'and it does not grow with the type').to.be.closeTo(before, 0.05);
        });
    });
});

describe('a page stacks its own blocks', () => {
    /*
     * A page is built out of panels -- the dashboard is five, Status is six, Settings is six --
     * and nothing put space between them, so every pair shared an edge.  Two 1px borders meeting
     * do not read as a seam between two surfaces; they read as one tall surface with a rule across
     * it, and which heading owns which content stops being obvious.
     *
     * The space is the page's, not the panel's.  How far a panel sits from its neighbour is a
     * property of the two of them being stacked, and the same panel also appears inside modals,
     * grids and Mantine `Stack`s that space it themselves.  This was tried the other way first, as
     * `margin-bottom` on `.wrolpi-panel`, and it failed in both of the ways that rule is known to
     * fail -- see the sibling test below, which is what stops it being tried again.
     */

    const gapsBetween = ($panels) => {
        const rects = [...$panels].map((el) => el.getBoundingClientRect());
        return rects.slice(1).map((rect, index) => rect.top - rects[index].bottom);
    };

    it('leaves a gap between the panels it stacks', () => {
        cy.mountUI(<div className='wrolpi-stack'>
            <Panel>Tags</Panel>
            <Panel>Status</Panel>
            <Panel>Calculators</Panel>
        </div>);

        cy.get('.wrolpi-stack').should(($stack) => {
            /*
             * Measured against the stack's own `row-gap` rather than a pixel range.  The range was
             * 12-28px, which assumes the default `--ui-scale`: at a larger scale the gap grows past
             * 28 and a correct layout would have failed the assertion.  A separate test covers the
             * ratio; this one is about the panels really being that far apart.
             */
            const declared = parseFloat(getComputedStyle($stack[0]).rowGap);
            expect(declared, 'the stack declares a gap').to.be.greaterThan(0);

            const gaps = gapsBetween($stack[0].querySelectorAll('.wrolpi-panel'));
            expect(gaps, 'both pairs measured').to.have.length(2);
            gaps.forEach((gap) => expect(gap, 'gap between panels').to.be.closeTo(declared, 0.5));
        });
    });

    it('spaces a block that is wrapped as readily as a bare one', () => {
        /*
         * This is the case that chose where the rule lives.  Several pages put a panel inside the
         * responsive `Media` component, so the page's child is a wrapper rather than the panel.
         *
         * Spacing from the page handles that for free -- it spaces the wrapper, and the wrapper is
         * the sibling.  A `margin-bottom` on the panel plus the `:last-child` reset that would
         * keep the trailing space off the bottom of a container does NOT: the panel is the only
         * child of its wrapper, so `:last-child` matches it, zeroes the margin, and leaves it hard
         * against the next panel.  On Status that separated four pairs out of five and left the
         * first touching -- one page showing both, which reads as a rendering glitch.
         */
        cy.mountUI(<div className='wrolpi-stack'>
            <div><Panel>Wrapped, as Media does it</Panel></div>
            <Panel>Bare</Panel>
        </div>);

        cy.get('.wrolpi-panel').should(($panels) =>
            expect(gapsBetween($panels)[0], 'gap across a wrapper').to.be.at.least(12));
    });

    it('survives a block that zeroes its own margin', () => {
        /*
         * The reason this is a gap and not `> * + * { margin-top }`.  The responsive `Media`
         * component injects `.fresnel-container { margin: 0; padding: 0 }` into the document at
         * runtime -- same specificity as the owl selector, later in source order -- so a wrapped
         * block threw the margin away and went on touching its neighbour, while the bare blocks
         * on the same page separated.  A gap is the parent's, and a child cannot zero it.
         *
         * The margin here stands in for fresnel's rule; the point is that the spacing does not
         * depend on the child's own margin being left alone.
         */
        cy.mountUI(<div className='wrolpi-stack'>
            <Panel>Before</Panel>
            <div style={{margin: 0}}><Panel>Zeroed its own margin</Panel></div>
        </div>);

        cy.get('.wrolpi-panel').should(($panels) =>
            expect(gapsBetween($panels)[0], 'gap despite the child margin').to.be.at.least(12));
    });

    it('adds nothing before the first block or after the last', () => {
        // A gap goes only between, so the page's own padding decides its edges.
        cy.mountUI(<div className='wrolpi-stack'>
            <Panel>First</Panel>
            <Panel>Last</Panel>
        </div>);

        cy.get('.wrolpi-stack').should(($stack) => {
            const stack = $stack[0].getBoundingClientRect();
            const panels = [...$stack[0].querySelectorAll('.wrolpi-panel')]
                .map(el => el.getBoundingClientRect());
            expect(panels[0].top - stack.top, 'above the first').to.be.closeTo(0, 0.5);
            expect(stack.bottom - panels[1].bottom, 'below the last').to.be.closeTo(0, 0.5);
        });
    });

    it('grows the gap with the interface scale', () => {
        // In px it would hold still while the panels either side of it grew.
        cy.mountUI(<div className='wrolpi-stack'>
            <Panel>One</Panel>
            <Panel>Two</Panel>
        </div>);

        cy.get('.wrolpi-stack').should(($stack) => {
            const before = parseFloat(getComputedStyle($stack[0]).rowGap);
            const root = Cypress.$('html')[0];
            const scale = parseFloat(getComputedStyle(root).getPropertyValue('--ui-scale')) || 1;
            root.style.setProperty('--ui-scale', String(scale * 2));
            const after = parseFloat(getComputedStyle($stack[0]).rowGap);
            root.style.removeProperty('--ui-scale');

            expect(before, 'the gap exists at all').to.be.greaterThan(0);
            expect(after / before, 'and doubles with the scale').to.be.closeTo(2, 0.05);
        });
    });

    it('contributes no gap for the half of a Media pair that is hidden', () => {
        /*
         * `Media` renders both viewports and hides one with `display: none`.  A hidden flex item
         * is not a flex item at all, so it takes no gap -- where `* + *` would have put space
         * around something invisible and left a page with a stray 1rem hole in it.
         */
        cy.mountUI(<div className='wrolpi-stack'>
            <Panel>Shown</Panel>
            <div style={{display: 'none'}}><Panel>The other viewport</Panel></div>
            <Panel>Also shown</Panel>
        </div>);

        // One gap, not two: measured against the declared gap rather than a pixel ceiling, which
        // would have false-failed at a larger interface scale instead of catching a doubled gap.
        cy.get('.wrolpi-stack').should(($stack) => {
            const declared = parseFloat(getComputedStyle($stack[0]).rowGap);
            const shown = $stack[0].querySelectorAll('.wrolpi-panel:not([style*="none"])');
            const visible = [...shown].filter((el) => el.offsetParent !== null);
            expect(visible, 'the hidden panel is not measured').to.have.length(2);
            expect(gapsBetween(visible)[0], 'one gap, not two').to.be.closeTo(declared, 0.5);
        });
    });

    it('leaves a panel with no outer margin, so a Stack can space it instead', () => {
        /*
         * The inverse rule, and the reason it is worth its own test: the moment a panel carries
         * its own margin, it adds to the spacing of every container that already spaces its
         * children.  Four `Stack`s in the app hold nothing but panels -- the conflict list, both
         * halves of the one-time pad, the electrical calculators -- and with `margin-bottom` on
         * the panel they spaced those lists at 35.2px against the 17.6px used everywhere else.
         */
        cy.mountUI(<Panel>Composable</Panel>);

        cy.get('.wrolpi-panel').should(($panel) => {
            const styles = getComputedStyle($panel[0]);
            ['marginTop', 'marginRight', 'marginBottom', 'marginLeft'].forEach((side) => {
                expect(parseFloat(styles[side]), side).to.equal(0);
            });
        });
    });
});

describe('a row of buttons is spaced and aligned by the row', () => {
    /*
     * Semantic's Button carried `margin: 0 .25em .25em 0` of its own, so a page could list
     * buttons as bare siblings and they arrived spaced.  Nothing replaced that margin, and
     * five pages still list them that way -- the archive page's six actions all shared edges.
     *
     * Two of those six also carried `marginTop: 0.5em`, which is what made "Update" sit lower
     * than its neighbours: a Button is `display: inline-flex; vertical-align: middle`, and
     * `vertical-align` aligns the MARGIN box, so half of any top margin pushes the visible
     * button down.  The margin was there to keep a wrapped row from touching vertically --
     * the right thing, solved in the wrong axis.  A flex row with `gap` covers both axes and
     * needs no per-button margin, so the alignment comes back for free.
     */

    const rowButtons = ($row) => [...$row[0].querySelectorAll('button')];

    it('puts a gap between the buttons, horizontally and when wrapped', () => {
        cy.mountUI(<div className='wrolpi-button-row'>
            <Button>View</Button>
            <Button>Read</Button>
            <Button>Update</Button>
        </div>);

        cy.get('.wrolpi-button-row').should(($row) => {
            const row = $row[0];
            const styles = getComputedStyle(row);
            const declared = parseFloat(styles.columnGap);
            expect(declared, 'the row declares a gap').to.be.greaterThan(0);
            expect(parseFloat(styles.rowGap), 'and the same one between wrapped lines')
                .to.be.closeTo(declared, 0.5);
            expect(styles.flexWrap, 'the row wraps rather than overflowing').to.equal('wrap');

            /*
             * Narrowed to exactly two buttons' worth, measured rather than guessed.  A hardcoded
             * 150px was a hidden assertion about both the font and the interface scale, and at 1.1
             * it fitted one button, not the two the assertions below are about.
             */
            const widths = rowButtons($row).map(el => el.getBoundingClientRect().width);
            expect(widths, 'three buttons measured').to.have.length(3);
            row.style.width = `${widths[0] + declared + widths[1] + 1}px`;

            const rects = rowButtons($row).map(el => el.getBoundingClientRect());
            const top = Math.min(...rects.map(rect => rect.top));
            const first = rects.filter(rect => Math.round(rect.top) === Math.round(top));
            expect(first, 'two buttons on the first line').to.have.length(2);
            expect(first[1].left - first[0].right, 'gap along the line').to.be.closeTo(declared, 0.5);

            // And the third dropped to a second line, held off the first by the same gap.
            const wrapped = rects.find(rect => Math.round(rect.top) !== Math.round(top));
            expect(wrapped, 'the third button wrapped').to.not.be.undefined;
            expect(wrapped.top - first[0].bottom, 'gap between the lines')
                .to.be.closeTo(declared, 0.5);
        });
    });

    it('centres its buttons against a taller item beside them', () => {
        /*
         * A row is not always all buttons: the doc page puts its format picker beside its actions,
         * and the downloads table an error trigger beside its two icon buttons.  Whatever is
         * tallest sets the line height, and `align-items: center` is what keeps the buttons reading
         * as part of that line rather than hanging from the top of it.
         *
         * Written as tops first, which was a test with no teeth -- `stretch` stretches the WRAPPER
         * and leaves the button at the top of it, so the tops agreed either way.  Centres are what
         * the property actually decides.
         *
         * The row is also mixed in the way the archive page's is: a button inside an `<a>`, a bare
         * one, and an APIButton.
         */
        cy.mountUI(<div className='wrolpi-button-row'>
            <div style={{height: '80px', width: '40px'}}>Tall</div>
            <a href='/media/archive.html'><Button>View</Button></a>
            <Button>Read</Button>
            <APIButton onClick={() => Promise.resolve()}>Update</APIButton>
        </div>);

        cy.get('.wrolpi-button-row').should(($row) => {
            const row = $row[0].getBoundingClientRect();
            expect(row.height, 'the tall item set the line height').to.be.at.least(80);

            const centers = rowButtons($row).map((el) => {
                const rect = el.getBoundingClientRect();
                return rect.top + rect.height / 2;
            });
            expect(centers, 'three buttons measured').to.have.length(3);
            const middle = row.top + row.height / 2;
            centers.forEach(center => expect(center, 'centred in the line').to.be.closeTo(middle, 1));
        });
    });

    it('counts a confirmed action as one item in the row, not two', () => {
        /*
         * `APIButton` with `confirmContent` returns a fragment -- the button AND a `<Confirm/>`.
         * In a flex row those flatten into siblings, so a Confirm that rendered anything in
         * place would take a gap of its own and open a hole between two buttons.  It portals,
         * and this is what says so; three of the archive page's six actions are confirmed.
         */
        cy.mountUI(<div className='wrolpi-button-row'>
            <Button>Plain</Button>
            <APIButton confirmContent='Sure?' onClick={() => Promise.resolve()}>Delete</APIButton>
            <Button>Also plain</Button>
        </div>);

        cy.get('.wrolpi-button-row').should(($row) => {
            const declared = parseFloat(getComputedStyle($row[0]).columnGap);
            const rects = rowButtons($row).map(el => el.getBoundingClientRect());
            expect(rects, 'three buttons measured').to.have.length(3);
            rects.slice(1).forEach((rect, index) => expect(
                rect.left - rects[index].right, 'gap either side of the confirmed action',
            ).to.be.closeTo(declared, 0.5));
        });
    });

    it('keeps its buttons their own width inside a page stack', () => {
        /*
         * `.wrolpi-stack` is a flex column at `align-items: stretch`, which is what keeps a panel
         * full-width as it was as a block element -- and which stretched every page's Back button
         * to the full width of the page, because a bare button was a direct child of it.
         *
         * The row is what absorbs that: the ROW is the stretched child, and it lays its buttons out
         * at their own width.  Both halves are asserted, because a row that also refused to stretch
         * would pass a test that only looked at the button.
         */
        cy.mountUI(<div className='wrolpi-stack'>
            <div className='wrolpi-button-row'><Button>Back</Button></div>
            <Panel>The page</Panel>
        </div>);

        cy.get('.wrolpi-stack').should(($stack) => {
            const stack = $stack[0].getBoundingClientRect();
            const row = $stack[0].querySelector('.wrolpi-button-row').getBoundingClientRect();
            const button = $stack[0].querySelector('button').getBoundingClientRect();

            expect(stack.width, 'the stack has a width to fill').to.be.greaterThan(200);
            expect(row.width, 'the row stretches, as the panel does').to.be.closeTo(stack.width, 0.5);
            expect(button.width, 'the button does not').to.be.lessThan(stack.width / 2);
        });
    });

    it('grows its gap with the interface scale', () => {
        cy.mountUI(<div className='wrolpi-button-row'><Button>One</Button><Button>Two</Button></div>);

        cy.get('.wrolpi-button-row').should(($row) => {
            const before = parseFloat(getComputedStyle($row[0]).columnGap);
            const root = Cypress.$('html')[0];
            const scale = parseFloat(getComputedStyle(root).getPropertyValue('--ui-scale')) || 1;
            root.style.setProperty('--ui-scale', String(scale * 2));
            const after = parseFloat(getComputedStyle($row[0]).columnGap);
            root.style.removeProperty('--ui-scale');

            expect(before, 'the gap exists at all').to.be.greaterThan(0);
            expect(after / before, 'and doubles with the scale').to.be.closeTo(2, 0.05);
        });
    });
});

describe('two choices of equal weight are split down the middle', () => {
    /*
     * The dashboard's Download/Upload panel, which Semantic drew as a `Segment placeholder` with a
     * vertical `Divider`.  The migrated version was a `Group` with a divider between the buttons,
     * so the halves were sized to their labels: the pair huddled in the middle of the panel with
     * the rule wherever they happened to leave it, rather than two equal fields split at the centre.
     */

    /*
     * The viewport is set explicitly.  Cypress component tests default to 500x500, which is BELOW
     * the 699px breakpoint where these halves stack -- so without this every assertion below would
     * be measuring the phone layout while claiming to measure the desktop one.
     */
    const mountSplit = (width = 1000) => cy.viewport(width, 700).then(() => cy.mountUI(<div>
        <Panel>
            <div className='wrolpi-or-split'>
                <div><Button role='primary'>Download</Button></div>
                <div><Button role='save'>Upload</Button></div>
                <span className='wrolpi-or-label'>Or</span>
            </div>
        </Panel>
    </div>));

    it('gives each choice half the panel, whatever its label says', () => {
        mountSplit();

        cy.get('.wrolpi-or-split').should(($split) => {
            const halves = [...$split[0].children]
                .filter(el => !el.classList.contains('wrolpi-or-label'))
                .map(el => el.getBoundingClientRect());
            expect(halves, 'two halves').to.have.length(2);
            // Equal, and each really is half -- not two content-sized boxes that happen to match.
            expect(halves[1].width, 'the halves are equal').to.be.closeTo(halves[0].width, 1);
            const split = $split[0].getBoundingClientRect();
            expect(halves[0].width, 'and each is half the row').to.be.closeTo(split.width / 2, 1);
        });
    });

    it('centres each button in its own half', () => {
        // Semantic centred them; the Group version left them either side of the divider instead.
        mountSplit();

        cy.get('.wrolpi-or-split').should(($split) => {
            const halves = [...$split[0].children]
                .filter(el => !el.classList.contains('wrolpi-or-label'));
            halves.forEach((half) => {
                const box = half.getBoundingClientRect();
                const button = half.querySelector('button').getBoundingClientRect();
                expect(button.left + button.width / 2, 'button centred in its half')
                    .to.be.closeTo(box.left + box.width / 2, 1);
            });
        });
    });

    it('puts the rule and its label at the true middle', () => {
        mountSplit();

        cy.get('.wrolpi-or-split').should(($split) => {
            const split = $split[0].getBoundingClientRect();
            const middle = split.left + split.width / 2;

            // The rule is the second half's left border, so its edge IS the middle.
            const second = $split[0].children[1];
            expect(parseFloat(getComputedStyle(second).borderLeftWidth), 'a rule is drawn')
                .to.be.greaterThan(0);
            expect(second.getBoundingClientRect().left, 'the rule falls at the middle')
                .to.be.closeTo(middle, 1);

            const label = $split[0].querySelector('.wrolpi-or-label').getBoundingClientRect();
            expect(label.left + label.width / 2, 'and the label rides it').to.be.closeTo(middle, 1);
            expect(label.top + label.height / 2, 'halfway down')
                .to.be.closeTo(split.top + split.height / 2, 1);
        });
    });

    it('stacks the halves below the tablet breakpoint', () => {
        // The other branch, and the one the suite would otherwise test by default.
        mountSplit(400);

        cy.get('.wrolpi-or-split').should(($split) => {
            const halves = [...$split[0].children]
                .filter(el => !el.classList.contains('wrolpi-or-label'));
            const boxes = halves.map(el => el.getBoundingClientRect());
            expect(boxes[1].top, 'the second sits below the first').to.be.greaterThan(boxes[0].top);
            expect(boxes[1].width, 'each takes the full width').to.be.closeTo(boxes[0].width, 1);

            const second = getComputedStyle(halves[1]);
            expect(parseFloat(second.borderLeftWidth), 'no vertical rule').to.equal(0);
            expect(parseFloat(second.borderTopWidth), 'a horizontal one instead').to.be.greaterThan(0);
        });
    });

    it('breaks the rule at the word rather than letting it strike through', () => {
        /*
         * The rule runs down, stops at the word, and picks up below it.  The break is made by
         * painting the word with the Panel's own color -- so the paint is load-bearing, and it has
         * to be that color or the word reads as a chip laid on the surface.
         *
         * The word carries no shape of its own: it is not a disc, and a border or a radius would
         * enclose it instead of breaking the line.
         */
        mountSplit();

        cy.get('.wrolpi-or-label').should(($label) => {
            const styles = getComputedStyle($label[0]);
            const panel = getComputedStyle(Cypress.$('.wrolpi-panel')[0]).backgroundColor;
            expect(styles.backgroundColor, 'painted with the panel').to.equal(panel);

            /*
             * All four sides, not just the top.  Reading one side was how a stray rule down the
             * word's left edge survived this test: the label is a third child of the grid, so the
             * `> * + *` that draws the divider matched it too and gave it a border of its own.
             */
            ['Top', 'Right', 'Bottom', 'Left'].forEach(side => expect(
                parseFloat(styles[`border${side}Width`]), `no rule on the word's ${side} edge`,
            ).to.equal(0));
            expect(parseFloat(styles.borderRadius), 'and no disc').to.equal(0);

            // Padded enough to actually open a gap, rather than sitting on the line unbroken...
            expect(parseFloat(styles.paddingTop), 'padded enough to break the rule')
                .to.be.greaterThan(0);
            /*
             * ...but its OWN padding, not a half's.  `.wrolpi-or-split > *` would lay this out as
             * a half if it were not excluded, and it currently escapes on source order alone --
             * same specificity, declared later.  Reordering the two blocks would quadruple the gap
             * and an assertion that only read "greater than zero" would not notice.
             */
            const half = getComputedStyle($label[0].parentElement.children[0]);
            expect(parseFloat(styles.paddingTop), "the word's own padding, not a half's")
                .to.be.lessThan(parseFloat(half.paddingTop));
        });
    });
});

describe('the video page insets what sits under its player', () => {
    /*
     * The video route is deliberately outside `VideosTabLayout`'s `PageContainer` so the player can
     * run to both edges of the window -- the most viewing area a phone can give it.  Everything
     * below the player inherited that, so the panels touched the left edge of the page.
     */
    it('pads the stack under the player, and nothing above it', () => {
        // Above the tablet breakpoint; below it a page has no side padding and neither has this.
        cy.viewport(1000, 700);
        cy.mountUI(<div>
            <video data-testid='player' style={{width: '100%'}}/>
            <div className='wrolpi-stack wrolpi-page-inset'>
                <Panel>About</Panel>
            </div>
        </div>);

        cy.get('.wrolpi-page-inset').should(($inset) => {
            const styles = getComputedStyle($inset[0]);
            const padding = parseFloat(styles.paddingLeft);
            expect(padding, 'the stack is inset').to.be.greaterThan(0);
            expect(parseFloat(styles.paddingRight), 'on both sides').to.be.closeTo(padding, 0.5);

            // The player keeps the full width; only what is under it moves in.
            const player = Cypress.$('[data-testid="player"]')[0].getBoundingClientRect();
            const panel = $inset[0].querySelector('.wrolpi-panel').getBoundingClientRect();
            expect(panel.left - player.left, 'the panel clears the edge the player touches')
                .to.be.closeTo(padding, 0.5);
        });
    });
});

/* `--panel` is authored as a hex; computed backgrounds come back as rgb(). */
const hexToRgb = (hex) => {
    const value = hex.replace('#', '');
    const [r, g, b] = [0, 2, 4].map(i => parseInt(value.slice(i, i + 2), 16));
    return `rgb(${r}, ${g}, ${b})`;
};

/*
 * Normalise a color to rgb(), and REFUSE anything that is neither a hex nor already
 * rgb().  Strictness is the point: feeding an unresolved `var(--blue)` to a luminance
 * calculation yields NaN, and `expect(NaN).to.not.equal(x)` passes -- a test that cannot
 * fail.  Better to blow up naming the value than to quietly measure nothing.
 *
 * Tokens do resolve: `getPropertyValue('--info')` returns `#20629c` in light, because
 * custom properties are substituted at computed-value time.  This guards the day that
 * stops being true on some engine, and catches the hex/rgb mismatch that is easy to hit
 * when reading a Mantine variable rather than a painted property.
 */
const toRgb = (value) => {
    const trimmed = String(value).trim();
    if (/^rgba?\(/.test(trimmed)) return trimmed;
    if (/^#[0-9a-fA-F]{6}$/.test(trimmed)) return hexToRgb(trimmed);
    throw new Error(`Not a resolved color: "${trimmed}"`);
};

/*
 * Layout and theming assertions for the component library, run in a real browser.
 *
 * These belong here rather than in ui.test.js because jsdom parses CSS but never lays it
 * out: getBoundingClientRect() returns zeros, getComputedStyle() will not resolve a custom
 * property through the cascade, and no filter is ever applied.  A jest test therefore
 * cannot tell whether two boxes overlap, whether a token resolved, or whether media got
 * tinted -- which is precisely how five unreadable inputs reached the Settings page.
 *
 * Keep this file to claims that need real layout.  Behaviour that jsdom can judge belongs
 * in ui.test.js, which runs in about two seconds against the whole library.
 */

describe('PathInput lays its prefix beside the value, never over it', () => {
    // Every theme, because a theme is free to restyle borders and padding, and the fix has
    // to hold in all four rather than in whichever one happened to be open.
    themeNames.forEach((theme) => {
        it(`keeps the prefix clear of the input in ${theme}`, () => {
            cy.mountUI(
                <PathInput
                    label='Archive Destination'
                    prefix='/media/wrolpi'
                    defaultValue='archive/%(domain)s'
                />,
                {theme},
            );

            cy.shouldNotOverlap('.wrolpi-path-input-prefix', '.wrolpi-path-input-control input');

            // Sharing one outline is the reason the pair reads as a single control; a gap
            // would mean the flex row broke and they are two separate fields again.
            cy.get('.wrolpi-path-input-prefix').then(($prefix) => {
                cy.get('.wrolpi-path-input-control input').then(($input) => {
                    const prefix = $prefix[0].getBoundingClientRect();
                    const input = $input[0].getBoundingClientRect();
                    expect(input.left - prefix.right, 'gap between prefix and input')
                        .to.be.closeTo(0, 2);
                });
            });
        });
    });

    it('shows the whole value, with room left to type', () => {
        cy.mountUI(
            <PathInput prefix='/media/wrolpi' defaultValue='archive/%(domain)s'/>,
        );

        /*
         * scrollWidth well beyond clientWidth means the value is cut off -- the visible
         * symptom when a prefix eats the input's usable width.  Both are rounded to whole
         * pixels from a fractional layout, so they disagree by a pixel on a field that fits
         * perfectly; the tolerance is for that, and is far below the tens of pixels a real
         * clip costs.
         */
        cy.get('.wrolpi-path-input-control input').should(($input) => {
            const el = $input[0];
            expect(el.scrollWidth, 'value is not clipped').to.be.at.most(el.clientWidth + 2);
            expect(el.clientWidth, 'input has usable width').to.be.greaterThan(80);
        });
    });

    it('still leaves somewhere to type when the media directory is a long path', () => {
        /*
         * The prefix is whatever the API reports as the media directory, so its length is not
         * ours to assume.  It is `/media/wrolpi` on a Pi, but a development box or an unusual
         * Docker mount can report something far longer, and a prefix that refuses to shrink
         * would take the whole row and leave the input at zero width -- a field that cannot
         * be typed into at all.
         */
        cy.mountUI(
            <div style={{width: 320}}>
                <PathInput
                    label='Archive Destination'
                    prefix='/mnt/storage/external/wrolpi-media-library-volume/'
                    defaultValue='archive/%(domain)s'
                />
            </div>,
        );

        cy.shouldNotOverlap('.wrolpi-path-input-prefix', '.wrolpi-path-input-control input');
        cy.get('.wrolpi-path-input-control input').should(($input) =>
            expect($input[0].clientWidth, 'input keeps a usable width').to.be.greaterThan(60));
        // The control must not spill out of the column it was given either.
        cy.get('.wrolpi-path-input-control').should(($control) =>
            expect($control[0].getBoundingClientRect().width).to.be.at.most(320));
    });

    it('detects the overlap that started this, so the check has teeth', () => {
        /*
         * The original defect, reproduced deliberately: Mantine turns leftSectionWidth into
         * --input-padding-inline-start, and `padding-inline-start: auto` is invalid, so it
         * resolves to zero and the absolutely-positioned section prints over the value.
         *
         * Asserting that this DOES overlap proves shouldNotOverlap is measuring something
         * real.  A geometry check that has never once gone red is indistinguishable from a
         * check that cannot fail.
         */
        cy.mountUI(
            <TextInput
                leftSectionWidth='auto'
                leftSection={<span className='probe-section'>/media/wrolpi</span>}
                defaultValue='archive/%(domain)s'
            />,
        );

        cy.get('.probe-section').then(($section) => {
            cy.get('input').then(($input) => {
                const section = $section[0].getBoundingClientRect();
                const input = $input[0].getBoundingClientRect();
                expect(
                    section.right > input.left + 0.5,
                    'the historical bug still overlaps, so the geometry check is meaningful',
                ).to.equal(true);
            });
        });
    });
});

describe('ActionInput', () => {
    it('joins its button to the field without covering it', () => {
        cy.mountUI(
            <ActionInput
                defaultValue='https://example.com'
                action={<Button>Fetch</Button>}
            />,
        );

        cy.shouldNotOverlap('.wrolpi-action-input input', '.wrolpi-action-input button');
    });
});

/* WCAG contrast between two rgb() strings, for judging how loud a border is. */
const luminance = (color) => {
    const [r, g, b] = (color.match(/[\d.]+/g) || []).map(Number);
    const channel = (v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
};

const contrast = (a, b) => {
    const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
};

const sampleTable = <Table>
    <Table.Header>
        <Table.Row>
            <Table.HeaderCell>URL</Table.HeaderCell>
            <Table.HeaderCell>Size</Table.HeaderCell>
        </Table.Row>
    </Table.Header>
    <Table.Body>
        <Table.Row><Table.Cell>one</Table.Cell><Table.Cell>1 kB</Table.Cell></Table.Row>
        <Table.Row><Table.Cell>two</Table.Cell><Table.Cell>2 kB</Table.Cell></Table.Row>
        <Table.Row><Table.Cell>three</Table.Cell><Table.Cell>3 kB</Table.Cell></Table.Row>
    </Table.Body>
</Table>;

describe('semantic roles read as severity in every theme', () => {
    /*
     * The point of the roles, and the only thing that makes them worth having.
     *
     * Light and dark spend a hue per role, so this is nearly free there.  Night is red and
     * nothing else and amber is amber and nothing else, so a role there is a step on a
     * brightness ramp -- and it has to be, because `--orange` in night is byte-identical to
     * `--text` and `--yellow` to `--amber`.  Picking between hue names in night is picking
     * between synonyms, which is why all four toast kinds were the same pixel.
     *
     * None of this is checkable in jsdom: every value is a token behind two levels of
     * var(), and the claim is about resolved luminance.
     */
    const ROLES = ['neutral', 'info', 'success', 'warning', 'danger'];

    const roleColors = () => {
        const root = getComputedStyle(document.documentElement);
        const panel = toRgb(root.getPropertyValue('--panel'));
        return {
            panel,
            text: toRgb(root.getPropertyValue('--text')),
            roles: ROLES.map(role => ({role, color: toRgb(root.getPropertyValue(`--${role}`))})),
        };
    };

    themeNames.forEach((theme) => {
        it(`gives every role a color of its own in ${theme}`, () => {
            // True everywhere.  Two roles resolving to the same value is the original bug.
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {roles} = roleColors();
                const colors = roles.map(r => r.color);
                colors.forEach((color, index) => {
                    expect(color, `${roles[index].role} resolved`).to.match(/^rgb\(/);
                });
                expect(new Set(colors).size, `five distinct roles, got ${colors.join(' ')}`)
                    .to.equal(5);
            });
        });

        it(`keeps every role legible in ${theme}`, () => {
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {panel, roles} = roleColors();
                roles.forEach(({role, color}) => {
                    /*
                     * 3:1 is the floor for anything that is not body text.  `neutral` is
                     * allowed to sit at the bottom of the ramp -- for `pending` and disabled,
                     * being dim IS the signal -- but it still has to be visible at all.
                     */
                    expect(contrast(color, panel), `${role} against the panel`)
                        .to.be.at.least(role === 'neutral' ? 2.5 : 3);
                });
            });
        });


        it(`gives each Status kind a color of its own in ${theme}`, () => {
            /*
             * The end of the chain, through a real component: four states, four distinct
             * painted colors.  In night these used to need three hand-written
             * `html[data-theme="night"]` overrides; the roles replaced all of them.
             */
            cy.mountUI(
                <Panel>
                    <Status kind='complete'>complete</Status>
                    <Status kind='active'>downloading</Status>
                    <Status kind='pending'>pending</Status>
                    <Status kind='failed'>failed</Status>
                </Panel>,
                {theme},
            );

            cy.get('.wrolpi-status').should(($all) => {
                expect($all.length).to.equal(4);
                const colors = [...$all].map(el => getComputedStyle(el).color);
                expect(new Set(colors).size, `four distinct colors, got ${colors.join(' ')}`)
                    .to.equal(4);
            });
        });
    });

    monochromeThemes.forEach((theme) => {
        it(`orders the roles by brightness in ${theme}, which is all it has`, () => {
            /*
             * Only here.  Light and dark spend a hue per role, so their contrast order is
             * an accident of which hues were chosen -- in light, blue is DARKER than green
             * on white, so asserting a ramp there fails on a design that is perfectly fine.
             * With hue gone, though, ordering is the only thing severity can be encoded in.
             */
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {panel, roles} = roleColors();
                const ratios = roles.map(({role, color}) => ({role, ratio: contrast(color, panel)}));
                ratios.slice(1).forEach((entry, index) => {
                    expect(entry.ratio, `${entry.role} is louder than ${ratios[index].role}`)
                        .to.be.greaterThan(ratios[index].ratio);
                });
            });
        });

        it(`makes warning and danger louder than ordinary text in ${theme}`, () => {
            /*
             * Only here.  A light theme's text is near-black at ~14:1 and no warning color
             * will ever match it -- there, hue is what marks a reading as flagged.  On a
             * single hue the roles and the text come off the same ramp, so anything meaning
             * "look at this" has to outrank the prose or it does not read as flagged at all.
             *
             * This is the assertion the Status page needed: an uncolored load reading
             * inherits `--text`, and warning used to sit just below it.
             */
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {panel, text, roles} = roleColors();
                const prose = contrast(text, panel);
                ['warning', 'danger'].forEach((name) => {
                    const role = roles.find(r => r.role === name).color;
                    expect(contrast(role, panel), `${name} against --text on the panel`)
                        .to.be.greaterThan(prose);
                });
            });
        });
    });

    it('does not leave failure to color alone', () => {
        // Brightness is the first thing lost on a dim screen, and it is all night has.
        cy.mountUI(
            <Panel>
                <Status kind='failed'>failed</Status>
                <Status kind='complete'>complete</Status>
            </Panel>,
            {theme: 'night'},
        );

        cy.get('.wrolpi-status-failed').should(($failed) => {
            const other = Cypress.$('.wrolpi-status-complete')[0];
            expect(parseInt(getComputedStyle($failed[0]).fontWeight, 10), 'failed is heavier')
                .to.be.greaterThan(parseInt(getComputedStyle(other).fontWeight, 10));
        });
    });
});

describe('a load reading ranks itself in the monochrome themes', () => {
    /*
     * The real `LoadStatistic`, at the real thresholds -- NOT a hand-built `Statistic` with
     * the roles typed in.  The first version of this did that, and it would have stayed green
     * with `LoadStatistic` reverted to `orange`/`red`: it proved only that role tokens resolve
     * distinctly, which the roles suite above already covers.
     *
     * This is the Status page's CPU load, and the clearest payoff of the roles outside the
     * library: `orange` above half the cores was byte-identical to `--text` in night, so a
     * machine under load rendered its warning as an ordinary uncolored number.
     *
     * Only a browser can see it.  jsdom rejects `color: var(--warning)` as invalid and drops
     * it, so the inline color reads back empty whatever the component did.
     */
    monochromeThemes.forEach((theme) => {
        it(`separates fine, warning and danger loads in ${theme}`, () => {
            cy.mountUI(
                <Panel>
                    <LoadStatistic label='1 Min. Load' value={1.9} cores={4}/>
                    <LoadStatistic label='5 Min. Load' value={2.6} cores={4}/>
                    <LoadStatistic label='15 Min. Load' value={4.1} cores={4}/>
                </Panel>,
                {theme},
            );

            cy.get('.wrolpi-statistic-value').should(($values) => {
                expect($values.length, 'three readings').to.equal(3);
                const [fine, warning, danger] = [...$values]
                    .map(el => toRgb(getComputedStyle(el).color));
                const panel = toRgb(getComputedStyle(
                    Cypress.$('.wrolpi-panel')[0]).backgroundColor);

                expect(new Set([fine, warning, danger]).size, 'three distinct readings').to.equal(3);
                /*
                 * Both flagged readings outrank a plain one.  This is what the ramp change
                 * bought: warning used to sit just UNDER `--text`, so a machine under load
                 * rendered marginally quieter than a healthy one.
                 */
                expect(contrast(warning, panel), 'warning is louder than a plain reading')
                    .to.be.greaterThan(contrast(fine, panel));
                expect(contrast(danger, panel), 'danger is louder than warning')
                    .to.be.greaterThan(contrast(warning, panel));
            });
        });
    });
});

describe('a heading keeps its trailing control on its own line', () => {
    /*
     * The defect this fixes: `.wrolpi-header` is a block, so a help icon placed after it
     * wrapped to the next line -- every `HelpHeader` and `InfoHeader` in the app, most
     * visibly "Root CA Certificate" on the Settings page.
     *
     * A pure layout claim, so jsdom cannot judge it: getBoundingClientRect returns zeros
     * there, and containment alone (which the jest tests assert) does not prove two boxes
     * share a line.
     */
    /*
     * The REAL wrapper, not a plain Button in an `after` slot.  A hand-built fixture would
     * miss the thing most likely to be wrong: `HelpModal` and `InfoPopup` carry their own
     * `iconStyle` default of `margin: 0.5em`, which was there to separate a free-floating
     * sibling and adds to the row's gap on every side once it is inside the row.
     */
    themeNames.forEach((theme) => {
        it(`sits a real help control beside the text in ${theme}`, () => {
            cy.mountUI(
                <HelpHeader headerSize='h3' headerContent='Root CA Certificate'
                            helpPath='/system/certificates/'/>,
                {theme},
            );

            cy.get('.wrolpi-header-after').should(($after) => {
                const control = $after[0].getBoundingClientRect();
                const text = $after[0].previousElementSibling.getBoundingClientRect();
                expect(control.top, 'control starts above the text baseline')
                    .to.be.lessThan(text.bottom);
                expect(text.top, 'text starts above the control baseline')
                    .to.be.lessThan(control.bottom);
                expect(control.left, 'control is after the text').to.be.at.least(text.right);
                /*
                 * Measured to the BUTTON, not to `.wrolpi-header-after`.  That wrapper is a
                 * flex container, so a margin on the button sits inside it and the wrapper's
                 * own rect does not move -- measuring the wrapper cannot see the margin at
                 * all, which is how this assertion first passed with it restored.
                 */
                const button = $after[0].querySelector('button').getBoundingClientRect();
                expect(button.left - text.right, 'the row gap alone, no icon margin on top')
                    .to.be.at.most(12);
            });
        });

        it(`sits an arbitrary control beside the text in ${theme}`, () => {
            cy.mountUI(
                <Header as='h3' after={<Button role='cancel' size='xs'>Help</Button>}>
                    Root CA Certificate
                </Header>,
                {theme},
            );

            cy.get('.wrolpi-header-after').should(($after) => {
                const control = $after[0].getBoundingClientRect();
                const text = $after[0].previousElementSibling.getBoundingClientRect();

                // Beside, not below: they overlap vertically and the control is to the right.
                expect(control.top, 'control starts above the text baseline')
                    .to.be.lessThan(text.bottom);
                expect(text.top, 'text starts above the control baseline')
                    .to.be.lessThan(control.bottom);
                expect(control.left, 'control is after the text').to.be.at.least(text.right);
            });
        });
    });

    it('does not stretch the heading to make room', () => {
        // A wrapped control would make the heading two lines tall.  One line is the claim.
        cy.mountUI(
            <Header as='h3' after={<Button role='cancel' size='xs'>Help</Button>}>
                Root CA Certificate
            </Header>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-header-text').should(($heading) => {
            const control = Cypress.$('.wrolpi-header-after')[0].getBoundingClientRect();
            expect($heading[0].getBoundingClientRect().height, 'heading is one row tall')
                .to.be.lessThan(control.height * 2);
        });
    });
});

describe('a heading opens a section rather than closing the last one', () => {
    it('leaves room above a heading that follows something', () => {
        /*
         * With no top margin a heading sat flush against the panel above it and read as part
         * of it -- "Tags" on /more/statistics touched the panel above with a 0px gap.
         */
        cy.mountUI(
            <div>
                <Panel>Files</Panel>
                <Header as='h3'>Tags</Header>
                <Panel>34 tags</Panel>
            </div>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-header').should(($header) => {
            const panel = Cypress.$('.wrolpi-panel')[0].getBoundingClientRect();
            const gap = $header[0].getBoundingClientRect().top - panel.bottom;
            expect(gap, 'gap above the heading').to.be.at.least(12);

            // And more above than below, because the heading belongs to what follows it.
            const below = Cypress.$('.wrolpi-panel')[1].getBoundingClientRect().top
                - $header[0].getBoundingClientRect().bottom;
            expect(gap, 'more air above the heading than below it').to.be.greaterThan(below);
        });
    });

    it('does not dent the top of its own container', () => {
        // A blanket margin would push a heading that opens a Panel away from the Panel's edge.
        cy.mountUI(<Panel><Header as='h3'>Downloads</Header><p>body</p></Panel>, {theme: 'light'});

        cy.get('.wrolpi-header').should(($header) => {
            expect(getComputedStyle($header[0]).marginTop, 'first child has no top margin')
                .to.equal('0px');
        });
    });
});

describe('a progress bar has room for the label inside it', () => {
    const bar = (props) => <Panel><Progress {...props}/></Panel>;

    it('leaves air above and below the text', () => {
        /*
         * The Status page draws 44 of these.  At 16px tall the 11px bold label left about
         * half a pixel of air, which is legible only if you already know what it says.
         */
        cy.mountUI(bar({percent: 62, label: 'CPU Usage (16 cores)'}), {theme: 'light'});

        cy.get('.wrolpi-progress').should(($bar) => {
            const box = $bar[0].getBoundingClientRect();
            expect(box.height, 'bar height').to.be.at.least(20);

            // The line box, measured from the text node itself rather than its stretched
            // flex container, which is inset:0 and therefore always the bar's height.
            const range = document.createRange();
            range.selectNodeContents($bar[0].querySelector('.wrolpi-progress-text'));
            expect(box.height - range.getBoundingClientRect().height, 'air around the label')
                .to.be.at.least(4);
        });
    });

    it('keeps a long label on one line', () => {
        /*
         * `white-space: nowrap` on the label.  The first version of this asserted the bar did
         * not get wider -- which it cannot: the label is `position: absolute; inset: 0`, so it
         * takes no part in its parent's width and the claim was unfalsifiable.  What a long
         * label really does is wrap to a second line inside a 22px bar and get cut in half by
         * the clip, so that is what is measured.
         */
        cy.mountUI(
            <div style={{width: 200}}>
                <Progress percent={40} label='nbd0 read 128.4 MBps sustained over 5 minutes'/>
            </div>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-progress-text').should(($text) => {
            const style = getComputedStyle($text[0]);
            expect(style.whiteSpace, 'label does not wrap').to.equal('nowrap');
            expect(style.textOverflow, 'and is cut with an ellipsis, not mid-glyph')
                .to.equal('ellipsis');

            const range = document.createRange();
            range.selectNodeContents($text[0]);
            expect(range.getClientRects().length, 'one line box').to.equal(1);
            /*
             * And that one line is genuinely wider than the space it has -- otherwise the
             * test proves nothing, since a label that fits occupies one line either way.
             * This is the case that used to wrap and get bisected by the clip.
             */
            expect(range.getBoundingClientRect().width, 'the label really is too long')
                .to.be.greaterThan($text[0].getBoundingClientRect().width);
        });
    });

    it('separates bars that are stacked directly on one another', () => {
        // The Status page's CPU and RAM bars are bare siblings in a Panel and were touching.
        cy.mountUI(
            <Panel>
                <Progress percent={20} label='CPU Usage'/>
                <Progress percent={70} label='RAM Usage'/>
            </Panel>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-progress').should(($bars) => {
            const [first, second] = [...$bars].map(b => b.getBoundingClientRect());
            expect(second.top - first.bottom, 'gap between stacked bars').to.be.at.least(6);
        });
    });

    it('adds no gap to a bar its container already spaces', () => {
        /*
         * The other half, and the reason for `* +` rather than a blanket margin: the drive
         * bandwidth bars each sit alone in a Grid column, which supplies the gutters.  A
         * blanket margin would add a second one on top.
         */
        cy.mountUI(
            <Panel>
                <div><Progress percent={20} label='nbd0 read'/></div>
                <div><Progress percent={30} label='nbd0 write'/></div>
            </Panel>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-progress').should(($bars) => {
            [...$bars].forEach((bar, index) =>
                expect(getComputedStyle(bar).marginTop, `bar ${index} is an only child`)
                    .to.equal('0px'));
        });
    });

    themeNames.forEach((theme) => {
        it(`reads its label against the track in ${theme}`, () => {
            /*
             * The label spans the whole bar, so it sits on the fill AND on the track.  This
             * asserts the track half only, and that is deliberate: over the FILL it measures
             * 5.49 in light but 2.35 / 2.48 / 2.74 in dark, night and amber -- below any
             * legibility floor.  Fixing that needs a per-half text color, which is a design
             * decision rather than a bug fix, so it is reported rather than quietly asserted
             * at a threshold low enough to pass.  See the note in ui.css.
             */
            cy.mountUI(bar({percent: 20, label: 'CPU Usage'}), {theme});

            cy.get('.wrolpi-progress').should(($bar) => {
                const text = toRgb(getComputedStyle(
                    $bar[0].querySelector('.wrolpi-progress-text')).color);
                const track = toRgb(getComputedStyle($bar[0]).backgroundColor);
                expect(contrast(text, track), 'label against the empty part of the bar')
                    .to.be.at.least(4.5);
            });
        });
    });

    it('keeps the indeterminate band inside the bar', () => {
        /*
         * The band slides on `margin-left` from -35% to 100%, so it genuinely does extend
         * past both edges and `getBoundingClientRect` reports that whether or not it is
         * painted.  The clip is what keeps it out of sight.
         *
         * The band is PINNED here rather than sampled mid-animation.  Reading a running
         * animation made this both flaky and, worse, permanently false for anyone with
         * Reduce Motion turned on: `prefers-reduced-motion` replaces the slide with
         * `width: 100%` and no negative margin, so the band never leaves the box and an
         * assertion that it does could not pass on that machine at all.
         */
        cy.mountUI(bar({indeterminate: true, label: 'Uploading…'}), {theme: 'light'});

        cy.get('.wrolpi-progress-indeterminate').should(($bar) => {
            expect(getComputedStyle($bar[0]).overflow, 'the bar clips its contents')
                .to.equal('hidden');

            const fill = $bar[0].querySelector('.wrolpi-progress-fill');
            // Where the animation's first keyframe puts it, held still.
            fill.style.animation = 'none';
            fill.style.width = '35%';
            fill.style.marginLeft = '-35%';

            const box = $bar[0].getBoundingClientRect();
            const band = fill.getBoundingClientRect();
            expect(band.left, 'the band does leave the box, so the clip is load-bearing')
                .to.be.lessThan(box.left - 1);
        });
    });

    it('does not move the band at all when motion is suppressed', () => {
        /*
         * The other branch, and the reason the test above pins rather than samples: with
         * Reduce Motion the bar fills instead of sliding, because motion was the only signal
         * it had.  A band that never moves must also never leave the box.
         */
        cy.mountUI(bar({indeterminate: true}), {theme: 'light'});
        cy.get('.wrolpi-progress-fill').should('exist');

        cy.document().then((doc) => {
            const probe = doc.createElement('style');
            probe.textContent = `
                .wrolpi-progress-indeterminate .wrolpi-progress-fill {
                    animation: none; width: 100%; opacity: 0.5;
                }`;
            doc.head.appendChild(probe);
        });

        cy.get('.wrolpi-progress-indeterminate').should(($bar) => {
            const box = $bar[0].getBoundingClientRect();
            const band = $bar[0].querySelector('.wrolpi-progress-fill').getBoundingClientRect();
            expect(band.left, 'band starts at the bar').to.be.closeTo(box.left, 2);
            expect(band.right, 'band ends at the bar').to.be.closeTo(box.right, 2);
        });
    });
});

describe('a table header is a surface, not just bold text', () => {
    themeNames.forEach((theme) => {
        it(`separates the header from every body row in ${theme}`, () => {
            /*
             * Mantine gives thead no background, so the header painted whatever was behind
             * the table -- which is exactly what an unstriped body row paints.  Against a
             * striped body the header read as one more stripe, and weight was the only
             * thing telling them apart.  None of this is visible to jsdom: the colors are
             * tokens, and "what is behind an unstriped row" is a question about painting.
             */
            cy.mountUI(sampleTable, {theme});

            cy.get('thead th').first().should(($th) => {
                const header = getComputedStyle($th[0]).backgroundColor;
                expect(header, 'the header paints a surface of its own')
                    .to.not.match(/^rgba\(.*,\s*0(\.0+)?\)$/);

                const page = hexToRgb(getComputedStyle(document.documentElement)
                    .getPropertyValue('--bg').trim());
                const rows = [...Cypress.$('tbody tr')].map(row => {
                    /*
                     * An unstriped row paints nothing, so what shows through is the page.
                     * That is `--bg`, taken from the token -- NOT
                     * getComputedStyle(documentElement).backgroundColor, which is
                     * `rgba(0, 0, 0, 0)` because `body` carries the page color and the root
                     * element carries none.  Comparing an opaque header against that string
                     * can never fail, which is how this passed before it was fixed.
                     */
                    const own = getComputedStyle(row).backgroundColor;
                    return /^rgba\(.*,\s*0(\.0+)?\)$/.test(own) ? page : own;
                });
                expect(rows.length).to.be.greaterThan(2);
                // Both kinds have to be present or the comparison only covers one of them.
                expect(new Set(rows).size, 'the body is striped').to.equal(2);
                rows.forEach((row, index) => {
                    expect(header, `header vs body row ${index}`).to.not.equal(row);
                });
            });
        });

        it(`rules off the header more heavily than it rules between rows in ${theme}`, () => {
            /*
             * The header/body division is the one that carries meaning -- everything above
             * it names, everything below is data -- so it is the one line allowed to be
             * loud.  Per theme, because a theme is free to restyle borders.
             */
            cy.mountUI(sampleTable, {theme});

            cy.get('thead th').first().should(($th) => {
                const header = getComputedStyle($th[0]);
                const row = getComputedStyle(Cypress.$('tbody tr')[0]);
                expect(parseFloat(header.borderBottomWidth), 'header rule width')
                    .to.be.greaterThan(parseFloat(row.borderBottomWidth));
            });
        });
    });
});

describe('table rules', () => {
    themeNames.forEach((theme) => {
        it(`keeps the rule between rows quieter than the table outline in ${theme}`, () => {
            /*
             * With a rule under every row at full border strength, a long table reads as a
             * stack of boxes rather than a list.  `--table-line` is the quieter token; the
             * outline around the table is not a row rule and keeps `--border`.
             *
             * Measured as contrast against the row's own surface rather than compared to a
             * token, so the claim is about what the eye gets.
             */
            cy.mountUI(sampleTable, {theme});

            cy.get('tbody tr').first().should(($row) => {
                const table = Cypress.$('table')[0];
                const token = (name) => hexToRgb(getComputedStyle(document.documentElement)
                    .getPropertyValue(name).trim());
                /*
                 * Against `--panel`, the surface a row paints on.  Not against the root
                 * background: nothing paints <html> under a mounted component, so it reads
                 * `rgba(0, 0, 0, 0)`, and measuring both lines against black ranks the
                 * *paler* one as louder -- which is how this assertion first passed
                 * backwards.
                 */
                const surface = token('--panel');
                const rule = contrast(getComputedStyle($row[0]).borderBottomColor, surface);
                const outline = contrast(getComputedStyle(table).borderTopColor, surface);

                expect(rule, 'row rule is quieter than the table outline').to.be.lessThan(outline);
            });
        });

        it(`draws nothing between the cells of a row in ${theme}`, () => {
            cy.mountUI(sampleTable, {theme});

            cy.get('tbody tr').first().find('td').first().should(($cell) => {
                expect(parseFloat(getComputedStyle($cell[0]).borderRightWidth),
                    'no rule between columns').to.equal(0);
            });
        });
    });
});

describe('a file row lines its icon up with its name', () => {
    /*
     * The file browser writes an icon and a filename as inline siblings in one cell.  An
     * inline SVG sits on the text baseline, so a 24px glyph beside 13px text hangs well
     * above it -- the icon looked centred in the row and the name looked like it was
     * resting on the icon's floor.
     *
     * Purely a question of layout: jsdom returns zeros from getBoundingClientRect, so
     * nothing there can tell a centred glyph from one hanging off a baseline.
     */
    /*
     * 24px, which is what the app renders.  A file row calls `<FileIcon size={null}/>`, and
     * a null size falls past Icon's 'small' default to Tabler's own 24.  The default 16px
     * icon is a much easier centring case and can look fine while the real one is visibly
     * off, so a fixture using it would be testing a size the file browser never draws.
     */
    const fileRow = <Table>
        <Table.Body>
            <Table.Row>
                <Table.Cell className='file-path'>
                    <Icon name='file audio' size={24}/>
                    big_buck_bunny.mp3
                </Table.Cell>
            </Table.Row>
        </Table.Body>
    </Table>;

    // A folder that is also ignored draws two glyphs before its name; they touched too.
    const folderRow = <Table>
        <Table.Body>
            <Table.Row>
                <Table.Cell className='file-path'>
                    <Icon name='folder' size={24}/>
                    <Icon name='eye slash' size={24}/>
                    config/
                </Table.Cell>
            </Table.Row>
        </Table.Body>
    </Table>;

    it('centres the glyph against the text rather than sitting it on the baseline', () => {
        cy.mountUI(fileRow, {theme: 'light'});

        cy.get('td.file-path svg').should(($icon) => {
            const icon = $icon[0].getBoundingClientRect();
            // The text node's own box, which is what the eye compares the icon to.
            const range = document.createRange();
            range.selectNodeContents($icon[0].nextSibling);
            const text = range.getBoundingClientRect();

            const iconCentre = icon.top + icon.height / 2;
            const textCentre = text.top + text.height / 2;
            expect(Math.abs(iconCentre - textCentre), 'icon centre vs text centre')
                .to.be.at.most(2);
        });
    });

    it('leaves a gap between the glyph and the name', () => {
        // They touched: the folder icon ran into the first letter of its own folder name.
        cy.mountUI(fileRow, {theme: 'light'});

        cy.get('td.file-path svg').should(($icon) => {
            const range = document.createRange();
            range.selectNodeContents($icon[0].nextSibling);
            const gap = range.getBoundingClientRect().left - $icon[0].getBoundingClientRect().right;
            expect(gap, 'gap between icon and filename').to.be.greaterThan(2);
        });
    });

    it('keeps two glyphs apart, and both clear of the name', () => {
        cy.mountUI(folderRow, {theme: 'light'});

        cy.get('td.file-path svg').should(($icons) => {
            expect($icons.length, 'two glyphs').to.equal(2);
            const [folder, ignored] = [...$icons].map(icon => icon.getBoundingClientRect());
            expect(ignored.left - folder.right, 'gap between the two glyphs')
                .to.be.greaterThan(2);

            const range = document.createRange();
            range.selectNodeContents($icons[1].nextSibling);
            expect(range.getBoundingClientRect().left - ignored.right, 'gap before the name')
                .to.be.greaterThan(2);

            // And the second glyph is centred on the name as well, not just the first.
            const text = range.getBoundingClientRect();
            expect(Math.abs((ignored.top + ignored.height / 2) - (text.top + text.height / 2)),
                'second glyph centre vs text centre').to.be.at.most(2);
        });
    });
});

describe('StatisticGroup separates its statistics with nothing but space', () => {
    /*
     * The group has no frame, no rules between cells and no surface of its own: the
     * statistics sit on whatever they were dropped onto and take its color.  That leaves
     * the gap as the only thing keeping them apart, and `auto-fit` decides how many rows
     * there are at paint time -- so whether they actually stay apart is a question only a
     * browser can answer.  jsdom has no tracks, no rows and no widths.
     */

    // Narrow enough that six statistics cannot fit on one row at a 150px minimum.
    /*
     * "Narrow" has to mean narrow RELATIVE TO THE TYPE, or the width stops meaning anything
     * when the interface scale changes.  At a fixed 340px this held two 150px statistic
     * tracks; the scale took the track to 165px and 340px became a single column, so a test
     * about the gap between columns had no second column to measure.
     */
    const inNarrowColumn = (children) =>
        <div style={{width: `${Math.round(340 * uiScale())}px`}}>{children}</div>;

    const sixStatistics = <StatisticGroup>
        <Statistic value='1,432' label='Videos'/>
        <Statistic value='896' label='Archives'/>
        <Statistic value='12,904' label='Files'/>
        <Statistic value='87.4 GiB' label='Free space'/>
        <Statistic value='14' label='Zim files'/>
        <Statistic value='312' label='eBooks'/>
    </StatisticGroup>;

    const rowTops = (cells) => [...new Set(
        [...cells].map((cell) => Math.round(cell.getBoundingClientRect().top))
    )].sort((a, b) => a - b);

    it('wraps into rows at this width, so the rest of these tests mean something', () => {
        cy.mountUI(inNarrowColumn(sixStatistics));

        cy.get('.wrolpi-statistic-cell').should(($cells) =>
            expect(rowTops($cells).length, 'rows the group wrapped into').to.be.greaterThan(1));
    });

    it('leaves real space between wrapped rows', () => {
        /*
         * With nothing drawn between them, the space *is* the separation.  The old group ruled
         * columns only -- a `border-right` on every cell but the last, which says nothing about
         * rows -- so wrapped rows sat flush and the Docs page's seven statistics ran together
         * into one block on a phone.  A row boundary has to be a gap you can see.
         */
        cy.mountUI(inNarrowColumn(sixStatistics));

        cy.get('.wrolpi-statistic-cell').should(($cells) => {
            const cells = [...$cells].map((cell) => cell.getBoundingClientRect());
            const tops = rowTops($cells);

            for (let row = 1; row < tops.length; row++) {
                const previousRowBottom = Math.max(...cells
                    .filter((rect) => Math.round(rect.top) === tops[row - 1])
                    .map((rect) => rect.bottom));
                expect(tops[row] - previousRowBottom, `space above row ${row + 1}`)
                    .to.be.at.least(12);
            }
        });
    });

    it('leaves more space between columns than between rows', () => {
        /*
         * Two statistics side by side have only air between them, and a value sitting close to
         * the label of the one beside it reads as a single column of text.  Stacked statistics
         * already have the label's own line between them, so they need less.
         */
        cy.mountUI(inNarrowColumn(sixStatistics));

        cy.get('.wrolpi-statistic-group').should(($group) => {
            const styles = getComputedStyle($group[0]);
            const columnGap = parseFloat(styles.columnGap);
            const rowGap = parseFloat(styles.rowGap);
            expect(rowGap, 'row gap').to.be.at.least(12);
            expect(columnGap, 'column gap is the wider of the two').to.be.greaterThan(rowGap);
        });

        cy.get('.wrolpi-statistic-cell').should(($cells) => {
            const cells = [...$cells].map((cell) => cell.getBoundingClientRect());
            const firstRow = cells
                .filter((rect) => Math.round(rect.top) === rowTops($cells)[0])
                .sort((a, b) => a.left - b.left);

            expect(firstRow.length, 'columns in the first row').to.be.greaterThan(1);
            for (let column = 1; column < firstRow.length; column++) {
                expect(firstRow[column].left - firstRow[column - 1].right, 'space between columns')
                    .to.be.at.least(20);
            }
        });
    });

    it('takes no color of its own, so it sits on the surface it is given', () => {
        /*
         * This is the point of having no chrome: dropped on the page it reads as page, dropped
         * in a Panel it reads as panel.  A background on the group or a cell -- which is how
         * this was built first, to carry hairlines -- would show as a patch of the wrong color
         * on every surface but the one it was picked for.
         */
        cy.mountUI(<div style={{background: 'rgb(1, 2, 3)', padding: 10}}>{sixStatistics}</div>);

        cy.get('.wrolpi-statistic-group').should(($group) => {
            const styles = getComputedStyle($group[0]);
            expect(styles.backgroundColor, 'group is transparent').to.equal('rgba(0, 0, 0, 0)');
            expect(styles.borderTopWidth, 'no frame').to.equal('0px');
            expect(styles.borderRightWidth, 'no frame').to.equal('0px');
            expect(styles.borderBottomWidth, 'no frame').to.equal('0px');
            expect(styles.borderLeftWidth, 'no frame').to.equal('0px');
            expect(styles.outlineStyle, 'no outline standing in for a frame').to.equal('none');
        });

        cy.get('.wrolpi-statistic-cell').each(($cell) => {
            const styles = getComputedStyle($cell[0]);
            expect(styles.backgroundColor, 'cell is transparent').to.equal('rgba(0, 0, 0, 0)');
            expect(styles.borderRightWidth, 'no rule between cells').to.equal('0px');
            expect(styles.outlineStyle, 'no rule between cells').to.equal('none');
        });
    });

    it('clears whatever precedes it, but does not indent itself', () => {
        /*
         * Nothing frames the group any more, so a Header directly above it put the heading
         * text against the first row of values.  A plain `margin-top` fixed that and broke
         * Apps, which opens each of its Panels with a group: the values were pushed down off
         * the panel's top padding while the bottom stayed put, leaving every panel lopsided.
         * So the margin is conditional on having a sibling before it.
         */
        cy.mountUI(<div>
            <div className='probe-panel' style={{padding: 20}}>
                <StatisticGroup>
                    <Statistic value='1,097' label='All files'/>
                </StatisticGroup>
            </div>
            <div className='probe-with-header' style={{padding: 20}}>
                <Header as='h2'>Files</Header>
                <StatisticGroup>
                    <Statistic value='1,097' label='All files'/>
                </StatisticGroup>
            </div>
        </div>);

        cy.get('.probe-panel .wrolpi-statistic-group').should(($group) =>
            expect(getComputedStyle($group[0]).marginTop, 'first child of a panel adds nothing')
                .to.equal('0px'));

        cy.get('.probe-with-header').then(($panel) => {
            const header = $panel[0].querySelector('.wrolpi-header').getBoundingClientRect();
            const group = $panel[0].querySelector('.wrolpi-statistic-group').getBoundingClientRect();
            expect(group.top - header.bottom, 'space below a heading').to.be.at.least(10);
        });
    });

    it('hides the cell of a statistic that rendered nothing', () => {
        /*
         * Status omits the fan reading on a device with no fan connector -- most of them --
         * by returning null from FanRPMStatistic.  The group still emits its cell, because it
         * cannot render a child to find out, so `:empty` has to take the cell out of the grid.
         * Left in, it held a track open and opened a hole in the middle of the row.
         */
        const NoFanFitted = () => null;
        cy.mountUI(<StatisticGroup>
            <Statistic value='0.4' label='1 Min. Load'/>
            <NoFanFitted/>
            <Statistic value='48' label='Temp C'/>
        </StatisticGroup>);

        cy.get('.wrolpi-statistic-cell').should('have.length', 3);
        cy.get('.wrolpi-statistic-cell').filter(':empty').should('not.be.visible');
        cy.get('.wrolpi-statistic-cell').filter(':empty').should(($cell) =>
            expect($cell[0].getBoundingClientRect().width, 'the empty cell takes no track').to.equal(0));
    });

    themeNames.forEach((theme) => {
        it(`reads its value and label from ${theme}'s tokens`, () => {
            // The contrast between value and label is all that structures a statistic now that
            // there is no cell around it, so both colors have to resolve in every theme.
            cy.mountUI(inNarrowColumn(sixStatistics), {theme});

            cy.get('.wrolpi-statistic-value').first().then(($value) => {
                const value = getComputedStyle($value[0]).color;

                cy.get('.wrolpi-statistic-label').first().should(($label) => {
                    const label = getComputedStyle($label[0]).color;
                    expect(value, 'value color resolved').to.match(/^rgba?\(/);
                    expect(label, 'label color resolved').to.match(/^rgba?\(/);
                    // The label is the muted token and the value is body text; if either fell
                    // back the two would come out the same and the statistic would flatten.
                    expect(label, 'label is distinct from the value').to.not.equal(value);
                });
            });
        });
    });
});

describe('a tag is legible in every theme, whatever color the user picked', () => {
    /*
     * Tag colors are the user's, stored per tag -- the only thing in the app painted with a
     * value no theme chose.  Tags.js calculates black or light text against that fill, and
     * night discards the fill entirely (a filled tag would be a bright patch) while amber
     * replaces it with its own.  Whether the text still reads afterwards is a question about
     * resolved color against a real painted surface, so it can only be asked here.
     */

    // The extremes of the black-or-light decision, plus a mid tone.
    const TAG_COLORS = [
        ['Reference', '#f2f2f2'],   // near-white: text is calculated black
        ['Archived', '#1b1c1d'],    // near-black: text is calculated light
        ['Water', '#2185d0'],
    ];

    const tags = <div>
        {TAG_COLORS.map(([name, color]) => <span
            key={name}
            className='wrolpi-label wrolpi-tag'
            data-tag={name}
            style={{'--label-color': color, '--label-text': contrastingColor(color)}}
        >{name}</span>)}
    </div>;

    themeNames.forEach((theme) => {
        TAG_COLORS.forEach(([name]) => {
            it(`reads ${name} against its real surface in ${theme}`, () => {
                cy.mountUI(tags, {theme});

                /*
                 * 4.5:1 is WCAG AA for body text.  Before this, night measured 1.1:1 on a
                 * near-white tag -- the black text calculated for that fill, painted onto a
                 * transparent tag over a near-black page.  The tag was readable only as an
                 * empty outline.
                 */
                cy.contrastRatio(`[data-tag="${name}"]`).should('be.at.least', 4.5);
            });
        });
    });

    it('detects the unreadable tag this started as, so the check has teeth', () => {
        /*
         * The original defect, reproduced deliberately: the calculated text color written to
         * `color` inline, which no stylesheet rule can outrank.  In night the tag becomes a
         * transparent outline over a near-black page, so the black text calculated for a
         * near-white fill is painted onto near-black.
         *
         * Asserting that this IS unreadable proves contrastRatio measures the surface actually
         * behind the text rather than the tag's own missing background.  A contrast check that
         * has never gone red is indistinguishable from one that cannot.
         */
        cy.mountUI(
            <span
                className='wrolpi-label wrolpi-tag'
                data-tag='Legacy'
                style={{'--label-color': '#f2f2f2', color: contrastingColor('#f2f2f2')}}
            >Reference</span>,
            {theme: 'night'},
        );

        cy.contrastRatio('[data-tag="Legacy"]').should('be.lessThan', 1.5);
    });

    it('is at least as large as the Semantic label it replaced', () => {
        // The first pass came out at 11.5px against Semantic's 12px and read as shrunken.
        // A tag is a hit target as well as a word, so it also has to stay tall enough to hit.
        cy.mountUI(tags);

        cy.get('.wrolpi-tag').first().should(($tag) => {
            expect(parseFloat(getComputedStyle($tag[0]).fontSize), 'font size').to.be.at.least(12);
            expect($tag[0].getBoundingClientRect().height, 'height').to.be.at.least(26);
        });
    });

    it("sets a tag's word within a fifth of the body text it sits beside", () => {
        /*
         * Matching Semantic was the wrong target for this one.  A tag is not an annotation on
         * something else -- it is the whole content of its chip, and the thing a user scans a
         * wall of them for -- so it wants to read as text, not as a footnote.  At 12.5px design
         * against a 16px base it was 78% of the prose around it, and on the dashboard, where
         * the tags ARE the content, that read as small.
         *
         * Expressed as a ratio rather than a pixel count so the assertion cannot be satisfied
         * by the interface scale alone: 1.1 raised the tag to 13.75px and the prose to 17.6px
         * at the same time, leaving the tag exactly as small next to it as before.
         */
        cy.mountUI(tags);

        cy.get('.wrolpi-tag').first().should(($tag) => {
            const tag = parseFloat(getComputedStyle($tag[0]).fontSize);
            const body = parseFloat(getComputedStyle(Cypress.$('html')[0]).fontSize);
            expect(tag / body, "the tag's share of body text").to.be.at.least(0.8);
            // And is still a chip rather than prose in a colored box.
            expect(tag / body, 'but not the same size as prose').to.be.at.most(0.95);
        });
    });
});

describe('a tag looks like a physical tag', () => {
    const tag = <span
        className='wrolpi-label wrolpi-tag'
        style={{'--label-color': '#2185d0', '--label-text': '#ffffff'}}
    >Water</span>;

    it('has a pointed left edge that spans the full height', () => {
        /*
         * The point is a square rotated 45 degrees behind the left edge.  Its diagonal has to
         * equal the body's height, or the two edges meet the body short of its corners and the
         * result reads as a notch stuck on the side rather than one tag-shaped outline.
         */
        cy.mountUI(tag);

        cy.get('.wrolpi-tag').should(($tag) => {
            const el = $tag[0];
            const height = el.getBoundingClientRect().height;
            const side = parseFloat(getComputedStyle(el, '::before').width);
            expect(side, 'the point is drawn at all').to.be.greaterThan(0);
            expect(side * Math.SQRT2, "the point's diagonal matches the body height")
                .to.be.closeTo(height, 2);
        });
    });

    /*
     * Where the tip of the point actually lands, relative to the body's left edge.
     *
     * The square's box spans [-side, 0] in padding-box coordinates (`right: 100%`), is shifted
     * by the transform's resolved horizontal translation, and then rotates about its own centre
     * -- so the tip reaches half a diagonal beyond that centre.  Padding-box coordinates are
     * inside the border, which is the whole reason the point needed nudging, so the border
     * width comes off at the end.
     */
    const tipOffset = (el) => {
        const before = getComputedStyle(el, '::before');
        const side = parseFloat(before.width);
        const translateX = parseFloat(before.transform.match(/matrix\(([^)]+)\)/)[1].split(',')[4]);
        const centre = -side + translateX + side / 2;
        return centre - (side * Math.SQRT2 / 2) - parseFloat(getComputedStyle(el).borderLeftWidth);
    };

    /* Where the point's centre sits, relative to the body's visible (border-box) left edge. */
    const pointCentreOffset = (el) => {
        const before = getComputedStyle(el, '::before');
        const side = parseFloat(before.width);
        const translateX = parseFloat(before.transform.match(/matrix\(([^)]+)\)/)[1].split(',')[4]);
        return (-side + translateX + side / 2) - parseFloat(getComputedStyle(el).borderLeftWidth);
    };

    it('grows the point out of the left edge rather than setting it into the body', () => {
        /*
         * `right: 100%` positions against the containing block's *padding* box, and the body
         * carries a 1px border -- so a square centred there sits a pixel inside the visible left
         * edge, and the point reads as set into the tag instead of growing out of it.
         *
         * Asserting the tip lands somewhere far to the left does not catch this: the un-nudged
         * version's tip is only 2px further right, still well clear of the body.  The claim is
         * about where the point is *centred*, which is the thing that differs.
         */
        cy.mountUI(tag);

        cy.get('.wrolpi-tag').should(($tag) =>
            expect(pointCentreOffset($tag[0]), 'the point is centred left of the visible edge')
                .to.be.at.most(-2));
    });

    it('reserves exactly the room the point takes', () => {
        // Without a margin covering the full protrusion the point prints over whatever sits to
        // its left -- the previous tag in the row.  The old value, 15px, was 2px short of this.
        cy.mountUI(tag);

        cy.get('.wrolpi-tag').should(($tag) => {
            const el = $tag[0];
            const needed = Math.abs(tipOffset(el));
            const margin = parseFloat(getComputedStyle(el).marginLeft);
            expect(margin, 'margin covers the protrusion').to.be.at.least(needed - 0.5);
            // And is not wasteful about it, or tags drift apart for no visible reason.
            expect(margin, 'margin is not far beyond it').to.be.at.most(needed + 3);
        });
    });

    it('does not print the point over the first letter', () => {
        /*
         * A positioned pseudo-element paints above the parent's text, not behind it, and the
         * point's inner half lies over the body.  Removing the left padding once hid the first
         * character of every tag: "Water" read as "ater".
         */
        cy.mountUI(tag);

        cy.get('.wrolpi-tag').should(($tag) => {
            const el = $tag[0];
            const styles = getComputedStyle(el);
            const overlapIntoBody = parseFloat(getComputedStyle(el, '::before').width) / 2;
            const textStartsAt = parseFloat(styles.paddingLeft) + parseFloat(styles.borderLeftWidth);
            expect(textStartsAt, 'text starts clear of the point').to.be.greaterThan(overlapIntoBody);
        });
    });

    it('keeps wrapped rows of tags off each other', () => {
        // Tags wrap wherever they are listed, and a wrapped row was sitting on the row above.
        cy.mountUI(<div style={{width: 240}}>
            {['Water', 'Food', 'Medical', 'Shelter', 'Power', 'Comms'].map((name) => <span
                key={name}
                className='wrolpi-label wrolpi-tag'
                style={{'--label-color': '#2185d0', '--label-text': '#ffffff'}}
            >{name}</span>)}
        </div>);

        cy.get('.wrolpi-tag').should(($tags) => {
            const rects = [...$tags].map((el) => el.getBoundingClientRect());
            const rows = [...new Set(rects.map((r) => Math.round(r.top)))].sort((a, b) => a - b);
            expect(rows.length, 'the tags wrapped').to.be.greaterThan(1);

            for (let row = 1; row < rows.length; row++) {
                const previousBottom = Math.max(...rects
                    .filter((r) => Math.round(r.top) === rows[row - 1])
                    .map((r) => r.bottom));
                expect(rows[row] - previousBottom, `gap above row ${row + 1}`).to.be.at.least(3);
            }
        });
    });
});

describe('tabs', () => {
    themeNames.forEach((theme) => {
        it(`gives an inactive tab no surface of its own in ${theme}`, () => {
            /*
             * A tab is a NavLink in the app's nav bars but a <button> on Inventory and in the
             * gallery, and a button carries the UA's `buttonface` background -- rgb(239,239,239).
             * Only the active tab set a background, so every inactive one was a near-white block
             * in dark, night and amber.
             */
            cy.mountUI(<TabBar>
                <button className={tabClassName(true)}>Videos</button>
                <button className={tabClassName(false)}>Channels</button>
            </TabBar>, {theme});

            cy.contains('button', 'Channels').should(($tab) =>
                expect(getComputedStyle($tab[0]).backgroundColor, 'inactive tab is transparent')
                    .to.equal('rgba(0, 0, 0, 0)'));
        });
    });
});

describe('a toast is readable in every theme', () => {
    /*
     * Mantine paints a dark-scheme notification title with `--mantine-color-white`, and the
     * bridge aliases that to `--btn-text` -- the text drawn on a filled button, which is
     * near-black in dark, night and amber.  The title measured about 1.1:1 against the toast's
     * own surface: present, and invisible.
     *
     * Only a browser can catch that.  jsdom resolves no `var()`, so the title's color there is
     * the literal string `var(--mantine-color-white)` and every contrast check passes.
     */

    /*
     * Mounts once, with the theme, and raises a toast.  Mounting a second time to raise it --
     * which is how this was first written -- resets the theme to the default, so all four
     * per-theme cases silently ran in light and none of them could fail.
     */
    const showToast = (theme) => {
        cy.mountUI(<>
            <Notifications position='top-right' limit={5}/>
            <button type='button' onClick={() => toast({
                type: 'error', title: 'Download failed',
                description: 'HTTP 403 from the remote server after 3 attempts.',
            })}>Raise one</button>
        </>, {theme});
        cy.contains('button', 'Raise one').click();
        cy.get('[class*="mantine-Notification-root"]').should('exist');
    };

    themeNames.forEach((theme) => {
        it(`reads its title and message in ${theme}`, () => {
            showToast(theme);

            // WCAG AA for both.  The description is the message itself, so it is held to the
            // same bar as the title rather than treated as decoration.
            cy.contrastRatio('[class*="mantine-Notification-title"]').should('be.at.least', 4.5);
            cy.contrastRatio('[class*="mantine-Notification-description"]').should('be.at.least', 4.5);
        });
    });

    monochromeThemes.forEach((theme) => {
        it(`tells its four kinds apart in ${theme}, which is the bug roles exist for`, () => {
            /*
             * The end of the chain, measured rather than inferred.  The jest tests assert the
             * Mantine variable NAME on the style attribute, which would still pass if someone
             * put four hue names back -- four distinct strings that resolve to two colors here.
             * This reads what is painted.
             */
            cy.mountUI(<>
                <Notifications position='top-right' limit={5}/>
                <button type='button' onClick={() => {
                    /*
                     * Mantine's notification store is module scope and outlives the mount, so
                     * a toast raised by an earlier test in this file is still queued here --
                     * which is how this first ran with five.
                     */
                    clearToasts();
                    ['info', 'success', 'warning', 'error'].forEach(type =>
                        toast({type, title: type, time: 0}));
                }}>Raise all four</button>
            </>, {theme});

            cy.contains('button', 'Raise all four').click();

            cy.get('[class*="mantine-Notification-root"]').should('have.length', 4);
            cy.get('[class*="mantine-Notification-root"]').should(($toasts) => {
                const colors = [...$toasts].map(t =>
                    getComputedStyle(t).getPropertyValue('--notification-color').trim());
                expect(new Set(colors).size, `four distinct kinds, got ${colors.join(' ')}`)
                    .to.equal(4);

                /*
                 * Distinctness alone does not catch the regression this is for.  Reverting to
                 * hue names gives four distinct values in night too -- blue, green, yellow and
                 * red are not the same color there.  What they are is cramped and badly
                 * ranked, with `--blue` at 2.29:1 against the toast surface: present, and
                 * invisible.  So the floor is the assertion that has teeth.
                 */
                const surface = toRgb(getComputedStyle($toasts[0]).backgroundColor);
                colors.forEach((color, index) => {
                    expect(contrast(toRgb(color), surface), `toast ${index} against its surface`)
                        .to.be.at.least(3);
                });
            });
        });

        it(`tells four Messages apart in ${theme}`, () => {
            cy.mountUI(
                <Panel>
                    <Message kind='info' title='info'/>
                    <Message kind='success' title='success'/>
                    <Message kind='warning' title='warning'/>
                    <Message kind='error' title='error'/>
                </Panel>,
                {theme},
            );

            cy.get('.wrolpi-message').should(($all) => {
                expect($all.length).to.equal(4);
                const colors = [...$all].map(m =>
                    getComputedStyle(m).getPropertyValue('--message-color').trim());
                expect(new Set(colors).size, `four distinct kinds, got ${colors.join(' ')}`)
                    .to.equal(4);
            });
        });
    });

    it('keeps the title more prominent than the message', () => {
        /*
         * Night and amber drop the description's muting, because `--muted` on a panel is 2.0:1
         * in night.  Weight has to carry the hierarchy once color cannot.
         */
        showToast('night');

        cy.get('[class*="mantine-Notification-title"]').then(($title) => {
            cy.get('[class*="mantine-Notification-description"]').should(($description) => {
                const weight = (el) => parseInt(getComputedStyle(el).fontWeight, 10);
                expect(weight($title[0]), 'title weight')
                    .to.be.greaterThan(weight($description[0]));
            });
        });
    });

    it('takes its surface from the theme, not from Mantine', () => {
        // A toast is a panel.  Left to Mantine it would be `--mantine-color-body`, which is not
        // one of our tokens and does not follow night or amber.
        showToast('night');

        cy.get('[class*="mantine-Notification-root"]').should(($toast) => {
            const panel = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim();
            expect(getComputedStyle($toast[0]).backgroundColor).to.equal(hexToRgb(panel));
        });
    });
});

/*
 * The color a box actually shows, looking through the layers in the order given.
 *
 * The order is the caller's business, because "the background" is ambiguous once
 * pseudo-elements are involved and picking wrong makes a test vacuous rather than wrong.
 * A Skeleton is three layers: the element paints nothing, ::before paints
 * --mantine-color-body (our `--bg`) at z-index 10, and ::after paints the bar the user
 * actually sees -- --mantine-color-gray-3 in light, --mantine-color-dark-4 in dark, which
 * themes/mantine.ts maps to `--head` and `--border` -- at z-index 11, on top.  Walk from
 * the element outward and you get `--bg` and compare the page background to the panel,
 * which differ by design in every theme, so the bars could vanish and nothing would fail.
 */
const paintedBackground = (el, order = [null, '::before', '::after']) => {
    for (const pseudo of order) {
        const color = getComputedStyle(el, pseudo).backgroundColor;
        if (color && !/^rgba\(.*,\s*0(\.0+)?\)$/.test(color) && color !== 'transparent') {
            return color;
        }
    }
    return null;
};

describe('a loading placeholder is visible on the surface it covers', () => {
    themeNames.forEach((theme) => {
        it(`separates the skeleton from the panel in ${theme}`, () => {
            /*
             * `--head` and `--border` are what the bars come out as, and neither was chosen
             * with a panel behind it in mind.  If they land on the panel's own color there
             * is no placeholder at all, only an empty box, and jsdom cannot see that.
             */
            cy.mountUI(<Panel><Placeholder lines={3}/></Panel>, {theme});

            cy.get('.mantine-Skeleton-root').first().should(($line) => {
                // Topmost layer first for the bar; the panel paints on the element itself.
                const line = paintedBackground($line[0], ['::after', '::before', null]);
                const panel = paintedBackground($line[0].closest('.wrolpi-panel'), [null]);
                expect(line, 'the skeleton paints something').to.not.equal(null);
                expect(panel, 'the panel paints something').to.not.equal(null);
                expect(line, 'the skeleton is not the panel it sits on').to.not.equal(panel);
            });
        });
    });

    it('keeps the last line short so the block reads as text', () => {
        // The jest test asserts the declared width; this asserts it survived layout.
        cy.mountUI(<Panel><Placeholder lines={3}/></Panel>, {theme: 'light'});

        cy.get('.mantine-Skeleton-root').should(($lines) => {
            const widths = [...$lines].map(line => line.getBoundingClientRect().width);
            expect(widths[2], 'last line').to.be.lessThan(widths[0] * 0.75);
            expect(widths[0], 'first two lines are the same length').to.be.closeTo(widths[1], 1);
        });
    });
});

describe('a spinner is visible in every theme', () => {
    themeNames.forEach((theme) => {
        it(`resolves the loader color in ${theme}`, () => {
            // `color='var(--blue)'` reaches Mantine as a string it does not understand and
            // passes straight through to CSS.  If the token were misspelled the property
            // would resolve to nothing and the spinner would paint in currentColor -- or,
            // for the segmented variants, not at all.
            cy.mountUI(<Loading>Loading backups…</Loading>, {theme});

            cy.get('.mantine-Loader-root').should(($loader) => {
                const blue = getComputedStyle(document.documentElement)
                    .getPropertyValue('--blue').trim();
                const resolved = getComputedStyle($loader[0])
                    .getPropertyValue('--loader-color').trim();
                expect(resolved, '--loader-color resolved through the token')
                    .to.be.oneOf([blue, hexToRgb(blue)]);
            });

            cy.get('.mantine-Loader-root').should('be.visible');
        });
    });
});

describe('an icon stack carries the surface it was placed on', () => {
    /*
     * The corner glyph paints a disc behind itself so the two sets of strokes do not cross.
     * That disc was hardcoded to the page background, which is right in the nav bar and
     * wrong inside the file browser's filled blue button, where it read as a hole punched
     * through the button.  It is now `--icon-stack-bg`, and the call site says.
     */
    themeNames.forEach((theme) => {
        it(`matches a filled button in ${theme}`, () => {
            cy.mountUI(
                <Button color='blue'>
                    {/* No style: a filled button supplies the surface through the cascade,
                        which is the point -- the call site cannot know it is about to be
                        disabled and repainted. */}
                    <IconStack corner={<Icon name='add'/>} label='New folder'>
                        <Icon name='folder'/>
                    </IconStack>
                </Button>,
                {theme},
            );

            cy.get('.wrolpi-icon-stack-corner').should(($corner) => {
                const disc = getComputedStyle($corner[0]).backgroundColor;
                const button = getComputedStyle($corner[0].closest('button')).backgroundColor;
                expect(disc, 'the disc is the button fill').to.equal(button);
            });
        });
    });

    it('follows a filled button when it is disabled', () => {
        /*
         * The file browser's New Folder button is disabled in WROL mode.  The disc has to
         * follow the button into that state, whatever the state happens to look like -- and
         * it has now looked like two different things.  Mantine used to repaint a disabled
         * button with `--mantine-color-disabled`, so a disc pinned to `--blue` became a blue
         * chip on a grey surface; disabled buttons keep their own fill now, so the disc must
         * be blue again.  This caught the disc still pinned to the old grey the moment that
         * changed, which is exactly what it is for.
         */
        cy.mountUI(
            <Button color='blue' disabled>
                <IconStack corner={<Icon name='add'/>} label='New folder'>
                    <Icon name='folder'/>
                </IconStack>
            </Button>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-icon-stack-corner').should(($corner) => {
            const disc = getComputedStyle($corner[0]).backgroundColor;
            const button = getComputedStyle($corner[0].closest('button')).backgroundColor;
            expect(disc, 'the disc is the disabled fill').to.equal(button);
        });
    });

    it('takes the surface from an ancestor, which is how the nav bar sets it', () => {
        /*
         * The nav bar's color is a user setting written inline on the <nav>, so the stack
         * inside it cannot name a token.  It sets --icon-stack-bg on the bar itself and lets
         * it inherit -- and this is the test for that, because setting the property on the
         * stack (as the file browser does) would pass even if inheritance were broken.
         */
        cy.mountUI(
            <div style={{background: 'var(--red)', '--icon-stack-bg': 'var(--red)', padding: 20}}>
                <IconStack corner={<Icon name='question'/>} label='WiFi status unknown'>
                    <Icon name='wifi'/>
                </IconStack>
            </div>,
            {theme: 'light'},
        );

        cy.get('.wrolpi-icon-stack-corner').should(($corner) => {
            const red = getComputedStyle(document.documentElement).getPropertyValue('--red').trim();
            expect(getComputedStyle($corner[0]).backgroundColor).to.equal(hexToRgb(red));
        });
    });

    it('defaults to the page background when nothing says otherwise', () => {
        // The fallback, for a stack standing on the page rather than under something that
        // sets a surface.  Both stacks in the app are covered by the two tests above -- the
        // nav bar by inheritance, the file browser by the button cascade -- so this one
        // guards the default that everything else is defined against.
        cy.mountUI(
            <IconStack corner={<Icon name='question'/>} label='WiFi status unknown'>
                <Icon name='wifi'/>
            </IconStack>,
            {theme: 'night'},
        );

        cy.get('.wrolpi-icon-stack-corner').should(($corner) => {
            const background = getComputedStyle(document.documentElement)
                .getPropertyValue('--bg').trim();
            expect(getComputedStyle($corner[0]).backgroundColor).to.equal(hexToRgb(background));
        });
    });
});

describe('corners stay hard', () => {
    it('squares off the pills a MultiSelect renders for its chosen options', () => {
        /*
         * The design has no rounded corners, and mantine.ts zeroes every radius variable so
         * a component that asks for `radius="md"` still gets none.  Pill escapes that: it
         * writes `--pill-radius: rem(1000)` onto the element, which outranks the theme, and
         * the tags in a MultiSelect came out as lozenges among a page of square boxes.
         */
        cy.mountUI(
            <MultiSelect data={['Preserve', 'Radio']} defaultValue={['Preserve']} label='Tags'/>,
            {theme: 'light'},
        );

        cy.get('[class*="mantine-Pill-root"]').should(($pill) => {
            expect(getComputedStyle($pill[0]).borderRadius).to.equal('0px');
        });
    });
});

describe('theme tokens actually resolve', () => {
    themeNames.forEach((theme) => {
        it(`paints text and borders from ${theme}'s table`, () => {
            cy.mountUI(<PathInput prefix='/media/wrolpi' defaultValue='x'/>, {theme});

            /*
             * A token that a theme forgot to define resolves to the empty string, and the
             * property falls back to something inherited -- usually black text on a dark
             * panel.  jsdom cannot catch that; it does not resolve var() at all.
             */
            cy.get('.wrolpi-path-input-control input').should(($input) => {
                const color = getComputedStyle($input[0]).color;
                expect(color, 'input text color resolved').to.match(/^rgba?\(/);
                // Only an rgba() alpha of zero is invisible.  Matching a trailing ", 0)"
                // loosely would flag amber's opaque rgb(255, 149, 0) for its blue channel.
                expect(color, 'input text is not transparent')
                    .not.to.match(/^rgba\(.*,\s*0(\.0+)?\)$/);
            });

            cy.get('.wrolpi-path-input-control').should(($control) => {
                expect(getComputedStyle($control[0]).borderTopColor, 'border resolved')
                    .to.match(/^rgba?\(/);
            });
        });
    });
});

describe('the video page keeps its phone layout edge to edge', () => {
    it('drops the inset below the tablet breakpoint, as every other page does', () => {
        /*
         * The other branch of `.wrolpi-page-inset`.  Below 699px a page has no side padding at all,
         * so the video page must not either -- and with cypress defaulting to a 500px viewport this
         * is the branch the rest of the suite runs in, which makes leaving it unasserted worse than
         * it looks: a regression that padded phones would show up nowhere.
         */
        cy.viewport(400, 700);
        cy.mountUI(<div className='wrolpi-stack wrolpi-page-inset'><Panel>About</Panel></div>);

        cy.get('.wrolpi-page-inset').should(($inset) => {
            const styles = getComputedStyle($inset[0]);
            expect(parseFloat(styles.paddingLeft), 'no left inset on a phone').to.equal(0);
            expect(parseFloat(styles.paddingRight), 'nor right').to.equal(0);

            // And the panel really does reach the edge, not just declare that it may.
            const panel = $inset[0].querySelector('.wrolpi-panel').getBoundingClientRect();
            expect(panel.left, 'the panel reaches the edge')
                .to.be.closeTo($inset[0].getBoundingClientRect().left, 0.5);
        });
    });
});

describe("a video's duration chip belongs to the theme, not to the poster", () => {
    /*
     * The chip was a literal `#ffffff` with black text.  The poster under it IS filtered by night
     * mode -- it is a `.media` leaf -- but the chip is drawn beside the image rather than inside it,
     * so the filter never reached it: a white tile on a card whose picture had gone dim red, and the
     * brightest thing on the videos page in the theme whose whole point is that nothing is bright.
     */
    themeNames.forEach((theme) => {
        it(`takes the surface and text of ${theme}`, () => {
            cy.mountUI(<><Panel>Surface</Panel><div className='duration-overlay'>12:34</div></>,
                {theme, mediaFilter: theme === 'night' ? 'night-red' : undefined});

            cy.get('.duration-overlay').should(($chip) => {
                const chip = getComputedStyle($chip[0]);
                const panel = getComputedStyle(Cypress.$('.wrolpi-panel')[0]);

                // The theme's surface, not a hardcoded one.
                expect(chip.backgroundColor, 'painted with the theme surface')
                    .to.equal(panel.backgroundColor);
                expect(chip.color, 'and the theme text').to.equal(panel.color);

                /*
                 * And an edge.  The chip is painted with `--panel`, so on a poster near that color
                 * -- a pale sky in light, most screenshots -- the border is the only thing telling
                 * the two apart.  Losing it leaves every contrast assertion above still green.
                 */
                expect(parseFloat(chip.borderTopWidth), 'has an edge').to.be.greaterThan(0);
                expect(chip.borderTopColor, 'the theme border')
                    .to.equal(toRgb(getComputedStyle(document.documentElement)
                        .getPropertyValue('--border')));

                // And still readable, which is what it is for: a length nobody can read is chrome.
                expect(contrast(chip.color, chip.backgroundColor), 'legible')
                    .to.be.at.least(4.5);
            });
        });
    });

    it('is never the brightest thing on a night card', () => {
        /*
         * The report, stated as something measurable.  In night the chip sat at full white against
         * a panel around 4% luminance -- the specific complaint was "the timestamp is white".
         */
        cy.mountUI(<><Panel>Card</Panel><div className='duration-overlay'>12:34</div></>,
            {theme: 'night', mediaFilter: 'night-red'});

        cy.get('.duration-overlay').should(($chip) => {
            const chip = getComputedStyle($chip[0]);
            /*
             * `--bg` read as a token, not `html`'s computed background.  Tokens paint `--bg` on
             * BODY, so `html` comes back `rgba(0, 0, 0, 0)` -- which `luminance` reads as black,
             * making this "no brighter than black + slack" rather than the claim in its name.  It
             * still failed the white chip, so it caught the reported bug by accident of the
             * comparison rather than by measuring the thing it says it measures.
             */
            const page = toRgb(getComputedStyle(document.documentElement).getPropertyValue('--bg'));
            expect(luminance(chip.backgroundColor), 'no brighter than the page it sits on')
                .to.be.at.most(luminance(page) + 0.05);
        });
    });
});

describe('media filtering', () => {
    it('tints a bare image in night', () => {
        cy.mountUI(<img alt='poster' src='/logo.png' width='80' height='80'/>,
            {theme: 'night', mediaFilter: 'night-red'});

        cy.get('img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.contain('wrolpi-night-red'));
    });

    it('filters a .media wrapper once, not its contents twice', () => {
        /*
         * Two passes of a luminance-to-red matrix is not the same as one -- the second pass
         * takes the luminance of an already-red pixel and the image comes out markedly
         * darker than its surroundings.  So a `.media` wrapper is filtered as a unit and the
         * leaf inside it must come back `none`.
         */
        cy.mountUI(
            <div className='media'>
                <img alt='poster' src='/logo.png' width='80' height='80'/>
            </div>,
            {theme: 'night', mediaFilter: 'night-red'},
        );

        cy.get('.media').should(($wrapper) =>
            expect(getComputedStyle($wrapper[0]).filter).to.contain('wrolpi-night-red'));
        cy.get('.media img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.equal('none'));
    });

    it('leaves media alone when the user has turned the filter off', () => {
        // The attribute is absent rather than empty when filtering is off, so night with the
        // setting disabled must match no rule at all.
        cy.mountUI(<img alt='poster' src='/logo.png' width='80' height='80'/>,
            {theme: 'night'});

        cy.get('img').should(($img) =>
            expect(getComputedStyle($img[0]).filter).to.equal('none'));
    });
});

/*
 * A poster of exact intrinsic dimensions.  It has to come over the wire rather than as a
 * data: URI, because CardPoster rewrites whatever it is given into `/media/<path>` -- so
 * the bytes are served by an intercept and the component builds its own URL, which is the
 * URL the app actually requests.
 */
const posterFile = (width, height) => ({
    id: 1,
    tags: [],
    poster_path: `videos/poster-${width}x${height}.svg`,
    primary_path: 'videos/one.mp4',
});

const servePoster = (width, height) => cy.intercept(
    'GET', `**/media/videos/poster-${width}x${height}.svg`,
    {
        headers: {'content-type': 'image/svg+xml'},
        body: `<svg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}'>` +
            `<rect width='100%' height='100%' fill='#888'/></svg>`,
    },
);

/* A card as narrow as the default grid makes them, which is where the cropping showed. */
const narrowCard = (children) =>
    <MemoryRouter><div style={{width: 233}}>{children}</div></MemoryRouter>;

/*
 * A card as wide as the grid makes it when it drops to ONE column -- a phone, or any window
 * under about 456px of content width.  Every case below used the narrow card, which is why
 * the wide card's own failure went unseen for the whole migration: a 16:9 poster held to a
 * 220px height is 391px wide, so a 451px card centred it with 30px of empty panel on either
 * side.  The height cap was doing its job for a book cover and letterboxing a video sideways.
 */
const wideCard = (children) =>
    <MemoryRouter><div style={{width: 451}}>{children}</div></MemoryRouter>;

/*
 * The height cap, read from the stylesheet rather than repeated here, so the two cannot
 * drift.  Deleting the declaration makes this NaN and every comparison against it fails,
 * which is the point -- and the bound below keeps "read whatever the CSS says" from being
 * a test that any value at all satisfies.
 */
const cardPosterCap = () => {
    /*
     * Resolved through the root font-size, because the cap is declared in rem so the
     * interface scale reaches it.  `parseFloat('12.5rem')` is 12.5, which sailed through as a
     * number and then failed the bound below -- five tests here broke that way when the scale
     * landed, and none of them mention the cap in their names.
     */
    const root = getComputedStyle(document.documentElement);
    const declared = root.getPropertyValue('--card-poster-max-height').trim();
    expect(declared, 'the cap is declared in rem, so it scales with the interface')
        .to.match(/^[\d.]+rem$/);

    const value = parseFloat(declared) * parseFloat(root.fontSize);
    expect(value, 'a poster cap is declared, and is small enough to be a cap')
        .to.be.within(80, 300);
    return value;
};

describe('a card poster is bounded by the card, and keeps its ratio', () => {
    /*
     * The poster carried a fixed 290x163 box.  A card in the default grid is about 233px
     * wide and Mantine's Card sets `overflow: hidden`, so the browser painted the middle
     * 233px of a 290px image: the ratio was right in the layout tree and wrong on screen.
     * None of that is visible to jsdom, which lays nothing out.
     *
     * The cap that replaced it is on the WIDTH, so a square or portrait source grows as
     * tall as it likes -- a 1:1 thumbnail became a 233px-tall band above a two-line title.
     * Hence a height cap as well.  Both caps have to preserve the ratio, which is the part
     * worth testing: `max-width` and `max-height` together only "contain" an image while
     * its own width and height stay `auto`.
     */
    const cases = [
        {name: 'a 16:9 video thumbnail', w: 1280, h: 720},
        {name: 'a square thumbnail', w: 600, h: 600},
        {name: 'a portrait book cover', w: 306, h: 396},
        {name: 'a poster smaller than the card', w: 120, h: 90},
    ];

    cases.forEach(({name, w, h}) => {
        it(`fits ${name} inside the card without distorting it`, () => {
            servePoster(w, h);
            cy.mountUI(narrowCard(<CardPoster file={posterFile(w, h)}/>));

            cy.get('.wrolpi-card-poster img')
                // The intrinsic size has to have arrived, or every ratio below is 0/0.
                .should(($img) => expect($img[0].naturalWidth, 'poster loaded').to.equal(w))
                .should(($img) => {
                    const img = $img[0];
                    const box = img.getBoundingClientRect();
                    const card = img.closest('.wrolpi-card-poster').getBoundingClientRect();

                    expect(box.width, 'poster stays within the card').to.be.at.most(card.width + 0.5);
                    expect(box.height, 'poster is capped in height').to.be.at.most(cardPosterCap() + 0.5);
                    // Never upscaled: a small poster is left at its own size.
                    expect(box.width, 'poster is not stretched past its own size').to.be.at.most(w + 0.5);
                    expect(box.width / box.height, `${name} keeps its ratio`)
                        .to.be.closeTo(w / h, 0.01);
                });
        });
    });

    it('shrinks a tall poster by its width rather than squashing it', () => {
        /*
         * The failure mode a ratio check alone would miss: a height cap applied while the
         * width is pinned crops or squashes instead of containing.  A 600x600 source in a
         * 233px card is width-bound at 233 if the cap is loose and height-bound if it is
         * tight -- either way the OTHER axis must have moved with it.
         */
        servePoster(600, 600);
        cy.mountUI(narrowCard(<CardPoster file={posterFile(600, 600)}/>));

        cy.get('.wrolpi-card-poster img')
            .should(($img) => expect($img[0].naturalWidth).to.equal(600))
            .should(($img) => {
                const box = $img[0].getBoundingClientRect();
                expect(box.height, 'the cap actually bit').to.be.at.most(cardPosterCap() + 0.5);
                expect(box.width, 'and the width came down with it')
                    .to.be.closeTo(box.height, 0.5);
            });
    });

    it('lets a landscape poster fill a one-column card instead of letterboxing it', () => {
        /*
         * The cap is a fixed height, so it stops scaling with the card: past 391px of card
         * width a 16:9 poster can no longer reach the edges and `justify-content: center`
         * splits the remainder into two margins.  On a phone -- one column, card the full
         * width of the screen -- that is every video thumbnail in the library.
         *
         * A source wider than the card is the case that matters.  1280px of intrinsic width
         * is available, so nothing here is upscaling: the poster is simply allowed to use
         * the width it has.
         */
        servePoster(1280, 720);
        cy.mountUI(wideCard(<CardPoster file={posterFile(1280, 720)}/>));

        cy.get('.wrolpi-card-poster img')
            .should(($img) => expect($img[0].naturalWidth, 'poster loaded').to.equal(1280))
            .should(($img) => {
                const img = $img[0];
                const box = img.getBoundingClientRect();
                const band = img.closest('.wrolpi-card-poster').getBoundingClientRect();

                expect(band.width - box.width, 'no empty panel beside the poster')
                    .to.be.at.most(1);
                expect(box.width / box.height, 'and it still keeps its ratio')
                    .to.be.closeTo(1280 / 720, 0.01);
            });
    });

    it('still keeps a portrait cover to a band on a one-column card', () => {
        /*
         * The other half, and the reason the cap exists at all: freed of it entirely, a
         * 306x396 book cover in a 451px card would stand 451px tall above a two-line title,
         * so the media dwarfs the thing it belongs to.
         *
         * The bound is stated as a fraction of the CARD rather than a pixel count, because
         * that is the actual rule -- the poster may be as tall as a 16:9 slice of this card
         * and no taller.  A portrait cover therefore grows with the card, which it should,
         * while never ceasing to be a band.
         */
        servePoster(306, 396);
        cy.mountUI(wideCard(<CardPoster file={posterFile(306, 396)}/>));

        cy.get('.wrolpi-card-poster img')
            .should(($img) => expect($img[0].naturalWidth, 'poster loaded').to.equal(306))
            .should(($img) => {
                const img = $img[0];
                const box = img.getBoundingClientRect();
                const band = img.closest('.wrolpi-card-poster').getBoundingClientRect();

                expect(box.height / band.width, 'the cover stays a band, not a column')
                    .to.be.at.most(0.58);
                expect(box.width / box.height, 'and keeps its ratio')
                    .to.be.closeTo(306 / 396, 0.01);
            });
    });
});

describe('a card reads as titles, not as a wall of links', () => {
    /*
     * A card's title and its author/channel/domain line are links, and they carried a
     * literal `color: black` from before the themes existed.  On the dark, night and amber
     * panels that is about 1.1:1 -- the titles were there, and invisible.  The date beside
     * them was fine, because it takes `--muted` from the card body, which is what made the
     * bug look like a card-title bug rather than a link bug.
     *
     * jsdom cannot see this: `.card-link` now resolves a custom property, and jsdom drops
     * `color: var(--text)` as an invalid declaration.
     */
    themeNames.forEach((theme) => {
        it(`keeps a card title legible in ${theme}`, () => {
            cy.mountUI(<MemoryRouter>
                <Card title={<a href='/videos/1' className='no-link-underscore card-link'>
                    How To Sharpen An Axe
                </a>} meta='Wranglerstar'/>
            </MemoryRouter>, {theme});

            cy.get('.card-link').should(($link) => {
                const panel = toRgb(getComputedStyle(document.documentElement)
                    .getPropertyValue('--panel'));
                const title = toRgb(getComputedStyle($link[0]).color);
                expect(contrast(title, panel), `card title on the panel in ${theme}`)
                    .to.be.greaterThan(4.5);
            });
        });
    });
});

describe('a card keeps its meta with the title and its actions at the foot', () => {
    /*
     * A grid stretches every card to the tallest in its row.  The meta line used to carry
     * `margin-top: auto`, so on /docs a PDF with no author had its date shoved 55px below
     * the title it belongs to, at the bottom of a card that was tall only because of its
     * neighbour.  Actions are the thing that wants the foot -- a row of cards should line
     * its buttons up however many lines each title took.
     *
     * Real layout, because `margin-top: auto` in a flex column is resolved by the layout
     * engine and jsdom has none.  The DOM ORDER half of this is in ui.test.js.
     */
    const row = <div style={{display: 'flex', alignItems: 'stretch', width: 520}}>
        {[
            'A title long enough to wrap onto three separate lines inside a narrow card',
            'Short',
        ].map((title, index) => <div key={index} style={{width: 240, display: 'flex'}}>
            <Card title={title} meta='example.com · 2025-01-30'
                  actions={<Button>Details</Button>}/>
        </div>)}
    </div>;

    it('leaves no gap between the title and the meta line', () => {
        cy.mountUI(row);

        cy.get('.wrolpi-card-meta').should(($metas) => {
            expect($metas.length).to.equal(2);
            const gaps = [...$metas].map((meta) => {
                const title = meta.previousElementSibling;
                return meta.getBoundingClientRect().top - title.getBoundingClientRect().bottom;
            });
            // The card body's own 4px gap, and nothing else.
            gaps.forEach((gap, index) => expect(gap, `card ${index} title-to-meta`).to.be.at.most(6));
            // Both cards really were stretched to the same height, or nothing was pushed.
            const heights = [...Cypress.$('.mantine-Card-root')]
                .map(card => Math.round(card.getBoundingClientRect().height));
            expect(new Set(heights).size, 'the row stretched both cards equally').to.equal(1);
        });
    });

    it('lines the actions up at the foot however tall the title got', () => {
        cy.mountUI(row);

        cy.get('.wrolpi-card-actions').should(($actions) => {
            expect($actions.length).to.equal(2);
            const [tall, short] = [...$actions];
            // The premise: the two titles really are different heights.
            const titleHeights = [...Cypress.$('.mantine-Card-root')].map(card =>
                Math.round(card.lastElementChild.firstElementChild.getBoundingClientRect().height));
            expect(new Set(titleHeights).size, 'the two titles differ in height').to.equal(2);

            expect(tall.getBoundingClientRect().bottom, 'both action rows sit on the same line')
                .to.be.closeTo(short.getBoundingClientRect().bottom, 1);
        });
    });
});

describe('a button and an icon button are the same height', () => {
    /*
     * Mantine gives ActionIcon a size scale of its own that is nothing like Button's --
     * `sm` is 22px against a button's 36px -- and defaults it to `md` where Button defaults
     * to `sm`.  So the Details/Open pair on an archive card came out 36px beside 28px, and
     * every other toolbar that mixes the two was ragged in the same way.
     *
     * Mantine already ships the aligned scale as `--ai-size-input-*`, for an ActionIcon
     * sitting beside an Input; those five values are identical to `--button-height-*`.  The
     * fix points one at the other, so this holds for a size we have never used as well as
     * the ones we have.
     *
     * Heights, so it belongs here: jsdom returns zero for both and the comparison would
     * pass on any pair of numbers at all.
     */
    const sizes = [undefined, 'xs', 'sm', 'md', 'lg', 'xl'];

    sizes.forEach((size) => {
        it(`matches at size ${size || '(default)'}`, () => {
            cy.mountUI(<div style={{display: 'flex', gap: '0.5em', alignItems: 'flex-start'}}>
                <Button size={size} icon='file alternate'>Details</Button>
                <IconButton size={size} icon='external' label='Open original URL'/>
            </div>);

            cy.get('button').should(($buttons) => {
                expect($buttons.length).to.equal(2);
                const [button, iconButton] = [...$buttons].map(el => el.getBoundingClientRect());
                // A zero-height pair would satisfy the equality below without meaning anything.
                expect(button.height, 'the button has a height at all').to.be.greaterThan(10);
                expect(iconButton.height, `icon button at size ${size || '(default)'}`)
                    .to.be.closeTo(button.height, 0.5);
                // Square, which is the whole point of an icon button.
                expect(iconButton.width, 'the icon button stays square')
                    .to.be.closeTo(iconButton.height, 0.5);
            });
        });
    });

    it('grows the icon button rather than shrinking the button', () => {
        /*
         * Both could be made equal by cutting the labelled button down to 28px, which would
         * be the wrong fix -- a 28px target is below the 44px-ish guidance already stretched
         * by having buttons this small, and every OTHER button on the page would still be 36.
         * Pinned so a future "make them match" cannot resolve the other way.
         */
        cy.mountUI(<IconButton icon='external' label='Open original URL'/>);

        cy.get('button').should(($el) =>
            expect($el[0].getBoundingClientRect().height, 'default icon button height')
                .to.be.at.least(34));
    });
});

describe('corner chrome sits on the poster, not on the band around it', () => {
    /*
     * The tag mark and the video duration are pinned to a corner of "the poster".  Once the
     * poster gained a height cap, the painted image stopped filling the band it sits in: a
     * portrait cover is 155px wide inside a 233px card, and a vertical video narrower still.
     * The mark then floats in empty letterbox space nowhere near the image's corner.
     *
     * Geometry against a real painted image, so it belongs here.  It has to be checked on a
     * ratio that is HEIGHT-bound -- on a 16:9 poster the image fills the band and a mark
     * pinned to either one lands in the same place, which is why this went unnoticed.
     */
    const tagged = (width, height) => ({...posterFile(width, height), tags: [{name: 'ham radio'}]});

    [
        {name: 'a portrait book cover', w: 306, h: 396},
        {name: 'a vertical video', w: 720, h: 1280},
        {name: 'a poster smaller than the card', w: 120, h: 90},
    ].forEach(({name, w, h}) => {
        it(`pins the tag to the corner of ${name}`, () => {
            servePoster(w, h);
            cy.mountUI(narrowCard(<CardPoster file={tagged(w, h)}/>));

            cy.get('.wrolpi-card-poster img')
                .should(($img) => expect($img[0].naturalWidth, 'poster loaded').to.equal(w))
                .should(($img) => {
                    const image = $img[0].getBoundingClientRect();
                    const band = $img[0].closest('.wrolpi-card-poster').getBoundingClientRect();
                    // The premise: this ratio really does leave letterbox space to get lost in.
                    expect(band.width - image.width, `${name} is narrower than its band`)
                        .to.be.greaterThan(20);

                    const mark = Cypress.$('.wrolpi-card-tag')[0].getBoundingClientRect();
                    expect(mark.left, 'tag tracks the image, not the band')
                        .to.be.closeTo(image.left, 2);
                    expect(mark.top, 'tag sits at the top of the image').to.be.closeTo(image.top, 2);
                });
        });
    });

    it('keeps the tag inside the poster link, so clicking it still navigates', () => {
        // The mark used to render inside the Link beside the image and was part of the
        // poster's hit target; a sibling placed before the link is a dead spot on the corner.
        servePoster(306, 396);
        cy.mountUI(narrowCard(<CardPoster to='/videos/1' file={tagged(306, 396)}/>));

        cy.get('.wrolpi-card-tag').should(($tag) =>
            expect($tag[0].closest('a'), 'the tag is inside the link').to.not.be.null);
    });
});

describe('a video card pins its duration to the poster', () => {
    /*
     * The same defect as the tag mark, on the other corner and reached by a different
     * route: the duration was pinned to a wrapper around CardPoster rather than to the
     * poster itself.  Mounted through the real VideoCard, because the wrapper was the
     * subject and a hand-built poster would not have one.
     */
    it('keeps the duration on a vertical video, not out in the band', () => {
        servePoster(720, 1280);
        // mountWithRouter, not mountUI: VideoCard reads the sort order from the query
        // context, which the spartan mount deliberately does not provide.
        cy.mountWithRouter(<div style={{width: 233}}><VideoCard file={{
            id: 1, tags: [], length: 95, primary_path: 'videos/short.mp4',
            title: 'A vertical video', mimetype: 'video/mp4',
            poster_path: 'videos/poster-720x1280.svg',
            video: {stem: 'short', channel: null},
        }}/></div>);

        cy.get('.wrolpi-card-poster img')
            .should(($img) => expect($img[0].naturalWidth, 'poster loaded').to.equal(720))
            .should(($img) => {
                const image = $img[0].getBoundingClientRect();
                const band = $img[0].closest('.wrolpi-card-poster').getBoundingClientRect();
                expect(band.width - image.width, 'the poster is narrower than its band')
                    .to.be.greaterThan(20);

                const badge = Cypress.$('.duration-overlay')[0].getBoundingClientRect();
                expect(badge.right, 'the duration tracks the image, not the band')
                    .to.be.closeTo(image.right, 6);
            });
    });
});

describe('the search clear button matches the field it clears', () => {
    /*
     * Aligning IconButton with Button changed every icon button in the app, and this is the
     * one in the library that stands beside an input rather than beside a button.  It is
     * also the case the remap was built for: `--ai-size-input-*` exists precisely so an
     * ActionIcon can match an Input, so if this pair is ragged the remap picked the wrong
     * scale.
     */
    it('is exactly as tall as the search field', () => {
        cy.mountUI(<SearchBox placeholder='Search' clearable value='axe' onChange={() => {}}/>);

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            const input = Cypress.$('input')[0].getBoundingClientRect();
            const clear = $clear[0].getBoundingClientRect();
            expect(input.height, 'the field has a height at all').to.be.greaterThan(10);
            expect(clear.height, 'clear button vs search field').to.be.closeTo(input.height, 0.5);
        });
    });
});

describe('pagination sits in the middle of its container', () => {
    /*
     * Three call sites wrap the pager in `<center>` or `text-align: center` and it still sat
     * hard against the left edge.  Both of those centre INLINE content, and Mantine's
     * Pagination root is a flex container that fills its parent's width -- so the buttons
     * were laid out at `flex-start` inside a box that was already the full width, and no
     * amount of centring outside it could move them.
     *
     * Measured as the gap on each side rather than by reading `justify-content`, so the
     * claim is about where the control actually lands.
     */
    it('leaves the same gap either side', () => {
        cy.mountUI(<div style={{width: 600}}>
            <Pagination activePage={3} totalPages={12} onPageChange={() => {}}/>
        </div>);

        cy.get('.wrolpi-pagination').should(($pager) => {
            const container = $pager[0].getBoundingClientRect();
            const buttons = [...$pager[0].querySelectorAll('button')]
                .map(button => button.getBoundingClientRect());
            expect(buttons.length, 'the pager rendered its controls').to.be.greaterThan(3);

            const left = Math.min(...buttons.map(b => b.left)) - container.left;
            const right = container.right - Math.max(...buttons.map(b => b.right));
            // The premise: the container really is wider than the strip, so there is slack
            // to distribute.  Without this the equality holds trivially at 0 and 0.
            expect(left + right, 'the container is wider than the strip').to.be.greaterThan(40);
            expect(left, 'gap left vs gap right').to.be.closeTo(right, 1);
        });
    });

    it('does not push its first page off the left edge when space is tight', () => {
        /*
         * The risk centring introduces.  Overflow in a `flex-start` row spills to the right,
         * where it can at least be scrolled to; centred, it spills BOTH ways and the first
         * page number is unreachable.  240px is narrower than any real layout gives it.
         */
        cy.mountUI(<div style={{width: 240}}>
            <Pagination activePage={6} totalPages={99} onPageChange={() => {}} showFirstAndLast/>
        </div>);

        cy.get('.wrolpi-pagination').should(($pager) => {
            const container = $pager[0].getBoundingClientRect();
            const buttons = [...$pager[0].querySelectorAll('button')]
                .map(button => button.getBoundingClientRect());
            expect(Math.min(...buttons.map(b => b.left)), 'nothing hangs off the left')
                .to.be.at.least(container.left - 0.5);
        });
    });
});

describe('the navigation bar is legible on every color a user can pick', () => {
    /*
     * The bar's background is the one surface the USER chooses, by hue name, and each theme
     * resolves those twelve names to twelve of its own colors.  Forty-eight backgrounds; the
     * links and status icons have to read on all of them.  They did not -- every one was
     * drawn in `--btn-text`, near-black in three of the four themes, against backgrounds like
     * night's `--brown` (#451212).  That glyph was 1.33:1 against the bar behind it.
     *
     * navColors.test.js measures the mapping against the palette parsed out of tokens.css,
     * which is the cheap and exhaustive half.  What it cannot see is whether the value the
     * mapping returns reaches the pixels: whether the tokens resolve through the cascade,
     * whether the style lands on the bar, and what an icon inside it actually inherits.  So
     * this measures the painted result and holds it against the number the component claims.
     *
     * `NavBarSample` is the gallery's bar rather than <NavBar/> itself, which needs the
     * settings, status and worker contexts and a dozen polling hooks.  Both build their style
     * with the same `navBarStyle(useNavColors(color))` call, and navColors.test.js has a
     * source guard holding NavBar to that.
     */
    const barsFor = (theme) => {
        cy.mountUI(<div>
            {navColorNames.map(color => <NavBarSample key={color} color={color}/>)}
        </div>, {theme});
    };

    themeNames.forEach((theme) => {
        it(`paints a resolved background for all twelve colors in ${theme}`, () => {
            barsFor(theme);

            navColorNames.forEach((color) => {
                cy.get(`[data-nav-sample="${color}"] .wrolpi-navbar`).should(($nav) => {
                    const background = getComputedStyle($nav[0]).backgroundColor;
                    // An unresolved token paints nothing at all, and a transparent bar over
                    // the page would read as "the color just looks wrong" rather than as a
                    // broken style.
                    expect(background, `${theme}/${color} bar background`)
                        .to.not.equal('rgba(0, 0, 0, 0)');
                });
            });
        });

        it(`clears 3:1 on every color in ${theme}`, () => {
            /*
             * 3:1 is the WCAG floor for graphical objects, which is what these icons are.
             * Twelve of the forty-eight combinations were below it before measurement.
             * Ten are still under 4.5:1 and cannot be lifted by any foreground -- a
             * monochrome theme resolves all twelve names onto one ramp, and a mid-tone of a
             * hue carries no text of that same hue.  That residue is the palette's, and it
             * is printed beside each sample in the gallery so it can be decided on.
             */
            barsFor(theme);

            navColorNames.forEach((color) => {
                cy.contrastRatio(`[data-nav-sample="${color}"] .wrolpi-navbar-link`)
                    .then((ratio) => {
                        expect(ratio, `${theme}/${color} link contrast`).to.be.greaterThan(3);
                    });
            });
        });

        it(`gives EVERY icon in the corner the same foreground as its links in ${theme}`, () => {
            /*
             * The actual complaint was about the icons, not the words -- and about two of
             * them specifically, the search glyph and the hamburger, which came out blue on
             * every bar in every theme while the rest of the bar was correct.
             *
             * They inherit nothing.  An anchor takes `a {color: var(--blue)}` from
             * tokens.css, which outranks the bar's inherited value; a Mantine ActionIcon
             * paints `--ai-color`, its own themed blue, and Mantine writes that variable
             * INLINE so no stylesheet variable can reach it.  Three routes to a color, of
             * which one worked.
             *
             * `querySelectorAll`, and the count asserted, because the version of this test
             * that shipped in the first pass read `querySelector('...svg')` -- one element,
             * the first, which was a plain inheriting Icon.  It claimed every icon and
             * measured the only one that was never broken.
             */
            barsFor(theme);

            navColorNames.forEach((color) => {
                cy.get(`[data-nav-sample="${color}"]`).should(($sample) => {
                    const link = $sample[0].querySelector('.wrolpi-navbar-link');
                    const expected = getComputedStyle(link).color;
                    const icons = [...$sample[0].querySelectorAll('.wrolpi-navbar-right svg')];

                    // Two bare Icons, one inside an anchor, one inside an ActionIcon.  If
                    // this drops, the loop below is covering less than it says.
                    expect(icons.length, `${theme}/${color} icons found`).to.equal(4);
                    icons.forEach((icon, index) => {
                        expect(getComputedStyle(icon).color, `${theme}/${color} icon ${index}`)
                            .to.equal(expected);
                    });
                });
            });
        });

        it(`paints the ratio it reports in ${theme}`, () => {
            /*
             * Ties the number to the pixels.  Without this the gallery could print a
             * comfortable figure beside a bar drawn in something else entirely, and both
             * halves would look right on their own.
             */
            barsFor(theme);

            navColorNames.forEach((color) => {
                cy.get(`[data-nav-sample-ratio="${color}"]`).invoke('text').then((text) => {
                    const reported = parseFloat(text);
                    expect(reported, `${theme}/${color} reported a ratio`).to.be.greaterThan(1);
                    cy.contrastRatio(`[data-nav-sample="${color}"] .wrolpi-navbar-link`)
                        .then((painted) => {
                            expect(painted, `${theme}/${color} painted vs reported`)
                                .to.be.closeTo(reported, 0.05);
                        });
                });
            });
        });
    });

    it('does not simply use --btn-text everywhere, which is what it replaced', () => {
        /*
         * The inverse.  Every case above would pass on the old fixed foreground in the two
         * themes where `--btn-text` happens to be the right end of the palette, so without
         * this the suite could go green on a revert.  Night is where the difference is
         * largest: `--brown` takes `--white` and `--red` keeps `--btn-text`, so the bar's
         * foreground is demonstrably not one value.
         *
         * `--btn-text` is READ from the theme rather than written out as a hex.  The unit
         * tests parse tokens.css precisely so a palette edit cannot leave a stale claim
         * behind, and a literal here would be the one place that rule was broken -- it would
         * either go stale or quietly stop testing anything if night's token moved.
         */
        cy.mountUI(<div>
            <NavBarSample color='brown'/>
            <NavBarSample color='red'/>
        </div>, {theme: 'night'});

        cy.get('[data-nav-sample="brown"] .wrolpi-navbar-link').then(($brown) => {
            cy.get('[data-nav-sample="red"] .wrolpi-navbar-link').then(($red) => {
                const brown = getComputedStyle($brown[0]).color;
                const red = getComputedStyle($red[0]).color;
                const btnText = getComputedStyle(document.documentElement)
                    .getPropertyValue('--btn-text');

                // The premise: the token resolved.  `toRgb` throws on an unresolved value
                // rather than letting the comparison below pass by comparing nothing.
                expect(toRgb(btnText), 'night --btn-text resolved').to.match(/^rgb/);
                expect(brown, 'brown and red bars take different foregrounds')
                    .to.not.equal(red);
                // And the one that changed is the one that was unreadable.
                expect(toRgb(brown), 'brown no longer takes --btn-text')
                    .to.not.equal(toRgb(btnText));
                // While red, which was always legible, still does.
                expect(toRgb(red), 'red still takes --btn-text').to.equal(toRgb(btnText));
            });
        });
    });
});

describe('the navigation bar corner', () => {
    /*
     * The real <DesktopNav/>, which takes its colors, home link and indicators as props and
     * so needs none of the polling hooks <NavBar/> wires up.  The indicators are the shapes
     * the app actually puts there, in the real NavIconWrapper: a bare-icon anchor (share), an
     * unwrapped anchor (search), and two IconButtons (hotspot, theme picker).  Those three
     * shapes take their geometry by three different routes, which is the whole problem.
     */
    const indicators = <>
        <NavIconWrapper>
            {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
            <a href='#' data-testid='share'><Icon name='share' size='large'/></a>
        </NavIconWrapper>
        <NavIconWrapper>
            <IconButton data-testid='hotspot' label='Hotspot' variant='subtle' icon={() =>
                <IconStack corner={<Icon name='x' size={12}/>} label='Hotspot'>
                    <Icon name='wifi' size='large'/>
                </IconStack>}/>
        </NavIconWrapper>
        <NavIconWrapper>
            <IconButton data-testid='theme' icon='sun' label='Theme' variant='subtle'/>
        </NavIconWrapper>
    </>;

    const mountBar = (width, theme = 'light') => cy.mountUI(
        <MemoryRouter><div style={{width}}>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={indicators}
            />
        </div></MemoryRouter>,
        {theme},
    );

    const centreOf = (rect) => rect.top + rect.height / 2;

    it('centres every indicator on the bar, whatever shape it is', () => {
        /*
         * The bug this replaces was a 0.8em top margin on the slot, which the corner centres
         * along with its content and so half-applied as a ~6px downward shift.  It looked
         * correct on the anchors and wrong on the two IconButtons, because an anchor's glyph
         * already sits high inside a line box that reserves descender space.
         *
         * Measured against the bar's own centre rather than against each other: three things
         * can be equally and consistently wrong, and were.
         */
        mountBar(1400);

        cy.get('.wrolpi-navbar').should(($nav) => {
            const bar = centreOf($nav[0].getBoundingClientRect());
            ['share', 'hotspot', 'theme'].forEach((name) => {
                const glyph = $nav[0].querySelector(`[data-testid="${name}"] svg`);
                expect(glyph, `${name} has a glyph`).to.not.be.null;
                expect(centreOf(glyph.getBoundingClientRect()), `${name} vertical centre`)
                    .to.be.closeTo(bar, 1.5);
            });
        });
    });

    it('gives the right-hand links the same hit area as the left-hand ones', () => {
        /*
         * Help and Admin highlighted only a box around their text, while Videos and
         * Statistics highlighted the full height of the bar.  The corner is a nested flex
         * container that centres its children, so a link inside it is sized to its content
         * while a link that is a direct child of the bar is stretched by `align-items:
         * stretch`.  Same class, same rules, different parent.
         *
         * The hover background is painted on the link box, so this IS the hover affordance.
         */
        mountBar(1400);

        cy.get('.wrolpi-navbar').should(($nav) => {
            const bar = $nav[0].getBoundingClientRect().height;
            const links = [...$nav[0].querySelectorAll('.wrolpi-navbar-link')];
            const corner = [...$nav[0]
                .querySelectorAll('.wrolpi-navbar-right .wrolpi-navbar-link')];

            // Help and Admin.  If the corner has no links this passes on an empty list.
            expect(corner.length, 'links in the corner').to.be.at.least(2);
            expect(links.length, 'links in total').to.be.greaterThan(corner.length);

            corner.forEach((link) => {
                expect(link.getBoundingClientRect().height, `${link.textContent} hit area`)
                    .to.be.closeTo(bar, 1);
            });
        });
    });

    it('is a real constraint: the left-hand links already filled the bar', () => {
        // Without this the case above could pass by the bar having collapsed to the height
        // of its text, which would be a different bug wearing the same number.
        mountBar(1400);

        cy.get('.wrolpi-navbar').should(($nav) => {
            const bar = $nav[0].getBoundingClientRect();
            const first = $nav[0].querySelector('.wrolpi-navbar-link');

            expect(bar.height, 'the bar is taller than a line of text').to.be.greaterThan(40);
            expect(first.getBoundingClientRect().height, 'a left-hand link fills it')
                .to.be.closeTo(bar.height, 1);
        });
    });
});

describe('the navigation bar never breaks onto a second line', () => {
    /*
     * The bar wraps as a failsafe (`flex-wrap: wrap`) and useOverflowNav is supposed to make
     * that unreachable by moving links into "More" before they overflow.  At certain widths
     * it did not, and the bar took two rows.
     *
     * The arithmetic was off by the bar's own horizontal padding: `recalculate` measured the
     * WRAPPER div's offsetWidth and subtracted only the home link and the corner, so it
     * believed it had ~8px more room than the row actually has.  Any width where the last
     * link overhangs by less than that got shown and wrapped -- a narrow band, which is why
     * it appeared only "at certain widths" while resizing.
     *
     * Swept rather than spot-checked, because a band that narrow is precisely what a
     * spot-check steps over.
     */
    /*
     * Hoisted, not written inline into `icons={...}`.  The icon-name audit in ui.test.js
     * reads every string literal inside such an expression as an icon name, so an inline
     * `label='Theme' variant='subtle'` fails that test with two names nobody wrote.
     */
    const themeIcon = <NavIconWrapper>
        <IconButton icon='sun' label='Theme' variant='subtle'/>
    </NavIconWrapper>;

    const mountAt = (width) => cy.mountUI(
        <MemoryRouter><div style={{width}}>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={themeIcon}
            />
        </div></MemoryRouter>,
    );

    // Wide enough that every link fits, so this is the height of exactly one row.
    let singleRow;

    before(() => {
        mountAt(1600);
        cy.get('.wrolpi-navbar').then(($nav) => {
            singleRow = $nav[0].getBoundingClientRect().height;
            expect(singleRow, 'a single row has a height to compare against')
                .to.be.greaterThan(30);
        });
    });

    /*
     * 6px steps across the range where links start moving into More.  Fine enough to land
     * inside an 8px band wherever it falls.
     */
    const widths = [];
    for (let width = 1180; width >= 640; width -= 6) widths.push(width);

    it('stays one row at every width from 1180 down to 640', () => {
        widths.forEach((width) => {
            mountAt(width);
            cy.get('.wrolpi-navbar').should(($nav) => {
                expect($nav[0].getBoundingClientRect().height, `bar height at ${width}px`)
                    .to.be.at.most(singleRow + 2);
            });
        });
    });

    it('keeps every visible link inside the bar rather than clipping it', () => {
        // The failure mode a naive "just use nowrap" fix would introduce: no second row,
        // but Admin hanging off the right edge where nothing can reach it.
        [1180, 1000, 860, 720, 640].forEach((width) => {
            mountAt(width);
            cy.get('.wrolpi-navbar').should(($nav) => {
                const bar = $nav[0].getBoundingClientRect();
                [...$nav[0].querySelectorAll('.wrolpi-navbar-link')].forEach((link) => {
                    expect(link.getBoundingClientRect().right, `${link.textContent} at ${width}px`)
                        .to.be.at.most(bar.right + 0.5);
                });
            });
        });
    });
});

describe('the navbar overflow menu keeps the bar\'s styling', () => {
    /*
     * Mantine's Menu.Target clones its child and hands it a className of its own.  The
     * trigger spread those cloned props AFTER its own `className` attribute, so the cloned
     * value replaced ours and the real More button rendered with NO class at all -- a bare
     * UA button, grey on dark and white on light, while every other item in the bar took the
     * user's navbar color.
     *
     * The hidden placeholder DesktopNav measures is NOT cloned by Menu.Target, so it kept its
     * class and stayed the width the styled button would have been.  That is why the width
     * sweep passed while the visible button was wrong: the two were the same component and
     * still not the same thing.
     */
    const themeIcon = <NavIconWrapper>
        <IconButton icon='sun' label='Theme' variant='subtle'/>
    </NavIconWrapper>;

    // Narrow enough that links have to move into More.
    const mountNarrow = (theme) => cy.mountUI(
        <MemoryRouter><div style={{width: 700}}>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={themeIcon}
            />
        </div></MemoryRouter>,
        {theme},
    );

    const moreButton = () => cy.contains('.wrolpi-navbar button', 'More');

    themeNames.forEach((theme) => {
        it(`draws More in the bar's own color in ${theme}`, () => {
            mountNarrow(theme);

            cy.get('.wrolpi-navbar').then(($nav) => {
                const expected = getComputedStyle($nav[0]).color;
                moreButton().should(($more) => {
                    const style = getComputedStyle($more[0]);
                    expect($more[0].className, 'More carries the bar classes')
                        .to.contain('wrolpi-navbar-link');
                    expect(style.color, `More text color in ${theme}`).to.equal(expected);
                    // A UA button paints a grey face; the bar's items are transparent.
                    expect(style.backgroundColor, `More background in ${theme}`)
                        .to.equal('rgba(0, 0, 0, 0)');
                });
            });
        });
    });

    it('gives More the same hit area and caret as the placeholder it was measured as', () => {
        // The measurement contract.  If the drawn button is narrower or shorter than the
        // space reserved for it, the row overflows and the bar wraps.
        mountNarrow('light');

        /*
         * Both measurements inside the retried assertion.  Reading the bar's height in a
         * plain `.then()` first captures whatever it was at that instant -- including the
         * transient wrapped state while the corner is still settling -- and then retries the
         * comparison against that stale number forever.
         */
        cy.get('.wrolpi-navbar').should(($nav) => {
            const bar = $nav[0].getBoundingClientRect().height;
            const more = [...$nav[0].querySelectorAll('button')]
                .find(button => button.textContent.includes('More'));

            expect(more, 'the bar has a More button at this width').to.not.be.undefined;
            expect(more.querySelector('svg'), 'More has its dropdown caret').to.not.be.null;
            expect(more.getBoundingClientRect().height, 'More fills the bar')
                .to.be.closeTo(bar, 1);
            expect(getComputedStyle(more).cursor, 'More is clickable').to.equal('pointer');
        });
    });
});

describe('the icon-only triggers in the navbar corner are reachable', () => {
    /*
     * The search glyph carried Semantic's `item` class, which has had no rules at all since
     * Semantic was removed: no pointer cursor, no hover highlight, and a hit area of the
     * 18px glyph rather than the height of the bar.  The share glyph did compute
     * `cursor: pointer` -- it is an `<a href>` -- but its target was the 24px box the icon
     * occupies, so the pointer showed only if you found it exactly.
     *
     * Both are icon-only triggers sitting beside Help and Admin, and should behave as those
     * do.  Measured against a real link in the same bar rather than against a number.
     */
    /*
     * The REAL ShareButton, and the real SearchIconButton that DesktopNav renders for
     * itself.  The first version of this suite used hand-written anchors carrying the
     * classes I expected the components to have, so reverting SearchIconButton to Semantic's
     * `item` left it green -- it was measuring my markup, not the app's.
     */
    const corner = <NavIconWrapper><ShareButton/></NavIconWrapper>;

    const triggers = {
        share: '.wrolpi-navbar-icon a',
        search: '.wrolpi-navbar [aria-label="Search"]',
    };

    beforeEach(() => cy.mountUI(
        <MemoryRouter><div style={{width: 1400}}>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={corner}
            />
        </div></MemoryRouter>,
    ));

    Object.entries(triggers).forEach(([name, selector]) => {
        it(`gives ${name} a pointer and the bar's full height`, () => {
            cy.get('.wrolpi-navbar').should(($nav) => {
                const bar = $nav[0].getBoundingClientRect().height;
                const trigger = $nav[0].querySelector(selector.replace('.wrolpi-navbar ', ''));

                expect(trigger, `${name} is in the bar`).to.not.be.null;
                expect(getComputedStyle(trigger).cursor, `${name} cursor`).to.equal('pointer');
                expect(trigger.getBoundingClientRect().height, `${name} hit area`)
                    .to.be.closeTo(bar, 1);
            });
        });

        it(`highlights ${name} on hover, as a link does`, () => {
            /*
             * The highlight is what tells a user the glyph is a control at all, and it is
             * the half of the complaint that a cursor check does not cover.
             *
             * `:hover` cannot be forced -- no event applies it, and getComputedStyle will
             * never report it -- so the real stylesheets are searched for a hover rule this
             * element matches that paints a background.  Resolved against the live CSSOM
             * rather than a file, so it fails if the rule is edited, dropped, or written
             * with a selector that misses.
             */
            cy.get(selector).should(($el) => {
                const element = $el[0];
                const painted = [...document.styleSheets].flatMap((sheet) => {
                    try {
                        return [...sheet.cssRules];
                    } catch (e) {
                        return []; // A cross-origin sheet; none of ours are.
                    }
                }).filter(rule => rule.selectorText
                    && rule.selectorText.includes(':hover')
                    && rule.style.backgroundColor
                    && rule.selectorText.split(',').some((selector) => {
                        const resting = selector.replace(/:hover/g, '').trim();
                        try {
                            return resting && element.matches(resting);
                        } catch (e) {
                            return false;
                        }
                    }));

                expect(painted.map(rule => rule.selectorText), `${name} hover rule`)
                    .to.not.be.empty;
            });
        });
    });
});

describe('the navbar recalculates when the corner changes, not only the window', () => {
    /*
     * The corner is not a fixed width.  The ⌘K hint beside the search glyph renders only
     * once `useKeyboardDetected` has seen a keypress, so it appears at an arbitrary later
     * moment; the load, memory, temperature and drive warnings appear and vanish as the
     * machine's state changes.  Each one changes the room the links have, and none of them
     * resizes the container.
     *
     * With only the container observed nothing recalculated, and the bar wrapped -- which is
     * why the same viewport wrapped or not depending on whether the user had touched a key,
     * and why the width sweep could pass while the real bar was broken.  The sweep measures
     * a bar whose corner never changes after mount; this one changes it.
     */
    const GrowingCorner = () => {
        // Stands in for the ⌘K hint and for a warning icon arriving: a corner that is one
        // width when the bar is measured and a wider one a moment later.
        const [grown, setGrown] = React.useState(false);
        React.useEffect(() => {
            const timer = setTimeout(() => setGrown(true), 150);
            return () => clearTimeout(timer);
        }, []);
        return <NavIconWrapper>
            <span data-testid='corner-filler'
                  style={{display: 'inline-block', width: grown ? 180 : 20}}/>
        </NavIconWrapper>;
    };

    const mountGrowing = (width) => cy.mountUI(
        <MemoryRouter><div style={{width}}>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={<GrowingCorner/>}
            />
        </div></MemoryRouter>,
    );

    it('gives up links when the corner grows after the bar was measured', () => {
        mountGrowing(900);

        // The corner has finished growing...
        cy.get('[data-testid="corner-filler"]').should(($filler) => {
            expect($filler[0].getBoundingClientRect().width, 'the corner grew').to.equal(180);
        });

        // ...and the bar is still one row, which it can only be if it recalculated.
        cy.get('.wrolpi-navbar').should(($nav) => {
            const rows = new Set([...$nav[0].querySelectorAll('.wrolpi-navbar-link')]
                .map(link => Math.round(link.getBoundingClientRect().top)));
            expect([...rows], 'every link shares one row').to.have.length(1);
        });
    });

    it('takes the links back when the corner shrinks again', () => {
        /*
         * The inverse, and the reason to recalculate rather than simply reserve the widest
         * corner the bar might ever have: a warning icon that clears must give its space
         * back, or the bar keeps a permanently shortened set of links until the next resize.
         */
        mountGrowing(900);

        cy.get('[data-testid="corner-filler"]').should(($filler) => {
            expect($filler[0].getBoundingClientRect().width).to.equal(180);
        });

        cy.get('.wrolpi-navbar').then(($nav) => {
            const shrunken = $nav[0].querySelectorAll('.wrolpi-navbar-link').length;

            // Shrink the corner back, as a cleared warning would.
            cy.get('[data-testid="corner-filler"]').then(($filler) => {
                $filler[0].style.width = '20px';
            });

            cy.get('.wrolpi-navbar').should(($after) => {
                expect($after[0].querySelectorAll('.wrolpi-navbar-link').length,
                    'links come back when the corner clears').to.be.greaterThan(shrunken);
            });
        });
    });
});

describe('the global search modal shows its results', () => {
    /*
     * The suggestion list overlays the page everywhere else, and should: a list that reflows
     * the page underneath while you type is unusable.  Inside the search modal that same rule
     * failed twice over.  An absolutely positioned list contributes no height, so the modal
     * panel sized itself to the search box alone -- 114px -- and the panel's own
     * `overflow: auto` then clipped the list at that edge.  What the user got was a search
     * box and the first line of the first group, with the page showing through below.
     *
     * The real SearchBox, in a panel with the modal's overflow, so the class that carries the
     * fix comes from the component rather than from markup written here.
     */
    const results = {
        channels: {
            name: 'Channels',
            results: Array.from({length: 8}, (unused, index) => ({
                title: `Channel ${index + 1}`, description: 'A channel of videos',
            })),
        },
        domains: {
            name: 'Domains',
            results: Array.from({length: 8}, (unused, index) => ({
                title: `example${index + 1}.com`, description: 'An archived domain',
            })),
        },
    };

    // The modal panel: Mantine caps its height and scrolls it, which is what did the clipping.
    const panel = (children) => <div className='fake-modal-content'
                                     style={{maxHeight: 504, overflow: 'auto', width: 440}}>
        {children}
    </div>;

    // The list is a combobox: it opens on typing, as it does for a real user.
    const openSuggestions = () => cy.get('.wrolpi-searchbox input').type('n');

    it('lays the suggestions out inside the panel rather than over the page', () => {
        cy.mountUI(panel(<div className='wrolpi-search-modal'>
            <SearchBox value='chan' results={results} onResultSelect={() => {}}/>
        </div>));
        openSuggestions();

        cy.get('.wrolpi-searchbox-results').should(($results) => {
            expect(getComputedStyle($results[0]).position, 'the list is in flow')
                .to.equal('static');
        });
    });

    it('grows the panel to fit them, so nothing is clipped', () => {
        cy.mountUI(panel(<div className='wrolpi-search-modal'>
            <SearchBox value='chan' results={results} onResultSelect={() => {}}/>
        </div>));
        openSuggestions();

        cy.get('.fake-modal-content').should(($panel) => {
            const box = $panel[0].getBoundingClientRect();
            const list = $panel[0].querySelector('.wrolpi-searchbox-results')
                .getBoundingClientRect();

            expect(list.height, 'the list has results to show').to.be.greaterThan(100);
            // The whole list is inside the panel, not spilling past its clipped edge.
            expect(list.bottom, 'the list ends inside the panel')
                .to.be.at.most(box.bottom + 0.5);
            // And the panel actually grew for it, rather than the list having been squashed.
            expect(box.height, 'the panel grew to hold the list')
                .to.be.greaterThan(list.height);
        });
    });

    it('is a real constraint: outside the modal the list still overlays', () => {
        /*
         * The inverse.  If the rule leaked to every searchbox, the file browser and the
         * videos page would push their content down on every keystroke -- a worse bug than
         * the one being fixed, and one this suite would otherwise not notice.
         */
        cy.mountUI(panel(
            <SearchBox value='chan' results={results} onResultSelect={() => {}}/>
        ));
        openSuggestions();

        cy.get('.wrolpi-searchbox-results').should(($results) => {
            expect(getComputedStyle($results[0]).position, 'still an overlay elsewhere')
                .to.equal('absolute');
        });
    });
});

describe('a toast does not cover the navigation bar', () => {
    /*
     * Toasts are fixed at `top: var(--mantine-spacing-md)` -- 16px -- while the bar occupies
     * the first 54px of the page, so every toast landed over the bar's right-hand corner:
     * the search glyph, the hamburger, Help and Admin.  For as long as it was up those
     * controls could not be clicked, and an error toast is exactly the moment a user reaches
     * for Admin.
     *
     * It surfaced as six e2e failures the day the search glyph was given a proper hit area:
     * at 18px it sat in the gap beneath the toast, and growing it to the height of the bar
     * moved it into the overlap.  The toast had been covering that corner all along; there
     * was simply nothing there to hit.
     *
     * Measured as `elementFromPoint`, which is the same question Cypress's actionability
     * check asks and the one a mouse asks -- a geometry-only comparison would miss a toast
     * that overlaps but sits behind, and a z-index comparison would miss one that is in
     * front but elsewhere on the screen.
     */
    const themeIcon = <NavIconWrapper>
        <IconButton icon='sun' label='Theme' variant='subtle'/>
    </NavIconWrapper>;

    const mountBarWithToast = () => {
        cy.mountUI(<MemoryRouter>
            <Notifications position='top-right'/>
            <DesktopNav
                navColors={{background: '#5c4fa8', color: '#ffffff', ratio: 6.69}}
                homeLink={<a className='wrolpi-navbar-link' href='#'><i>WROLPi</i></a>}
                icons={themeIcon}
            />
        </MemoryRouter>);
        cy.then(() => {
            clearToasts();
            // The shape CI produces: an error toast, which is the kind that lingers.
            toast({type: 'error', title: 'Unexpected error', description: 'Something failed.'});
        });
        cy.get('.mantine-Notification-root').should('exist');
    };

    it('leaves the search control clickable while a toast is up', () => {
        mountBarWithToast();

        cy.get('.wrolpi-navbar [aria-label="Search"]').should(($search) => {
            const box = $search[0].getBoundingClientRect();
            const topmost = document.elementFromPoint(
                box.left + box.width / 2, box.top + box.height / 2);

            expect(topmost, 'something is at the search glyph').to.not.be.null;
            expect($search[0].contains(topmost) || topmost === $search[0],
                `search is the topmost element, not ${topmost && topmost.className}`).to.be.true;
        });
    });

    it('leaves every control in the corner clickable', () => {
        // Help and Admin are the ones that matter most: an error toast is when a user goes
        // looking for the admin pages, and it was sitting on top of the link.
        mountBarWithToast();

        cy.get('.wrolpi-navbar-right').should(($corner) => {
            const controls = [...$corner[0].querySelectorAll('a, button')];
            expect(controls.length, 'there are controls to check').to.be.at.least(3);

            const covered = controls.filter((control) => {
                const box = control.getBoundingClientRect();
                const topmost = document.elementFromPoint(
                    box.left + box.width / 2, box.top + box.height / 2);
                return !(control.contains(topmost) || topmost === control);
            }).map(control => control.textContent.trim()
                || control.getAttribute('aria-label') || '(unlabelled)');

            expect(covered).to.deep.equal([]);
        });
    });

    it('starts the toast below the bar rather than beside it', () => {
        /*
         * The mechanism, stated separately from the effect.  The two cases above would also
         * pass if the toast merely happened to be narrow enough to miss the controls at this
         * viewport, which is how the bar came to be covered at some widths and not others.
         */
        mountBarWithToast();

        cy.get('.mantine-Notifications-root').should(($root) => {
            const toastTop = $root[0].getBoundingClientRect().top;
            const barBottom = Cypress.$('.wrolpi-navbar')[0].getBoundingClientRect().bottom;

            expect(barBottom, 'the bar has height to clear').to.be.greaterThan(40);
            expect(toastTop, 'the toast starts below the bar').to.be.at.least(barBottom);
        });
    });
});

describe('a disabled button keeps its own color', () => {
    /*
     * Mantine repaints a disabled button flat grey -- background, text and border all
     * replaced with `--mantine-color-disabled`.  Semantic kept the color and dropped the
     * whole control to `opacity: 0.45`, so a disabled Delete was still visibly the red one.
     *
     * The file browser is where this bites.  Its footer is eight buttons, six of which are
     * disabled until something is selected, so the toolbar a user meets on arriving at /files
     * is an undifferentiated grey row -- Delete, Rename, Move, Ignore and Tag all identical.
     * Color is how those are told apart at a glance, and disabling them threw it away.
     *
     * Opacity is the better signal anyway: it says "not available" without also saying "no
     * longer the delete button".
     *
     * Mantine leaves `--button-bg` intact on a disabled button -- it overrides the painted
     * `background` rather than the variable -- so the color the call site asked for is still
     * there to be read back.
     */
    const pairs = [
        {color: 'red', label: 'Delete'},
        {color: 'yellow', label: 'Rename'},
        {color: 'teal', label: 'Move'},
        {color: 'violet', label: 'Tag'},
        {color: 'grey', label: 'Ignore'},
    ];

    const mountPairs = (theme) => cy.mountUI(<div>
        {pairs.map(({color, label}) => <span key={color}>
            <Button color={color} data-testid={`on-${color}`}>{label}</Button>
            <Button color={color} disabled data-testid={`off-${color}`}>{label}</Button>
        </span>)}
    </div>, {theme});

    themeNames.forEach((theme) => {
        it(`keeps every color recognisable while disabled in ${theme}`, () => {
            mountPairs(theme);

            cy.get('[data-testid^="off-"]').should(($disabled) => {
                expect($disabled, 'a disabled button per color').to.have.length(pairs.length);

                pairs.forEach(({color}) => {
                    const on = Cypress.$(`[data-testid="on-${color}"]`)[0];
                    const off = Cypress.$(`[data-testid="off-${color}"]`)[0];

                    expect(getComputedStyle(off).backgroundColor, `${theme}/${color} fill`)
                        .to.equal(getComputedStyle(on).backgroundColor);
                });
            });
        });

        it(`still marks them as unavailable in ${theme}`, () => {
            /*
             * Keeping the color must not cost the affordance: a disabled button that looks
             * identical to an enabled one is a worse bug than a grey one.
             *
             * Against `--disabled-opacity` rather than a band.  A band tolerates an
             * accidentally different fade, or an opacity leaking in from somewhere else, and
             * still reports success -- and the fade is an authored value, so it can be read.
             */
            mountPairs(theme);

            cy.get('[data-testid="off-red"]').should(($off) => {
                const authored = parseFloat(getComputedStyle(document.documentElement)
                    .getPropertyValue('--disabled-opacity'));
                const disabled = parseFloat(getComputedStyle($off[0]).opacity);
                const enabled = parseFloat(
                    getComputedStyle(Cypress.$('[data-testid="on-red"]')[0]).opacity);

                expect(authored, 'the token resolved').to.be.within(0.1, 0.9);
                expect(enabled, `${theme} enabled is solid`).to.equal(1);
                expect(disabled, `${theme} disabled matches the token`).to.equal(authored);
            });
        });
    });

    themeNames.forEach((theme) => {
        it(`tells two disabled buttons of different colors apart in ${theme}`, () => {
            /*
             * The claim stated as the user meets it, and the inverse of the bug: five grey
             * blobs were five EQUAL greys.  Comparing each against its enabled twin above
             * would still pass if every pair were grey, so this compares them to each other.
             *
             * Every theme, not just light.  Night and amber are where it is both most
             * valuable and most fragile: one hue means the five differ only in brightness,
             * so if any theme is going to collapse them back together it is those two.
             */
            mountPairs(theme);

            cy.get('[data-testid^="off-"]').should(($disabled) => {
                const fills = [...$disabled]
                    .map(button => getComputedStyle(button).backgroundColor);

                expect(new Set(fills).size,
                    `${theme}: five colors, distinct fills: ${fills.join(' ')}`)
                    .to.equal(pairs.length);
            });
        });
    });

    it('does not fade a button that is merely busy', () => {
        /*
         * Mantine renders a loading button as `disabled={disabled || loading}`, so every busy
         * control in the app is `:disabled` -- an APIButton mid-request, refresh, the
         * flasher's connect.  Mantine's own grey repaint excludes `[data-loading]` for
         * exactly this reason, and the first version of this rule did not, so "working..."
         * faded to 0.45 and read as unavailable rather than active.
         */
        cy.mountUI(<div>
            <Button color='blue' loading data-testid='busy'>Saving</Button>
            <Button color='blue' disabled data-testid='off'>Save</Button>
            <IconButton icon='trash' label='Deleting' color='red' variant='filled' loading
                        data-testid='busy-icon'/>
        </div>);

        cy.get('[data-testid="busy"]').should(($busy) => {
            expect(parseFloat(getComputedStyle($busy[0]).opacity), 'a busy button is solid')
                .to.equal(1);
            // Paired with the disabled one, so this cannot pass by nothing fading at all.
            expect(parseFloat(getComputedStyle(Cypress.$('[data-testid="off"]')[0]).opacity),
                'while a disabled one beside it still fades').to.be.lessThan(1);
            expect(parseFloat(getComputedStyle(Cypress.$('[data-testid="busy-icon"]')[0]).opacity),
                'and the same for an icon button').to.equal(1);
        });
    });

    it('keeps night\'s dashed danger treatment when disabled', () => {
        /*
         * Night has no second hue, so danger is a dashed border on a transparent fill rather
         * than a red one.  The general disabled rule repaints from `--button-bg` -- the
         * filled red Mantine leaves in the variable -- and at equal specificity it won on
         * source order, turning the file browser's disabled Delete into a solid red chip in
         * the one theme where that is not what danger means.
         */
        cy.mountUI(<div>
            <Button role='danger' disabled data-testid='danger-off'>Delete</Button>
        </div>, {theme: 'night'});

        cy.get('[data-testid="danger-off"]').should(($button) => {
            const style = getComputedStyle($button[0]);

            expect(style.backgroundColor, 'no fill').to.equal('rgba(0, 0, 0, 0)');
            expect(style.borderStyle, 'still dashed').to.equal('dashed');
            expect(toRgb(style.borderTopColor), 'in the danger color')
                .to.equal(toRgb(style.getPropertyValue('--danger') || '#ff5757'));
            expect(parseFloat(style.opacity), 'and still faded').to.be.lessThan(1);
        });
    });

    it('is a real constraint: light DOES fill a disabled danger button', () => {
        // Without this the case above would also pass on a rule that stripped the fill from
        // every disabled danger button in every theme, which would break the other three.
        cy.mountUI(<div>
            <Button role='danger' disabled data-testid='danger-off'>Delete</Button>
        </div>, {theme: 'light'});

        cy.get('[data-testid="danger-off"]').should(($button) => {
            expect(getComputedStyle($button[0]).backgroundColor, 'light danger is filled')
                .to.not.equal('rgba(0, 0, 0, 0)');
        });
    });

    it('restores text and border on variants that carry no fill', () => {
        /*
         * `default` and `outline` buttons say what they are with their text and border, not
         * their background, so a background-only check would pass on them while they were
         * still painted Mantine's disabled grey.
         */
        cy.mountUI(<div>
            <Button variant='outline' color='red' data-testid='outline-on'>Delete</Button>
            <Button variant='outline' color='red' disabled data-testid='outline-off'>Delete</Button>
        </div>);

        cy.get('[data-testid="outline-off"]').should(($off) => {
            const on = getComputedStyle(Cypress.$('[data-testid="outline-on"]')[0]);
            const off = getComputedStyle($off[0]);

            expect(off.color, 'text color survives').to.equal(on.color);
            expect(off.borderTopColor, 'border color survives').to.equal(on.borderTopColor);
        });
    });

    it('does the same for icon-only buttons', () => {
        // The file browser's row actions are IconButtons, and they disable the same way.
        cy.mountUI(<div>
            {/* Filled, so there is a color to lose.  IconButton defaults to Mantine's
                `default` variant, which is a white face, and comparing white with white
                would prove nothing. */}
            <IconButton icon='trash' label='Delete' color='red' variant='filled'
                        data-testid='icon-on'/>
            <IconButton icon='trash' label='Delete' color='red' variant='filled' disabled
                        data-testid='icon-off'/>
        </div>);

        cy.get('[data-testid="icon-off"]').should(($off) => {
            const on = Cypress.$('[data-testid="icon-on"]')[0];

            expect(getComputedStyle($off[0]).backgroundColor, 'icon button keeps its fill')
                .to.equal(getComputedStyle(on).backgroundColor);
            expect(parseFloat(getComputedStyle($off[0]).opacity), 'and is faded')
                .to.be.lessThan(0.7);
        });
    });
});

describe('a button with an icon and no label centres the icon', () => {
    /*
     * Mantine's `leftSection` carries a `margin-inline-end` to hold the icon off the label.
     * With no label that margin is pure offset, and the glyph sits about 8px left of the
     * button's centre.
     *
     * The Settings config table is where it showed: Import and Save are icon-only Buttons and
     * looked visibly off, while Restore in the same row looked right -- Restore is an
     * IconButton, which centres a lone glyph by construction.  Measured on the running app at
     * -8px before the fix.
     */
    it('puts the glyph in the middle when there is nothing else in the button', () => {
        cy.mountUI(<Button icon='upload' aria-label='Import' data-testid='icon-only'/>);

        cy.get('[data-testid="icon-only"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();
            const glyph = $button[0].querySelector('svg').getBoundingClientRect();
            const offset = (glyph.left + glyph.width / 2) - (box.left + box.width / 2);

            expect(box.width, 'the button has width to be off-centre in')
                .to.be.greaterThan(glyph.width + 8);
            expect(offset, 'glyph centre vs button centre').to.be.closeTo(0, 1);
        });
    });

    it('treats a null label as no label, which is how the file browser renders', () => {
        /*
         * The footer passes `{label('Delete')}`, and that is null whenever the bar is too
         * narrow for words -- so those buttons are icon-only at exactly the widths where the
         * offset is most visible.  `React.Children.toArray` drops nulls; a plain truthiness
         * check on `children` would not.
         */
        cy.mountUI(<Button icon='trash' aria-label='Delete' data-testid='null-label'>
            {null}
        </Button>);

        cy.get('[data-testid="null-label"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();
            const glyph = $button[0].querySelector('svg').getBoundingClientRect();

            expect((glyph.left + glyph.width / 2) - (box.left + box.width / 2),
                'glyph centre vs button centre').to.be.closeTo(0, 1);
        });
    });

    it('is a real constraint: a labelled button keeps its icon on the left', () => {
        // The inverse.  Centring the glyph must not apply when there IS a label, or every
        // labelled button in the app loses its leading icon's position.
        cy.mountUI(<Button icon='trash' data-testid='labelled'>Delete</Button>);

        cy.get('[data-testid="labelled"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();
            const glyph = $button[0].querySelector('svg').getBoundingClientRect();

            expect((glyph.left + glyph.width / 2) - (box.left + box.width / 2),
                'the icon leads the label').to.be.lessThan(-4);
            expect($button[0].textContent, 'and the label is still there').to.contain('Delete');
        });
    });

    it('treats blank and empty children as no label', () => {
        /*
         * `Children.toArray` drops null, undefined and booleans but KEEPS an empty or
         * whitespace-only string, so a length check alone would call these labelled and leave
         * the glyph off-centre.
         */
        cy.mountUI(<div>
            <Button icon='upload' aria-label='Empty' data-testid='empty'>{''}</Button>
            <Button icon='upload' aria-label='Blank' data-testid='blank'>{'   '}</Button>
        </div>);

        cy.get('[data-testid="blank"]').should(() => {
            ['empty', 'blank'].forEach((id) => {
                const button = Cypress.$(`[data-testid="${id}"]`)[0];
                const box = button.getBoundingClientRect();
                const glyph = button.querySelector('svg').getBoundingClientRect();

                expect((glyph.left + glyph.width / 2) - (box.left + box.width / 2),
                    `${id} glyph centre`).to.be.closeTo(0, 1);
            });
        });
    });

    it('treats any element child as a label, including an empty fragment', () => {
        /*
         * Recording what actually happens rather than what would be tidy.  `toArray` does not
         * look inside a fragment -- it returns the fragment itself as one child -- so `<></>`
         * is indistinguishable from real content and the icon stays in `leftSection`.
         *
         * Detecting it would mean recursing into fragment props, and no call site writes an
         * empty fragment as a button's children.  `<>Delete</>` is the shape that does occur,
         * and it lands on the same path for the right reason.
         */
        cy.mountUI(<div>
            <Button icon='trash' data-testid='fragment'><></></Button>
            <Button icon='trash' data-testid='wrapped'><>Delete</></Button>
        </div>);

        cy.get('[data-testid="wrapped"]').should(() => {
            ['fragment', 'wrapped'].forEach((id) => {
                const button = Cypress.$(`[data-testid="${id}"]`)[0];
                const box = button.getBoundingClientRect();
                const glyph = button.querySelector('svg').getBoundingClientRect();

                expect((glyph.left + glyph.width / 2) - (box.left + box.width / 2),
                    `${id} keeps the icon leading`).to.be.lessThan(-3);
            });
        });
    });

    it('centres a trailing-only icon too', () => {
        // `rightSection` has the mirror-image margin.
        cy.mountUI(<Button iconAfter='upload' aria-label='Send' data-testid='after-only'/>);

        cy.get('[data-testid="after-only"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();
            const glyph = $button[0].querySelector('svg').getBoundingClientRect();

            expect((glyph.left + glyph.width / 2) - (box.left + box.width / 2))
                .to.be.closeTo(0, 1);
        });
    });
});

describe('the file browser footer is a row of buttons, not a slab', () => {
    /*
     * The footer was a plain block, so its buttons -- inline-block elements with no whitespace
     * between them, since JSX drops whitespace-only lines -- sat flush against each other in
     * one unbroken bar.  Every other group of buttons in the app is a Mantine `Group`, which
     * is a flex row with a gap; this one is hand-rolled and never got one.
     *
     * The class carries the layout, so the class is what is mounted.  FileBrowser itself
     * needs the file API, drag selection and a router, none of which decides the spacing.
     */
    it('leaves a gap between adjacent buttons', () => {
        cy.mountUI(<div className='sticky-footer'>
            <Button color='red' data-testid='a'>Delete</Button>
            <Button color='yellow' data-testid='b'>Rename</Button>
            <Button color='teal' data-testid='c'>Move</Button>
        </div>);

        cy.get('.sticky-footer').should(($footer) => {
            const boxes = ['a', 'b', 'c']
                .map(id => $footer[0].querySelector(`[data-testid="${id}"]`).getBoundingClientRect());

            expect(boxes[1].left - boxes[0].right, 'gap between the first two')
                .to.be.greaterThan(2);
            expect(boxes[2].left - boxes[1].right, 'gap between the next two')
                .to.be.greaterThan(2);
        });
    });

    it('keeps them on one line and vertically aligned', () => {
        // A flex row is only right if it behaves like one: the buttons share a baseline and
        // do not stack while there is room for them.
        cy.mountUI(<div className='sticky-footer'>
            <Button data-testid='a'>Delete</Button>
            <Button data-testid='b'>Rename</Button>
        </div>);

        cy.get('.sticky-footer').should(($footer) => {
            const a = $footer[0].querySelector('[data-testid="a"]').getBoundingClientRect();
            const b = $footer[0].querySelector('[data-testid="b"]').getBoundingClientRect();

            expect(a.top, 'same row').to.be.closeTo(b.top, 1);
        });
    });
});

describe('the search field\'s clear button is attached to it', () => {
    /*
     * The control is a bordered box with `padding: 0 8px`, so the clear button sat 9px short
     * of the right edge and 2px short of the full height -- a glyph dropped inside the input
     * rather than a control of its own.
     *
     * Semantic rendered it as an action button welded to the field.  Measured on the QA Pi,
     * which still runs Semantic: zero gap from the input, zero to the outer edge, and the
     * full height of the field.
     */
    const mountField = () => cy.mountUI(<div style={{width: 420}}>
        <SearchBox value='wind turbine' clearable onChange={() => {}}/>
    </div>);

    it('meets the right-hand edge of the field', () => {
        mountField();

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            const control = Cypress.$('.wrolpi-searchbox-control')[0].getBoundingClientRect();
            const clear = $clear[0].getBoundingClientRect();

            expect(control.right - clear.right, 'gap to the field edge').to.be.closeTo(0, 1.5);
        });
    });

    it('fills the height of the field', () => {
        /*
         * Half the reason it read as "inside": a 36px control floating in a 38px box.
         *
         * Measured against the control's CONTENT box, not its border box.  The field's own
         * 1px border is the only thing left above and below the button, and the button
         * should sit inside it rather than paint over it -- `clientHeight` is that box, and
         * comparing against `getBoundingClientRect().height` would be demanding the button
         * cover the field's border, which is a different and wrong design.
         */
        mountField();

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            const control = Cypress.$('.wrolpi-searchbox-control')[0];
            const border = parseFloat(getComputedStyle(control).borderTopWidth);

            expect(border, 'the field has a border to sit inside').to.be.greaterThan(0);
            expect($clear[0].getBoundingClientRect().height, 'clear button height')
                .to.be.closeTo(control.clientHeight, 1);
        });
    });

    it('is divided from the text rather than merged into it', () => {
        // Attached is not the same as indistinguishable: without a rule between them the
        // glyph reads as part of the input again, just further right.
        mountField();

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            const style = getComputedStyle($clear[0]);

            expect(parseFloat(style.borderLeftWidth), 'a divider on its left')
                .to.be.greaterThan(0);
            expect(style.borderLeftStyle).to.not.equal('none');
        });
    });

    it('keeps the loading spinner off the clear button', () => {
        /*
         * `SearchResultsInput` can pass `loading` and `clearable` together, and the DOM order
         * is input, spinner, clear.  An earlier version of the weld cancelled the flex gap on
         * the clear button's LEFT as well as the padding on its right, which welded the
         * spinner to the divider -- the spinner is not part of this control.
         */
        cy.mountUI(<div style={{width: 420}}>
            <SearchBox value='wind turbine' clearable loading onChange={() => {}}/>
        </div>);

        cy.get('.wrolpi-searchbox-loading').should(($spinner) => {
            const clear = Cypress.$('.wrolpi-searchbox-clear')[0].getBoundingClientRect();

            expect(clear.left - $spinner[0].getBoundingClientRect().right,
                'gap between the spinner and the divider').to.be.greaterThan(2);
        });
    });

    it('owns the height in both directions, not just downwards', () => {
        /*
         * `align-self: stretch` cannot shrink a box below its own `min-height`, and Mantine
         * sets that from `--ai-size` alongside `height`.  Overriding `height` alone owns the
         * sizing in one direction only -- it happens to look right because the field is
         * 36.15px against a 36px minimum, a margin of 0.15px.
         *
         * The property rather than the geometry, deliberately.  Making the field genuinely
         * shorter than 36px means overriding the input's own font size and padding, which no
         * part of the app does, and a test that fabricates a layout to prove a rule is not
         * evidence about this app.  This asserts what the rule is for: the minimum is no
         * longer `--ai-size`.  Removing `min-height: unset` fails it.
         */
        cy.mountUI(<div style={{width: 420}}>
            <SearchBox value='wind turbine' clearable onChange={() => {}}/>
            {/* An ActionIcon outside the field, to show where the minimum comes from. */}
            <IconButton icon='trash' label='Delete' data-testid='plain'/>
        </div>);

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            /*
             * Resolved lengths, not the raw variable: `--ai-size` reads back as
             * `calc(2.25rem * var(--mantine-scale))` while `min-height` computes to `36px`, so
             * comparing the two strings can never match and asserts nothing.  The first
             * version of this did exactly that and stayed green with the rule removed.
             */
            const minimum = (element) => parseFloat(getComputedStyle(element).minHeight) || 0;

            // The inverse and the premise together: an ordinary IconButton DOES carry the
            // minimum, so its absence here is this rule's doing and not Mantine's default.
            expect(minimum(Cypress.$('[data-testid="plain"]')[0]),
                'an ordinary icon button has a minimum height').to.be.greaterThan(0);
            expect(minimum($clear[0]), 'the welded one does not').to.equal(0);
        });
    });

    it('has square corners, so nothing shows through at the field edge', () => {
        // A rounded ActionIcon stretched flush to a square field leaves panel-colored wedges
        // at the corners.  Nothing sets this here: the theme zeroes every radius, and this
        // records that the weld depends on it.
        mountField();

        cy.get('.wrolpi-searchbox-clear').should(($clear) => {
            expect(getComputedStyle($clear[0]).borderRadius, 'no rounded corners')
                .to.equal('0px');
        });
    });

    it('is a real constraint: the field itself is still padded', () => {
        /*
         * The negative margins are aimed at one child.  If the control's padding had simply
         * been removed instead, the search icon and the text would sit against the border
         * too -- so this checks the thing that must NOT have moved.
         */
        mountField();

        cy.get('.wrolpi-searchbox-icon').should(($icon) => {
            const control = Cypress.$('.wrolpi-searchbox-control')[0].getBoundingClientRect();

            expect($icon[0].getBoundingClientRect().left - control.left, 'icon is inset')
                .to.be.greaterThan(4);
        });
    });
});

describe('icon-only action buttons in a row are one size', () => {
    /*
     * The map's pin table gives every row three actions: edit, add-to-playlist and delete,
     * all asking for `size='xs'`.  They rendered 46x30, 30x30 and 54x36 -- three different
     * sizes, for three different reasons.
     *
     * Two of those are structural.  `AddToPlaylistButton` renders an IconButton when it has no
     * label, and an ActionIcon is square by construction, while a Button is as wide as its
     * content plus its horizontal padding.  Their heights already agree, because ActionIcon's
     * size scale was remapped onto Button's; width was never aligned.
     *
     * The third is a plain bug: `useAPIButton` never put `size` into the props it hands to
     * Button, so every APIButton in the app rendered at Mantine's default regardless of what
     * its call site asked for.  Seventeen call sites pass a size, from `xs` here to `huge` on
     * Settings.
     */
    const sizes = ['xs', 'sm', 'md', 'lg'];

    sizes.forEach((size) => {
        it(`gives an icon-only Button and an IconButton the same box at ${size}`, () => {
            cy.mountUI(<div>
                <Button size={size} icon='edit' aria-label='Edit' data-testid='plain'/>
                <IconButton size={size} icon='list' label='Add' data-testid='action'/>
            </div>);

            cy.get('[data-testid="action"]').should(($action) => {
                const button = Cypress.$('[data-testid="plain"]')[0].getBoundingClientRect();
                const icon = $action[0].getBoundingClientRect();

                expect(button.height, `${size} heights`).to.be.closeTo(icon.height, 1);
                expect(button.width, `${size} widths`).to.be.closeTo(icon.width, 1);
            });
        });
    });

    it('makes an icon-only button square, not merely equal to its neighbour', () => {
        // Stated separately: two buttons could agree with each other and both be wrong.  A
        // lone glyph in a control belongs in a square one.
        cy.mountUI(<Button size='xs' icon='edit' aria-label='Edit' data-testid='plain'/>);

        cy.get('[data-testid="plain"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();

            expect(box.width, 'square').to.be.closeTo(box.height, 1);
        });
    });

    it('is a real constraint: a labelled button is still as wide as its label', () => {
        // The inverse.  Squaring must apply only to the icon-only case, or every labelled
        // button in the app collapses to a square and clips its text.
        cy.mountUI(<Button size='xs' icon='edit' data-testid='labelled'>Edit this pin</Button>);

        cy.get('[data-testid="labelled"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();

            expect(box.width, 'wider than it is tall').to.be.greaterThan(box.height * 2);
        });
    });
});

describe('APIButton honours the size its call site asks for', () => {
    /*
     * `useAPIButton` assembled the props it hands to Button and left `size` out, so it was
     * dropped at every call site -- seventeen of them, from the map pins' `xs` to Settings'
     * `huge`.  The map's delete pin came out 36px tall beside two 30px siblings.
     */
    it('renders a small APIButton smaller than a large one', () => {
        cy.mountUI(<div>
            <APIButton size='xs' icon='trash' onClick={() => {}} data-testid='small'/>
            <APIButton size='lg' icon='trash' onClick={() => {}} data-testid='large'/>
        </div>);

        cy.get('[data-testid="large"]').should(($large) => {
            const small = Cypress.$('[data-testid="small"]')[0].getBoundingClientRect();

            expect(small.height, 'xs is shorter than lg')
                .to.be.lessThan($large[0].getBoundingClientRect().height - 4);
        });
    });

    it('matches a plain Button given the same size', () => {
        // The claim that matters at the call site: an APIButton and a Button asking for the
        // same size are the same control.
        cy.mountUI(<div>
            <APIButton size='xs' icon='trash' onClick={() => {}} data-testid='api'/>
            <Button size='xs' icon='trash' aria-label='Delete' data-testid='plain'/>
        </div>);

        cy.get('[data-testid="api"]').should(($api) => {
            const plain = Cypress.$('[data-testid="plain"]')[0].getBoundingClientRect();
            const api = $api[0].getBoundingClientRect();

            expect(api.height, 'heights').to.be.closeTo(plain.height, 1);
            expect(api.width, 'widths').to.be.closeTo(plain.width, 1);
        });
    });

    it('honours the Semantic size names the call sites actually use', () => {
        /*
         * The seventeen call sites that were being ignored do not say `xs` and `lg` -- they say
         * `small`, `big`, `large` and `huge`, which `resolveSize` translates.  Testing only the
         * Mantine names would leave the translation step untested on the exact spellings that
         * were broken.  `small` maps to `sm`, which is what the accidental default already was,
         * which is why most detail pages do not move.
         */
        cy.mountUI(<div>
            <APIButton size='small' icon='trash' onClick={() => {}} data-testid='small'/>
            <APIButton size='big' icon='trash' onClick={() => {}} data-testid='big'/>
            <APIButton size='huge' icon='trash' onClick={() => {}} data-testid='huge'/>
            {/* The reference: what `small` is claimed to translate INTO. */}
            <APIButton size='sm' icon='trash' onClick={() => {}} data-testid='reference-sm'/>
        </div>);

        cy.get('[data-testid="huge"]').should(($huge) => {
            const height = (id) =>
                Cypress.$(`[data-testid="${id}"]`)[0].getBoundingClientRect().height;

            /*
             * Measured against a real `sm` button rather than against 36px.  The literal was a
             * hidden assertion that the interface scale is 1, and it broke at 1.1 -- while the
             * claim it is making, that `small` resolves to `sm`, was never about a pixel count.
             */
            expect(height('small'), "small resolves to Mantine's sm")
                .to.be.closeTo(height('reference-sm'), 0.5);
            expect(height('big'), 'big is taller than small').to.be.greaterThan(height('small'));
            expect($huge[0].getBoundingClientRect().height, 'huge is taller than big')
                .to.be.greaterThan(height('big'));
        });
    });

    it('stays square while it is loading', () => {
        /*
         * A loading button swaps its glyph for a spinner sized from the button's height, and
         * the square rule fixes the width to that height -- so a spinner that did not fit
         * would either be clipped or stretch the box.  Both Button and APIButton, since
         * APIButton is what actually spends time loading.
         */
        cy.mountUI(<div>
            <Button size='xs' icon='trash' aria-label='Delete' loading data-testid='busy'/>
            <APIButton size='xs' icon='trash' loading onClick={() => {}} data-testid='busy-api'/>
        </div>);

        cy.get('[data-testid="busy-api"]').should(() => {
            ['busy', 'busy-api'].forEach((id) => {
                const box = Cypress.$(`[data-testid="${id}"]`)[0].getBoundingClientRect();

                expect(box.height, `${id} has a height`).to.be.greaterThan(20);
                expect(box.width, `${id} is still square`).to.be.closeTo(box.height, 1);
            });
        });
    });

    it('squares an iconAfter-only button too', () => {
        // The square rule keys off the same `data-icon-only` marker as the centring, and
        // `iconAfter` alone is one of the cases that sets it.
        cy.mountUI(<Button size='xs' iconAfter='upload' aria-label='Send' data-testid='after'/>);

        cy.get('[data-testid="after"]').should(($button) => {
            const box = $button[0].getBoundingClientRect();

            expect(box.width, 'square').to.be.closeTo(box.height, 1);
        });
    });

    it('is a real constraint: an APIButton with no size keeps the default it had', () => {
        /*
         * `useAPIButton` declared `size = 'medium'` as a parameter default while never using
         * it.  Passing that through would have fixed the bug by breaking everything else --
         * every APIButton that names no size would have grown from Mantine's `sm` to `md`.
         */
        cy.mountUI(<div>
            <APIButton icon='trash' onClick={() => {}} data-testid='default'/>
            <Button icon='trash' aria-label='Delete' data-testid='plain'/>
        </div>);

        cy.get('[data-testid="default"]').should(($api) => {
            const plain = Cypress.$('[data-testid="plain"]')[0].getBoundingClientRect();

            expect($api[0].getBoundingClientRect().height, 'unchanged default')
                .to.be.closeTo(plain.height, 1);
        });
    });
});

describe('a row of icon controls sits level and spaced', () => {
    /*
     * The map's pin actions are three icon controls in one table cell: edit (Button),
     * add-to-playlist (IconButton) and delete (APIButton).  They were laid out as bare
     * siblings, so they were inline-block boxes aligned on their BASELINES -- and a Button's
     * baseline is not an ActionIcon's, so the middle one sat 4.3px higher than the other two.
     * They also touched, because JSX leaves no whitespace between elements.
     *
     * Both are what `Group` is for, which is how every other row of buttons in the app is
     * built.  Measured on the running app at tops 258.6 / 254.2 / 258.6 before the fix.
     */
    const controls = <>
        <Button size='xs' icon='edit' aria-label='Edit' data-testid='edit'/>
        <IconButton size='xs' icon='list' label='Add to Playlist' data-testid='add'/>
        <APIButton size='xs' icon='trash' onClick={() => {}} data-testid='delete'/>
    </>;

    const tops = (root) => ['edit', 'add', 'delete']
        .map(id => root.querySelector(`[data-testid="${id}"]`).getBoundingClientRect().top);

    it('is misaligned without a Group, which is why one is needed', () => {
        /*
         * The premise for the case below, and the thing a reader will not believe otherwise:
         * three controls of identical height still do not line up when they are laid out
         * inline, because they are aligned on text baselines they do not share.
         */
        cy.mountUI(<div data-testid='bare'>{controls}</div>);

        cy.get('[data-testid="bare"]').should(($bare) => {
            const spread = Math.max(...tops($bare[0])) - Math.min(...tops($bare[0]));

            expect(spread, 'bare siblings do not line up').to.be.greaterThan(1);
        });
    });

    it('lines them up when wrapped in a Group', () => {
        cy.mountUI(<Group gap='xs' data-testid='grouped'>{controls}</Group>);

        cy.get('[data-testid="grouped"]').should(($group) => {
            const spread = Math.max(...tops($group[0])) - Math.min(...tops($group[0]));

            expect(spread, 'all three share a top edge').to.be.lessThan(1);
        });
    });

    it('leaves a gap between them', () => {
        cy.mountUI(<Group gap='xs' data-testid='grouped'>{controls}</Group>);

        cy.get('[data-testid="grouped"]').should(($group) => {
            const boxes = ['edit', 'add', 'delete']
                .map(id => $group[0].querySelector(`[data-testid="${id}"]`).getBoundingClientRect());

            expect(boxes[1].left - boxes[0].right, 'first gap').to.be.greaterThan(2);
            expect(boxes[2].left - boxes[1].right, 'second gap').to.be.greaterThan(2);
        });
    });
});
