import React from 'react';
import fs from 'fs';
import path from 'path';
import {act, render, screen, waitFor} from '../test-utils';
import userEvent from '@testing-library/user-event';
import {
    CardLink, contrastingColor, contrastRatio, DirectorySearch, ExternalCardLink, HelpHeader,
    InfoHeader, loadRole,
    PageContainer,
    SearchResultsInput, TAG_TEXT_DARK, TAG_TEXT_LIGHT,
} from './Common';
import {healthRole} from './admin/ControllerPage';

// Mock debounce to make tests run faster
jest.mock('lodash/debounce', () => jest.fn(fn => {
    fn.cancel = jest.fn();
    return fn;
}));

// Mock useSearchDirectories hook to avoid async state updates that cause act() warnings
const mockSetDirectoryName = jest.fn();
let mockHookState = {
    directoryName: '',
    directories: [],
    channelDirectories: [],
    domainDirectories: [],
    isDir: false,
    loading: false,
};

jest.mock('../hooks/customHooks', () => ({
    ...jest.requireActual('../hooks/customHooks'),
    useSearchDirectories: (value) => {
        // Return current mock state - tests control state via setMockHookState
        return {
            ...mockHookState,
            setDirectoryName: (newValue) => {
                mockHookState.directoryName = newValue;
                mockSetDirectoryName(newValue);
            },
        };
    },
}));

describe('DirectorySearch', () => {
    const mockOnSelect = jest.fn();

    const mockSearchResults = {
        directories: [
            {path: 'videos/nature'},
            {path: 'videos/tech'}
        ],
        channelDirectories: [
            {path: 'videos/channels/news', name: 'News Channel'}
        ],
        domainDirectories: [
            {path: 'archive/example.com', domain: 'example.com'}
        ],
    };

    // Helper to reset mock hook state with specific values
    const setMockHookState = (overrides = {}) => {
        mockHookState = {
            directoryName: '',
            directories: [],
            channelDirectories: [],
            domainDirectories: [],
            isDir: false,
            loading: false,
            ...overrides,
        };
    };

    beforeEach(() => {
        jest.clearAllMocks();
        // Reset mock hook state with default search results
        setMockHookState({
            ...mockSearchResults,
            isDir: false,
        });
    });

    describe('Rendering', () => {
        it('renders with placeholder text', () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toBeInTheDocument();
        });

        it('shows initial value when provided', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'videos/test',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value="videos/test"/>);

            const input = screen.getByDisplayValue('videos/test');
            expect(input).toBeInTheDocument();
        });

        it('applies disabled state correctly', () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" disabled/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toBeDisabled();
        });

        it('renders the dropdown without crashing when directoryName is null', async () => {
            // An unset form field (e.g. the new Channel page) passes a null value.  With
            // isDir=false a "New Directory" result is built from directoryName; if that title is
            // null, Semantic UI's Search crashes reading null.length when the menu opens.
            setMockHookState({
                directories: [],
                channelDirectories: [],
                domainDirectories: [],
                isDir: false,
                directoryName: null,
            });

            render(<DirectorySearch onSelect={mockOnSelect} value={null}/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            // Opening the menu (as Tab/focus does in the browser) must not throw.
            await userEvent.click(input);

            await waitFor(() => {
                expect(screen.getByText(/New Directory/i)).toBeInTheDocument();
            });
        });

        it('displays with required indicator', () => {
            render(
                <DirectorySearch onSelect={mockOnSelect} value="" required/>
            );

            // Unlike Semantic UI's Search, the SearchBox forwards `required` straight
            // onto the input.
            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toBeRequired();
        });
    });

    describe('Search Functionality', () => {
        it('triggers setDirectoryName on value change', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.type(input, 'videos');

            // Verify setDirectoryName was called (via mocked hook)
            expect(mockSetDirectoryName).toHaveBeenCalled();
            // Debounce is mocked, so each character triggers a call
            // Verify it was called 6 times (one per character in "videos")
            expect(mockSetDirectoryName.mock.calls.length).toBe(6);
        });

        it('shows loading indicator when loading state is true', () => {
            setMockHookState({
                ...mockSearchResults,
                loading: true,
            });

            const {container} = render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            // SearchBox renders a Loader alongside the input while `loading` is true.
            expect(container.querySelector('.wrolpi-searchbox-loading')).toBeInTheDocument();
        });

        it('hides loading indicator when loading state is false', () => {
            setMockHookState({
                ...mockSearchResults,
                loading: false,
            });

            const {container} = render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            expect(container.querySelector('.wrolpi-searchbox-loading')).not.toBeInTheDocument();
        });

        it('displays categorized results', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            // Click to open dropdown
            await userEvent.click(input);

            await waitFor(() => {
                // Should show category names
                expect(screen.getAllByText(/Directories/i).length).toBeGreaterThan(0);
                expect(screen.getAllByText(/Channels/i).length).toBeGreaterThan(0);
                expect(screen.getAllByText(/Domains/i).length).toBeGreaterThan(0);
            });
        });

        it('shows "New Directory" when path doesn\'t exist (isDir=false)', async () => {
            setMockHookState({
                directories: [],
                channelDirectories: [],
                domainDirectories: [],
                isDir: false,
                directoryName: 'new/path',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            await waitFor(() => {
                expect(screen.getByText(/New Directory/i)).toBeInTheDocument();
            });
        });

        it('hides "New Directory" when path exists (isDir=true)', async () => {
            setMockHookState({
                directories: [{path: 'videos/nature/wildlife'}],
                channelDirectories: [],
                domainDirectories: [],
                isDir: true,
                directoryName: 'videos/nature',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            // "New Directory" should not appear when is_dir=true
            expect(screen.queryByText(/New Directory/i)).not.toBeInTheDocument();
        });

        it('debounces rapid typing (verifies setDirectoryName is called)', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Type rapidly
            await userEvent.type(input, 'abc', {delay: 10});

            // Verify setDirectoryName was called
            expect(mockSetDirectoryName).toHaveBeenCalled();
        });
    });

    describe('User Interactions', () => {
        it('calls onSelect when result is clicked', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            await waitFor(() => {
                expect(screen.getByText('videos/nature')).toBeInTheDocument();
            });

            // Click on a result
            const result = screen.getByText('videos/nature');
            await userEvent.click(result);

            expect(mockOnSelect).toHaveBeenCalledWith('videos/nature');
        });

        it('commits typed value on blur when directoryName differs from value', async () => {
            // Set up mock state where directoryName differs from the prop value
            // This simulates what happens after user types in the input
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'typed/path',  // User has typed this
            });

            // Render with empty value prop (different from directoryName)
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            // The SearchBox wires `onBlur` straight to the input (there is no longer a
            // wrapping Search component to blur instead).
            const input = screen.getByPlaceholderText(/search directory names/i);

            // Blur the input - should trigger onBlur which calls onSelect
            await act(async () => {
                const {fireEvent} = require('../test-utils');
                fireEvent.blur(input);
            });

            // Should call onSelect with directoryName from hook state
            expect(mockOnSelect).toHaveBeenCalledWith('typed/path');
        });

        it('does not call onSelect on blur if value unchanged', async () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'existing/path',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value="existing/path"/>);

            const input = screen.getByDisplayValue('existing/path');

            // Blur without changing value
            await act(async () => {
                input.blur();
            });

            // Should not call onSelect since value didn't change
            expect(mockOnSelect).not.toHaveBeenCalled();
        });

        it('disabled state prevents interactions', () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" disabled/>);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Input should be disabled
            expect(input).toBeDisabled();
        });

        it('handles rapid selection changes', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            await waitFor(() => {
                expect(screen.getByText('videos/nature')).toBeInTheDocument();
            });

            // Click multiple results in succession. Choosing a result closes the
            // dropdown (as any combobox would) without moving focus off the input
            // (the option is chosen on mousedown, with the default prevented), so
            // pressing a key that reopens the list -- same as a real user -- is
            // needed before the next selection.
            await userEvent.click(screen.getByText('videos/nature'));
            await userEvent.keyboard('{ArrowDown}');
            await waitFor(() => {
                expect(screen.getByText('videos/tech')).toBeInTheDocument();
            });
            await userEvent.click(screen.getByText('videos/tech'));

            // Should call onSelect for each selection
            expect(mockOnSelect).toHaveBeenCalledWith('videos/nature');
            expect(mockOnSelect).toHaveBeenCalledWith('videos/tech');
        });
    });

    describe('Hook Integration', () => {
        it('calls setDirectoryName from hook on search change', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.type(input, 'archive');

            expect(mockSetDirectoryName).toHaveBeenCalled();
        });

        it('displays results from hook state', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            await waitFor(() => {
                // Should display results from mock hook state
                expect(screen.getByText('videos/nature')).toBeInTheDocument();
                expect(screen.getByText('videos/tech')).toBeInTheDocument();
                expect(screen.getByText('News Channel')).toBeInTheDocument();
            });
        });
    });

    describe('Edge Cases', () => {
        it('renders without error when directories are null (initial state)', async () => {
            // Simulate the initial state before API call completes
            setMockHookState({
                directories: null,
                channelDirectories: null,
                domainDirectories: null,
                isDir: false,
                directoryName: '',
                loading: true,
            });

            // This should not throw an error
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Clicking input should not throw "Cannot read properties of null"
            await userEvent.click(input);

            // Component should still be rendered
            expect(input).toBeInTheDocument();
        });

        it('handles null/undefined initial value', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: '',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value={null}/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toHaveValue('');
        });

        it('clears results display when empty', async () => {
            setMockHookState({
                directories: [],
                channelDirectories: [],
                domainDirectories: [],
                isDir: false,
                directoryName: '',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toHaveValue('');
        });

        it('maintains value when component remounts', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'videos/test',
            });

            const {rerender} = render(
                <DirectorySearch onSelect={mockOnSelect} value="videos/test"/>
            );

            expect(screen.getByDisplayValue('videos/test')).toBeInTheDocument();

            // Remount with same value
            rerender(<DirectorySearch onSelect={mockOnSelect} value="videos/test"/>);

            expect(screen.getByDisplayValue('videos/test')).toBeInTheDocument();
        });

        it('handles special characters in path', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value=""/>);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Type path with special characters
            const specialPath = 'videos/test-folder_2024/v1.0';
            await userEvent.type(input, specialPath);

            expect(mockSetDirectoryName).toHaveBeenCalled();
        });
    });
});

describe('SearchResultsInput', () => {
    const results = {
        tags: {name: 'Tags', results: [{type: 'tag', title: 'Cooking'}]},
        videos: {name: 'Videos', results: [
            {title: 'How To Sharpen An Axe', description: 'Wranglerstar', location: '/videos/1'},
        ]},
    };

    it('hands the selected suggestion to its caller as {result}', async () => {
        /*
         * Regression: the migration passed the bare result, but every caller destructures
         * `{result}` (see Search.js), so `result.location` was undefined and clicking a
         * search suggestion navigated nowhere.
         */
        const handleResultSelect = jest.fn();
        render(<SearchResultsInput searchStr='axe' onSubmit={jest.fn()} results={results}
                                   handleResultSelect={handleResultSelect}/>);

        await userEvent.click(screen.getByRole('combobox'));
        await userEvent.click(screen.getByText('How To Sharpen An Axe'));

        expect(handleResultSelect).toHaveBeenCalledWith(
            {result: expect.objectContaining({location: '/videos/1'})});
    });

    it('forwards resultRenderer so a caller keeps its own suggestion markup', async () => {
        // Search.js renders a tag suggestion as a tag chip, not a line of text.
        const resultRenderer = (result) => <span>rendered:{result.title}</span>;
        render(<SearchResultsInput searchStr='cook' onSubmit={jest.fn()} results={results}
                                   handleResultSelect={jest.fn()} resultRenderer={resultRenderer}/>);

        await userEvent.click(screen.getByRole('combobox'));

        expect(screen.getByText('rendered:Cooking')).toBeInTheDocument();
    });
});

describe('contrastingColor', () => {
    /*
     * This decides the text color on every tag, against a fill the user picked, so it is the
     * one place in the app where legibility is computed rather than designed.
     */

    it('picks whichever of the two options actually reads better', () => {
        // Semantic's blue.  The old threshold check chose light text here, at 2.9:1, when dark
        // text on the same fill gives 5.3:1 -- the worse of the only two available answers.
        // Every mid-tone blue, teal and purple a user might choose sat in that band.
        const blue = '#2185d0';

        const chosen = contrastingColor(blue);
        const rejected = chosen === TAG_TEXT_DARK ? TAG_TEXT_LIGHT : TAG_TEXT_DARK;

        expect(contrastRatio(chosen, blue)).toBeGreaterThan(contrastRatio(rejected, blue));
        expect(chosen).toBe(TAG_TEXT_DARK);
    });

    it('never picks the worse option, for any color', () => {
        // The property, rather than a list of examples: whatever it returns must be at least as
        // legible as the alternative would have been.
        const colors = [
            '#000000', '#ffffff', '#f2f2f2', '#1b1c1d', '#2185d0', '#21ba45', '#db2828',
            '#fbbd08', '#6435c9', '#a5673f', '#00b5ad', '#e03997', '#b5cc18', '#767676',
            '#808080', '#7f7f7f',
        ];

        for (const color of colors) {
            const chosen = contrastingColor(color);
            const rejected = chosen === TAG_TEXT_DARK ? TAG_TEXT_LIGHT : TAG_TEXT_DARK;
            expect(contrastRatio(chosen, color))
                .toBeGreaterThanOrEqual(contrastRatio(rejected, color));
        }
    });

    it('returns one of the two text colors and nothing else', () => {
        // It is written into `--label-text`; anything undefined leaves the tag unstyled.
        for (const color of ['#000000', '#ffffff', '#2185d0']) {
            expect([TAG_TEXT_DARK, TAG_TEXT_LIGHT]).toContain(contrastingColor(color));
        }
    });

    it('measures contrast on the WCAG scale', () => {
        // Anchors the ratio itself, so "better" above is comparing real numbers.
        expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
        expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    });
});

describe('contrastingColor with shorthand hex', () => {
    /*
     * Tag colors reach the UI from the database, and a tags config is a file a user can edit
     * by hand -- configs are the source of truth in WROLPi -- so a perfectly valid `#fff` can
     * arrive here.  `hexToRGBArray` used to reject anything but six digits, which left the
     * luminance at zero: a near-white tag was treated as black and given light text.
     */

    it('reads a three-digit hex as the color it is', () => {
        expect(contrastRatio('#000000', '#fff')).toBeCloseTo(21, 1);
        expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(contrastRatio('#000000', '#fff'), 5);
    });

    it('picks dark text for a near-white shorthand fill', () => {
        expect(contrastingColor('#fff')).toBe(TAG_TEXT_DARK);
    });

    it('picks light text for a near-black shorthand fill', () => {
        expect(contrastingColor('#000')).toBe(TAG_TEXT_LIGHT);
    });

    it('agrees with the six-digit form of the same color', () => {
        for (const [short, long] of [['#fff', '#ffffff'], ['#000', '#000000'],
                                     ['#f00', '#ff0000'], ['#1b2', '#11bb22']]) {
            expect(contrastingColor(short)).toBe(contrastingColor(long));
        }
    });
});

describe('loadRole', () => {
    /*
     * The branches, tested as branches.  This used to be a source guard scraping the
     * function body out of Common.js, because the obvious render test cannot work: jsdom
     * REJECTS `color: var(--danger)` as an invalid declaration and drops it, so every inline
     * color reads back as the empty string and the assertions passed for that reason alone.
     * Pulling the mapping out as a pure function is the honest fix.
     *
     * Thresholds are halves and three quarters of the core count, so each is asserted either
     * side of its boundary rather than at one comfortable value.
     */
    it('says nothing about a load below half the cores', () => {
        expect(loadRole(1.9, 4)).toBeUndefined();
        expect(loadRole(0, 4)).toBeUndefined();
    });

    it('warns from half the cores', () => {
        expect(loadRole(2.0, 4)).toBe('warning');
        expect(loadRole(2.9, 4)).toBe('warning');
    });

    it('calls it danger from three quarters', () => {
        expect(loadRole(3.0, 4)).toBe('danger');
        expect(loadRole(99, 4)).toBe('danger');
    });

    it('says nothing when the core count is unknown', () => {
        // Both thresholds are guarded on `cores`.  Without it every load would read as fine,
        // which is the safe direction, but worth pinning so it stays deliberate.
        expect(loadRole(12, undefined)).toBeUndefined();
        expect(loadRole(12, 0)).toBeUndefined();
    });

    it('never returns a hue', () => {
        // The regression this exists for: `orange` is byte-identical to `--text` in night,
        // so a warning load rendered as an ordinary uncolored number.
        [loadRole(1, 4), loadRole(2.5, 4), loadRole(4, 4)].filter(Boolean).forEach(role =>
            expect(role).not.toMatch(/^(red|green|amber|yellow|orange|blue)$/));
    });
});

describe('healthRole', () => {
    it('maps every SMART assessment to a severity', () => {
        expect(healthRole('PASS')).toBe('success');
        expect(healthRole('WARN')).toBe('warning');
        expect(healthRole('FAIL')).toBe('danger');
    });

    it('is not case sensitive, because the value comes from smartctl', () => {
        expect(healthRole('pass')).toBe('success');
        expect(healthRole('Fail')).toBe('danger');
    });

    it('treats a missing or unrecognised assessment as unknown, not as healthy', () => {
        // Reporting an unreadable drive as PASS would be the dangerous direction.
        [undefined, null, '', 'SOMETHING_ELSE'].forEach(value =>
            expect(healthRole(value)).toBe('neutral'));
    });
});

describe('a heading keeps its help icon on the same row as the text', () => {
    /*
     * `HelpHeader` and `InfoHeader` put their icon in a sibling `<span>` beside a `<label>`,
     * held on one line by `.inline-header h1..h5 {display: inline-block}` in App.css.  That
     * worked while the heading was a bare `<h2>`; the moment it gained a block wrapper the
     * label's block child forced a break, and every help icon in the app dropped below its
     * own heading -- visible on "Root CA Certificate" in Settings.
     *
     * They pass the icon through the heading's `after` slot now.  Containment is the claim
     * jsdom can judge; that the two actually share a line is asserted in ui-layout.cy.js,
     * since jsdom has no layout at all.
     */
    it("renders the help control in the heading's row", () => {
        const {container} = render(
            <HelpHeader headerSize='h3' headerContent='Root CA Certificate'
                        helpPath='/system/certificates/'/>);

        expect(container.querySelector('.wrolpi-header-row'))
            .toContainElement(screen.getByRole('button', {name: 'Help'}));
        // And not inside the heading itself, which would put it in the accessible name.
        expect(screen.getByRole('heading')).toHaveAccessibleName('Root CA Certificate');
    });

    it("renders the info popup in the heading's row", () => {
        const {container} = render(
            <InfoHeader headerSize='h4' headerContent='Video Resolutions'
                        popupContent='Highest available is tried first.'/>);

        expect(container.querySelector('.wrolpi-header-after svg')).not.toBeNull();
    });

    it('renders no label at all when there is no field to name', () => {
        /*
         * Several call sites pass an InfoHeader as the `label` prop of InputForm/ToggleForm,
         * which wraps it in a `<label>` of its own.  An unconditional label here nested one
         * inside another -- invalid HTML, and it makes clicking the text ambiguous.
         */
        const {container} = render(
            <InfoHeader headerSize='h5' headerContent='Video File Format' popupContent='...'/>);

        expect(container.querySelector('label')).toBeNull();
        expect(screen.getByRole('heading', {name: /Video File Format/})).toBeInTheDocument();
    });

    it('keeps the label association, which is what `for_` is for', () => {
        // Three call sites use it to tie the heading text to the field below it.
        render(<InfoHeader headerSize='h4' headerContent='Video Resolutions'
                           for_='video_resolutions_input' popupContent='...'/>);

        expect(screen.getByText(/Video Resolutions/).closest('label'))
            .toHaveAttribute('for', 'video_resolutions_input');
    });

    it('leaves no .inline-header behind', () => {
        // The class and its stylesheet rules are gone; a stray one would be dead markup
        // relying on CSS that no longer exists.
        const {container} = render(<HelpHeader headerContent='Root CA Certificate' helpPath='/x/'/>);

        expect(container.querySelector('.inline-header')).toBeNull();
    });
});

describe('card links', () => {
    /*
     * `.card-link` is what makes a card's title read as the card's text rather than as a
     * link, so a title that misses it is the one thing on the card in the wrong color.
     * Both helpers set the class and then spread the caller's props over it, so any call
     * site passing a className of its own -- which is every archive title, via
     * `card-title-ellipsis` -- silently replaced the class instead of adding to it.
     */
    it.each([
        ['CardLink', <CardLink to='/archives/1' className='card-title-ellipsis'>Title</CardLink>],
        ['ExternalCardLink',
            <ExternalCardLink to='http://x/a.html' className='card-title-ellipsis'>Title</ExternalCardLink>],
    ])('%s keeps its own classes when the call site adds one', (_name, element) => {
        render(element);

        const link = screen.getByText('Title');
        expect(link).toHaveClass('card-link');
        expect(link).toHaveClass('no-link-underscore');
        expect(link).toHaveClass('card-title-ellipsis');
    });
});

describe('PageContainer', () => {
    /*
     * The wrapper that decides how far apart a page's blocks sit.  The spacing itself is a
     * stylesheet rule and is measured in ui-layout.cy.js, where there is a layout engine; what
     * this asserts is that the rule is REACHED -- the class has to be on both of the responsive
     * branches, or the spacing silently applies on one viewport and not the other.
     */
    it('marks both of its viewport branches as a stack', () => {
        const {container} = render(<PageContainer><div>Body</div></PageContainer>);

        const stacks = container.querySelectorAll('.wrolpi-stack');
        // Mobile and tablet-and-up, both rendered; `Media` hides one with CSS.
        expect(stacks).toHaveLength(2);
        stacks.forEach(stack => expect(stack.textContent).toBe('Body'));
    });

    it('is never rendered by a page whose route already provides page chrome', () => {
        /*
         * `PageContainer` carries `margin-top: 1em` and `padding: 1em`, so nesting one inside
         * another applies both twice: the page is pushed 1em further down and inset 1em further
         * in on all four sides than every other page in the app.  `/archives/settings` did this
         * -- `ArchiveRoute` wraps its `<Routes>` in one, and `ArchiveSettingsPage` wrapped itself
         * in another -- and read as "more margin than /archives/domains", which is exactly what
         * it was.
         *
         * Nothing about a doubled margin throws, so this is a source scan.  It finds each router
         * whose enclosing `return` provides page chrome, takes the components it routes to, and
         * checks the ones declared in the same file -- which is where a route and its pages
         * normally live together.
         *
         * "Chrome" is `PageContainer` OR a `wrolpi-stack` wrapper, not just the former.  Keying on
         * `PageContainer` alone missed `MapRoute` and `ZimRoute`, which wrap their own content in a
         * stack instead -- and three pages under them (`ManageMap`, `MapPins`, `ManageZim`) mounted
         * a `PageContainer` each, so they sat a further 1em down and 1em in from the tab bar than
         * the viewers beside them.  The same defect as Archive, in a shape the first scan could not
         * see.
         *
         * Known limit: a layout that routes through `<Outlet/>` has its `<Route>` list in App.js,
         * naming components from other files, so the page cannot be resolved from one file's text.
         * That is `VideosTabLayout`, whose pages are clean today but are not covered here.
         */
        const src = SRC;
        const files = () => sourceFiles();

        const offenders = [];
        for (const file of files(src)) {
            const text = fs.readFileSync(file, 'utf8');
            for (const block of chromedRouterBlocks(text)) {
                for (const name of routedComponents(block)) {
                    if (bodyOf(text, name).includes('<PageContainer>')) {
                        offenders.push(`${path.relative(src, file)}: ${name}`);
                    }
                }
            }
        }

        /*
         * The premise: a scan that found no routers, or resolved no page components, would report
         * no offenders and read exactly like a clean codebase.
         */
        const blocks = files(src).flatMap(file => chromedRouterBlocks(fs.readFileSync(file, 'utf8')));
        expect(blocks.length).toBeGreaterThan(3);
        expect(blocks.flatMap(routedComponents).length).toBeGreaterThan(8);

        expect(offenders).toEqual([]);
    });
});

describe('a row of buttons', () => {
    /*
     * Semantic's Button brought `margin: 0 .25em .25em 0` with it, so a page could list buttons as
     * bare siblings and they arrived both spaced and, when the row wrapped, separated.  Nothing
     * replaced that margin.  The archive page's six actions shared edges, and two of them carried
     * `marginTop: 0.5em` -- put there to keep a wrapped row from touching vertically, which instead
     * made those two sit lower than the rest, because `vertical-align: middle` aligns the margin box.
     *
     * `.wrolpi-button-row` is a flex row with a gap, so it covers both axes at once and no button
     * needs a margin of its own.  ui-layout.cy.js measures that the row really spaces and aligns
     * what it holds; these two scans are about the row being REACHED and left alone -- neither of
     * which throws, and both of which is how the app got here.
     */

    /*
     * `=>` is blanked before any tag scanning.  An arrow function in a prop -- `onClick={() =>
     * handleDelete(false)}`, which most of these buttons have -- puts a `>` inside an opening tag,
     * and a scanner reading `>` as "tag ends here" splits one button into two bogus tags.  Two
     * characters for two, so every index still points where it did in the original text.
     */
    const scannable = (text) => text.replace(/=>/g, '=~');

    const TAG = /<(\/?)([A-Za-z][\w.]*)([^>]*?)(\/?)>/g;
    const tagsIn = (text) => [...scannable(text).matchAll(TAG)].map(match => ({
        start: match.index,
        end: match.index + match[0].length,
        attributes: match[3],
        closing: match[1] === '/',
        selfClosing: match[4] === '/',
    }));

    /**
     * The tag that encloses `index`: walk the tags before it backwards, letting a close push the
     * depth up and an open bring it back down, and stop at the first open that is still unclosed.
     */
    const enclosingTag = (tags, index) => {
        let depth = 0;
        for (const tag of [...tags].filter(tag => tag.end <= index).reverse()) {
            if (tag.selfClosing) continue;
            if (tag.closing) depth += 1;
            else if (depth === 0) return tag;
            else depth -= 1;
        }
        return null;
    };

    /**
     * Every `const <name> = ...` declared at any indentation, as button consts are.
     *
     * Every one, not the first: Archive.js declares a `deleteButton` in the archive page and
     * another in the domain edit page, and a resolver that stopped at the first found the clean one
     * and reported the page with the margin on it as clean too.
     */
    const localBodiesOf = (text, name) => {
        const pattern = new RegExp(`^[ \\t]*(?:const|let)\\s+${name}\\s*=`, 'gm');
        return [...text.matchAll(pattern)].map(found => {
            const after = text.slice(found.index + found[0].length);
            const next = after.search(/\n[ \t]*(?:const|let|function|return|\})[\s(]/);
            return next === -1 ? after : after.slice(0, next);
        });
    };

    /** Every `const actionButtons = <>...</>` fragment in `text`: a button row under another name. */
    const actionFragments = (text) => {
        const bodies = [];
        const pattern = /^[ \t]*const\s+actionButtons\s*=\s*<>/gm;
        for (const found of text.matchAll(pattern)) {
            const from = found.index + found[0].length;
            const end = text.indexOf('</>', from);
            if (end !== -1) bodies.push(text.slice(from, end));
        }
        return bodies;
    };

    const VERTICAL_MARGIN = /margin(?:Top|Bottom)\s*:|margin\s*:/;

    /*
     * The classes that lay buttons out in a row.  A row is a row whatever it is called -- the file
     * preview's toolbar had one before this, at a tighter gap because its buttons are icons -- so
     * the check below is "is this one of them", and the test after it is what keeps the list honest
     * by reading each one out of the stylesheet and confirming it really is a flex row with a gap.
     */
    const ROW_CLASSES = [
        'wrolpi-button-row', 'wrolpi-modal-actions', 'wrolpi-confirm-actions', 'preview-toolbar-group',
    ];
    const isRow = (tag) => !!tag && ROW_CLASSES.some(name => tag.attributes.includes(name));

    it('lays every row out as a flex row with a gap', () => {
        // Otherwise the list above is just a list of names the scans below happen to accept.
        const stylesheets = ['components/ui/ui.css', 'App.css']
            .map(name => fs.readFileSync(path.join(SRC, name), 'utf8')).join('\n');

        ROW_CLASSES.forEach(name => {
            const found = new RegExp(`\\.${name}\\s*\\{([^}]*)\\}`).exec(stylesheets);
            // Named in the failure rather than passed to `expect`, which takes no message.
            expect(found ? name : `${name} is not declared`).toBe(name);
            expect(found[1]).toMatch(/display:\s*flex/);
            expect(found[1]).toMatch(/gap:/);
        });
    });

    it('never stamps a vertical margin on a button the row already spaces', () => {
        /*
         * The margin and the gap add up.  Nine buttons across the three collection edit pages had
         * `marginTop: 1em` each and sat 1em below the Save button beside them; the archive page's
         * Update and Generate Screenshot had 0.5em and sat half that below their own neighbours.
         */
        const offenders = [];
        let rows = 0;
        let resolved = 0;

        for (const file of sourceFiles()) {
            const text = fs.readFileSync(file, 'utf8');
            const where = path.relative(SRC, file);

            const blocks = actionFragments(text);
            for (const tag of tagsIn(text)) {
                if (!tag.closing && tag.attributes.includes('wrolpi-button-row')) {
                    // A row holds buttons, not more divs, so its first `</div>` is its own.
                    const closes = text.indexOf('</div>', tag.end);
                    blocks.push(closes === -1 ? '' : text.slice(tag.end, closes));
                }
            }
            rows += blocks.length;

            for (const block of blocks) {
                // A button declared inline in the row, style and all.
                if (VERTICAL_MARGIN.test(block)) offenders.push(`${where}: inline in the row`);
                // ...or interpolated by name, which is how most of them are written.
                for (const name of new Set([...block.matchAll(/\{(\w*[Bb]utton\w*)\}/g)]
                    .map(match => match[1]))) {
                    for (const body of localBodiesOf(text, name)) {
                        resolved += 1;
                        if (VERTICAL_MARGIN.test(body)) offenders.push(`${where}: ${name}`);
                    }
                }
            }
        }

        // A scan that found no rows, or resolved none of their buttons, reports a clean app.
        expect(rows).toBeGreaterThan(3);
        expect(resolved).toBeGreaterThan(8);

        expect(offenders).toEqual([]);
    });

    it('puts every row of buttons in a row', () => {
        /*
         * The other half: a page can have margin-free buttons and still list them as bare siblings,
         * which is the touching this fixes.  Every `{actionButtons}` is rendered somewhere, and the
         * element it is rendered into is what has to carry the gap -- on the doc page that was a
         * plain `<div style={{marginTop: '1em'}}>`, spacing the row from what was above it while
         * leaving the buttons inside it edge to edge.
         */
        const offenders = [];
        let sites = 0;

        for (const file of sourceFiles()) {
            const text = fs.readFileSync(file, 'utf8');
            if (!text.includes('{actionButtons}')) continue;
            const tags = tagsIn(text);

            for (const found of text.matchAll(/\{actionButtons\}/g)) {
                // `actionButtons={actionButtons}` is the prop being handed down, not a render.
                if (text.slice(found.index - 14, found.index) === 'actionButtons=') continue;
                sites += 1;
                const parent = enclosingTag(tags, found.index);
                if (!isRow(parent)) {
                    offenders.push(`${path.relative(SRC, file)}: ${
                        parent ? parent.attributes.trim().slice(0, 40) : 'no enclosing tag'}`);
                }
            }
        }

        /*
         * Three: the shared collection edit form, which three pages hand a fragment to, and the doc
         * page's own two responsive branches.  A scan that counted the `actionButtons={...}` props
         * instead would reach eight and never look at a render site at all.
         */
        expect(sites).toBe(3);

        expect(offenders).toEqual([]);
    });

    it('never lists buttons as bare siblings', () => {
        /*
         * The touching itself, and the reported defect: the archive page interpolated six buttons
         * one after another straight into its Panel, so every pair shared an edge.
         *
         * A run of adjacent button interpolations is the shape to look for.  Runs inside an
         * `actionButtons` fragment are blanked first -- a fragment is spread into its parent's row
         * and has no business being one itself, which the previous test is what checks.  Blanked
         * rather than skipped so every index still points where it did.
         */
        const offenders = [];
        let runs = 0;

        for (const file of sourceFiles()) {
            let text = fs.readFileSync(file, 'utf8');
            for (const fragment of actionFragments(text)) {
                text = text.replace(fragment, ' '.repeat(fragment.length));
            }
            const tags = tagsIn(text);

            for (const found of text.matchAll(/\{\w*[Bb]utton\w*\}(?:\s*\{\w*[Bb]utton\w*\})+/g)) {
                runs += 1;
                const parent = enclosingTag(tags, found.index);
                if (!isRow(parent)) {
                    offenders.push(`${path.relative(SRC, file)}: ${found[0].replace(/\s+/g, '')}`);
                }
            }
        }

        /*
         * Four: the archive page's actions, the file preview's toolbar (which had a row of its own
         * already), the downloads table's edit/restart pair, and the doc page's format picker
         * beside its actions.  Asserted exactly, because a run that stopped being recognised would
         * leave this reporting a clean app.
         */
        expect(runs).toBe(4);

        expect(offenders).toEqual([]);
    });

    it('puts every Back button in a row, so the page stack cannot stretch it', () => {
        /*
         * A page's blocks are stacked by `.wrolpi-stack`, which is a flex column at
         * `align-items: stretch` -- deliberately, because a panel was full-width as a block
         * element and has to stay that way.  A BARE button as a direct child of that stack is
         * stretched too, and every page's Back button was one: full-page-width, and on the domain,
         * channel and playlist edit pages the button beside it was pushed onto its own line where
         * the two had been inline before.
         *
         * A row fixes it without touching the stack: the row is the stretched child, and it lays
         * its buttons out at their own width.  Nine sites, so this scan rather than nine
         * assertions -- and a scan because a stretched button is still a working button.
         */
        const offenders = [];
        let found = 0;

        for (const file of sourceFiles()) {
            const text = fs.readFileSync(file, 'utf8');
            const tags = tagsIn(text);

            for (const match of text.matchAll(/<BackButton\b/g)) {
                found += 1;
                if (!isRow(enclosingTag(tags, match.index))) {
                    offenders.push(`${path.relative(SRC, file)}:${
                        text.slice(0, match.index).split('\n').length}`);
                }
            }
        }

        // Nine renders.  Common.js declares it, and a declaration is not a `<BackButton`.
        expect(found).toBe(9);

        expect(offenders).toEqual([]);
    });
});

/** The app's own source, minus its tests: what a source scan is allowed to read. */
const SRC = path.join(__dirname, '..');
const sourceFiles = (dir = SRC) => fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.jsx?$/.test(entry.name)) return [];
    if (/\.(test|cy)\.jsx?$/.test(entry.name)) return [];
    return [full];
});

/**
 * Every `<Routes>...</Routes>` in `text` whose enclosing `return` provides page chrome -- a
 * `PageContainer` or a `wrolpi-stack` wrapper.  Those are the routers that have already spaced and
 * inset the page, so a page under one must not do it again.
 *
 * All of them, and located from the router rather than from the chrome: keying on the first
 * `<PageContainer>` in a file missed this entirely in Archive.js, where the first one belongs to
 * the offending page and holds no router at all.
 */
const chromedRouterBlocks = (text) => {
    const blocks = [];
    let from = 0;
    for (;;) {
        const start = text.indexOf('<Routes>', from);
        if (start === -1) return blocks;
        const end = text.indexOf('</Routes>', start);
        if (end === -1) return blocks;
        from = end + 1;

        const returned = text.lastIndexOf('return', start);
        if (returned === -1) continue;
        const chrome = text.slice(returned, start);
        if (chrome.includes('<PageContainer>') || chrome.includes('wrolpi-stack')) {
            blocks.push(text.slice(start, end));
        }
    }
};

/**
 * The page components a router block routes to.  Any capitalised tag that is not routing furniture,
 * so `element={<ErrorBoundary><Page/></ErrorBoundary>}` yields `Page` as well as the plain
 * `element={<Page/>}` form.
 */
const FURNITURE = new Set(['Route', 'Routes', 'ErrorBoundary', 'Suspense', 'Navigate', 'Outlet']);
const routedComponents = (block) => [...new Set(
    [...block.matchAll(/<([A-Z]\w*)/g)].map(m => m[1]).filter(name => !FURNITURE.has(name)))];

/**
 * The source of the component named `name`, bounded by the next top-level declaration.  `class` is
 * in both patterns because `ManageZim` is one, and a scan that only knew about functions would
 * have reported it clean.
 */
const bodyOf = (text, name) => {
    const declaration = new RegExp(`^(?:export\\s+)?(?:function|const|class)\\s+${name}\\b`, 'm');
    const found = declaration.exec(text);
    if (!found) return '';   // Declared elsewhere; out of this scan's reach.
    const after = text.slice(found.index + 1);
    const next = after.search(/^(?:export\s+)?(?:function|const|class)\s/m);
    return next === -1 ? after : after.slice(0, next);
};
