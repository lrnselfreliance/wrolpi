import React from 'react';
import {act, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {FilePreviewContext, FilePreviewProvider} from './FilePreview';
import {getFile} from '../api';

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getFile: jest.fn(),
    tagFileGroup: jest.fn(),
    untagFileGroup: jest.fn(),
}));

const imageFile = {primary_path: 'pictures/cat.png', mimetype: 'image/png', size: 100, taggable: true, tags: []};

/** getFile calls that would mark the file viewed (skipTracking not set). */
const trackedCalls = () => getFile.mock.calls.filter(([, skipTracking]) => !skipTracking);

/** Exposes the provider's context so a test can open a preview the way PreviewLink does. */
let context;
const ContextSpy = () => {
    context = React.useContext(FilePreviewContext);
    return null;
};

const renderProvider = (preview = null) => renderWithProviders(
    <FilePreviewProvider><ContextSpy/></FilePreviewProvider>,
    {
        route: '/files',
        query: {searchParams: new URLSearchParams(preview ? {preview} : {}), updateQuery: jest.fn()},
    },
);

describe('FilePreview view tracking', () => {
    beforeEach(() => {
        getFile.mockReset();
        getFile.mockResolvedValue(imageFile);
        context = null;
    });

    test('opening a preview from the URL marks the file viewed once', async () => {
        renderProvider(imageFile.primary_path);

        await waitFor(() => expect(getFile).toHaveBeenCalled());
        await waitFor(() => expect(context.previewModal).not.toBeNull());
        expect(trackedCalls()).toHaveLength(1);
    });

    test('opening a preview from a link marks the file viewed once', async () => {
        renderProvider();

        act(() => context.setPreviewFile(imageFile));

        await waitFor(() => expect(trackedCalls()).toHaveLength(1));
        expect(getFile).toHaveBeenCalledTimes(1);
    });

    test('refreshing the open file (after tagging) is not another view', async () => {
        renderProvider();
        act(() => context.setPreviewFile(imageFile));
        await waitFor(() => expect(trackedCalls()).toHaveLength(1));

        // localFetchFile replaces previewFile with the re-fetched file after a tag change.
        act(() => context.setPreviewFile({...imageFile, tags: ['animals']}));
        await waitFor(() => expect(context.previewFile.tags).toEqual(['animals']));

        expect(trackedCalls()).toHaveLength(1);
    });

    test('closing and reopening the same file is another view', async () => {
        renderProvider();
        act(() => context.setPreviewFile(imageFile));
        await waitFor(() => expect(trackedCalls()).toHaveLength(1));

        act(() => context.setPreviewFile(null));
        act(() => context.setPreviewFile(imageFile));

        await waitFor(() => expect(trackedCalls()).toHaveLength(2));
    });
});
