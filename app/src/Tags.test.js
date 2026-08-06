import React from 'react';
import {screen, waitFor} from '@testing-library/react';
import {render} from './test-utils';
import {queryContextFixture} from './test-fixtures';
import {QueryContext} from './contexts/contexts';
import {useTags} from './Tags';

/*
 * Tests for the real tag chip.
 *
 * Everything else in the suite takes `NameToTagLabel` from `tagsContextFixture`, which stubs
 * it as a function returning the name -- so nothing exercised the component that actually
 * paints a tag.  That is how a tag came to be unreadable in night mode without a single test
 * noticing: the colors are decided here, in the one place in the app that paints with a
 * value no theme chose.
 */

jest.mock('./api', () => ({
    getTags: jest.fn(),
    getRecentTags: jest.fn(),
    saveTag: jest.fn(),
    deleteTag: jest.fn(),
}));

import {getTags, getRecentTags} from './api';

const BRIGHT = '#ffe066';   // contrastingColor -> black
const DARK = '#1a1a2e';     // contrastingColor -> light

// A harness that renders the real NameToTagLabel out of the real hook.
const TagProbe = ({name}) => {
    const {NameToTagLabel} = useTags();
    return <NameToTagLabel name={name}/>;
};

const renderTag = (name, tags) => render(
    <QueryContext.Provider value={queryContextFixture()}>
        <TagProbe name={name}/>
    </QueryContext.Provider>
);

// The same, for the group -- which is where a row's spacing is decided.
const GroupProbe = ({tagNames, ...props}) => {
    const {TagsLinkGroup} = useTags();
    return <TagsLinkGroup tagNames={tagNames} {...props}/>;
};

const renderGroup = (tagNames, props = {}) => render(
    <QueryContext.Provider value={queryContextFixture()}>
        <GroupProbe tagNames={tagNames} {...props}/>
    </QueryContext.Provider>
);

const tagOf = (name) => screen.getByText(name);

/*
 * Wait for the fetched colors to arrive.  Before they do, `NameToTagLabel` falls back to a
 * plain `<Label tag>` -- which also carries `wrolpi-tag`, so waiting on the class alone
 * passes against the fallback and asserts nothing about the real chip.  Wait for the user's
 * color instead.
 */
const awaitColored = async (name, color) => {
    await waitFor(() =>
        expect(tagOf(name).style.getPropertyValue('--label-color')).toBe(color));
    return tagOf(name);
};

describe('a tag chip', () => {
    beforeEach(() => {
        getTags.mockResolvedValue({
            tags: [
                {id: 1, name: 'Water', color: BRIGHT},
                {id: 2, name: 'Archived', color: DARK},
                {id: 3, name: 'Uncolored', color: null},
            ],
        });
        getRecentTags.mockResolvedValue({tags: []});
    });

    it('carries the tag shape, not just the chip shape', async () => {
        renderTag('Water');

        const tag = await awaitColored('Water', BRIGHT);
        expect(tag).toHaveClass('wrolpi-tag');
        expect(tag).toHaveClass('wrolpi-label');
    });

    it('puts the calculated text color in a variable, never in `color`', async () => {
        /*
         * This is the whole defect.  As an inline `color` declaration nothing in a stylesheet
         * could outrank it, so night -- which turns a tag into an outline over a near-black
         * page -- was still painting the black text that had been calculated for a bright
         * yellow fill.  The tag was legible only by its border.
         */
        renderTag('Water');

        const tag = await awaitColored('Water', BRIGHT);
        expect(tag.style.getPropertyValue('--label-text')).toBe('#000000');
        expect(tag.style.color).toBe('');
    });

    it('calculates light text for a dark tag', async () => {
        renderTag('Archived');

        const tag = await awaitColored('Archived', DARK);
        const text = tag.style.getPropertyValue('--label-text');
        // Non-empty first: an absent variable would satisfy "not black" for free.
        expect(text).toBeTruthy();
        expect(text).not.toBe('#000000');
    });

    it('falls back to a default color rather than leaving the fill unset', async () => {
        renderTag('Uncolored');

        // The tag exists with no color of its own, so the default stands in.
        await waitFor(() =>
            expect(tagOf('Uncolored').style.getPropertyValue('--label-color')).toBeTruthy());
    });

    it('still shows the name before any tags have been fetched', async () => {
        // The colors are not known yet; the word matters more than the color.
        getTags.mockResolvedValue({tags: []});
        renderTag('Water');

        expect(await screen.findByText('Water')).toBeInTheDocument();
    });
});

/*
 * How far apart a row of tags sits.
 *
 * A tag already carries a `margin-left` in ui.css, and that one is structural: the point is
 * drawn outside the body, so the margin is the room it needs and cannot be reclaimed.  Every
 * other gap in a row was decoration on top of it, and measured on the dashboard the tags were
 * 34.7px apart horizontally and 18.5px apart vertically -- of which only 18.7px was the point.
 *
 * Rendered px throughout, measured in the browser at the default interface scale.  ui.css states
 * the same margin in design px, as `1.0625rem`.
 */
describe('a row of tags', () => {
    beforeEach(() => {
        getTags.mockResolvedValue({
            tags: [
                {id: 1, name: 'Water', color: BRIGHT},
                {id: 2, name: 'Archived', color: DARK},
            ],
        });
        getRecentTags.mockResolvedValue({tags: []});
    });

    it('adds no margin of its own around a linked tag', async () => {
        /*
         * The link wrapper carried `0.3em` either side, from when these were framework labels
         * that had no margin of their own.  It is 0.3em twice, plus the group's gap, plus the
         * structural margin -- so two tags sat 34.7px apart where the point needs 18.7px, and
         * a wall of tags on the dashboard read as loose.
         */
        renderGroup(['Water', 'Archived']);

        const tag = await awaitColored('Water', BRIGHT);
        // The link has to exist first, or `null.style` would be the failure rather than a margin.
        const link = tag.closest('a');
        expect(link).toBeTruthy();
        expect(link.style.marginLeft).toBe('');
        expect(link.style.marginRight).toBe('');
    });

    it('applies the caller-given spacing to the group, not to every tag in it', async () => {
        /*
         * The dashboard passes `marginTop` to space the row below its heading.  `TagsLinkGroup`
         * spread its props all the way down to each chip, so that margin landed on all 34 tags
         * -- which is not a margin above the row, it is 7.7px added between every wrapped row
         * of it.  The tags were the only thing on the page whose rows were further apart than
         * the group's own gap.
         */
        renderGroup(['Water', 'Archived'], {style: {marginTop: '0.5em'}});

        const tag = await awaitColored('Water', BRIGHT);
        // Not on the chip ...
        expect(tag.style.marginTop).toBe('');

        // ... and on the group, so the spacing the caller asked for still happens.
        const group = tag.closest('.mantine-Group-root');
        expect(group).toBeTruthy();
        expect(group.style.marginTop).toBe('0.5em');
    });

    it('dresses the row with a className, and still hands the rest to each tag', async () => {
        /*
         * `className` goes the same way as `style`, and for the same reason: it describes the row.
         * It is tested rather than only documented because the two halves of this contract are
         * one destructure apart, and the `style` half was wrong for as long as it existed.
         *
         * `onClick` is the other half, asserted here so a later tidy-up cannot route everything
         * to the group and leave a wall of tags that no longer responds to a click.
         */
        const onClick = jest.fn();
        renderGroup(['Water', 'Archived'], {className: 'tag-row', onClick});

        const tag = await awaitColored('Water', BRIGHT);
        expect(tag.className).not.toContain('tag-row');
        expect(tag.closest('.mantine-Group-root').className).toContain('tag-row');

        tag.click();
        expect(onClick).toHaveBeenCalled();
    });
});
