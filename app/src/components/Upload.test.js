import React from 'react';
import {screen} from '@testing-library/react';
import {UploadModal} from './Upload';
import {renderWithProviders} from '../test-utils';

const mockUseUploadFile = {
    setFiles: jest.fn(),
    progresses: {},
    destination: '',
    setDestination: jest.fn(),
    doClear: jest.fn(),
    tagsSelector: null,
    overwrite: false,
    setOverwrite: jest.fn(),
    overallProgress: 0,
    inProgress: false,
};

jest.mock('../hooks/customHooks', () => require('../test-utils').mockModule(
    jest.requireActual('../hooks/customHooks'),
    {useUploadFile: () => mockUseUploadFile},
));

jest.mock('react-dropzone', () => ({
    useDropzone: () => ({getRootProps: () => ({}), getInputProps: () => ({})}),
}));

// The real `useMediaDirectory`, reading the settings the providers supply.
const render = ui => renderWithProviders(ui, {settings: {media_directory: '/media/wrolpi'}});

/*
 * The dashboard and the file browser open the SAME dialog.  They were two components with two
 * copies of the dropzone, the overwrite toggle and the progress bars, which is why the file
 * browser's grew to fill its dialog and the dashboard's stayed a strip.  These assert the one
 * difference that is real -- whether the destination is asked for -- so a future change to one
 * entry point cannot quietly fork them again.
 */
describe('one upload dialog, two entry points', () => {
    beforeEach(() => jest.clearAllMocks());

    it('asks for a destination when the caller has none', () => {
        render(<UploadModal open={true} onClose={() => {}}/>);

        expect(screen.getByText('Destination')).toBeInTheDocument();
        // Nowhere to put a file yet, so the target is replaced by the instruction.
        expect(screen.getByText(/must search for a directory/)).toBeInTheDocument();
        expect(screen.queryByText(/drop files here/)).not.toBeInTheDocument();
    });

    it('uploads into the destination it is given, and names it', () => {
        render(<UploadModal open={true} onClose={() => {}} destination='videos'/>);

        expect(screen.getByText('Upload to: /media/wrolpi/videos')).toBeInTheDocument();
        expect(screen.queryByText('Destination')).not.toBeInTheDocument();
        expect(screen.getByText(/drop files here/)).toBeInTheDocument();
        expect(mockUseUploadFile.setDestination).toHaveBeenCalledWith('videos');
    });

    /*
     * '' is the media directory, which is where the file browser uploads to when no folder is
     * selected.  Only `undefined` means "ask" -- a falsy check here would send that user to a
     * DirectorySearch instead of the drop target.
     */
    it('treats the media directory as a destination, not a missing one', () => {
        render(<UploadModal open={true} onClose={() => {}} destination=''/>);

        expect(screen.queryByText('Destination')).not.toBeInTheDocument();
        expect(screen.getByText(/drop files here/)).toBeInTheDocument();
    });
});
