import React from 'react';
import {
    ActionInput, Button, Header, Icon, IconStack, Loading, MultiSelect, Panel, PathInput,
    Message, Placeholder, Statistic, StatisticGroup, Status, TabBar, Table, tabClassName,
    TextInput,
} from './index';
import {contrastingColor, LoadStatistic} from '../Common';
import {Notifications} from '@mantine/notifications';
import {clearToasts, toast} from './toast';
import {monochromeThemes, themeNames} from '../../themes/names';

/* `--panel` is authored as a hex; computed backgrounds come back as rgb(). */
const hexToRgb = (hex) => {
    const value = hex.replace('#', '');
    const [r, g, b] = [0, 2, 4].map(i => parseInt(value.slice(i, i + 2), 16));
    return `rgb(${r}, ${g}, ${b})`;
};

/*
 * Normalise a colour to rgb(), and REFUSE anything that is neither a hex nor already
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
    throw new Error(`Not a resolved colour: "${trimmed}"`);
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
const luminance = (colour) => {
    const [r, g, b] = (colour.match(/[\d.]+/g) || []).map(Number);
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

    const roleColours = () => {
        const root = getComputedStyle(document.documentElement);
        const panel = toRgb(root.getPropertyValue('--panel'));
        return {
            panel,
            text: toRgb(root.getPropertyValue('--text')),
            roles: ROLES.map(role => ({role, colour: toRgb(root.getPropertyValue(`--${role}`))})),
        };
    };

    themeNames.forEach((theme) => {
        it(`gives every role a colour of its own in ${theme}`, () => {
            // True everywhere.  Two roles resolving to the same value is the original bug.
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {roles} = roleColours();
                const colours = roles.map(r => r.colour);
                colours.forEach((colour, index) => {
                    expect(colour, `${roles[index].role} resolved`).to.match(/^rgb\(/);
                });
                expect(new Set(colours).size, `five distinct roles, got ${colours.join(' ')}`)
                    .to.equal(5);
            });
        });

        it(`keeps every role legible in ${theme}`, () => {
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {panel, roles} = roleColours();
                roles.forEach(({role, colour}) => {
                    /*
                     * 3:1 is the floor for anything that is not body text.  `neutral` is
                     * allowed to sit at the bottom of the ramp -- for `pending` and disabled,
                     * being dim IS the signal -- but it still has to be visible at all.
                     */
                    expect(contrast(colour, panel), `${role} against the panel`)
                        .to.be.at.least(role === 'neutral' ? 2.5 : 3);
                });
            });
        });


        it(`gives each Status kind a colour of its own in ${theme}`, () => {
            /*
             * The end of the chain, through a real component: four states, four distinct
             * painted colours.  In night these used to need three hand-written
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
                const colours = [...$all].map(el => getComputedStyle(el).color);
                expect(new Set(colours).size, `four distinct colours, got ${colours.join(' ')}`)
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
                const {panel, roles} = roleColours();
                const ratios = roles.map(({role, colour}) => ({role, ratio: contrast(colour, panel)}));
                ratios.slice(1).forEach((entry, index) => {
                    expect(entry.ratio, `${entry.role} is louder than ${ratios[index].role}`)
                        .to.be.greaterThan(ratios[index].ratio);
                });
            });
        });

        it(`makes danger at least as loud as ordinary text in ${theme}`, () => {
            /*
             * Also only here.  A light theme's text is near-black at ~14:1 and no danger
             * colour will ever match it; on a single hue the roles and the text are drawn
             * from the same ramp, so the loudest role must not be quieter than the prose.
             */
            cy.mountUI(<Panel>roles</Panel>, {theme});

            cy.get('.wrolpi-panel').should(() => {
                const {panel, text, roles} = roleColours();
                const danger = roles.find(r => r.role === 'danger').colour;
                expect(contrast(danger, panel), 'danger vs --text against the panel')
                    .to.be.at.least(contrast(text, panel) * 0.95);
            });
        });
    });

    it('does not leave failure to colour alone', () => {
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
     * machine under load rendered its warning as an ordinary uncoloured number.
     *
     * Only a browser can see it.  jsdom rejects `color: var(--warning)` as invalid and drops
     * it, so the inline colour reads back empty whatever the component did.
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
                expect(contrast(danger, panel), 'danger is louder than warning')
                    .to.be.greaterThan(contrast(warning, panel));
                expect(contrast(danger, panel), 'danger is louder than a plain reading')
                    .to.be.greaterThan(contrast(fine, panel));

                /*
                 * NOT asserted: that warning outranks a plain reading.  It does not, and that
                 * is a live question rather than an oversight -- an uncoloured value inherits
                 * `--text`, which in night is 4.98:1 against 4.91:1 for `--warning`.  So a
                 * machine under load is marginally QUIETER than one that is fine.
                 *
                 * Lifting warning above text is a palette change, not a call-site one: on a
                 * dark panel the only way up is lightness, and night's danger would desaturate
                 * from #ff3e3e to about #ff5d5d -- trading the theme's "red only" character
                 * for loudness.  Worth a deliberate decision, so it is flagged rather than
                 * quietly made here.
                 */
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
    themeNames.forEach((theme) => {
        it(`sits the control beside the text in ${theme}`, () => {
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

describe('a table header is a surface, not just bold text', () => {
    themeNames.forEach((theme) => {
        it(`separates the header from every body row in ${theme}`, () => {
            /*
             * Mantine gives thead no background, so the header painted whatever was behind
             * the table -- which is exactly what an unstriped body row paints.  Against a
             * striped body the header read as one more stripe, and weight was the only
             * thing telling them apart.  None of this is visible to jsdom: the colours are
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
                     * `rgba(0, 0, 0, 0)` because `body` carries the page colour and the root
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

    monochromeThemes.forEach((theme) => {
        it(`tells its four kinds apart in ${theme}, which is the bug roles exist for`, () => {
            /*
             * The end of the chain, measured rather than inferred.  The jest tests assert the
             * Mantine variable NAME on the style attribute, which would still pass if someone
             * put four hue names back -- four distinct strings that resolve to two colours here.
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
                const colours = [...$toasts].map(t =>
                    getComputedStyle(t).getPropertyValue('--notification-color').trim());
                expect(new Set(colours).size, `four distinct kinds, got ${colours.join(' ')}`)
                    .to.equal(4);

                /*
                 * Distinctness alone does not catch the regression this is for.  Reverting to
                 * hue names gives four distinct values in night too -- blue, green, yellow and
                 * red are not the same colour there.  What they are is cramped and badly
                 * ranked, with `--blue` at 2.29:1 against the toast surface: present, and
                 * invisible.  So the floor is the assertion that has teeth.
                 */
                const surface = toRgb(getComputedStyle($toasts[0]).backgroundColor);
                colours.forEach((colour, index) => {
                    expect(contrast(toRgb(colour), surface), `toast ${index} against its surface`)
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
                const colours = [...$all].map(m =>
                    getComputedStyle(m).getPropertyValue('--message-color').trim());
                expect(new Set(colours).size, `four distinct kinds, got ${colours.join(' ')}`)
                    .to.equal(4);
            });
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

/*
 * The colour a box actually shows, looking through the layers in the order given.
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
        const colour = getComputedStyle(el, pseudo).backgroundColor;
        if (colour && !/^rgba\(.*,\s*0(\.0+)?\)$/.test(colour) && colour !== 'transparent') {
            return colour;
        }
    }
    return null;
};

describe('a loading placeholder is visible on the surface it covers', () => {
    themeNames.forEach((theme) => {
        it(`separates the skeleton from the panel in ${theme}`, () => {
            /*
             * `--head` and `--border` are what the bars come out as, and neither was chosen
             * with a panel behind it in mind.  If they land on the panel's own colour there
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
        it(`resolves the loader colour in ${theme}`, () => {
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
         * The file browser's New Folder button is disabled in WROL mode, and Mantine swaps a
         * disabled button's fill for --mantine-color-disabled.  A disc pinned to `--blue`
         * then becomes a blue chip on a grey surface -- the same defect as the original
         * hole, inverted.  The disc has to follow the button, not the button's enabled fill.
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
         * The nav bar's colour is a user setting written inline on the <nav>, so the stack
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
