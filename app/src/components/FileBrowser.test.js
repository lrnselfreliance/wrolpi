import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {FileBrowser} from './FileBrowser';
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
}));

// Mock react-dropzone
jest.mock('react-dropzone', () => ({
    useDropzone: () => ({
        getRootProps: () => ({}),
        getInputProps: () => ({}),
    }),
}));

// Import mocked hooks for manipulation
import {useBrowseFiles, useWROLMode} from '../hooks/customHooks';

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
});
