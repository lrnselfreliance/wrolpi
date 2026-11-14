import {
    EMPTY_FEATURES,
    formatLatitude,
    formatLongitude,
    quadAt,
    quadGridLines,
    quadLabel,
    quadPolygon,
    quadSize,
} from './mapQuads';

describe('the quadrangle a point is in', () => {
    test('has its edges on whole multiples of 7.5 minutes', () => {
        expect(quadAt(-111.9345, 40.2802)).toEqual({
            id: '322:-896', row: 322, col: -896, west: -112, south: 40.25, east: -111.875, north: 40.375,
        });
        // South and east of the origin.
        expect(quadAt(151.21, -33.87)).toMatchObject({west: 151.125, south: -33.875, east: 151.25, north: -33.75});
    });

    test('a point on an edge belongs to the quadrangle north and east of it', () => {
        expect(quadAt(-112, 40.25)).toMatchObject({west: -112, south: 40.25});
        expect(quadAt(-112.0000001, 40.2499999)).toMatchObject({west: -112.125, south: 40.125});
    });

    test('is the same wherever around the world the map has been dragged to', () => {
        expect(quadAt(-111.9345 + 360, 40.2802)).toEqual(quadAt(-111.9345, 40.2802));
        expect(quadAt(-111.9345 - 720, 40.2802)).toEqual(quadAt(-111.9345, 40.2802));
        expect(quadAt(180, 0)).toMatchObject({west: -180, east: -179.875});
    });

    test('is nothing off the map', () => {
        expect(quadAt(0, 86)).toBeNull();
        expect(quadAt(0, -85)).toBeNull();
        expect(quadAt(NaN, 0)).toBeNull();
        expect(quadAt(0, undefined)).toBeNull();
    });

    test('has an outline which closes', () => {
        const ring = quadPolygon(quadAt(-111.9345, 40.2802)).geometry.coordinates[0];
        expect(ring).toEqual([[-112, 40.25], [-111.875, 40.25], [-111.875, 40.375], [-112, 40.375], [-112, 40.25]]);
    });
});

describe('the grid across the map', () => {
    const lines = bounds => quadGridLines(bounds).features[0].geometry.coordinates;

    test('covers the view, out to the edges of the quadrangles it shows part of', () => {
        const grid = lines({west: -112.05, south: 40.26, east: -111.8, north: 40.4});
        // Parallels at 40.25, 40.375, 40.5; meridians at -112.125, -112, -111.875, -111.75.
        expect(grid).toHaveLength(7);
        expect(grid.slice(0, 3)).toEqual([
            [[-112.125, 40.25], [-111.75, 40.25]],
            [[-112.125, 40.375], [-111.75, 40.375]],
            [[-112.125, 40.5], [-111.75, 40.5]],
        ]);
        expect(grid[3]).toEqual([[-112.125, 40.25], [-112.125, 40.5]]);
        expect(grid[6]).toEqual([[-111.75, 40.25], [-111.75, 40.5]]);
    });

    test('is not made when the view is of too many quadrangles', () => {
        expect(quadGridLines({west: -125, south: 25, east: -66, north: 50})).toBeNull();
    });

    test('stops where the map does', () => {
        const grid = lines({west: 0, south: 84.9, east: 0.1, north: 89});
        expect(Math.max(...grid.flat().map(point => point[1]))).toBe(85);
    });

    test('is empty for a view of nothing', () => {
        expect(quadGridLines({west: 0, south: 88, east: 1, north: 89})).toBe(EMPTY_FEATURES);
    });
});

describe('what a quadrangle is called', () => {
    test('is where its southwest corner is', () => {
        expect(quadLabel(quadAt(-111.9345, 40.2802))).toBe('40°15′N 112°00′W');
        expect(quadLabel(quadAt(-111.8, 40.4))).toBe('40°22′30″N 111°52′30″W');
        expect(quadLabel(quadAt(151.21, -33.87))).toBe('33°52′30″S 151°07′30″E');
    });

    test('a coordinate is written in degrees, minutes and seconds', () => {
        expect(formatLatitude(0)).toBe('0°00′N');
        expect(formatLatitude(-0.125)).toBe('0°07′30″S');
        expect(formatLongitude(-179.875)).toBe('179°52′30″W');
    });
});

describe('the size of a quadrangle', () => {
    test('is narrower further from the equator, and about as tall everywhere', () => {
        const equator = quadSize(quadAt(0, 0));
        const utah = quadSize(quadAt(-111.9345, 40.2802));
        const alaska = quadSize(quadAt(-150, 64.8));
        expect(equator.widthMeters).toBeGreaterThan(utah.widthMeters);
        expect(utah.widthMeters).toBeGreaterThan(alaska.widthMeters);
        for (const size of [equator, utah, alaska]) {
            expect(size.heightMeters).toBeGreaterThan(13800);
            expect(size.heightMeters).toBeLessThan(14000);
        }
    });

    test('is that of a 1:24,000 sheet', () => {
        // A quadrangle at 40 degrees north is about 10.6 km by 13.9 km: about 17.4 by 22.8 inches of paper.
        const {widthMeters, heightMeters, sheetWidthMm, sheetHeightMm} = quadSize(quadAt(-111.9345, 40.2802));
        expect(widthMeters / 1000).toBeCloseTo(10.62, 1);
        expect(heightMeters / 1000).toBeCloseTo(13.88, 1);
        expect(sheetWidthMm / 25.4).toBeCloseTo(17.4, 0);
        expect(sheetHeightMm / 25.4).toBeCloseTo(22.8, 0);
        expect(sheetWidthMm).toBeCloseTo(widthMeters / 24, 6);
    });
});
