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
 * The dashboard and the file browser open the same dialog, and differ only in whether it asks
 * where the files go.  That fork, and the `''` contract underneath it, are what these pin.
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
     * '' is the media directory -- where the file browser uploads when no folder is selected,
     * which is the state its Upload button is enabled in.  Every falsy check along this path
     * reads it as "no destination", so each is asserted separately: the fork, the title, and
     * what the hook is told.
     */
    it('treats the media directory as a destination, not a missing one', () => {
        render(<UploadModal open={true} onClose={() => {}} destination=''/>);

        expect(screen.queryByText('Destination')).not.toBeInTheDocument();
        expect(screen.getByText(/drop files here/)).toBeInTheDocument();
        expect(screen.getByText('Upload to: /media/wrolpi')).toBeInTheDocument();
        expect(mockUseUploadFile.setDestination).toHaveBeenCalledWith('');
    });

    /*
     * The clearing effect ran on every render for a `''` destination, and `doClear` sets state,
     * so each run scheduled the render that ran it again -- "Maximum update depth exceeded" on
     * the file browser's default Upload.  A fixed destination is never cleared, so it is never
     * the thing that empties the queue.
     */
    it('does not clear the queue it is about to upload', () => {
        const {rerender} = render(<UploadModal open={true} onClose={() => {}} destination=''/>);
        rerender(<UploadModal open={true} onClose={() => {}} destination=''/>);

        expect(mockUseUploadFile.doClear).not.toHaveBeenCalled();
    });

    // Asking is the case that does clear: the user emptied their own search.
    it('clears the queue when the user clears their search', () => {
        render(<UploadModal open={true} onClose={() => {}}/>);

        expect(mockUseUploadFile.doClear).toHaveBeenCalled();
    });
});
