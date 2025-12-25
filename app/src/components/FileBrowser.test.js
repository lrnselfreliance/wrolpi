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
});
