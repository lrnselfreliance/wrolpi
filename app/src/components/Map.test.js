import fs from 'fs';
import path from 'path';

/*
 * The map pin table's action cells.
 *
 * Each row offers edit, add-to-playlist and delete, and they were laid out as bare siblings in
 * a table cell.  That makes them inline-block boxes aligned on their text BASELINES, and a
 * Button's baseline is not an ActionIcon's -- measured on the running app, the middle control
 * sat 4.3px above the other two -- and they touched, because JSX leaves no whitespace between
 * elements.  `Group` is what every other row of buttons in the app uses.
 *
 * Checked in the source because neither row is reachable from a test that could measure it:
 * `MapPins` fetches its pins from the API and builds its rows through SortableTable, and the
 * row builders are internal to the module.  ui-layout.cy.js measures the pattern itself --
 * that bare siblings really are misaligned and that a Group really does fix it -- so what is
 * left to guard is that these cells use one.
 */

const source = fs.readFileSync(path.join(__dirname, 'Map.js'), 'utf8');

/** The contents of every `<Table.Cell>` in the file. */
const cells = () => {
    const found = [];
    const open = '<Table.Cell';
    for (let at = source.indexOf(open); at !== -1; at = source.indexOf(open, at + 1)) {
        const end = source.indexOf('</Table.Cell>', at);
        if (end !== -1) found.push(source.slice(at, end));
    }
    return found;
};

describe('the map pin action cells', () => {
    it('finds the cells at all', () => {
        // The premise.  A parser that matched nothing would report no offenders and read
        // exactly like a file that was already correct.
        expect(cells().length).toBeGreaterThan(5);
    });

    /*
     * Named cells, not a count of control tags.
     *
     * Counting was tried first and does not work: a cell whose buttons are the two arms of a
     * ternary renders exactly one of them and needs no Group -- the "Built" / "Build" cell on
     * the map files table is that shape -- and excluding ternaries to allow for it also
     * excluded the subscribe cell, whose `role={isSubscribed ? ... : ...}` has nothing to do
     * with how many controls it holds.  A guard that quietly stops covering a cell is worse
     * than one with a stated scope.
     *
     * So each cell is named by something only it contains, and the general claim -- that bare
     * inline controls really are misaligned and that a Group really does fix it -- is measured
     * in ui-layout.cy.js instead.
     */
    const rows = [
        {name: 'pin actions', marker: 'setEditingId(pin.id)'},
        /*
         * `role='cancel'`, not `onSave(...)`: the edit row's TextInput calls onSave from its
         * own onKeyDown, in a different cell, so that marker matched the input's cell and this
         * quietly checked the wrong one.  A marker has to be unique to the cell it names.
         */
        {name: 'pin edit save/cancel', marker: "role='cancel'"},
        {name: 'map file subscribe', marker: 'setPreviewOpen(true)'},
    ];

    rows.forEach(({name, marker}) => {
        it(`groups the ${name} cell`, () => {
            const cell = cells().find(candidate => candidate.includes(marker));

            /*
             * The premise and the claim in one object, because jest's `expect` takes no
             * message argument -- that is chai, and passing one throws rather than annotating.
             * A rename of the marker would otherwise turn this into a test of nothing.
             */
            /*
             * The Group must CONTAIN the cell's controls, not merely appear in it.  Asserting
             * that `<Group` is present anywhere would pass on an empty one left beside the
             * bare siblings it was supposed to wrap.
             */
            const between = (text, open, close) => {
                const from = text.indexOf(open);
                if (from === -1) return '';
                const to = text.indexOf(close, from);
                // An unclosed Group would otherwise swallow the rest of the cell, which is how
                // the first version of this let an EMPTY Group pass with the controls left
                // outside it.
                return to === -1 ? '' : text.slice(from, to);
            };
            const inGroup = cell === undefined ? '' : between(cell, '<Group', '</Group>');
            const controls = (text) =>
                (text.match(/<(?:API)?Button\b|<IconButton\b|<AddToPlaylistButton\b/g) || []).length;

            expect({
                marker,
                found: cell !== undefined,
                grouped: !!cell?.includes('<Group'),
                // Every control the cell has is inside the Group, none left outside it.
                controlsInsideGroup: cell === undefined ? 0 : controls(inGroup),
                controlsInCell: cell === undefined ? -1 : controls(cell),
            }).toEqual({
                marker, found: true, grouped: true,
                controlsInsideGroup: cell === undefined ? 0 : controls(cell),
                controlsInCell: cell === undefined ? -1 : controls(cell),
            });
        });
    });
});

describe('the map\'s icon-only controls have accessible names', () => {
    /*
     * An icon-only Button carries no text, so without `aria-label` it reaches assistive tech
     * as an unnamed button.  `IconButton` requires a label by construction and
     * AddToPlaylistButton supplies one; the plain Button and APIButton used for edit, delete
     * and the catalog preview did not, and this change rewrote all three rows.
     *
     * In the source, for the same reason as the Group guard: these rows are built inside the
     * module and fetched from the API.
     */
    const openingTag = (text, at) => {
        let depth = 0;
        for (let i = at; i < text.length; i++) {
            const c = text[i];
            if (c === '{' || c === '(') depth += 1;
            else if (c === '}' || c === ')') depth -= 1;
            else if (c === '>' && depth === 0) return {tag: text.slice(at, i + 1), end: i};
        }
        return {tag: '', end: at};
    };

    /** Every `<Button>`/`<APIButton>` in the file whose only content is an icon. */
    const iconOnlyControls = () => {
        const found = [];
        for (const match of source.matchAll(/<(?:API)?Button\b/g)) {
            const {tag, end} = openingTag(source, match.index);
            if (!/\bicon=/.test(tag)) continue;
            // Self-closing, or immediately followed by another tag rather than by a label.
            const following = source.slice(end + 1, end + 40).trim();
            if (!(tag.endsWith('/>') || following.startsWith('<') || following.startsWith('}'))) {
                continue;
            }
            found.push({line: source.slice(0, match.index).split('\n').length, tag});
        }
        return found;
    };

    it('finds the icon-only controls at all', () => {
        // The premise.  A scanner that matched nothing would report no offenders and read
        // exactly like a file that was already correct.
        expect(iconOnlyControls().length).toBeGreaterThan(2);
    });

    it('names every one of them', () => {
        const unnamed = iconOnlyControls()
            .filter(({tag}) => !/aria-label/.test(tag))
            .map(({line, tag}) => `line ${line}: ${tag.split('\n')[0].trim()}`);

        expect(unnamed).toEqual([]);
    });
});
