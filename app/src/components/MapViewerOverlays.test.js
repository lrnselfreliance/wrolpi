import React from 'react';
import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {renderWithProviders as render} from '../test-utils';
import MapViewer from './MapViewer';
import {STORAGE_KEY_OVERLAYS} from './mapOverlays';

// How the viewer draws the map files it is given: which become the basemap, which are offered as
// overlays in the layer control, and what the control's checkboxes do to the map's layers.

/*
 * MapLibre needs WebGL, which jsdom lacks, so it is mocked down to the surface MapViewer uses.
 * A constructed map keeps the style it was given, and the visibility of each of its layers as
 * `setLayoutProperty` changes it -- the two things these tests read.
 */
const constructed = [];

jest.mock('maplibre-gl', () => {
    class FakeMap {
        constructor(options) {
            this.options = options;
            this.style = options.style;
            constructed.push(this);
        }

        on(event, callback) {
            // MapLibre fires `load` asynchronously once the style resolves.
            if (event === 'load') setTimeout(() => callback(), 0);
            return this;
        }

        once() {
            return this;
        }

        getStyle() {
            return this.style;
        }

        setStyle(style) {
            this.style = style;
        }

        getLayer(id) {
            return this.style.layers.find(l => l.id === id);
        }

        setLayoutProperty(id, name, value) {
            const layer = this.getLayer(id);
            layer.layout = {...layer.layout, [name]: value};
        }

        visibility(id) {
            return this.getLayer(id)?.layout?.visibility ?? 'visible';
        }

        getCanvas() {
            return global.document.createElement('canvas');
        }

        getCenter() {
            return {lat: 0, lng: 0};
        }

        getZoom() {
            return 2;
        }

        setCenter() {
        }

        setZoom() {
        }

        addControl() {
            return this;
        }

        removeControl() {
        }

        remove() {
        }
    }

    class Control {
    }

    return {
        __esModule: true,
        default: {
            Map: FakeMap, addProtocol: jest.fn(), Marker: Control, Popup: Control,
            NavigationControl: Control, FullscreenControl: Control, ScaleControl: Control,
            GeolocateControl: Control,
        },
    };
});
jest.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));
jest.mock('pmtiles', () => ({
    __esModule: true, Protocol: class {
        tile = jest.fn();
    },
}));
// The basemap theme: a layer of each kind the tests care about, for whichever source asks.
jest.mock('protomaps-themes-base', () => ({
    __esModule: true,
    default: (source) => [
        {id: 'earth', type: 'fill', source},
        {id: 'water', type: 'fill', source},
        {id: 'places_locality', type: 'symbol', source},
    ],
}));
jest.mock('@acalcutt/maplibre-contour-pmtiles', () => ({__esModule: true, default: {}}));
jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getMapFiles: jest.fn(),
    getMapPins: jest.fn(),
}));

const api = require('../api');

const mapFile = (map_path, kind, extra = {}) => ({
    name: map_path.split('/').pop(), map_path, path: `map/${map_path}`, kind,
    tile_type: 'mvt', size: 1024, visible: true, vector_layers: [], ...extra,
});
const layer = (id, geometry) => ({id, geometry, minzoom: 0, maxzoom: 8, description: null});

const PLANET = mapFile('20260329.pmtiles', 'basemap', {size: 134e9});
const REGION = mapFile('regions/oregon.pmtiles', 'basemap');
// An overlay with a layer named like one of the basemap's.
const FEATURES = mapFile('extras/features.pmtiles', 'overlay', {
    title: 'Topographic Features', description: 'Topographic features', min_zoom: 0, max_zoom: 8,
    vector_layers: [layer('water', 'Polygon'), layer('power_lines', 'LineString'), layer('towers', 'Point')],
});
const SATELLITE = mapFile('satellite.pmtiles', 'overlay', {tile_type: 'jpeg'});

const WATER = 'overlay:extras/features.pmtiles:water:fill';
const POWER_LINES = 'overlay:extras/features.pmtiles:power_lines:line';
const TOWERS = 'overlay:extras/features.pmtiles:towers:circle';
const RASTER = 'overlay:satellite.pmtiles:raster';

/** Render the viewer with these map files, and open its layer control.  Returns the map. */
const renderViewer = async (files) => {
    api.getMapFiles.mockResolvedValue({files});
    render(<MapViewer/>, {route: '/map'});
    await waitFor(() => expect(constructed).toHaveLength(1));
    // The layer control appears once the map has loaded; it starts collapsed.
    fireEvent.click(await screen.findByTitle('Layers'));
    return constructed[0];
};

const click = async (element) => {
    await act(async () => {
        fireEvent.click(element);
    });
};

beforeEach(() => {
    constructed.length = 0;
    localStorage.clear();
    jest.clearAllMocks();
    api.getMapPins.mockResolvedValue({pins: []});
    // The layer control asks whether this is a narrow screen; the global stub's implementation is
    // reset between tests.
    window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: false, media: query, onchange: null,
        addListener: jest.fn(), removeListener: jest.fn(),
        addEventListener: jest.fn(), removeEventListener: jest.fn(), dispatchEvent: jest.fn(),
    }));
    // The overview blob is only asked for when there is no planet file.
    global.fetch = jest.fn().mockResolvedValue({ok: true});
});

describe('which files the viewer draws', () => {
    test('a planet file is the basemap, and an overlay is drawn with it', async () => {
        const map = await renderViewer([PLANET, REGION, FEATURES]);
        expect(Object.keys(map.style.sources)).toEqual(['20260329.pmtiles', 'overlay:extras/features.pmtiles']);
        // The overlay is drawn as itself, not with the basemap theme.
        expect(map.style.layers.filter(l => l.source === 'overlay:extras/features.pmtiles').map(l => l.id))
            .toEqual([WATER, POWER_LINES, TOWERS]);
    });

    test('files are fetched from where they are, sub-directories included', async () => {
        const map = await renderViewer([REGION, FEATURES]);
        expect(map.style.sources['regions/oregon.pmtiles'].url).toBe('pmtiles:///media/map/regions/oregon.pmtiles');
        expect(map.style.sources['overlay:extras/features.pmtiles'].url)
            .toBe('pmtiles:///media/map/extras/features.pmtiles');
    });

    test('an ignored file is neither drawn nor offered', async () => {
        const map = await renderViewer([{...PLANET, visible: false}, REGION, {...FEATURES, visible: false}, SATELLITE]);
        // Without the planet file the regional basemap (over the overview) is drawn.
        expect(Object.keys(map.style.sources))
            .toEqual(['map-overview', 'regions/oregon.pmtiles', 'overlay:satellite.pmtiles']);
        expect(screen.queryByLabelText('Topographic Features')).not.toBeInTheDocument();
        expect(screen.getByLabelText('satellite')).toBeInTheDocument();
    });

    test('no overlays, no Overlays section', async () => {
        await renderViewer([PLANET]);
        expect(screen.queryByText('Overlays')).not.toBeInTheDocument();
    });
});

describe('an overlay in the layer control', () => {
    test('is named by the file, and starts hidden', async () => {
        const map = await renderViewer([PLANET, FEATURES, SATELLITE]);
        expect(screen.getByText('Overlays')).toBeInTheDocument();
        expect(screen.getByLabelText('Topographic Features')).not.toBeChecked();
        expect(screen.getByLabelText('satellite')).not.toBeChecked();
        expect([WATER, POWER_LINES, TOWERS, RASTER].map(id => map.visibility(id)))
            .toEqual(['none', 'none', 'none', 'none']);
    });

    test('is drawn when it is turned on, and that is remembered', async () => {
        const map = await renderViewer([PLANET, FEATURES, SATELLITE]);
        await click(screen.getByLabelText('Topographic Features'));

        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['visible', 'visible', 'visible']);
        // The other overlay is untouched.
        expect(map.visibility(RASTER)).toBe('none');
        expect(JSON.parse(localStorage.getItem(STORAGE_KEY_OVERLAYS)))
            .toEqual({'extras/features.pmtiles': {enabled: true}});

        await click(screen.getByLabelText('Topographic Features'));
        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['none', 'none', 'none']);
    });

    test('is drawn from the start when it was turned on before', async () => {
        localStorage.setItem(STORAGE_KEY_OVERLAYS, JSON.stringify({
            'extras/features.pmtiles': {enabled: true, layers: {towers: false}},
        }));
        const map = await renderViewer([PLANET, FEATURES]);
        expect(screen.getByLabelText('Topographic Features')).toBeChecked();
        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['visible', 'visible', 'none']);
    });

    test('each layer of a vector file has its own checkbox', async () => {
        const map = await renderViewer([PLANET, FEATURES]);
        await click(screen.getByLabelText('Topographic Features'));
        await click(screen.getByRole('button', {name: 'Show layers of Topographic Features'}));

        await click(screen.getByLabelText('towers'));
        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['visible', 'visible', 'none']);

        await click(screen.getByText('None'));
        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['none', 'none', 'none']);
        expect(screen.getByLabelText('power_lines')).not.toBeChecked();

        await click(screen.getByText('All'));
        expect([WATER, POWER_LINES, TOWERS].map(id => map.visibility(id))).toEqual(['visible', 'visible', 'visible']);
    });

    test('a raster file has no layers to choose from', async () => {
        const map = await renderViewer([PLANET, SATELLITE]);
        expect(screen.queryByRole('button', {name: /layers of satellite/})).not.toBeInTheDocument();
        await click(screen.getByLabelText('satellite'));
        expect(map.visibility(RASTER)).toBe('visible');
    });
});

describe('the basemap layer groups', () => {
    test("do not show or hide an overlay's layer of the same name", async () => {
        const map = await renderViewer([PLANET, FEATURES]);
        await click(screen.getByLabelText('Topographic Features'));
        expect(map.visibility('water')).toBe('visible');
        expect(map.visibility(WATER)).toBe('visible');

        // Hide the basemap's water: the overlay's `water` layer stays.
        await click(screen.getByLabelText('Water'));
        expect(map.visibility('water')).toBe('none');
        expect(map.visibility(WATER)).toBe('visible');

        // Hide the overlay, then show the basemap's water: the overlay's stays hidden.
        await click(screen.getByLabelText('Topographic Features'));
        await click(screen.getByLabelText('Water'));
        expect(map.visibility('water')).toBe('visible');
        expect(map.visibility(WATER)).toBe('none');
    });
});
