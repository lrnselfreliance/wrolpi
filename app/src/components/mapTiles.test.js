import {readTileBounds, readVectorTile} from './mapTiles';

const mockOpened = [];
const mockTiles = {};
const mockHeaders = {};

jest.mock('pmtiles', () => ({
    PMTiles: class {
        constructor(address) {
            this.address = address;
            mockOpened.push(address);
        }

        async getHeader() {
            return mockHeaders[this.address] || {};
        }

        async getZxy(z, x, y) {
            return mockTiles[`${this.address} ${z}/${x}/${y}`];
        }
    },
}));

describe('reading a tile of a map file', () => {
    test('is of the file a source of the map has as its URL, which is opened once', async () => {
        // A tile with nothing in it.
        mockTiles['https://example.com/a.pmtiles 14/3/5'] = {data: new ArrayBuffer(0)};
        const tile = await readVectorTile('pmtiles://https://example.com/a.pmtiles', {z: 14, x: 3, y: 5});
        expect(tile.layers).toEqual({});
        await readVectorTile('pmtiles://https://example.com/a.pmtiles', {z: 14, x: 3, y: 6});
        expect(mockOpened).toEqual(['https://example.com/a.pmtiles']);
    });

    test('is nothing when the file has no such tile', async () => {
        expect(await readVectorTile('pmtiles:///media/b.pmtiles', {z: 14, x: 0, y: 0})).toBeNull();
        expect(mockOpened).toContain('/media/b.pmtiles');
    });
});

describe('the edges of a map file', () => {
    test('are what the file says: west, south, east and north', async () => {
        mockHeaders['/media/c.pmtiles'] = {minLon: -150, minLat: 61, maxLon: -149, maxLat: 62, maxZoom: 15};
        expect(await readTileBounds('pmtiles:///media/c.pmtiles')).toEqual([-150, 61, -149, 62]);
    });

    test('are not known when the file does not say', async () => {
        mockHeaders['/media/d.pmtiles'] = {minLon: 0, minLat: 0, maxLon: 0, maxLat: 0};
        expect(await readTileBounds('pmtiles:///media/d.pmtiles')).toBeNull();
        expect(await readTileBounds('pmtiles:///media/e.pmtiles')).toBeNull();
    });
});
