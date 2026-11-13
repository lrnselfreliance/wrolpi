import React from 'react';
import {act, fireEvent, screen} from '@testing-library/react';
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
    setMapFileVisible: jest.fn(),
    rebuildMapSearchIndex: jest.fn(),
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

    test('a pin opens the Solar calculator at its location', async () => {
        api.getMapPins.mockResolvedValue({pins: [{id: 1, lat: 40.12346, lon: -111.2, label: 'Camp', color: '#f00'}]});
        renderAt('/map/pins');
        await act(async () => {
        });
        fireEvent.click(screen.getAllByRole('button', {name: 'Solar estimate for Camp'})[0]);
        expect(window.location.pathname).toBe('/more/calculators');
        expect(window.location.search).toBe('?calc=solar&lat=40.1235&lon=-111.2');
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

    // The "View All Regions" preview draws the catalog; a pending or failed catalog must not be
    // previewed as zero regions.
    test('pending: the regions preview is disabled', async () => {
        api.fetchMapSubscriptions.mockReturnValue(pending());
        renderAt('/map/manage');
        await act(async () => {
        });
        expect(screen.getByRole('button', {name: 'View All Regions'})).toBeDisabled();
    });

    test('failed: the regions preview is disabled', async () => {
        api.fetchMapSubscriptions.mockResolvedValue(undefined);
        renderAt('/map/manage');
        await act(async () => {
        });
        expect(screen.getByRole('button', {name: 'View All Regions'})).toBeDisabled();
    });

    test('loaded: the regions preview is enabled', async () => {
        renderAt('/map/manage');
        await act(async () => {
        });
        expect(screen.getByRole('button', {name: 'View All Regions'})).toBeEnabled();
    });
});

describe('the Manage tab files table', () => {
    const mapFile = (map_path, kind, extra = {}) => ({
        name: map_path.split('/').pop(), map_path, path: `map/${map_path}`, kind,
        size: 1024, visible: true, has_search_index: false, title: null, ...extra,
    });
    const FILES = [
        mapFile('us-west.pmtiles', 'basemap', {title: 'Protomaps Basemap'}),
        mapFile('extras/features.pmtiles', 'overlay', {title: 'Topographic Features'}),
        mapFile('terrain-planet.pmtiles', 'terrain'),
        mapFile('broken.pmtiles', 'unknown'),
    ];
    const rowOf = (text) => screen.getByText(text).closest('tr');
    const cellsOf = (text) => [...rowOf(text).querySelectorAll('td')].map(td => td.textContent);

    const renderFiles = async (files = FILES) => {
        api.getMapFiles.mockResolvedValue({files});
        renderAt('/map/manage');
        await act(async () => {
        });
    };

    test('a file is listed with its directory, its own name, and how the map draws it', async () => {
        await renderFiles();
        expect(cellsOf('extras/features.pmtiles').slice(0, 2))
            .toEqual(['extras/features.pmtilesTopographic Features', 'Overlay']);
        expect(cellsOf('us-west.pmtiles')[1]).toBe('Basemap');
        expect(cellsOf('terrain-planet.pmtiles')[1]).toBe('Terrain');
        expect(cellsOf('broken.pmtiles')[1]).toBe('Unreadable');
    });

    test('only a basemap offers a search index', async () => {
        await renderFiles();
        const builds = screen.getAllByRole('button', {name: 'Build'});
        expect(builds).toHaveLength(1);
        expect(rowOf('us-west.pmtiles')).toContainElement(builds[0]);
    });

    test('the search index of a file in a sub-directory is built by its path', async () => {
        await renderFiles([mapFile('regions/oregon.pmtiles', 'basemap')]);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: 'Build'}));
        });
        expect(api.rebuildMapSearchIndex).toHaveBeenCalledWith('regions/oregon.pmtiles');
    });

    test('a file is ignored with its toggle, and the list is fetched again', async () => {
        await renderFiles();
        const toggle = screen.getByRole('switch', {name: 'Show extras/features.pmtiles on the map'});
        expect(toggle).toBeChecked();

        api.getMapFiles.mockResolvedValue({
            files: FILES.map(f => f.kind === 'overlay' ? {...f, visible: false} : f),
        });
        const before = api.getMapFiles.mock.calls.length;
        await act(async () => {
            fireEvent.click(toggle);
        });

        expect(api.setMapFileVisible).toHaveBeenCalledWith('extras/features.pmtiles', false);
        expect(api.getMapFiles.mock.calls.length).toBe(before + 1);
        // Only the ignored file's toggle is off.
        expect(screen.getByRole('switch', {name: 'Show extras/features.pmtiles on the map'})).not.toBeChecked();
        expect(screen.getByRole('switch', {name: 'Show us-west.pmtiles on the map'})).toBeChecked();
    });

    test('an ignored file is shown again with its toggle', async () => {
        await renderFiles([mapFile('satellite.pmtiles', 'overlay', {visible: false})]);
        const toggle = screen.getByRole('switch', {name: 'Show satellite.pmtiles on the map'});
        expect(toggle).not.toBeChecked();
        await act(async () => {
            fireEvent.click(toggle);
        });
        expect(api.setMapFileVisible).toHaveBeenCalledWith('satellite.pmtiles', true);
    });
});
