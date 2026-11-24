import {WEAPON_CHOICES} from './FalloutPanel';
import {serveFallout} from '../map-shared/fallout/work.js';
import {loadTerrainGrid} from './falloutTerrain';

// No terrain files under Jest, until a test gives a grid.
jest.mock('./falloutTerrain', () => ({loadTerrainGrid: jest.fn(async () => null)}));

// Fallout workers serving their tasks (as fallout.worker.js does) here, as a browser's would on
// another thread: messages arrive later, copied.  `made` are those made since it was emptied.
const made = [];
const copy = (v) => {
    if (v instanceof ArrayBuffer) return v.slice(0);
    if (ArrayBuffer.isView(v)) return v.slice();
    if (Array.isArray(v)) return v.map(copy);
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, copy(x)]));
    return v;
};
function worker({fail = false} = {}) {
    const scope = {postMessage: (data) => setTimeout(() => !w.terminated && w.onmessage?.({data}), 0)};
    serveFallout(scope);
    const w = {
        terminated: false, onmessage: null, onerror: null, given: [], kind: null,
        postMessage(data) {
            if (data.type === 'start') w.kind = data.kind;
            if (data.type === 'task') w.given.push(data.k);
            const copied = copy(data);
            setTimeout(() => {
                if (w.terminated) return;
                if (fail && data.type === 'task') w.onerror?.({message: 'No such script'});
                else scope.onmessage({data: copied});
            }, 0);
        },
        terminate() {
            w.terminated = true;
        },
    };
    made.push(w);
    return w;
}

describe('the fallout panel\'s weapons', () => {
    test('are grouped by country, then a yield of one\'s own', () => {
        const groups = WEAPON_CHOICES.map((g) => g.group);
        expect(groups[0]).toBe('United States');
        expect(groups).toContain('Russia');
        expect(groups).toContain('Improvised nuclear device');
        expect(groups[groups.length - 1]).toBe('Other');
        expect(WEAPON_CHOICES[groups.length - 1].items.map((i) => i.value)).toEqual(['custom']);
    });

    test('each read differently, by name and yield', () => {
        const labels = WEAPON_CHOICES.flatMap((g) => g.items.map((i) => i.label));
        expect(new Set(labels).size).toBe(labels.length);
        expect(labels).toContain('B61-12 bomb, 0.3 kt, half fission');
    });

    test('say their yield', () => {
        const w88 = WEAPON_CHOICES[0].items.find((i) => i.value === 'w88');
        expect(w88.label).toBe('W88 (Trident II D5), 455 kt, half fission');
    });
});

describe('the fallout panel\'s winds', () => {
    const {windProfile, hourLabel} = require('./FalloutPanel');

    test('fall back to one wind at every height until there is a forecast', () => {
        const profile = windProfile({wind: 'forecast', direction: 270, speed: 10});
        expect(profile).toHaveLength(1);
        expect(profile[0][1]).toBeGreaterThan(0);
    });

    test('mark the hour nearest now', () => {
        expect(hourLabel('2026-11-22T00:00Z', true)).toMatch(/\(now\)$/);
        expect(hourLabel('2026-11-22T00:00Z', false)).not.toMatch(/now/);
    });
});

describe('the fallout of several bursts', () => {
    const {simulateBursts} = require('./FalloutPanel');
    const {prepareField} = require('../map-shared/fallout/winds.js');
    const winds = {profile: [[0, 10, 0]]};
    const bursts = [
        {lat: 40, lon: -105, yieldKt: 10, fissionFraction: 0.5},
        {lat: 40.5, lon: -104, yieldKt: 100, fissionFraction: 0.5},
    ];

    // A forecast over 39-42 N, 106-103 W, every degree, whose wind turns from the west to the
    // south-west over the hours, on ground rising to the east.
    const HOURS = ['2026-11-22T00:00Z', '2026-11-22T01:00Z', '2026-11-22T02:00Z'];
    function forecast() {
        const points = [];
        for (const lat of [39, 40, 41, 42]) for (const lon of [-106, -105, -104, -103]) points.push({lat, lon, elevation: 1500 + (lon + 106) * 100});
        return {
            source: 'Open-Meteo', fetched_at: '2026-11-22T00:30:00+00:00', spacing: 1, points, hours: HOURS,
            winds: points.map(() => HOURS.map((_, h) => [[10, 12, 270 - 20 * h], [20000, 30, 260 - 20 * h]])),
            rain: points.map(() => HOURS.map(() => 0)),
        };
    }
    const fieldWinds = () => ({prepared: prepareField(forecast()), startMs: Date.parse(HOURS[0])});

    test('carries each burst by the winds where it is, from the ground there', async () => {
        const ran = await simulateBursts(bursts, {winds: fieldWinds(), useTerrain: false});
        expect(ran.grid.values.some((v) => v > 0)).toBe(true);
        // Not as one wind would carry them.
        const one = await simulateBursts(bursts, {winds, useTerrain: false});
        expect(ran.grid.values.length === one.grid.values.length
            && ran.grid.values.every((v, i) => v === one.grid.values[i])).toBe(false);
    });

    test('is drawn on one grid around the first burst', async () => {
        const one = await simulateBursts(bursts.slice(0, 1), {winds, useTerrain: false});
        const both = await simulateBursts(bursts, {winds, useTerrain: false});
        expect(both.origin).toBe(bursts[0]);
        const sum = (g) => g.values.reduce((a, v) => a + v, 0) * g.cell ** 2;
        expect(sum(both.grid)).toBeGreaterThan(sum(one.grid) * 5);
        expect(both.terrainStatus).toMatch(/terrain is off/);
    });

    test('stops when it is no longer wanted', async () => {
        expect(await simulateBursts(bursts, {winds, useTerrain: false, cancelled: () => true})).toBeNull();
    });

    const MANY = Array.from({length: 7}, (_, i) => ({lat: 40 + 0.2 * i, lon: -105 + 0.3 * i, yieldKt: 5 * (i + 1), fissionFraction: 0.5}));
    // Whether two results have the same grid (said quickly: Jest's diff of such arrays takes minutes).
    const same = (a, b) => a.grid.cell === b.grid.cell && a.grid.values.length === b.grid.values.length
        && a.grid.values.every((v, i) => v === b.grid.values[i]);

    test('spreads the bursts over workers, as the page calculates them', async () => {
        for (const w of [winds, fieldWinds()]) {
            made.length = 0;
            const here = await simulateBursts(MANY, {winds: w, useTerrain: false});
            const heard = [];
            const spread = await simulateBursts(MANY, {winds: w, useTerrain: false, workers: 3, makeWorker: () => worker(),
                onProgress: (done, total) => heard.push([done, total])});
            // The bursts by three workers, then the grid's parts by three more.
            const burstWorkers = made.filter((x) => x.kind === 'bursts');
            const gridWorkers = made.filter((x) => x.kind === 'grid');
            expect(burstWorkers).toHaveLength(3);
            expect(gridWorkers).toHaveLength(3);
            expect(burstWorkers.flatMap((x) => x.given).sort()).toEqual([0, 1, 2, 3, 4, 5, 6]);
            expect(gridWorkers.flatMap((x) => x.given).length).toBeGreaterThan(3);
            expect(made.every((x) => x.given.length > 0 && x.terminated)).toBe(true);
            expect(heard[heard.length - 1]).toEqual([7, 7]);
            expect(same(spread, here)).toBe(true);
            expect(JSON.stringify(spread.spots) === JSON.stringify(here.spots)).toBe(true);
        }
    });

    test('gives its workers the terrain, when it is read', async () => {
        // Ground rising to the north-east of the bursts.
        const nx = 81, ny = 81, step = 0.05;
        const grid = {west: -107, south: 38, step, nx, ny, values: new Float32Array(nx * ny)};
        for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) grid.values[j * nx + i] = 1500 + 40 * (i + j);
        loadTerrainGrid.mockImplementation(async () => ({grid, zoom: 9, coverage: 1}));
        try {
            const flat = await simulateBursts(MANY, {winds: fieldWinds(), useTerrain: false});
            const here = await simulateBursts(MANY, {winds: fieldWinds(), useTerrain: true});
            made.length = 0;
            const heard = [];
            const spread = await simulateBursts(MANY, {winds: fieldWinds(), useTerrain: true, workers: 2,
                makeWorker: () => worker(), onProgress: (done, total) => heard.push([done, total])});
            expect(here.terrainStatus).toMatch(/Follows the terrain/);
            expect(same(here, flat)).toBe(false);
            expect(same(spread, here)).toBe(true);
            // A pass on flat ground, then another over the terrain, each by its own workers.
            expect(made.map((x) => x.kind)).toEqual(['bursts', 'bursts', 'grid', 'grid', 'bursts', 'bursts', 'grid', 'grid']);
            expect(heard[heard.length - 1]).toEqual([14, 14]);
        } finally {
            loadTerrainGrid.mockImplementation(async () => null);
        }
    });

    test('stops its workers at once when cancelled', async () => {
        made.length = 0;
        const controller = new AbortController();
        const running = simulateBursts(MANY, {winds, useTerrain: false, workers: 3, makeWorker: () => worker(),
            signal: controller.signal});
        controller.abort();
        expect(await running).toBeNull();
        expect(made).toHaveLength(3);
        expect(made.every((x) => x.terminated)).toBe(true);
    });

    test('calculates on the page when its workers fail, or there are none', async () => {
        made.length = 0;
        const error = jest.spyOn(console, 'error').mockImplementation(() => null);
        const here = await simulateBursts(MANY, {winds, useTerrain: false});
        const ran = await simulateBursts(MANY, {winds, useTerrain: false, workers: 2, makeWorker: () => worker({fail: true})});
        expect(error).toHaveBeenCalled();
        error.mockRestore();
        expect(made.every((x) => x.terminated)).toBe(true);
        expect(same(ran, here)).toBe(true);
        const none = await simulateBursts(MANY, {winds, useTerrain: false, workers: 2, makeWorker: () => null});
        expect(same(none, here)).toBe(true);
    });
});

describe('the fallout image', () => {
    const {imageRows} = require('./FalloutPanel');

    test('takes each row from the grid row at its own latitude', () => {
        // A grid from 20 to 80 degrees north, around 40: a tenth of a degree a row.
        const grid = {y0: -20 * 111320, cell: 11132, ny: 600, nx: 1};
        const rows = imageRows(grid, 40, 600);
        // The top row is the grid's northernmost, the bottom its southernmost.
        expect(rows[0]).toBe(599);
        expect(rows[599]).toBe(0);
        // Halfway down the image, in Web Mercator, is well north of halfway in latitude (50 degrees).
        expect(rows[300]).toBeGreaterThan(330);
        for (let r = 1; r < 600; r++) expect(rows[r]).toBeLessThanOrEqual(rows[r - 1]);
    });

    test('is the plain grid over a small area', () => {
        const grid = {y0: -5000, cell: 100, ny: 100, nx: 1};
        const rows = imageRows(grid, 40, 100);
        expect(rows[0]).toBe(99);
        expect(Math.abs(rows[50] - 49)).toBeLessThanOrEqual(1);
    });
});

describe('the fallout timeline', () => {
    const {screen, fireEvent} = require('@testing-library/react');
    const {renderWithProviders} = require('../test-utils');
    const {Timeline} = require('./FalloutPanel');

    test('says what it shows, and moves and plays the hours', () => {
        const onAfter = jest.fn(), onPlaying = jest.fn();
        const {unmount} = renderWithProviders(<Timeline after={0} onAfter={onAfter} playing={false}
                                                        onPlaying={onPlaying} startMs={null}/>);
        expect(screen.getByText(/All the fallout, as at H\+1/)).toBeTruthy();
        fireEvent.change(screen.getByLabelText('Hours after the bursts'), {target: {value: '6'}});
        expect(onAfter).toHaveBeenCalledWith(6);
        fireEvent.click(screen.getByLabelText('Play'));
        expect(onPlaying).toHaveBeenCalledWith(true);

        unmount();
        renderWithProviders(<Timeline after={6} onAfter={onAfter} playing={true} onPlaying={onPlaying}
                                      startMs={Date.parse('2026-11-22T00:00Z')}/>);
        expect(screen.getByText(/^H\+6, .*: the fallout landed by then$/)).toBeTruthy();
        fireEvent.click(screen.getByLabelText('Pause'));
        expect(onPlaying).toHaveBeenLastCalledWith(false);
    });
});

describe('the total dose view', () => {
    const {TOTAL_BANDS, DOSE_BANDS, legendHeading, legendText} = require('./FalloutPanel');

    test('has its own bands, each saying what it does to a person', () => {
        expect(TOTAL_BANDS.map((b) => b.rate)).toEqual([1000, 450, 100, 25, 5]);
        for (const b of TOTAL_BANDS) expect(b.meaning.length).toBeGreaterThan(5);
        // The same colors, highest first.
        expect(TOTAL_BANDS.map((b) => b.color)).toEqual(DOSE_BANDS.map((b) => b.color));
    });

    test('says what is shown, by the hour', () => {
        expect(legendHeading('total', 0)).toBe('Total dose in the first two weeks');
        expect(legendHeading('total', 6)).toBe('Total dose by 6 hours after the bursts');
        expect(legendHeading('rate', 0)).toBe('Dose rate, as at 1 hour after the bursts');
        expect(legendHeading('rate', 1)).toBe('Dose rate 1 hour after the bursts');
        expect(legendText('total', 0)).toMatch(/outdoors the whole time/);
        expect(legendText('rate', 3)).toMatch(/landed by then/);
    });

    test('labels the timeline as a dose', () => {
        const {screen} = require('@testing-library/react');
        const {renderWithProviders} = require('../test-utils');
        const {Timeline} = require('./FalloutPanel');
        renderWithProviders(<Timeline show="total" after={0} onAfter={() => null} playing={false}
                                      onPlaying={() => null} startMs={null}/>);
        expect(screen.getByText(/The first two weeks/)).toBeTruthy();
    });
});

describe('the fallout of past days', () => {
    const {simulateClimate, CLIMATE_BANDS} = require('./FalloutPanel');
    const {parseClimatology} = require('../map-shared/fallout/climatology.js');

    // Days on a coarse grid (lat 90..-90 every 30, lon 0..330 every 30), each one wind [east, north].
    function climate(days) {
        const header = {version: 1, levels_hpa: [1000, 500], lat: [90, -30, 7], lon: [0, 30, 12],
            days: days.map((_, k) => `200${k}-05-01`)};
        const head = new TextEncoder().encode(JSON.stringify(header));
        const size = 2 * 7 * 12;
        const bytes = new Uint8Array(10 + head.length + 2 * size + days.length * 2 * size);
        bytes.set([87, 70, 67, 76], 0);
        const view = new DataView(bytes.buffer);
        view.setUint16(4, 1, true);
        view.setUint32(6, head.length, true);
        bytes.set(head, 10);
        let at = 10 + head.length;
        for (let c = 0; c < size; c++) view.setInt16(at + 2 * c, c < size / 2 ? 100 : 5500, true);
        at += 2 * size;
        for (const [e, n] of days) {
            for (let c = 0; c < size; c++) view.setInt8(at + c, e);
            for (let c = 0; c < size; c++) view.setInt8(at + size + c, n);
            at += 2 * size;
        }
        return parseClimatology(bytes);
    }

    test('counts the days each place was reached, for all the bursts at once', async () => {
        const bursts = [{lat: 30, lon: -120, yieldKt: 10, fissionFraction: 1}, {lat: 31, lon: -118, yieldKt: 10, fissionFraction: 1}];
        const heard = [];
        const ran = await simulateClimate(bursts, climate([[10, 0], [10, 0], [0, 10]]),
            {rate: 1, onProgress: (done, total) => heard.push([done, total])});
        expect(ran.origin).toBe(bursts[0]);
        expect(ran.grid.days).toBe(3);
        const most = ran.grid.values.reduce((a, v) => Math.max(a, v), 0);
        expect(most).toBeGreaterThan(0.3);
        expect(most).toBeLessThanOrEqual(1);
        expect(heard[heard.length - 1]).toEqual([6, 6]);
        // The bands go from most days to any.
        expect(CLIMATE_BANDS.map((b) => b.rate)).toEqual([...CLIMATE_BANDS.map((b) => b.rate)].sort((a, b) => b - a));
    });

    test('stops when cancelled', async () => {
        const bursts = [{lat: 30, lon: -120, yieldKt: 10, fissionFraction: 1}];
        expect(await simulateClimate(bursts, climate([[10, 0], [0, 10]]), {cancelled: () => true})).toBeNull();
    });

    const BURSTS = [{lat: 30, lon: -120, yieldKt: 10, fissionFraction: 1}, {lat: 31, lon: -118, yieldKt: 10, fissionFraction: 1}];
    const DAYS = [[10, 0], [10, 0], [0, 10], [-8, 4], [3, -9]];

    test('spreads the days over workers, and counts them as the page does', async () => {
        made.length = 0;
        const clim = climate(DAYS);
        const here = await simulateClimate(BURSTS, clim, {rate: 1});
        const heard = [];
        const spread = await simulateClimate(BURSTS, clim, {rate: 1, workers: 2, makeWorker: () => worker(),
            onProgress: (done, total) => heard.push([done, total])});
        expect(made).toHaveLength(2);
        // Every day given once, to one worker or the other, and both given some.
        expect(made.flatMap((w) => w.given).sort()).toEqual([0, 1, 2, 3, 4]);
        expect(made.every((w) => w.given.length > 0)).toBe(true);
        expect(made.every((w) => w.terminated)).toBe(true);
        expect(heard[heard.length - 1]).toEqual([10, 10]);
        expect(spread.grid.days).toBe(5);
        expect(spread.grid.cell).toBe(here.grid.cell);
        expect(Array.from(spread.grid.values)).toEqual(Array.from(here.grid.values));
    });

    test('stops its workers at once when cancelled', async () => {
        made.length = 0;
        const controller = new AbortController();
        const running = simulateClimate(BURSTS, climate(DAYS), {rate: 1, workers: 3, makeWorker: () => worker(),
            signal: controller.signal});
        controller.abort();
        expect(await running).toBeNull();
        expect(made).toHaveLength(3);
        expect(made.every((w) => w.terminated)).toBe(true);
    });

    test('calculates on the page when its workers fail', async () => {
        made.length = 0;
        const error = jest.spyOn(console, 'error').mockImplementation(() => null);
        const clim = climate(DAYS);
        const here = await simulateClimate(BURSTS, clim, {rate: 1});
        const ran = await simulateClimate(BURSTS, clim, {rate: 1, workers: 2, makeWorker: () => worker({fail: true})});
        expect(error).toHaveBeenCalled();
        error.mockRestore();
        expect(made.every((w) => w.terminated)).toBe(true);
        expect(Array.from(ran.grid.values)).toEqual(Array.from(here.grid.values));
        // And where there are none to be had.
        const none = await simulateClimate(BURSTS, clim, {rate: 1, workers: 2, makeWorker: () => null});
        expect(Array.from(none.grid.values)).toEqual(Array.from(here.grid.values));
    });
});


describe('the fallout panel\'s progress', () => {
    const {screen} = require('@testing-library/react');
    const {renderWithProviders} = require('../test-utils');
    const {FalloutProgress} = require('./FalloutPanel');

    test('is a bar filled as far as the bursts are calculated', () => {
        const {unmount} = renderWithProviders(<FalloutProgress busy={true} progress={{done: 1170, total: 4680}}/>);
        const bar = screen.getByRole('progressbar');
        expect(bar.getAttribute('aria-valuenow')).toBe('25');
        expect(screen.getByText('Calculating 1,170 of 4,680')).toBeTruthy();
        unmount();
    });

    test('has a button which cancels the calculation', () => {
        const {fireEvent} = require('@testing-library/react');
        const onCancel = jest.fn();
        const {unmount} = renderWithProviders(<FalloutProgress busy={true} progress={{done: 1, total: 2}} onCancel={onCancel}/>);
        fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
        expect(onCancel).toHaveBeenCalledTimes(1);
        unmount();
    });

    test('moves without a count until there is one, and is gone when done', () => {
        const {rerender, unmount} = renderWithProviders(<FalloutProgress busy={true} progress={null}/>);
        expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBeNull();
        expect(screen.getByText('Calculating…')).toBeTruthy();
        rerender(<FalloutProgress busy={false} progress={null}/>);
        expect(screen.queryByRole('progressbar')).toBeNull();
        unmount();
    });
});
