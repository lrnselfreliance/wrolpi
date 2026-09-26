import React from 'react';
import {act, screen} from '@testing-library/react';
import {Route, Routes} from 'react-router';
import {renderWithProviders as render} from '../test-utils';
import {MapRoute} from './Map';

// What the map's Pins and Manage tabs show while their lists are still loading, when the
// fetch failed, and when the server confirmed the list is empty.  The empty messages invite
// the user to act ("Right-click on the map to add one"), so they may only appear for a
// confirmed empty list.

jest.mock('maplibre-gl', () => ({
    __esModule: true,
    default: {Map: class {
        }, addProtocol: jest.fn(), Marker: class {
        }},
}));
jest.mock('pmtiles', () => ({
    __esModule: true, Protocol: class {
        tile = jest.fn();
    },
}));
jest.mock('protomaps-themes-base', () => ({__esModule: true, default: () => []}));
jest.mock('./MapViewer', () => ({__esModule: true, default: () => null}));

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getMapFiles: jest.fn(),
    fetchMapSubscriptions: jest.fn(),
    getMapPins: jest.fn(),
}));

const api = require('../api');

const pending = () => new Promise(() => {
});
const NO_PINS = /No pins\. Right-click/;
const NO_RESULTS = /^No results$/;

// The pins page renders one table per breakpoint through `Media`, so the real media provider is
// needed; the queries below tolerate either variant being in the tree.
const renderAt = (route) => render(
    <Routes><Route path='/map/*' element={<MapRoute/>}/></Routes>,
    {route, withMedia: true},
);

beforeEach(() => {
    jest.clearAllMocks();
    // The media provider reads matchMedia; the global stub's implementation is reset between
    // tests, so give it one here.  Only the computer breakpoint (1024px) matches, so the
    // provider reports a desktop viewport and the pins page renders its desktop table.
    window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: query.includes('1024'), media: query, onchange: null,
        addListener: jest.fn(), removeListener: jest.fn(),
        addEventListener: jest.fn(), removeEventListener: jest.fn(), dispatchEvent: jest.fn(),
    }));
    api.getMapFiles.mockResolvedValue({files: []});
    api.fetchMapSubscriptions.mockResolvedValue({catalog: [], subscriptions: []});
    api.getMapPins.mockResolvedValue({pins: []});
});

describe('the Pins tab', () => {
    test('pending: shows a placeholder, not "No pins"', () => {
        api.getMapPins.mockReturnValue(pending());
        const {container} = renderAt('/map/pins');
        expect(container.querySelector('.wrolpi-placeholder')).toBeInTheDocument();
        expect(screen.queryAllByText(NO_PINS)).toHaveLength(0);
    });

    test('failed: shows an error, not "No pins"', async () => {
        // The api helper returns undefined on a non-OK response.
        api.getMapPins.mockResolvedValue(undefined);
        renderAt('/map/pins');
        await act(async () => {
        });
        expect(screen.getByText(/Could not fetch map pins/)).toBeInTheDocument();
        expect(screen.queryAllByText(NO_PINS)).toHaveLength(0);
    });

    test('empty: shows "No pins"', async () => {
        renderAt('/map/pins');
        await act(async () => {
        });
        expect(screen.getAllByText(NO_PINS).length).toBeGreaterThan(0);
    });

    test('loaded: lists the pins', async () => {
        api.getMapPins.mockResolvedValue({pins: [{id: 1, lat: 40.1, lon: -111.2, label: 'Camp', color: '#f00'}]});
        renderAt('/map/pins');
        await act(async () => {
        });
        expect(screen.getAllByText('Camp').length).toBeGreaterThan(0);
        expect(screen.queryAllByText(NO_PINS)).toHaveLength(0);
    });
});

describe('the Manage tab subscriptions table', () => {
    test('pending: shows a placeholder, not "No results"', async () => {
        api.fetchMapSubscriptions.mockReturnValue(pending());
        const {container} = renderAt('/map/manage');
        await act(async () => {
        });
        // The files table has loaded (empty); the subscriptions table is still pending.
        expect(container.querySelector('.wrolpi-placeholder')).toBeInTheDocument();
        expect(screen.queryByText(NO_RESULTS)).not.toBeInTheDocument();
    });

    test('failed: shows an error, not "No results"', async () => {
        api.fetchMapSubscriptions.mockResolvedValue(undefined);
        renderAt('/map/manage');
        await act(async () => {
        });
        expect(screen.getByText(/Could not fetch map subscriptions/)).toBeInTheDocument();
        expect(screen.queryByText(NO_RESULTS)).not.toBeInTheDocument();
    });

    test('empty: shows "No results"', async () => {
        renderAt('/map/manage');
        await act(async () => {
        });
        expect(screen.getByText(NO_RESULTS)).toBeInTheDocument();
    });
});
