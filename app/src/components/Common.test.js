import React from 'react';
import {act, render, screen, waitFor} from '../test-utils';
import userEvent from '@testing-library/user-event';
import {
    contrastingColor, contrastRatio, DirectorySearch, SearchResultsInput, TAG_TEXT_DARK, TAG_TEXT_LIGHT,
} from './Common';

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
     * This decides the text colour on every tag, against a fill the user picked, so it is the
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

    it('never picks the worse option, for any colour', () => {
        // The property, rather than a list of examples: whatever it returns must be at least as
        // legible as the alternative would have been.
        const colours = [
            '#000000', '#ffffff', '#f2f2f2', '#1b1c1d', '#2185d0', '#21ba45', '#db2828',
            '#fbbd08', '#6435c9', '#a5673f', '#00b5ad', '#e03997', '#b5cc18', '#767676',
            '#808080', '#7f7f7f',
        ];

        for (const colour of colours) {
            const chosen = contrastingColor(colour);
            const rejected = chosen === TAG_TEXT_DARK ? TAG_TEXT_LIGHT : TAG_TEXT_DARK;
            expect(contrastRatio(chosen, colour))
                .toBeGreaterThanOrEqual(contrastRatio(rejected, colour));
        }
    });

    it('returns one of the two text colours and nothing else', () => {
        // It is written into `--label-text`; anything undefined leaves the tag unstyled.
        for (const colour of ['#000000', '#ffffff', '#2185d0']) {
            expect([TAG_TEXT_DARK, TAG_TEXT_LIGHT]).toContain(contrastingColor(colour));
        }
    });

    it('measures contrast on the WCAG scale', () => {
        // Anchors the ratio itself, so "better" above is comparing real numbers.
        expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
        expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    });
});
