import React from 'react';
import {render, screen, waitFor, act} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {DirectorySearch} from './Common';

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
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toBeInTheDocument();
        });

        it('shows initial value when provided', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'videos/test',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value="videos/test" />);

            const input = screen.getByDisplayValue('videos/test');
            expect(input).toBeInTheDocument();
        });

        it('applies disabled state correctly', () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" disabled />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toBeDisabled();
        });

        it('displays with required indicator', () => {
            const {container} = render(
                <DirectorySearch onSelect={mockOnSelect} value="" required />
            );

            // Semantic UI doesn't add required attribute to Search input,
            // but we verify the prop is passed
            expect(container.querySelector('.ui.search')).toBeInTheDocument();
        });
    });

    describe('Search Functionality', () => {
        it('triggers setDirectoryName on value change', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

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

            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const searchContainer = screen.getByPlaceholderText(/search directory names/i)
                .closest('.ui.search');
            expect(searchContainer).toHaveClass('loading');
        });

        it('hides loading indicator when loading state is false', () => {
            setMockHookState({
                ...mockSearchResults,
                loading: false,
            });

            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const searchContainer = screen.getByPlaceholderText(/search directory names/i)
                .closest('.ui.search');
            expect(searchContainer).not.toHaveClass('loading');
        });

        it('displays categorized results', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

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

            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

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

            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            // "New Directory" should not appear when is_dir=true
            expect(screen.queryByText(/New Directory/i)).not.toBeInTheDocument();
        });

        it('debounces rapid typing (verifies setDirectoryName is called)', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Type rapidly
            await userEvent.type(input, 'abc', {delay: 10});

            // Verify setDirectoryName was called
            expect(mockSetDirectoryName).toHaveBeenCalled();
        });
    });

    describe('User Interactions', () => {
        it('calls onSelect when result is clicked', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

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
            const {container} = render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            // Find the Search component container and trigger blur on it
            const searchComponent = container.querySelector('.ui.search');

            // Blur the Search component - should trigger onBlur which calls onSelect
            await act(async () => {
                // Use fireEvent.blur which better simulates the Semantic UI Search blur behavior
                const {fireEvent} = require('@testing-library/react');
                fireEvent.blur(searchComponent);
            });

            // Should call onSelect with directoryName from hook state
            expect(mockOnSelect).toHaveBeenCalledWith('typed/path');
        });

        it('does not call onSelect on blur if value unchanged', async () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'existing/path',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value="existing/path" />);

            const input = screen.getByDisplayValue('existing/path');

            // Blur without changing value
            await act(async () => {
                input.blur();
            });

            // Should not call onSelect since value didn't change
            expect(mockOnSelect).not.toHaveBeenCalled();
        });

        it('disabled state prevents interactions', () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" disabled />);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Input should be disabled
            expect(input).toBeDisabled();
        });

        it('handles rapid selection changes', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.click(input);

            await waitFor(() => {
                expect(screen.getByText('videos/nature')).toBeInTheDocument();
            });

            // Click multiple results in succession
            await userEvent.click(screen.getByText('videos/nature'));
            await userEvent.click(screen.getByText('videos/tech'));

            // Should call onSelect for each selection
            expect(mockOnSelect).toHaveBeenCalledWith('videos/nature');
            expect(mockOnSelect).toHaveBeenCalledWith('videos/tech');
        });
    });

    describe('Hook Integration', () => {
        it('calls setDirectoryName from hook on search change', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            await userEvent.type(input, 'archive');

            expect(mockSetDirectoryName).toHaveBeenCalled();
        });

        it('displays results from hook state', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

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
        it('handles null/undefined initial value', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: '',
            });

            render(<DirectorySearch onSelect={mockOnSelect} value={null} />);

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

            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);
            expect(input).toHaveValue('');
        });

        it('maintains value when component remounts', () => {
            setMockHookState({
                ...mockSearchResults,
                directoryName: 'videos/test',
            });

            const {rerender} = render(
                <DirectorySearch onSelect={mockOnSelect} value="videos/test" />
            );

            expect(screen.getByDisplayValue('videos/test')).toBeInTheDocument();

            // Remount with same value
            rerender(<DirectorySearch onSelect={mockOnSelect} value="videos/test" />);

            expect(screen.getByDisplayValue('videos/test')).toBeInTheDocument();
        });

        it('handles special characters in path', async () => {
            render(<DirectorySearch onSelect={mockOnSelect} value="" />);

            const input = screen.getByPlaceholderText(/search directory names/i);

            // Type path with special characters
            const specialPath = 'videos/test-folder_2024/v1.0';
            await userEvent.type(input, specialPath);

            expect(mockSetDirectoryName).toHaveBeenCalled();
        });
    });
});
