/**
 * The map preview modals must actually build a map.
 *
 * `RegionPreviewModal` (the eye button on a catalog row) and `AllRegionsPreviewModal` (the
 * "View All Regions" button) each render a `<div>` into a Modal and hand it to MapLibre.  They
 * did that by reading a `useRef` inside an effect gated on `open`:
 *
 *     React.useEffect(() => {
 *         if (!open || !mapContainer.current) return;   // <-- ref is null here
 *
 * Mantine's Modal mounts its body one commit AFTER `opened` flips true, so on the render that
 * opens the modal the ref is still null, the effect returns, and -- because neither `open` nor
 * the other deps change again -- it never runs a second time.  The div sits in the DOM, empty,
 * with no console error and no rejected promise to point at any of this.
 *
 * It worked before the Mantine migration because Semantic UI's Portal put the modal body in
 * the DOM in the same commit that opened it, so the ref was attached by the time effects ran.
 * The effect bodies are byte-identical across that change; the modal library is the only
 * variable.  Confirmed on hardware still running the older build, where both previews render.
 *
 * So these tests assert the outcome -- a map got constructed against a node that is really in
 * the document -- rather than the mechanism, which is the part that quietly changed under it.
 */
import React from 'react';
import {act, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Route, Routes} from 'react-router';
import {renderWithProviders as render} from '../test-utils';
import {MapRoute} from './Map';

/*
 * MapLibre cannot run in jsdom -- it wants WebGL -- so it is mocked down to the surface Map.js
 * uses.  Every constructed map records the container it was given, which is the whole claim.
 */
const constructed = [];

jest.mock('maplibre-gl', () => {
    class FakeMap {
        constructor(options) {
            this.options = options;
            this.container = options.container;
            this.handlers = {};
            // Recorded on the instance rather than watched with a spy installed after the
            // fact: a spy attached post-construction misses whatever the real `load` already
            // drew, which is the only thing worth asserting about.
            this.sources = [];
            constructed.push(this);
        }

        on(event, callback) {
            this.handlers[event] = callback;
            // MapLibre fires `load` asynchronously once the style resolves.
            if (event === 'load') setTimeout(() => callback(), 0);
            return this;
        }

        addSource(id) {
            this.sources.push(id);
            return this;
        }

        addLayer() {
            return this;
        }

        addControl() {
            return this;
        }

        fitBounds() {
            return this;
        }

        remove() {
            this.removed = true;
        }
    }

    return {__esModule: true, default: {Map: FakeMap, addProtocol: jest.fn(), Marker: FakeMap}};
});

jest.mock('pmtiles', () => ({
    __esModule: true,
    Protocol: class {
        tile = jest.fn();
    },
}));

// The real one returns the full protomaps layer list; nothing here depends on its contents.
jest.mock('protomaps-themes-base', () => ({__esModule: true, default: () => []}));

// Map.js imports the viewer, which pulls in the contour worker.  The previews do not use it.
jest.mock('./MapViewer', () => ({__esModule: true, default: () => null}));

const CATALOG = [
    {name: 'United States (West)', region: 'us-west', bbox: '-125.0,24.4,-104.0,49.4', size_estimate: 5e9},
    {name: 'Alaska', region: 'us-alaska', bbox: '-180.0,51.0,-129.0,72.0', size_estimate: 1.3e9},
    // A region with no bbox, as the terrain subscription really is -- it must not be drawn,
    // and must not throw while the others are.
    {name: 'Terrain (Global Hillshade & Contours)', region: 'terrain', bbox: null, size_estimate: 12e9},
];

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getMapFiles: jest.fn(),
    fetchMapSubscriptions: jest.fn(),
    getMapPins: jest.fn(),
    deleteMapFile: jest.fn(),
    deleteMapPin: jest.fn(),
    updateMapPin: jest.fn(),
    mapSubscribe: jest.fn(),
    mapUnsubscribe: jest.fn(),
    rebuildMapSearchIndex: jest.fn(),
}));

const api = require('../api');

/** Render the Manage tab with a catalog and the given map files. */
const renderManage = async ({files = []} = {}) => {
    api.getMapFiles.mockResolvedValue({files});
    api.fetchMapSubscriptions.mockResolvedValue({catalog: CATALOG, subscriptions: []});
    api.getMapPins.mockResolvedValue({pins: []});
    /*
     * Mounted under `/map/*` as App.js does, not bare.  MapRoute's own `<Route path='manage'>`
     * is relative, so rendering it at the root resolves that to `/manage` and the Manage tab
     * never matches -- the page renders its tab bar and nothing else.
     */
    const result = render(
        <Routes><Route path='/map/*' element={<MapRoute/>}/></Routes>,
        {route: '/map/manage'},
    );
    /*
     * Wait on a catalog row, not on the "View All Regions" button.  That button renders as
     * soon as the file list arrives, which is a separate request from the catalog -- waiting
     * on it let a test reach the eye buttons before the rows existed.
     */
    await screen.findByRole('button', {name: 'View All Regions'});
    await screen.findByRole('button', {name: 'Preview Alaska'});
    return result;
};

beforeEach(() => {
    constructed.length = 0;
    jest.clearAllMocks();
});

describe('the "View All Regions" preview', () => {
    it('renders the button at all', async () => {
        // The premise.  Everything below waits on a click, and a test that could not find the
        // button would fail for a reason that has nothing to do with the map.
        await renderManage();
        expect(screen.getByRole('button', {name: 'View All Regions'})).toBeInTheDocument();
    });

    it('builds a map when opened', async () => {
        await renderManage();
        expect(constructed).toHaveLength(0);

        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));

        // This is the assertion that fails on the original code: the modal opens, the div is
        // rendered, and no map is ever constructed against it.
        await waitFor(() => expect(constructed).toHaveLength(1));
    });

    it('builds the map against a node that is in the document', async () => {
        /*
         * Not merely "a map was constructed".  A fix that passed a detached node -- one held
         * from a previous render, say -- would satisfy the test above and still draw nothing a
         * user can see, which is the failure being guarded against.
         */
        await renderManage();
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));

        await waitFor(() => expect(constructed).toHaveLength(1));
        const {container} = constructed[0];
        expect(container).toBeInstanceOf(HTMLElement);
        expect(document.body.contains(container)).toBe(true);
    });

    it('draws a source for every region that has a bbox, and only those', async () => {
        /*
         * The component's own `load` handler does the drawing -- FakeMap fires it as MapLibre
         * does, and nothing here fires it a second time.  An earlier version spied on
         * `addSource` after construction and then re-invoked `load` by hand, which meant the
         * count came entirely from that manual call and said nothing about the real path.
         */
        await renderManage();
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));
        await waitFor(() => expect(constructed).toHaveLength(1));

        const withBbox = CATALOG.filter(r => r.bbox);
        expect(withBbox.length).toBeLessThan(CATALOG.length);  // the premise: one has no bbox

        const map = constructed[0];
        await waitFor(() => expect(map.sources).toHaveLength(withBbox.length));
        // Exactly once each, in catalog order -- a handler that ran twice would double these.
        expect(map.sources).toEqual(withBbox.map((_, i) => `region-${i}`));
    });
});

describe('a single region preview', () => {
    it('builds a map when the eye button is clicked', async () => {
        await renderManage();
        expect(constructed).toHaveLength(0);

        await userEvent.click(screen.getByRole('button', {name: 'Preview Alaska'}));

        await waitFor(() => expect(constructed).toHaveLength(1));
        expect(document.body.contains(constructed[0].container)).toBe(true);
    });
});

describe('the basemap source', () => {
    it("uses the user's planet file when they have one", async () => {
        await renderManage({files: [{name: '20260329.pmtiles', size: 134e9}]});
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));
        await waitFor(() => expect(constructed).toHaveLength(1));

        const {sources} = constructed[0].options.style;
        expect(sources.basemap.url).toBe('pmtiles:///media/map/20260329.pmtiles');
    });

    it('falls back to the overview blob when there is no planet file', async () => {
        await renderManage({files: [{name: 'us-west-20260329.pmtiles', size: 5e9}]});
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));
        await waitFor(() => expect(constructed).toHaveLength(1));

        const {sources} = constructed[0].options.style;
        expect(sources.basemap.url).toBe('pmtiles:///blobs/map-overview.pmtiles');
    });
});

describe('closing a preview', () => {
    it('removes the map', async () => {
        /*
         * MapLibre holds a WebGL context; the browser caps how many may exist at once, so a
         * preview that leaks one on every open eventually takes the whole page's maps down.
         */
        await renderManage();
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));
        await waitFor(() => expect(constructed).toHaveLength(1));

        // Escape rather than the close control: Mantine's close button carries no accessible
        // name of its own, so a query for it is a query for markup rather than for behavior.
        await userEvent.keyboard('{Escape}');

        await waitFor(() => expect(constructed[0].removed).toBe(true));
    });


    /*
     * The two below are a matched pair, and neither means anything alone.
     *
     * A first attempt at the cancel test closed the modal immediately after the click and
     * passed with the `cancelled` guard deleted -- because Mantine had not mounted the modal
     * body yet, so the effect had never run and there was nothing to cancel.  It asserted that
     * nothing happened in a test where nothing could have happened.  The control is what makes
     * the cancel test falsifiable: it proves this exact setup DOES build a map when the modal
     * stays open, so a zero in the other test is the flag working rather than the harness
     * never having started.
     */
    const openWithHeldSource = async () => {
        let releaseFiles;
        const before = api.getMapFiles.mock.calls.length;
        api.getMapFiles.mockReturnValue(new Promise(resolve => {
            releaseFiles = resolve;
        }));
        await userEvent.click(screen.getByRole('button', {name: 'View All Regions'}));
        // Wait for the effect to actually reach the source lookup.  Waiting on the click alone
        // is too early: the modal body mounts a commit later, which is the whole bug this file
        // exists for.
        await waitFor(() => expect(api.getMapFiles.mock.calls.length).toBe(before + 1));
        expect(constructed).toHaveLength(0);  // in flight, nothing built yet
        return releaseFiles;
    };

    it('builds the map when the held source resolves while still open', async () => {
        // The control.  See the note above.
        await renderManage();
        const releaseFiles = await openWithHeldSource();

        await act(async () => {
            releaseFiles({files: []});
        });

        expect(constructed).toHaveLength(1);
    });

    it('builds no map when closed before the source resolves', async () => {
        /*
         * The race the `cancelled` flag exists for, and the one "removes the map" does NOT
         * cover: that one waits for the map before closing, so cleanup always finds a map to
         * remove.  Here cleanup runs while `map` is still undefined; without the flag the
         * promise then resolves and builds a map nothing will ever remove -- a WebGL context
         * leaked on every quick open-and-close.
         */
        await renderManage();
        const releaseFiles = await openWithHeldSource();

        await userEvent.keyboard('{Escape}');
        await act(async () => {
            releaseFiles({files: []});
        });

        expect(constructed).toHaveLength(0);
    });
});
