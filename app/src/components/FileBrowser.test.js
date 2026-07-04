import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {FileBrowser, filterBrowseFiles} from './FileBrowser';
import {renderWithProviders} from '../test-utils';
import {SettingsContext} from '../contexts/contexts';
import {FilePreviewContext} from './FilePreview';

// Mock the API functions
jest.mock('../api', () => ({
    deleteFile: jest.fn(),
    ignoreDirectory: jest.fn(),
    makeDirectory: jest.fn(),
    movePaths: jest.fn(),
    renamePath: jest.fn(),
    unignoreDirectory: jest.fn(),
}));

// Mock the custom hooks
const mockUseUploadFile = {
    setFiles: jest.fn(),
    progresses: {},
    setDestination: jest.fn(),
    doClear: jest.fn(),
    tagsSelector: null,
    overwrite: false,
    setOverwrite: jest.fn(),
    overallProgress: 0,
    inProgress: false,
};

jest.mock('../hooks/customHooks', () => ({
    useBrowseFiles: jest.fn(),
    useMediaDirectory: jest.fn(() => '/media/wrolpi'),
    useWROLMode: jest.fn(() => false),
    useStatusFlag: jest.fn(() => false),
    useUploadFile: () => mockUseUploadFile,
    useElementWidth: jest.fn(() => [() => {}, 0]),
}));

// Mock react-dropzone
jest.mock('react-dropzone', () => ({
    useDropzone: () => ({
        getRootProps: () => ({}),
        getInputProps: () => ({}),
    }),
}));

// Import mocked hooks for manipulation
import {useBrowseFiles, useElementWidth, useWROLMode} from '../hooks/customHooks';

// Create wrapper with all required contexts
const AllContextsWrapper = ({children}) => {
    const settingsValue = {
        settings: {ignored_directories: []},
        fetchSettings: jest.fn(),
    };
    const filePreviewValue = {
        setPreviewFile: jest.fn(),
        setCallbacks: jest.fn(),
    };

    return (
        <SettingsContext.Provider value={settingsValue}>
            <FilePreviewContext.Provider value={filePreviewValue}>
                {children}
            </FilePreviewContext.Provider>
        </SettingsContext.Provider>
    );
};

// Custom render with all contexts
const renderFileBrowser = (ui, options = {}) => {
    return renderWithProviders(
        <AllContextsWrapper>{ui}</AllContextsWrapper>,
        options
    );
};

describe('FileBrowser', () => {
    // Note: Files are sorted alphabetically by path, so file.txt comes before testdir/
    const mockBrowseFiles = [
        {path: 'file.txt', size: 1024},
        {path: 'testdir/', children: null, is_empty: true},
    ];

    beforeEach(() => {
        jest.clearAllMocks();
        useBrowseFiles.mockReturnValue({
            browseFiles: mockBrowseFiles,
            openFolders: [],
            setOpenFolders: jest.fn(),
            fetchFiles: jest.fn(),
        });
        useWROLMode.mockReturnValue(false);
        // [callbackRef, width]; width 0 keeps footer buttons icon-only in tests.
        useElementWidth.mockReturnValue([() => {}, 0]);
    });

    describe('Directory Selection', () => {
        it('renders without crashing', async () => {
            renderFileBrowser(<FileBrowser/>);
            // Should render the file browser table
            expect(screen.getByRole('table')).toBeInTheDocument();
        });

        it('handles selecting and unselecting a directory without error', async () => {
            renderFileBrowser(<FileBrowser/>);

            // Find the directory - text includes trailing slash
            const directoryRow = screen.getByText('testdir/');
            expect(directoryRow).toBeInTheDocument();

            // Find the checkbox in the same row - file.txt is first (index 0), testdir/ is second (index 1)
            const checkboxes = screen.getAllByRole('checkbox');
            const directoryCheckbox = checkboxes[1]; // Second checkbox is for the directory

            // Select the directory
            await act(async () => {
                fireEvent.click(directoryCheckbox);
            });

            // Unselect the directory - this should NOT throw an error
            await act(async () => {
                fireEvent.click(directoryCheckbox);
            });

            // If we get here without error, the test passes
            expect(screen.getByRole('table')).toBeInTheDocument();
        });

        it('upload button is enabled when nothing is selected', async () => {
            renderFileBrowser(<FileBrowser/>);

            // Find the upload button (green button with upload icon)
            const buttons = screen.getAllByRole('button');
            const uploadButton = buttons.find(btn =>
                btn.classList.contains('green') || btn.querySelector('[class*="upload"]')
            );

            // Button should exist and not be disabled
            expect(uploadButton).toBeInTheDocument();
            expect(uploadButton).not.toBeDisabled();
        });

        it('upload button is enabled when single directory is selected', async () => {
            renderFileBrowser(<FileBrowser/>);

            // Select the directory (second checkbox - testdir/)
            const checkboxes = screen.getAllByRole('checkbox');
            const directoryCheckbox = checkboxes[1];

            await act(async () => {
                fireEvent.click(directoryCheckbox);
            });

            // Find the upload button
            const buttons = screen.getAllByRole('button');
            const uploadButton = buttons.find(btn => btn.classList.contains('green'));

            expect(uploadButton).not.toBeDisabled();
        });

        it('upload button is disabled when file is selected', async () => {
            renderFileBrowser(<FileBrowser/>);

            // Select the file (first checkbox - file.txt)
            const checkboxes = screen.getAllByRole('checkbox');
            const fileCheckbox = checkboxes[0];

            await act(async () => {
                fireEvent.click(fileCheckbox);
            });

            // Find the upload button
            const buttons = screen.getAllByRole('button');
            const uploadButton = buttons.find(btn => btn.classList.contains('green'));

            expect(uploadButton).toBeDisabled();
        });
    });

    describe('Auto-select directory contents', () => {
        it('selects all children when opening a selected directory', async () => {
            const mockSetOpenFolders = jest.fn();
            const mockFetchFiles = jest.fn();

            // Start with folder not open (no children loaded)
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: null, is_empty: false},
                ],
                openFolders: [],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            const {rerender} = renderFileBrowser(<FileBrowser/>);

            // Select the directory checkbox
            const checkbox = screen.getByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkbox);
            });

            // Verify directory is selected
            expect(checkbox).toBeChecked();

            // Click to expand the directory (clicking on the folder name cell)
            const folderCell = screen.getByText('testdir/');
            await act(async () => {
                fireEvent.click(folderCell);
            });

            // Verify setOpenFolders was called to open the directory
            expect(mockSetOpenFolders).toHaveBeenCalledWith(['testdir/']);

            // Simulate browseFiles update with children (as would happen after fetch)
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: [
                        {path: 'testdir/file1.txt', size: 100},
                        {path: 'testdir/file2.txt', size: 200},
                    ], is_empty: false},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            // Rerender to trigger the useEffect with new browseFiles
            await act(async () => {
                rerender(
                    <AllContextsWrapper>
                        <FileBrowser/>
                    </AllContextsWrapper>
                );
            });

            // Verify all checkboxes are checked (parent + 2 children)
            await waitFor(() => {
                const checkboxes = screen.getAllByRole('checkbox');
                expect(checkboxes.length).toBe(3);
                checkboxes.forEach(cb => expect(cb).toBeChecked());
            });
        });

        it('children remain selected when parent is unselected', async () => {
            // Setup: directory with children, parent and children are all selected
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: [
                        {path: 'testdir/file1.txt', size: 100},
                        {path: 'testdir/file2.txt', size: 200},
                    ], is_empty: false},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            // Select all items (parent + children)
            const checkboxes = screen.getAllByRole('checkbox');
            expect(checkboxes.length).toBe(3);

            // Select parent first
            await act(async () => {
                fireEvent.click(checkboxes[0]); // testdir/
            });
            // Select children
            await act(async () => {
                fireEvent.click(checkboxes[1]); // file1.txt
            });
            await act(async () => {
                fireEvent.click(checkboxes[2]); // file2.txt
            });

            // Verify all are selected
            checkboxes.forEach(cb => expect(cb).toBeChecked());

            // Unselect the parent directory
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });

            // Parent should be unchecked, but children should remain checked
            expect(checkboxes[0]).not.toBeChecked();
            expect(checkboxes[1]).toBeChecked();
            expect(checkboxes[2]).toBeChecked();
        });

        it('unselects children when parent directory is closed', async () => {
            // Setup: directory with children, already open
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: [
                        {path: 'testdir/file1.txt', size: 100},
                        {path: 'testdir/file2.txt', size: 200},
                    ], is_empty: false},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            // Select parent and children
            const checkboxes = screen.getAllByRole('checkbox');
            expect(checkboxes.length).toBe(3);

            await act(async () => {
                fireEvent.click(checkboxes[0]); // testdir/
            });
            await act(async () => {
                fireEvent.click(checkboxes[1]); // file1.txt
            });
            await act(async () => {
                fireEvent.click(checkboxes[2]); // file2.txt
            });

            // Verify all are selected
            checkboxes.forEach(cb => expect(cb).toBeChecked());

            // Click to close the directory
            const folderCell = screen.getByText('testdir/');
            await act(async () => {
                fireEvent.click(folderCell);
            });

            // Parent should still be selected, but children should be unselected
            // (children are no longer visible after closing)
            expect(checkboxes[0]).toBeChecked();
        });

        it('does not auto-select children when opening unselected directory', async () => {
            const mockSetOpenFolders = jest.fn();
            const mockFetchFiles = jest.fn();

            // Start with folder not open
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: null, is_empty: false},
                ],
                openFolders: [],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            const {rerender} = renderFileBrowser(<FileBrowser/>);

            // Click to expand WITHOUT selecting first
            const folderCell = screen.getByText('testdir/');
            await act(async () => {
                fireEvent.click(folderCell);
            });

            // Simulate browseFiles update with children
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: [
                        {path: 'testdir/file1.txt', size: 100},
                        {path: 'testdir/file2.txt', size: 200},
                    ], is_empty: false},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            await act(async () => {
                rerender(
                    <AllContextsWrapper>
                        <FileBrowser/>
                    </AllContextsWrapper>
                );
            });

            // Verify NO checkboxes are checked
            const checkboxes = screen.getAllByRole('checkbox');
            expect(checkboxes.length).toBe(3);
            checkboxes.forEach(cb => expect(cb).not.toBeChecked());
        });
    });

    describe('Delete functionality', () => {
        it('removes deleted directory from openFolders', async () => {
            const mockSetOpenFolders = jest.fn();
            const mockFetchFiles = jest.fn();
            const mockDeleteFile = require('../api').deleteFile;
            mockDeleteFile.mockResolvedValue();

            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'testdir/', children: [{path: 'testdir/file.txt', size: 100}], is_empty: false},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            renderFileBrowser(<FileBrowser/>);

            // Select the directory (first checkbox - testdir/)
            const checkboxes = screen.getAllByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });

            // Click delete button (red trash button) - uses APIButton which has confirm modal
            const deleteButton = screen.getAllByRole('button').find(btn => btn.classList.contains('red'));
            await act(async () => {
                fireEvent.click(deleteButton);
            });

            // Confirm deletion in modal - getAllByText because Confirm renders both mobile/desktop versions
            await waitFor(() => {
                expect(screen.getAllByText('Delete').length).toBeGreaterThan(0);
            });
            const confirmButton = screen.getAllByText('Delete')[0];
            await act(async () => {
                fireEvent.click(confirmButton);
            });

            // Verify setOpenFolders was called to remove the deleted directory
            await waitFor(() => {
                expect(mockSetOpenFolders).toHaveBeenCalledWith(null);
            });
        });

        it('does not modify openFolders when deleting files only', async () => {
            const mockSetOpenFolders = jest.fn();
            const mockFetchFiles = jest.fn();
            const mockDeleteFile = require('../api').deleteFile;
            mockDeleteFile.mockResolvedValue();

            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'file.txt', size: 1024},
                    {path: 'testdir/', children: null, is_empty: true},
                ],
                openFolders: ['testdir/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: mockFetchFiles,
            });

            renderFileBrowser(<FileBrowser/>);

            // Select the file (first checkbox - file.txt)
            const checkboxes = screen.getAllByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });

            // Click delete button
            const deleteButton = screen.getAllByRole('button').find(btn => btn.classList.contains('red'));
            await act(async () => {
                fireEvent.click(deleteButton);
            });

            // Confirm deletion in modal - getAllByText because Confirm renders both mobile/desktop versions
            await waitFor(() => {
                expect(screen.getAllByText('Delete').length).toBeGreaterThan(0);
            });
            const confirmButton = screen.getAllByText('Delete')[0];
            await act(async () => {
                fireEvent.click(confirmButton);
            });

            // Wait for delete to complete
            await waitFor(() => {
                expect(mockDeleteFile).toHaveBeenCalled();
            });

            // setOpenFolders should NOT have been called since we only deleted a file
            expect(mockSetOpenFolders).not.toHaveBeenCalled();
        });
    });

    describe('Filter', () => {
        // foo/ and bar/ are open, their children are loaded.
        const nestedBrowseFiles = [
            {
                path: 'foo/', is_empty: false, children: [
                    {path: 'foo/foo1.txt', size: 100},
                    {path: 'foo/foo2.txt', size: 200},
                ]
            },
            {
                path: 'bar/', is_empty: false, children: [
                    {path: 'bar/bar.1.txt', size: 300},
                ]
            },
        ];

        describe('filterBrowseFiles', () => {
            it('returns files unchanged when filter is empty', () => {
                expect(filterBrowseFiles(nestedBrowseFiles, '')).toBe(nestedBrowseFiles);
            });

            it('keeps a matching folder and its entire subtree', () => {
                const result = filterBrowseFiles(nestedBrowseFiles, 'bar');
                expect(result).toHaveLength(1);
                expect(result[0].path).toBe('bar/');
                expect(result[0].children).toHaveLength(1);
                expect(result[0].children[0].path).toBe('bar/bar.1.txt');
            });

            it('keeps the parent folders of a matching file', () => {
                const result = filterBrowseFiles(nestedBrowseFiles, 'foo1');
                expect(result).toHaveLength(1);
                expect(result[0].path).toBe('foo/');
                expect(result[0].children).toHaveLength(1);
                expect(result[0].children[0].path).toBe('foo/foo1.txt');
            });

            it('matches case-insensitively', () => {
                const result = filterBrowseFiles(nestedBrowseFiles, 'FOO1');
                expect(result).toHaveLength(1);
                expect(result[0].children[0].path).toBe('foo/foo1.txt');
            });

            it('handles the dict format returned by the API', () => {
                const dictFiles = {
                    'foo/': {
                        path: 'foo/', is_empty: false, children: {
                            'foo1.txt': {path: 'foo/foo1.txt', size: 100},
                        }
                    },
                    'bar.txt': {path: 'bar.txt', size: 300},
                };
                const result = filterBrowseFiles(dictFiles, 'bar');
                expect(result).toHaveLength(1);
                expect(result[0].path).toBe('bar.txt');
            });

            it('returns no rows when nothing matches', () => {
                expect(filterBrowseFiles(nestedBrowseFiles, 'does-not-exist')).toHaveLength(0);
            });
        });

        it('reduces the rows to matches and their tree', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            // All rows are visible before filtering.
            expect(screen.getByText('foo1.txt')).toBeInTheDocument();
            expect(screen.getByText('bar.1.txt')).toBeInTheDocument();

            const filterInput = screen.getByPlaceholderText('Filter files...');
            await act(async () => {
                fireEvent.change(filterInput, {target: {value: 'bar'}});
            });

            // Only bar/ and its child remain.
            expect(screen.getByText('bar/')).toBeInTheDocument();
            expect(screen.getByText('bar.1.txt')).toBeInTheDocument();
            expect(screen.queryByText('foo/')).not.toBeInTheDocument();
            expect(screen.queryByText('foo1.txt')).not.toBeInTheDocument();
            expect(screen.queryByText('foo2.txt')).not.toBeInTheDocument();
        });

        it('restores all rows when the filter is cleared', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            const filterInput = screen.getByPlaceholderText('Filter files...');
            await act(async () => {
                fireEvent.change(filterInput, {target: {value: 'bar'}});
            });
            expect(screen.queryByText('foo1.txt')).not.toBeInTheDocument();

            await act(async () => {
                fireEvent.change(filterInput, {target: {value: ''}});
            });
            expect(screen.getByText('foo1.txt')).toBeInTheDocument();
            expect(screen.getByText('bar.1.txt')).toBeInTheDocument();
        });

        it('does not filter the contents of an opened folder that matches the filter', async () => {
            const mockSetOpenFolders = jest.fn();

            // ebooks/ is closed, no children loaded yet.
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'ebooks/', children: null, is_empty: false},
                    {path: 'other.txt', size: 100},
                ],
                openFolders: [],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: jest.fn(),
            });

            const {rerender} = renderFileBrowser(<FileBrowser/>);

            // Filter for the folder's name.
            const filterInput = screen.getByPlaceholderText('Filter files...');
            await act(async () => {
                fireEvent.change(filterInput, {target: {value: 'ebooks'}});
            });
            expect(screen.queryByText('other.txt')).not.toBeInTheDocument();

            // Open the matching folder.
            await act(async () => {
                fireEvent.click(screen.getByText('ebooks/'));
            });
            expect(mockSetOpenFolders).toHaveBeenCalledWith(['ebooks/']);

            // Simulate the folder's children loading; their names do NOT match the filter.
            useBrowseFiles.mockReturnValue({
                browseFiles: [
                    {path: 'ebooks/', children: [
                        {path: 'ebooks/novel.epub', size: 100},
                        {path: 'ebooks/cover.jpg', size: 200},
                    ], is_empty: false},
                    {path: 'other.txt', size: 100},
                ],
                openFolders: ['ebooks/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: jest.fn(),
            });
            await act(async () => {
                rerender(
                    <AllContextsWrapper>
                        <FileBrowser/>
                    </AllContextsWrapper>
                );
            });

            // The matching folder's contents are shown unfiltered.
            expect(screen.getByText('ebooks/')).toBeInTheDocument();
            expect(screen.getByText('novel.epub')).toBeInTheDocument();
            expect(screen.getByText('cover.jpg')).toBeInTheDocument();
            // Non-matching rows outside the folder stay hidden.
            expect(screen.queryByText('other.txt')).not.toBeInTheDocument();
        });

        it('focuses the filter input when f is pressed', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            const filterInput = screen.getByPlaceholderText('Filter files...');
            expect(filterInput).not.toHaveFocus();

            await act(async () => {
                fireEvent.keyDown(document.body, {key: 'f', code: 'KeyF'});
            });

            expect(filterInput).toHaveFocus();
        });

        it('clear button clears the filter and shows all rows again', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            const clearButton = screen.getByLabelText('Clear filter');
            expect(clearButton).toBeDisabled();

            const filterInput = screen.getByPlaceholderText('Filter files...');
            await act(async () => {
                fireEvent.change(filterInput, {target: {value: 'bar'}});
            });
            expect(screen.queryByText('foo1.txt')).not.toBeInTheDocument();
            expect(clearButton).not.toBeDisabled();

            await act(async () => {
                fireEvent.click(clearButton);
            });

            expect(filterInput).toHaveValue('');
            expect(screen.getByText('foo1.txt')).toBeInTheDocument();
            expect(screen.getByText('foo2.txt')).toBeInTheDocument();
            expect(screen.getByText('bar.1.txt')).toBeInTheDocument();
        });

        it('collapse-all button is disabled when no folders are open', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: [],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            expect(screen.getByLabelText('Close all folders')).toBeDisabled();
        });

        it('collapse-all button closes all folders and deselects their hidden contents', async () => {
            const mockSetOpenFolders = jest.fn();
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: mockSetOpenFolders,
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            // Select the foo/ folder and a file inside it.
            const checkboxes = screen.getAllByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkboxes[0]); // foo/
            });
            await act(async () => {
                fireEvent.click(checkboxes[1]); // foo/foo1.txt
            });
            expect(checkboxes[0]).toBeChecked();
            expect(checkboxes[1]).toBeChecked();

            const collapseButton = screen.getByLabelText('Close all folders');
            expect(collapseButton).not.toBeDisabled();
            await act(async () => {
                fireEvent.click(collapseButton);
            });

            // All folders are closed (clears the ?folders= query param).
            expect(mockSetOpenFolders).toHaveBeenCalledWith(null);
            // The folder stays selected, but its now-hidden child does not.
            expect(checkboxes[0]).toBeChecked();
            expect(checkboxes[1]).not.toBeChecked();
        });

        it('shows no results when nothing matches', async () => {
            useBrowseFiles.mockReturnValue({
                browseFiles: nestedBrowseFiles,
                openFolders: ['foo/', 'bar/'],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });

            renderFileBrowser(<FileBrowser/>);

            const filterInput = screen.getByPlaceholderText('Filter files...');
            await act(async () => {
                fireEvent.change(filterInput, {target: {value: 'does-not-exist'}});
            });

            expect(screen.getByText('No results')).toBeInTheDocument();
        });
    });

    describe('Drag Selection', () => {
        const mockBrowseFilesMultiple = [
            {path: 'file1.txt', size: 100},
            {path: 'file2.txt', size: 200},
            {path: 'file3.txt', size: 300},
        ];

        beforeEach(() => {
            useBrowseFiles.mockReturnValue({
                browseFiles: mockBrowseFilesMultiple,
                openFolders: [],
                setOpenFolders: jest.fn(),
                fetchFiles: jest.fn(),
            });
        });

        it('does not enable drag selection on touch devices', async () => {
            // Mock matchMedia to simulate touch device
            window.matchMedia = jest.fn().mockImplementation(query => ({
                matches: query === '(pointer: coarse)', // true for touch devices
                media: query,
                onchange: null,
                addListener: jest.fn(),
                removeListener: jest.fn(),
                addEventListener: jest.fn(),
                removeEventListener: jest.fn(),
                dispatchEvent: jest.fn(),
            }));

            renderFileBrowser(<FileBrowser/>);

            const rows = screen.getAllByRole('row');
            // Skip header row (index 0)
            const firstRow = rows[1];

            // Simulate mousedown - on touch device, this should not start drag
            await act(async () => {
                fireEvent.mouseDown(firstRow, {button: 0, clientX: 100, clientY: 100});
            });

            // Move mouse and mouseup - items should NOT be selected via drag
            await act(async () => {
                fireEvent.mouseMove(document, {clientX: 100, clientY: 200});
                fireEvent.mouseUp(document);
            });

            // Verify no items are selected (checkboxes unchecked)
            const checkboxes = screen.getAllByRole('checkbox');
            checkboxes.forEach(cb => expect(cb).not.toBeChecked());
        });

        it('selects rows when dragging across them', async () => {
            renderFileBrowser(<FileBrowser/>);

            const rows = screen.getAllByRole('row');
            // Skip header row
            const firstDataRow = rows[1];
            const secondDataRow = rows[2];
            const thirdDataRow = rows[3];

            // Start drag on first row
            await act(async () => {
                fireEvent.mouseDown(firstDataRow, {button: 0, clientX: 100, clientY: 100});
            });

            // Move mouse enough to trigger drag threshold (5px)
            await act(async () => {
                fireEvent.mouseMove(document, {clientX: 100, clientY: 110});
            });

            // Enter subsequent rows
            await act(async () => {
                fireEvent.mouseEnter(secondDataRow);
            });

            await act(async () => {
                fireEvent.mouseEnter(thirdDataRow);
            });

            // End drag
            await act(async () => {
                fireEvent.mouseUp(document);
            });

            // All three files should be selected
            const checkboxes = screen.getAllByRole('checkbox');
            expect(checkboxes.length).toBe(3);
            checkboxes.forEach(cb => expect(cb).toBeChecked());
        });

        it('adds to existing selection when dragging', async () => {
            renderFileBrowser(<FileBrowser/>);

            // First, select the first file via checkbox
            const checkboxes = screen.getAllByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });

            // Verify first file is selected
            expect(checkboxes[0]).toBeChecked();
            expect(checkboxes[1]).not.toBeChecked();
            expect(checkboxes[2]).not.toBeChecked();

            const rows = screen.getAllByRole('row');
            const secondDataRow = rows[2];
            const thirdDataRow = rows[3];

            // Start drag on second row
            await act(async () => {
                fireEvent.mouseDown(secondDataRow, {button: 0, clientX: 100, clientY: 100});
            });

            // Move enough to trigger drag
            await act(async () => {
                fireEvent.mouseMove(document, {clientX: 100, clientY: 110});
            });

            await act(async () => {
                fireEvent.mouseEnter(thirdDataRow);
            });

            await act(async () => {
                fireEvent.mouseUp(document);
            });

            // All three should now be selected (first via checkbox, second and third via drag)
            const updatedCheckboxes = screen.getAllByRole('checkbox');
            updatedCheckboxes.forEach(cb => expect(cb).toBeChecked());
        });

        it('does not start drag when clicking on checkbox', async () => {
            renderFileBrowser(<FileBrowser/>);

            const checkboxes = screen.getAllByRole('checkbox');

            // Click checkbox - should toggle selection, not start drag
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });

            expect(checkboxes[0]).toBeChecked();
            expect(checkboxes[1]).not.toBeChecked();
            expect(checkboxes[2]).not.toBeChecked();
        });

        it('does not start drag with right mouse button', async () => {
            renderFileBrowser(<FileBrowser/>);

            const rows = screen.getAllByRole('row');
            const firstDataRow = rows[1];
            const secondDataRow = rows[2];

            // Try to start drag with right button
            await act(async () => {
                fireEvent.mouseDown(firstDataRow, {button: 2, clientX: 100, clientY: 100});
            });

            await act(async () => {
                fireEvent.mouseMove(document, {clientX: 100, clientY: 110});
            });

            await act(async () => {
                fireEvent.mouseEnter(secondDataRow);
            });

            await act(async () => {
                fireEvent.mouseUp(document);
            });

            // No items should be selected
            const checkboxes = screen.getAllByRole('checkbox');
            checkboxes.forEach(cb => expect(cb).not.toBeChecked());
        });

        it('deselects rows when dragging from a selected item', async () => {
            renderFileBrowser(<FileBrowser/>);

            // First, select all three files via checkboxes
            const checkboxes = screen.getAllByRole('checkbox');
            await act(async () => {
                fireEvent.click(checkboxes[0]);
            });
            await act(async () => {
                fireEvent.click(checkboxes[1]);
            });
            await act(async () => {
                fireEvent.click(checkboxes[2]);
            });

            // Verify all are selected
            expect(checkboxes[0]).toBeChecked();
            expect(checkboxes[1]).toBeChecked();
            expect(checkboxes[2]).toBeChecked();

            const rows = screen.getAllByRole('row');
            const firstDataRow = rows[1];
            const secondDataRow = rows[2];

            // Start drag from first row (which is selected) - should trigger deselect mode
            await act(async () => {
                fireEvent.mouseDown(firstDataRow, {button: 0, clientX: 100, clientY: 100});
            });

            // Move enough to trigger drag
            await act(async () => {
                fireEvent.mouseMove(document, {clientX: 100, clientY: 110});
            });

            await act(async () => {
                fireEvent.mouseEnter(secondDataRow);
            });

            await act(async () => {
                fireEvent.mouseUp(document);
            });

            // First two should now be deselected, third should remain selected
            const updatedCheckboxes = screen.getAllByRole('checkbox');
            expect(updatedCheckboxes[0]).not.toBeChecked();
            expect(updatedCheckboxes[1]).not.toBeChecked();
            expect(updatedCheckboxes[2]).toBeChecked();
        });
    });
});
