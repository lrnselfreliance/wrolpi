import React from 'react';
import {act, render, screen} from '../test-utils';
import {createTestForm} from '../test-utils';
import {DownloaderSelector} from './Download';
import {getDownloaders} from '../api';

// The RSS form's Downloader select is filled from the API.  Until the list arrives, or if it could
// not be fetched, the select must say so rather than sit empty as though there were no downloaders.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getDownloaders: jest.fn(),
}));

const makeForm = () => createTestForm({}, {
    overrides: {getSelectionProps: () => [{value: null, onChange: jest.fn(), disabled: false, error: null}]},
});

beforeEach(() => getDownloaders.mockReset());

test('pending: the select says it is loading and is disabled', () => {
    getDownloaders.mockReturnValue(new Promise(() => {
    }));
    render(<DownloaderSelector form={makeForm()}/>);
    const input = screen.getByPlaceholderText('Loading downloaders…');
    expect(input).toBeDisabled();
});

test('failed: the select says the downloaders could not be fetched', async () => {
    getDownloaders.mockResolvedValue(undefined);
    render(<DownloaderSelector form={makeForm()}/>);
    await act(async () => {
    });
    expect(screen.getByPlaceholderText('Could not fetch downloaders')).toBeDisabled();
});

test('loaded: the select offers the downloaders', async () => {
    getDownloaders.mockResolvedValue({downloaders: [{name: 'video', pretty_name: 'Videos'}]});
    render(<DownloaderSelector form={makeForm()}/>);
    await act(async () => {
    });
    expect(screen.getByPlaceholderText('Select a downloader')).toBeEnabled();
});
