import fs from 'fs';
import path from 'path';

/*
 * The size of the interface.
 *
 * Measured on the QA Pi at 1280px against the build users had before, the drift was not
 * one number: its headings were h1 28 / h2 24 / h3 18 / h4 15 / h5 14 against our 26 / 21 / 17
 * / 14 / 13, and its video card a fixed 290px with an 18px title against our 238px with a 13px
 * one -- while our BODY text and chrome went the other way, 16px base against its 14 and
 * 42px buttons against 36.  So no per-component nudge reproduces what a user comparing the two
 * actually sees, which is the whole page at once.
 *
 * Ten percent is not a fudge factor.  Our heading scale multiplied by 1.1 is 28.6 / 23.1 / 18.7
 * / 15.4 / 14.3 -- the old numbers, to within a pixel at every step.
 *
 * The lever is the root font-size, and everything that should grow with it is written in `rem`.
 * That is Mantine's own mechanism: its 644 size declarations are `calc(Xrem * var(--mantine-
 * scale))`, and `theme.scale` exists specifically to CANCEL a customised root font-size, which
 * is why it must stay at 1 here -- we want those sizes to grow.
 *
 * `zoom: 1.1` on the root was tried first and rejected.  It works, and it is one line, but it
 * scales at paint time: every 1px hairline becomes 1.1px and softens on a 1x display, and
 * viewport units do not shrink to compensate, so `100vh` paints 110% of the screen -- a 95vw
 * modal overflowed sideways and the CBZ viewer's fullscreen overflowed down.  Rem scales real
 * lengths instead, leaves borders crisp, leaves viewport units alone, and respects a user's own
 * browser font-size setting rather than overriding it.
 */

const SRC = path.join(__dirname, '..');
const tokens = fs.readFileSync(path.join(__dirname, 'tokens.css'), 'utf8');

/** Our own stylesheets -- the ones the scale has to reach. */
const STYLESHEETS = ['themes/tokens.css', 'App.css', 'index.css', 'components/ui/ui.css']
    .map(file => [file, path.join(SRC, file)])
    .filter(([, full]) => fs.existsSync(full));

/** `source` with every comment blanked, keeping line numbers intact. */
const stripComments = (source) => source
    .replace(/\/\*[\s\S]*?\*\//g, block => block.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (all, before) => before + ' '.repeat(all.length - before.length));

/** Every source file under src/, excluding tests. */
const sourceFiles = (dir = SRC) => fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === 'node_modules' ? [] : sourceFiles(full);
    if (!/\.(js|jsx|ts|tsx|css)$/.test(entry.name)) return [];
    if (/\.(test|cy)\.(js|jsx|ts|tsx)$/.test(entry.name)) return [];
    return [full];
});

describe('--ui-scale', () => {
    it('scales the interface from the root font-size', () => {
        // A percentage of the browser's own default, not a px value: a user who has set a
        // larger default font keeps it, scaled, instead of having it overridden.
        expect(tokens).toMatch(/--ui-scale:\s*1\.1;/);
        expect(tokens).toMatch(/\n\s*font-size:\s*calc\(100%\s*\*\s*var\(--ui-scale\)\)/);
    });

    it('leaves Mantine free to grow with it', () => {
        /*
         * `theme.scale` divides Mantine's rem lengths by itself, to undo a customised root
         * font-size.  Setting it to 1.1 alongside a 110% root would therefore cancel out
         * exactly, leaving Mantine's half of the interface at its original size while ours
         * grew -- buttons the old size beside 10% larger text.
         */
        const mantine = fs.readFileSync(path.join(__dirname, 'mantine.ts'), 'utf8');
        expect(stripComments(mantine)).not.toMatch(/\bscale:\s*[\d.]/);
    });

    it('writes every scalable length in our stylesheets in rem, so the scale reaches it', () => {
        /*
         * A px font-size does not grow with the root, so it would shrink RELATIVE to
         * everything around it -- the failure is a 13px caption beside 14.3px prose, which
         * reads as sloppy rather than broken and so never gets reported.
         *
         * Borders are exempt and must stay px: a hairline is a hairline at any text size, and
         * scaling it is exactly what made `zoom` the wrong tool.  Same for outlines, which are
         * hairlines wearing a different name.
         */
        /*
         * `transform` and `flex-basis` are on the list because a length there is as much part
         * of the layout as a padding.  The first version left them off and the name of this
         * test still said "every scalable length": `transform: translateX(26px)` sat in App.css
         * untouched while the track and knob either side of it were converted to rem, so a
         * switch's thumb travelled 26px across a track that had grown to 54px.
         */
        const SCALABLE = new RegExp('^\\s*(' + [
            'font-size', 'padding', 'padding-\\w+', 'margin', 'margin-\\w+',
            'gap', 'row-gap', 'column-gap', 'width', 'min-width', 'max-width',
            'height', 'min-height', 'max-height', 'border-radius',
            'top', 'right', 'bottom', 'left',
            'transform', '-webkit-transform', '-ms-transform', 'translate',
            'flex', 'flex-basis',
        ].join('|') + ')\\s*:');

        const offenders = [];
        let scanned = 0;
        let negatives = 0;
        for (const [name, full] of STYLESHEETS) {
            stripComments(fs.readFileSync(full, 'utf8')).split('\n').forEach((line, index) => {
                if (!SCALABLE.test(line)) return;
                scanned += 1;
                /*
                 * The optional leading `-` is load-bearing.  Without it the lookbehind treated
                 * a minus sign as part of the preceding token, so every NEGATIVE length was
                 * invisible: `left: -7px` and `margin-top: -2.5px` position the eyelet on a
                 * tag whose diamond had been converted to rem, and `right: -3px` / `bottom:
                 * -3px` place the corner badge on an icon that had also been converted.  Each
                 * one is a piece of geometry that stopped tracking the piece it belongs to.
                 */
                const px = [...line.matchAll(/(?<![\w.])(-?\d+(?:\.\d+)?)px/g)]
                    // 0 has no unit to scale, and 1px either way is a hairline.
                    .filter(match => Math.abs(parseFloat(match[1])) > 1);
                if (px.some(match => match[1].startsWith('-'))) negatives += 1;
                if (px.length) offenders.push(`${name}:${index + 1}: ${line.trim().slice(0, 64)}`);
            });
        }

        // The premise: a regex that matched no declarations would report no offenders.
        expect(scanned).toBeGreaterThan(100);
        expect(offenders).toEqual([]);
    });

    it('keeps hairlines out of the scale', () => {
        /*
         * The inverse of the rule above, and the reason it is worth a test of its own: a bulk
         * px-to-rem pass that also converted the borders would leave every rule in the app
         * growing with the type, which is the defect `zoom` had.  At least most borders must
         * still be px.
         */
        /*
         * Only the properties that carry a border's THICKNESS.  `border-radius` is a
         * scalable length -- a 10% larger control wants a proportionally larger corner --
         * and an earlier version of this matched it, so it failed on the correct answer.
         */
        const THICKNESS = /^\s*(border|border-(top|right|bottom|left|inline|block)(-\w+)?|border-width|outline|outline-offset)\s*:/;

        const borders = [];
        for (const [, full] of STYLESHEETS) {
            stripComments(fs.readFileSync(full, 'utf8')).split('\n').forEach(line => {
                if (THICKNESS.test(line) && !/radius/.test(line)) borders.push(line);
            });
        }
        const pxBorders = borders.filter(line => /\dpx/.test(line));
        const remBorders = borders.filter(line => /\drem/.test(line));

        expect(borders.length).toBeGreaterThan(30);
        expect({rem: remBorders, someArePx: pxBorders.length > 20})
            .toEqual({rem: [], someArePx: true});
    });

    it('writes no px font-size inline, anywhere', () => {
        /*
         * An inline size is part of the scale whether or not it looks like one: a bare number
         * in `fontSize` is px by React's own rule, so `fontSize: 12` is a 12px caption that
         * stays 12px while the prose beside it grows to 13.2.  Nothing breaks -- it just reads
         * as slightly sloppy, in 46 places, which is not a bug anyone reports.
         *
         * The whole of src is scanned, the gallery included.  /theme-sample is linked from
         * Settings and ships to users, so its annotations are interface text too.
         */
        const offenders = [];
        for (const file of sourceFiles()) {
            if (file.endsWith('.css')) continue;
            stripComments(fs.readFileSync(file, 'utf8')).split('\n').forEach((line, index) => {
                /*
                 * A bare number (px by React's rule) or an explicit px.  Relative units are
                 * fine and are not offences: `em` resolves against the parent's font-size and
                 * `%` likewise, so both already grow with the scale.  An earlier version
                 * allowed only `rem` and reported 21 perfectly good `0.85em` captions.
                 */
                if (/fontSize:\s*(\d|['"][\d.]+px)/.test(line)) {
                    offenders.push(`${path.relative(SRC, file)}:${index + 1}: ${line.trim().slice(0, 60)}`);
                }
            });
        }

        /*
         * The premise: `fontSize` in rem has to be found, or a codebase with no inline sizes
         * at all would read identically to one that had converted them.
         *
         * Occurrences rather than files.  Counting files gave 8 for the 46 conversions -- 32
         * of them are in the gallery -- so a threshold set from the conversion count failed
         * against the correct answer.
         */
        const remSizes = sourceFiles().flatMap(file =>
            [...fs.readFileSync(file, 'utf8').matchAll(/fontSize:\s*['"][\d.]+rem/g)]);
        expect(remSizes.length).toBeGreaterThan(40);

        expect(offenders).toEqual([]);
    });

    it('keeps numeric geometry out of the component library, where a scale cannot reach it', () => {
        /*
         * The library's own inline styles, held to the same rule as its font sizes.  `gap: 10`
         * in Confirm and `padding: '10px 12px 12px'` in Card were px forever, so the ten such
         * blocks moved into ui.css; this is what stops the eleventh being written.
         *
         * Deliberately the LIBRARY only.  There are about 176 numeric geometry values left in
         * 23 feature files -- the map overlays were the visible ones and are converted, but
         * sweeping the rest is a change to 23 files that nobody has looked at, and it is not
         * this test's job to pretend otherwise.  That gap is the reason the sibling test above
         * says "in our stylesheets" rather than "everywhere": an earlier name claimed the
         * whole app while scanning four files.
         */
        const GEOMETRY = new RegExp('\\b(' + [
            'padding', 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight',
            'margin', 'marginTop', 'marginBottom', 'marginLeft', 'marginRight',
            'gap', 'rowGap', 'columnGap', 'width', 'height', 'minWidth', 'minHeight',
            'maxWidth', 'maxHeight', 'borderRadius', 'flexBasis',
        ].join('|') + "):\\s*(-?[1-9][0-9]*\\b|['\"]-?[\\d.]+px)");

        const offenders = [];
        for (const file of sourceFiles(path.join(SRC, 'components', 'ui'))) {
            if (file.endsWith('.css')) continue;
            stripComments(fs.readFileSync(file, 'utf8')).split('\n').forEach((line, index) => {
                if (GEOMETRY.test(line)) {
                    offenders.push(`${path.relative(SRC, file)}:${index + 1}: ${line.trim().slice(0, 60)}`);
                }
            });
        }

        expect(offenders).toEqual([]);
    });
});
