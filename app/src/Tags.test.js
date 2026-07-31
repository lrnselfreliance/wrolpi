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
 * noticing: the colours are decided here, in the one place in the app that paints with a
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

const tagOf = (name) => screen.getByText(name);

/*
 * Wait for the fetched colours to arrive.  Before they do, `NameToTagLabel` falls back to a
 * plain `<Label tag>` -- which also carries `wrolpi-tag`, so waiting on the class alone
 * passes against the fallback and asserts nothing about the real chip.  Wait for the user's
 * colour instead.
 */
const awaitColoured = async (name, color) => {
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
                {id: 3, name: 'Uncoloured', color: null},
            ],
        });
        getRecentTags.mockResolvedValue({tags: []});
    });

    it('carries the tag shape, not just the chip shape', async () => {
        renderTag('Water');

        const tag = await awaitColoured('Water', BRIGHT);
        expect(tag).toHaveClass('wrolpi-tag');
        expect(tag).toHaveClass('wrolpi-label');
    });

    it('puts the calculated text colour in a variable, never in `color`', async () => {
        /*
         * This is the whole defect.  As an inline `color` declaration nothing in a stylesheet
         * could outrank it, so night -- which turns a tag into an outline over a near-black
         * page -- was still painting the black text that had been calculated for a bright
         * yellow fill.  The tag was legible only by its border.
         */
        renderTag('Water');

        const tag = await awaitColoured('Water', BRIGHT);
        expect(tag.style.getPropertyValue('--label-text')).toBe('#000000');
        expect(tag.style.color).toBe('');
    });

    it('calculates light text for a dark tag', async () => {
        renderTag('Archived');

        const tag = await awaitColoured('Archived', DARK);
        const text = tag.style.getPropertyValue('--label-text');
        // Non-empty first: an absent variable would satisfy "not black" for free.
        expect(text).toBeTruthy();
        expect(text).not.toBe('#000000');
    });

    it('falls back to a default colour rather than leaving the fill unset', async () => {
        renderTag('Uncoloured');

        // The tag exists with no colour of its own, so the default stands in.
        await waitFor(() =>
            expect(tagOf('Uncoloured').style.getPropertyValue('--label-color')).toBeTruthy());
    });

    it('still shows the name before any tags have been fetched', async () => {
        // The colours are not known yet; the word matters more than the colour.
        getTags.mockResolvedValue({tags: []});
        renderTag('Water');

        expect(await screen.findByText('Water')).toBeInTheDocument();
    });
});
