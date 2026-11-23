import {WEAPON_CHOICES} from './FalloutPanel';

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
    const profileFor = () => [[0, 10, 0]];
    const bursts = [
        {lat: 40, lon: -105, yieldKt: 10, fissionFraction: 0.5},
        {lat: 40.5, lon: -104, yieldKt: 100, fissionFraction: 0.5},
    ];

    test('carries each burst by its own winds, from its own ground', async () => {
        const asked = [];
        const windsFor = (b, ground) => {
            asked.push([b.lat, ground]);
            return {profile: [[0, 10, 0]]};
        };
        const result = await simulateBursts(bursts, {windsFor, groundOf: (b) => b.lat * 10, useTerrain: false});
        expect(asked).toEqual([[40, 400], [40.5, 405]]);
        expect(result.grid.values.some((v) => v > 0)).toBe(true);
    });

    test('is drawn on one grid around the first burst', async () => {
        const one = await simulateBursts(bursts.slice(0, 1), {profileFor, useTerrain: false});
        const both = await simulateBursts(bursts, {profileFor, useTerrain: false});
        expect(both.origin).toBe(bursts[0]);
        const sum = (g) => g.values.reduce((a, v) => a + v, 0) * g.cell ** 2;
        expect(sum(both.grid)).toBeGreaterThan(sum(one.grid) * 5);
        expect(both.terrainStatus).toMatch(/terrain is off/);
    });

    test('stops when it is no longer wanted', async () => {
        expect(await simulateBursts(bursts, {profileFor, useTerrain: false, cancelled: () => true})).toBeNull();
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
});

