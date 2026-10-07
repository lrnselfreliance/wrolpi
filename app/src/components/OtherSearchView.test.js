import React from 'react';
import {act, render, screen} from '../test-utils';
import {OtherSearchView} from './Search';
import {searchChannels, searchRepos} from '../api';

// What the search page's Other tab shows for each state of useSearchChannels.  "No Channels"
// must only appear once the server has confirmed there are none.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    searchChannels: jest.fn(),
    searchRepos: jest.fn(),
}));

const NO_CHANNELS = /No Channels/;

beforeEach(() => {
    searchChannels.mockReset();
    searchRepos.mockReset();
    searchRepos.mockResolvedValue({repos: [], total: 0});
});

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

describe('Repos', () => {
    test('pending: the Repos section loads while Channels are shown', async () => {
        searchChannels.mockResolvedValue({channels: []});
        searchRepos.mockReturnValue(new Promise(() => {
        }));
        const {container} = render(<OtherSearchView loading={false}/>);
        await act(async () => {
        });
        expect(screen.getByText(NO_CHANNELS)).toBeInTheDocument();
        expect(container.querySelector('.wrolpi-loading')).toBeInTheDocument();
        expect(screen.queryByText('No Repos')).not.toBeInTheDocument();
    });

    test('empty: shows "No Repos"', async () => {
        searchChannels.mockResolvedValue({channels: []});
        render(<OtherSearchView loading={false}/>);
        await act(async () => {
        });
        expect(screen.getByText('No Repos')).toBeInTheDocument();
    });

    test('failed: shows an error only in the Repos section', async () => {
        searchChannels.mockResolvedValue({channels: [{id: 1, name: 'Cooking'}]});
        searchRepos.mockRejectedValue(new Error('boom'));
        const spy = jest.spyOn(console, 'error').mockImplementation(() => {
        });
        try {
            render(<OtherSearchView loading={false}/>);
            await act(async () => {
            });
            expect(screen.getByText('Cooking')).toBeInTheDocument();
            expect(screen.getByText(/Could not fetch the repos/)).toBeInTheDocument();
        } finally {
            spy.mockRestore();
        }
    });

    test('loaded: lists repos by the search, with their README headline', async () => {
        searchChannels.mockResolvedValue({channels: []});
        searchRepos.mockResolvedValue({
            total: 1, repos: [{
                id: 7, name: 'kiwix-tools', tag_name: null,
                // The server escapes the README; only the highlight is markup.
                readme_headline: 'Serve <b>Zim</b> files &lt;script&gt;',
            }],
        });
        const searchParams = new URLSearchParams('q=zim&tag=Software');
        const {container} = render(<OtherSearchView loading={false}/>, {query: {searchParams}});
        await act(async () => {
        });
        expect(searchRepos).toHaveBeenCalledWith('zim', ['Software']);
        expect(screen.getByText('kiwix-tools').closest('a')).toHaveAttribute('href', '/repos/7');
        expect(container.querySelector('u').textContent).toBe('Zim');
        expect(container.querySelector('script')).toBeNull();
        expect(screen.getByText(/files <script>/)).toBeInTheDocument();
    });
});
