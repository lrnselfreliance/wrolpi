import React from 'react';
import {render, screen} from '../test-utils';
import {MapSearchView} from './MapSearchView';
import {getMapSearchStatus, searchMap} from '../api';

// The map search tab says "No map locations found" only when the server searched and found none,
// and "No maps are installed" only when the server said so.  A failed request is an error.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getMapSearchStatus: jest.fn(),
    searchMap: jest.fn(),
}));

const NOT_FOUND = /No map locations found/;
const NO_MAPS = /No maps are installed/;
const FAILED = /Could not search the map/;

const renderAt = (q) => render(<MapSearchView/>, {query: {searchParams: new URLSearchParams({q})}});

beforeEach(() => {
    getMapSearchStatus.mockReset();
    searchMap.mockReset();
    getMapSearchStatus.mockResolvedValue({indexed: ['utah'], missing: []});
});

test('found nothing: says so', async () => {
    searchMap.mockResolvedValue({results: [], total: 0});
    renderAt('camp');
    expect(await screen.findByText(NOT_FOUND)).toBeInTheDocument();
});

test('a failed search shows an error, not "No map locations found"', async () => {
    searchMap.mockResolvedValue(undefined);
    renderAt('camp');
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    expect(screen.queryByText(NOT_FOUND)).not.toBeInTheDocument();
});

test('a failed status check does not claim no maps are installed', async () => {
    getMapSearchStatus.mockResolvedValue(undefined);
    searchMap.mockResolvedValue({results: [], total: 0});
    renderAt('camp');
    expect(await screen.findByText(NOT_FOUND)).toBeInTheDocument();
    expect(screen.queryByText(NO_MAPS)).not.toBeInTheDocument();
});

test('a thrown status check does not claim no maps are installed', async () => {
    getMapSearchStatus.mockRejectedValue(new Error('down'));
    searchMap.mockResolvedValue({results: [], total: 0});
    renderAt('camp');
    expect(await screen.findByText(NOT_FOUND)).toBeInTheDocument();
    expect(screen.queryByText(NO_MAPS)).not.toBeInTheDocument();
});

test('the server saying no maps are installed is shown', async () => {
    getMapSearchStatus.mockResolvedValue({indexed: [], missing: []});
    searchMap.mockResolvedValue({results: [], total: 0});
    renderAt('camp');
    expect(await screen.findByText(NO_MAPS)).toBeInTheDocument();
});
