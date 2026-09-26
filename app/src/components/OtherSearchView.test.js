import React from 'react';
import {act, render, screen} from '../test-utils';
import {OtherSearchView} from './Search';
import {searchChannels} from '../api';

// What the search page's Other tab shows for each state of useSearchChannels.  "No Channels"
// must only appear once the server has confirmed there are none.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    searchChannels: jest.fn(),
}));

const NO_CHANNELS = /No Channels/;

beforeEach(() => searchChannels.mockReset());

test('pending: shows a loader, not "No Channels"', () => {
    searchChannels.mockReturnValue(new Promise(() => {
    }));
    const {container} = render(<OtherSearchView loading={false}/>);
    expect(container.querySelector('.wrolpi-loading')).toBeInTheDocument();
    expect(screen.queryByText(NO_CHANNELS)).not.toBeInTheDocument();
});

test('failed: shows an error, not "No Channels"', async () => {
    searchChannels.mockResolvedValue(undefined);
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {
    });
    try {
        render(<OtherSearchView loading={false}/>);
        await act(async () => {
        });
        expect(screen.getByText(/Could not fetch the channels/)).toBeInTheDocument();
        expect(screen.queryByText(NO_CHANNELS)).not.toBeInTheDocument();
    } finally {
        spy.mockRestore();
    }
});

test('empty: shows "No Channels"', async () => {
    searchChannels.mockResolvedValue({channels: []});
    render(<OtherSearchView loading={false}/>);
    await act(async () => {
    });
    expect(screen.getByText(NO_CHANNELS)).toBeInTheDocument();
});

test('loaded: lists the channels', async () => {
    searchChannels.mockResolvedValue({channels: [{id: 1, name: 'Cooking'}]});
    render(<OtherSearchView loading={false}/>);
    await act(async () => {
    });
    expect(screen.getByText('Cooking')).toBeInTheDocument();
    expect(screen.queryByText(NO_CHANNELS)).not.toBeInTheDocument();
});
