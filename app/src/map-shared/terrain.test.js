import {contourInterval, contourThresholds, DEFAULT_TERRAIN_MAX_ZOOM, terrainMaxZoom} from './terrain.js';

describe('how deep a terrain file is read', () => {
    test('as deep as the file goes', () => {
        expect(terrainMaxZoom({max_zoom: 8})).toBe(8);
        expect(terrainMaxZoom({max_zoom: 12})).toBe(12);
        expect(terrainMaxZoom({max_zoom: 5})).toBe(5);
    });

    test('as the terrain WROLPi offers, when the file does not say', () => {
        expect(DEFAULT_TERRAIN_MAX_ZOOM).toBe(8);
        const unsaid = [undefined, null, {}, {max_zoom: null}, {max_zoom: 'deep'}, {max_zoom: 0}, {max_zoom: 9.5}];
        for (const file of unsaid) {
            expect(terrainMaxZoom(file)).toBe(8);
        }
    });

    test('and no deeper than a map goes', () => {
        expect(terrainMaxZoom({max_zoom: 22})).toBe(15);
    });
});

describe('how far apart the contour lines are', () => {
    test('are as they have always been for the terrain WROLPi offers', () => {
        expect(contourThresholds(true, 8)).toEqual({
            4: [1000, 5000], 5: [500, 2500], 6: [200, 1000], 7: [200, 1000], 8: [100, 500],
        });
        expect(contourThresholds(false, 8)).toEqual({
            4: [500, 2500], 5: [200, 1000], 6: [100, 500], 7: [100, 500], 8: [50, 200],
        });
        // And when it is not said how deep the file is.
        expect(contourThresholds(true)).toEqual(contourThresholds(true, 8));
        expect(contourThresholds(false, undefined)).toEqual(contourThresholds(false, 8));
    });

    test('are finer for a file which goes deeper: 40 feet, or 20 meters, as a 1:24,000 sheet has', () => {
        const feet = contourThresholds(true, 12);
        expect(feet[12]).toEqual([40, 200]);
        expect(feet[11]).toEqual([40, 200]);
        expect(feet[10]).toEqual([100, 500]);
        expect(contourThresholds(false, 12)[12]).toEqual([20, 100]);
        // What was there for a shallower file is unchanged.
        expect(feet).toMatchObject(contourThresholds(true, 8));
    });

    test('are no finer than the file can bear', () => {
        expect(Object.keys(contourThresholds(true, 10)).map(Number)).toEqual([4, 5, 6, 7, 8, 9, 10]);
        // A file deeper than any interval keeps the finest.
        expect(contourThresholds(true, 15)).toEqual(contourThresholds(true, 12));
        // A file shallower than every interval still has contours.
        expect(contourThresholds(true, 2)).toEqual({4: [1000, 5000]});
        expect(contourThresholds(false, 4)).toEqual({4: [500, 2500]});
    });

    test('never have a minor line which is not a part of a major one', () => {
        for (const imperial of [true, false]) {
            for (const [minor, major] of Object.values(contourThresholds(imperial, 15))) {
                expect(major % minor).toBe(0);
                expect(major).toBeGreaterThan(minor);
            }
        }
    });
});

describe('how far apart the contour lines of a map at one zoom are', () => {
    test('is the interval of the tiles the lines are made for', () => {
        // A sheet is drawn at about zoom 13, from a file which goes to 12: tiles of zoom 12.
        expect(contourInterval(true, 12, 13.2)).toEqual([40, 200]);
        expect(contourInterval(false, 12, 13.2)).toEqual([20, 100]);
        // The file which WROLPi offers goes to zoom 8, whatever the map is zoomed to.
        expect(contourInterval(true, 8, 13.2)).toEqual([100, 500]);
        expect(contourInterval(false, DEFAULT_TERRAIN_MAX_ZOOM, 14.9)).toEqual([50, 200]);
        // A file deeper than the finest interval has the finest.
        expect(contourInterval(true, 15, 14.2)).toEqual([40, 200]);
        // A map zoomed out has the interval of its zoom.
        expect(contourInterval(true, 12, 6.9)).toEqual([200, 1000]);
        expect(contourInterval(true, 12, 10.99)).toEqual([100, 500]);
        expect(contourInterval(true, 12, 11)).toEqual([40, 200]);
    });

    test('is the same as the lines which are drawn: the interval of the nearest zoom below', () => {
        for (const [maxZoom, zoom] of [[8, 13.2], [12, 13.2], [12, 9.5], [3, 13], [undefined, 13]]) {
            const thresholds = contourThresholds(true, maxZoom);
            const tile = Math.min(Math.floor(zoom), maxZoom ?? DEFAULT_TERRAIN_MAX_ZOOM);
            const below = Math.max(...Object.keys(thresholds).map(Number).filter(i => i <= tile));
            expect(contourInterval(true, maxZoom, zoom)).toEqual(thresholds[below] ?? null);
        }
    });

    test('is nothing where no line is drawn', () => {
        expect(contourInterval(true, 12, 3.9)).toBeNull();
        expect(contourInterval(false, 8, 0)).toBeNull();
        // A file shallower than every interval has lines only from the zoom of the coarsest.
        expect(contourInterval(true, 3, 13)).toBeNull();
    });
});
