import fs from "fs";
import path from "path";
import {decodeClimatology, lookupClimatology} from "./solarData";
import {estimateProduction} from "./solar";
import {encodeClimatology, uniformClimatology} from "./solarData.fixtures";

describe('decodeClimatology', () => {
    test('accepts a valid file', () => {
        expect(decodeClimatology(uniformClimatology()).length).toBe(4 * 12 * 180 * 360);
    });

    test('rejects a file that is not ours, a newer version, or truncated', () => {
        const good = new Uint8Array(uniformClimatology());
        const wrongMagic = good.slice();
        wrongMagic[0] = 'X'.charCodeAt(0);
        expect(() => decodeClimatology(wrongMagic.buffer)).toThrow('Not a solar climatology file');

        const newer = good.slice();
        newer[4] = 2;
        expect(() => decodeClimatology(newer.buffer)).toThrow('Unsupported');

        expect(() => decodeClimatology(good.slice(0, 1000).buffer)).toThrow('truncated');
    });
});

describe('lookupClimatology', () => {
    // A field that varies with longitude, so interpolation is visible: GHI = 3 + lon/100.
    const sloped = decodeClimatology(encodeClimatology((key, month, lat, lon) => ({
        ghi: 3 + lon / 100,
        diffuse: 1,
        albedo: lat > 60 ? 0.8 : 0.2,
        temperature: -10 + month,
    })[key]));

    test('returns a cell center value exactly', () => {
        const values = lookupClimatology(sloped, 40.5, -104.5);
        expect(values.ghi[0]).toBeCloseTo(3 - 1.045, 1);
        expect(values.temperature.map(v => Math.round(v))).toEqual([-10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1]);
        expect(values.diffuse[6]).toBeCloseTo(1, 1);
    });

    test('interpolates between cell centers', () => {
        // Halfway between the cells centered on -105.5 and -104.5.
        const mid = lookupClimatology(sloped, 40.5, -105).ghi[0];
        const west = lookupClimatology(sloped, 40.5, -105.5).ghi[0];
        const east = lookupClimatology(sloped, 40.5, -104.5).ghi[0];
        expect(mid).toBeCloseTo((west + east) / 2, 6);
        // Interpolates in latitude too: halfway between albedo 0.2 and 0.8 cells.
        expect(lookupClimatology(sloped, 60, 0).albedo[0]).toBeCloseTo(0.5, 2);
    });

    test('wraps across the antimeridian', () => {
        // Between the cells centered on 179.5 (ghi 4.795) and -179.5 (ghi 1.205).
        expect(lookupClimatology(sloped, 0.5, 180).ghi[0]).toBeCloseTo((4.795 + 1.205) / 2, 1);
        expect(lookupClimatology(sloped, 0.5, -180).ghi[0]).toBeCloseTo((4.795 + 1.205) / 2, 1);
    });

    test('clamps at the poles', () => {
        expect(lookupClimatology(sloped, 90, 0.5).ghi[0]).toBeCloseTo(3.005, 1);
        expect(lookupClimatology(sloped, -90, 0.5).ghi[0]).toBeCloseTo(3.005, 1);
    });

    test('skips cells with no data and returns null when all are missing', () => {
        const holes = decodeClimatology(encodeClimatology((key, month, lat, lon) =>
            (lon > 0 ? null : {ghi: 5, diffuse: 1, albedo: 0.2, temperature: 10}[key])));
        // Straddling lon 0: only the western cells have data.
        expect(lookupClimatology(holes, 10.5, 0).ghi[0]).toBeCloseTo(5, 1);
        expect(lookupClimatology(holes, 10.5, 90).ghi[0]).toBeNull();
    });
});

// The real data file, when it has been built.  The expected values come from NASA POWER's point API
// (2001-2020 climatology), so these confirm the build script and decoder agree end to end.
const REAL_FILE = path.join(__dirname, '../../../public/data/solar-climatology.bin');
const describeReal = fs.existsSync(REAL_FILE) ? describe : describe.skip;

describeReal('the built climatology file', () => {
    let grid;
    beforeAll(() => {
        grid = decodeClimatology(fs.readFileSync(REAL_FILE).buffer.slice(0));
    });

    // NASA POWER's monthly GHI for two cells, copied from its API (2001-2020 climatology).  A cell
    // center is returned exactly, give or take the file's 0.04 kWh/m²/day step.
    const expectCell = (actual, expected) => actual.forEach((v, i) => expect(Math.abs(v - expected[i]))
        .toBeLessThanOrEqual(0.021));

    test('matches NASA POWER at the cell near Denver', () => {
        const values = lookupClimatology(grid, 40.5, -104.5);
        expectCell(values.ghi,
            [2.4089, 3.2969, 4.6241, 5.6225, 6.3463, 7.2588, 7.0428, 6.2326, 5.2351, 3.7486, 2.6717, 2.0921]);
        expect(values.diffuse.every((v, i) => v > 0 && v < values.ghi[i])).toBe(true);
        expect(values.temperature[6]).toBeGreaterThan(values.temperature[0] + 15);
    });

    test('matches NASA POWER at the cell near Sydney, with the seasons reversed', () => {
        const values = lookupClimatology(grid, -33.5, 151.5);
        expectCell(values.ghi,
            [6.4908, 5.6611, 4.8137, 3.8191, 2.9803, 2.357, 2.772, 3.6725, 4.8242, 5.6698, 6.2074, 6.5594]);
    });

    // PVWatts v8 results for a 1 kW standard-module, open-rack, fixed array with the default 14.08%
    // losses, DC output in kWh, fetched from developer.nlr.gov on 2026-10-04.  PVWatts uses NREL's NSRDB
    // typical-year weather, not NASA POWER, so the two agree only within the data sets' differences.
    const PVWATTS = {
        Phoenix: {
            lat: 33.45, lon: -112.07, tilt: 33, azimuth: 180,
            monthly: [139.7, 139.1, 166.3, 175.4, 175.8, 165.2, 152.4, 155.2, 157.6, 157.8, 144.8, 140.3],
        },
        Seattle: {
            lat: 47.61, lon: -122.33, tilt: 48, azimuth: 180,
            monthly: [51.9, 67.3, 89.6, 115.5, 127.1, 116.7, 130.3, 141.0, 111.9, 82.0, 48.6, 42.8],
        },
        Anchorage: {
            lat: 61.22, lon: -149.90, tilt: 61, azimuth: 180,
            monthly: [19.6, 45.0, 119.2, 117.4, 124.2, 118.0, 109.4, 109.4, 87.8, 52.0, 23.3, 12.6],
        },
    };

    test.each(Object.entries(PVWATTS))('agrees with PVWatts in %s', (name, site) => {
        const sunlight = lookupClimatology(grid, site.lat, site.lon);
        const result = estimateProduction({
            latitude: site.lat, kwp: 1, tilt: site.tilt, azimuth: site.azimuth, ...sunlight,
        });
        const annual = site.monthly.reduce((a, b) => a + b, 0);
        expect(result.annual / annual).toBeGreaterThan(0.9);
        expect(result.annual / annual).toBeLessThan(1.1);
        // Dark months are small and the two data sets disagree most there; check the months that matter.
        const meanMonth = annual / 12;
        result.months.forEach((m, i) => {
            if (site.monthly[i] >= 0.6 * meanMonth) {
                expect(m.energy / site.monthly[i]).toBeGreaterThan(0.75);
                expect(m.energy / site.monthly[i]).toBeLessThan(1.25);
            }
        });
    });

    test('has polar night', () => {
        expect(lookupClimatology(grid, 80, 15).ghi[11]).toBeLessThan(0.05);
    });
});
