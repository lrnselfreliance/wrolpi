import React from 'react';
import {
    ActionInput, Button, Header, PathInput, Statistic, StatisticGroup, TabBar, tabClassName, TextInput,
} from './index';
import {contrastingColor} from '../Common';
import {Notifications} from '@mantine/notifications';
import {toast} from './toast';
import {themeNames} from '../../themes/names';

/* `--panel` is authored as a hex; computed backgrounds come back as rgb(). */
const hexToRgb = (hex) => {
    const value = hex.replace('#', '');
    const [r, g, b] = [0, 2, 4].map(i => parseInt(value.slice(i, i + 2), 16));
    return `rgb(${r}, ${g}, ${b})`;
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

describe('StatisticGroup separates its statistics with nothing but space', () => {
    /*
     * The group has no frame, no rules between cells and no surface of its own: the
     * statistics sit on whatever they were dropped onto and take its colour.  That leaves
     * the gap as the only thing keeping them apart, and `auto-fit` decides how many rows
     * there are at paint time -- so whether they actually stay apart is a question only a
     * browser can answer.  jsdom has no tracks, no rows and no widths.
     */

    // Narrow enough that six statistics cannot fit on one row at a 150px minimum.
    const inNarrowColumn = (children) => <div style={{width: 340}}>{children}</div>;

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

    it('takes no colour of its own, so it sits on the surface it is given', () => {
        /*
         * This is the point of having no chrome: dropped on the page it reads as page, dropped
         * in a Panel it reads as panel.  A background on the group or a cell -- which is how
         * this was built first, to carry hairlines -- would show as a patch of the wrong colour
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
            // there is no cell around it, so both colours have to resolve in every theme.
            cy.mountUI(inNarrowColumn(sixStatistics), {theme});

            cy.get('.wrolpi-statistic-value').first().then(($value) => {
                const value = getComputedStyle($value[0]).color;

                cy.get('.wrolpi-statistic-label').first().should(($label) => {
                    const label = getComputedStyle($label[0]).color;
                    expect(value, 'value colour resolved').to.match(/^rgba?\(/);
                    expect(label, 'label colour resolved').to.match(/^rgba?\(/);
                    // The label is the muted token and the value is body text; if either fell
                    // back the two would come out the same and the statistic would flatten.
                    expect(label, 'label is distinct from the value').to.not.equal(value);
                });
            });
        });
    });
});

describe('a tag is legible in every theme, whatever colour the user picked', () => {
    /*
     * Tag colours are the user's, stored per tag -- the only thing in the app painted with a
     * value no theme chose.  Tags.js calculates black or light text against that fill, and
     * night discards the fill entirely (a filled tag would be a bright patch) while amber
     * replaces it with its own.  Whether the text still reads afterwards is a question about
     * resolved colour against a real painted surface, so it can only be asked here.
     */

    // The extremes of the black-or-light decision, plus a mid tone.
    const TAG_COLOURS = [
        ['Reference', '#f2f2f2'],   // near-white: text is calculated black
        ['Archived', '#1b1c1d'],    // near-black: text is calculated light
        ['Water', '#2185d0'],
    ];

    const tags = <div>
        {TAG_COLOURS.map(([name, color]) => <span
            key={name}
            className='wrolpi-label wrolpi-tag'
            data-tag={name}
            style={{'--label-color': color, '--label-text': contrastingColor(color)}}
        >{name}</span>)}
    </div>;

    themeNames.forEach((theme) => {
        TAG_COLOURS.forEach(([name]) => {
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
         * The original defect, reproduced deliberately: the calculated text colour written to
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
     * Only a browser can catch that.  jsdom resolves no `var()`, so the title's colour there is
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

    it('keeps the title more prominent than the message', () => {
        /*
         * Night and amber drop the description's muting, because `--muted` on a panel is 2.0:1
         * in night.  Weight has to carry the hierarchy once colour cannot.
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
                const colour = getComputedStyle($input[0]).color;
                expect(colour, 'input text colour resolved').to.match(/^rgba?\(/);
                // Only an rgba() alpha of zero is invisible.  Matching a trailing ", 0)"
                // loosely would flag amber's opaque rgb(255, 149, 0) for its blue channel.
                expect(colour, 'input text is not transparent')
                    .not.to.match(/^rgba\(.*,\s*0(\.0+)?\)$/);
            });

            cy.get('.wrolpi-path-input-control').should(($control) => {
                expect(getComputedStyle($control[0]).borderTopColor, 'border resolved')
                    .to.match(/^rgba?\(/);
            });
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
