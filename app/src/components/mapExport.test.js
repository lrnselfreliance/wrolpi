import {
    BACKGROUND_GROUP,
    exportFileName,
    exportCredits,
    exportDate,
    exportContours,
    exportFrame,
    exportGroups,
    exportSheet,
    exportStyle,
    exportTitle,
    loadRoadNames,
    namedRoads,
    placeRoadNames,
    tilesOfBounds,
    unnamedRoadLayers,
    maxExportPixels,
    renderExport,
} from './mapExport';
import {quadAt} from './mapQuads';

const ANCHORAGE = quadAt(-149.93, 61.19);
const BERTHOUD = quadAt(-105.0595, 40.31);

describe('how a quadrangle is drawn', () => {
    test('is the size of a 1:24,000 sheet, at the sharpness asked for', () => {
        const frame = exportFrame(ANCHORAGE);
        // 11.0 inches wide at 150 CSS pixels an inch, and twice that many real pixels (300 DPI).
        expect(frame.cssWidth).toBe(1654);
        expect(frame.cssHeight).toBe(3432);
        expect(frame.pixelRatio).toBe(2);
        expect(frame.dpi).toBe(300);
        expect(frame.zoom).toBeCloseTo(13.18, 2);

        // Wider nearer the equator, and no taller.
        const south = exportFrame(BERTHOUD);
        expect(south.cssWidth).toBe(2615);
        expect(Math.abs(south.cssHeight - frame.cssHeight)).toBeLessThan(15);
        expect(south.zoom).toBeCloseTo(13.84, 2);
    });

    test('is exactly the quadrangle: its edges are the edges of the map', () => {
        const {cssWidth, cssHeight, zoom, center} = exportFrame(ANCHORAGE);
        // Web Mercator, as the map draws it: pixels from the center to a point.
        const world = 512 * 2 ** zoom;
        const x = lng => (lng + 180) / 360 * world;
        const y = lat => (1 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / Math.PI) / 2 * world;
        expect(x(ANCHORAGE.east) - x(ANCHORAGE.west)).toBeCloseTo(cssWidth, 6);
        expect(x(center[0]) - x(ANCHORAGE.west)).toBeCloseTo(cssWidth / 2, 6);
        expect(y(ANCHORAGE.south) - y(center[1])).toBeCloseTo(y(center[1]) - y(ANCHORAGE.north), 6);
        // The height is whole pixels, so it is within half of one of the quadrangle's.
        expect(Math.abs((y(ANCHORAGE.south) - y(ANCHORAGE.north)) - cssHeight)).toBeLessThanOrEqual(0.5);
    });

    test('is sharper when that is asked for, and no larger on paper', () => {
        const frame = exportFrame(ANCHORAGE, {dpi: 400});
        expect(frame.dpi).toBe(400);
        expect(frame.pixelRatio).toBeCloseTo(400 / 150, 10);
        // The same sheet, the same text and detail: only more pixels.
        expect(frame).toMatchObject({cssWidth: 1654, cssHeight: 3432});
        expect(frame.zoom).toBe(exportFrame(ANCHORAGE).zoom);
    });

    test('is less sharp when it would be more pixels than the API makes a PDF of', () => {
        // A quadrangle at the equator is square, and at 400 DPI is 83 megapixels.
        const equator = quadAt(0.05, 0.05);
        const asked = exportFrame(equator, {dpi: 400});
        expect(asked.cssWidth * asked.cssHeight * asked.pixelRatio ** 2).toBeGreaterThan(80e6);

        const frame = exportFrame(equator, {dpi: 400, maxPixels: maxExportPixels(1)});
        const pixels = Math.round(frame.cssWidth * frame.pixelRatio) * Math.round(frame.cssHeight * frame.pixelRatio);
        expect(pixels).toBeLessThanOrEqual(64e6);
        expect(pixels).toBeGreaterThan(63.5e6);
        expect(frame.dpi).toBeGreaterThan(345);
        expect(frame.dpi).toBeLessThan(355);

        // With many layers on, each may be less.
        expect(maxExportPixels(1)).toBe(64e6);
        expect(maxExportPixels(15)).toBe(64e6);
        expect(maxExportPixels(25)).toBe(40e6);
        const many = exportFrame(equator, {maxPixels: maxExportPixels(25)});
        expect(many.dpi).toBeLessThan(300);
        expect(25 * many.cssWidth * many.cssHeight * many.pixelRatio ** 2).toBeLessThanOrEqual(1e9);
        // A map which is within what the API takes is as sharp as was asked for.
        expect(exportFrame(ANCHORAGE, {dpi: 400, maxPixels: maxExportPixels(13)}).dpi).toBe(400);
    });

    test('is less sharp where the browser can not make a canvas that large', () => {
        const frame = exportFrame(ANCHORAGE, {maxSide: 4096});
        expect(frame.cssWidth).toBe(1654);
        expect(frame.cssHeight * frame.pixelRatio).toBeCloseTo(4096, 6);
        expect(frame.dpi).toBeCloseTo(179, 0);
    });
});

const LAYER_GROUPS = {
    'Hillshade': ['hillshade'],
    'Water': ['water'],
    'Buildings': ['buildings'],
    'Roads - Minor': ['roads_minor', 'roads_other'],
    'Labels': ['roads_labels', 'places_', 'water_label'],
};
const hidden = {layout: {visibility: 'none'}};
const STYLE_LAYERS = [
    {id: 'background', type: 'background'},
    {id: 'earth', type: 'fill'},
    {id: 'water', type: 'fill'},
    {id: 'hillshade', type: 'hillshade', ...hidden},
    {id: 'buildings', type: 'fill'},
    {id: 'roads_minor_casing', type: 'line'},
    {id: 'roads_minor', type: 'line'},
    // A second basemap file's layers carry its name.
    {id: 'oregon.pmtiles:water', type: 'fill'},
    {id: 'oregon.pmtiles:roads_minor', type: 'line'},
    {id: 'overlay:satellite.pmtiles:raster', type: 'raster', source: 'overlay:satellite.pmtiles'},
    // The ground of an overlay is under the basemap's labels, and its own labels are over them.
    {id: 'overlay:extras/features.pmtiles:water:fill', type: 'fill', source: 'overlay:extras/features.pmtiles', ...hidden},
    {id: 'overlay:extras/features.pmtiles:lines:line', type: 'line', source: 'overlay:extras/features.pmtiles'},
    {id: 'water_label_ocean', type: 'symbol'},
    {id: 'places_locality', type: 'symbol'},
    {id: 'overlay:extras/features.pmtiles:towers:circle', type: 'circle', source: 'overlay:extras/features.pmtiles'},
    {id: 'overlay:extras/features.pmtiles:towers:names', type: 'symbol', source: 'overlay:extras/features.pmtiles'},
    {id: 'overlay:off.pmtiles:raster', type: 'raster', source: 'overlay:off.pmtiles', ...hidden},
];
const OVERLAY_LABELS = {
    'overlay:satellite.pmtiles': 'Satellite imagery',
    'overlay:extras/features.pmtiles': 'Infrastructure',
};

describe('the layers of the PDF', () => {
    const groups = exportGroups(STYLE_LAYERS, {layerGroups: LAYER_GROUPS, overlayLabels: OVERLAY_LABELS});

    test('are the layers which are on, as the layer control names them, from the bottom up', () => {
        expect(groups.map(g => g.name)).toEqual([
            BACKGROUND_GROUP, 'Buildings', 'Water', 'Roads - Minor', 'Satellite imagery', 'Infrastructure', 'Labels',
            'Infrastructure (labels)',
        ]);
    });

    test('each has the layers of the style which are of it', () => {
        const ids = Object.fromEntries(groups.map(g => [g.name, g.ids]));
        // What is in no group is the ground the rest is drawn on.
        expect(ids[BACKGROUND_GROUP]).toEqual(['background', 'earth']);
        // Of every basemap file.
        expect(ids['Water']).toEqual(['water', 'oregon.pmtiles:water']);
        expect(ids['Roads - Minor']).toEqual(['roads_minor_casing', 'roads_minor', 'oregon.pmtiles:roads_minor']);
        // A water label is a label.
        expect(ids['Labels']).toEqual(['water_label_ocean', 'places_locality']);
        // An overlay's layers are of the overlay, whatever they are named, and only those which are on.
        expect(ids['Infrastructure']).toEqual(['overlay:extras/features.pmtiles:lines:line']);
        // Its labels are a layer of their own, because the basemap's labels are between the two.
        expect(ids['Infrastructure (labels)']).toEqual([
            'overlay:extras/features.pmtiles:towers:circle', 'overlay:extras/features.pmtiles:towers:names',
        ]);
    });

    test('a layer which is off is not exported', () => {
        expect(groups.map(g => g.name)).not.toContain('Hillshade');
        expect(groups.flatMap(g => g.ids)).not.toContain('overlay:off.pmtiles:raster');
    });

    test('says which are photographs', () => {
        expect(groups.filter(g => g.raster).map(g => g.name)).toEqual(['Satellite imagery']);
    });

    test('an overlay with no label goes by its source, and two of one name are told apart', () => {
        const names = exportGroups([
            {id: 'water', type: 'fill'},
            {id: 'overlay:a.pmtiles:x:line', type: 'line', source: 'overlay:a.pmtiles'},
            {id: 'overlay:b.pmtiles:x:line', type: 'line', source: 'overlay:b.pmtiles'},
            {id: 'overlay:c.pmtiles:x:line', type: 'line', source: 'overlay:c.pmtiles'},
        ], {
            layerGroups: LAYER_GROUPS,
            overlayLabels: {'overlay:a.pmtiles': 'Water', 'overlay:b.pmtiles': 'Water'},
        }).map(g => g.name);
        expect(names).toEqual(['Water', 'Water (2)', 'Water (3)', 'overlay:c.pmtiles']);
    });

    test('an overlay which is only ground, or only labels, is one layer by its own name', () => {
        const names = layers => exportGroups(layers, {
            layerGroups: LAYER_GROUPS, overlayLabels: {'overlay:a.pmtiles': 'Towers'},
        }).map(g => g.name);
        expect(names([
            {id: 'places_locality', type: 'symbol'},
            {id: 'overlay:a.pmtiles:x:icons', type: 'symbol', source: 'overlay:a.pmtiles'},
        ])).toEqual(['Labels', 'Towers']);
        expect(names([
            {id: 'overlay:a.pmtiles:x:line', type: 'line', source: 'overlay:a.pmtiles'},
            {id: 'places_locality', type: 'symbol'},
            // Its labels are turned off.
            {id: 'overlay:a.pmtiles:x:icons', type: 'symbol', source: 'overlay:a.pmtiles', ...hidden},
        ])).toEqual(['Towers', 'Labels']);
    });

    test('there are none when nothing is on', () => {
        expect(exportGroups([{id: 'water', type: 'fill', ...hidden}], {layerGroups: LAYER_GROUPS})).toEqual([]);
    });
});

describe('the style which is exported from', () => {
    test('draws nothing to begin with, and has nothing of the app in it', () => {
        const style = {
            version: 8,
            glyphs: '/fonts',
            sources: {basemap: {type: 'vector'}, 'quad-grid': {type: 'geojson'}},
            layers: [
                {id: 'water', type: 'fill', source: 'basemap'},
                {id: 'places', type: 'symbol', source: 'basemap', layout: {'text-size': 12}},
                {id: 'quad-grid-lines', type: 'line', source: 'quad-grid'},
            ],
        };
        const exported = exportStyle(style, ['quad-']);
        expect(exported.glyphs).toBe('/fonts');
        expect(Object.keys(exported.sources)).toEqual(['basemap']);
        expect(exported.layers).toEqual([
            {id: 'water', type: 'fill', source: 'basemap', layout: {visibility: 'none'}},
            {id: 'places', type: 'symbol', source: 'basemap', layout: {'text-size': 12, visibility: 'none'}},
        ]);
        // The map's own style is as it was.
        expect(style.layers[0].layout).toBeUndefined();
    });

    test('a layer which would not name roads names the roads which were read for it', () => {
        const roadNames = {'a.pmtiles': POINTS};
        const exported = exportStyle(TOWN, [], {zoom: 13.2, roadNames});
        expect(exported.sources['export-road-names:a.pmtiles']).toEqual({type: 'geojson', data: POINTS});
        expect(exported.sources['a.pmtiles']).toBe(TOWN.sources['a.pmtiles']);

        expect(exported.layers.map(l => l.id)).toEqual(TOWN.layers.map(l => l.id));
        const [, minor, major, address] = exported.layers;
        // In its own style, at whatever zoom: each name where it was put, turned as its road is.
        expect(minor).toEqual({
            id: 'roads_labels_minor', type: 'symbol', source: 'export-road-names:a.pmtiles',
            filter: ['in', 'kind', 'minor_road'],
            layout: {
                'symbol-placement': 'point', 'text-rotate': ['get', 'export:angle'], 'text-max-width': 1000,
                'text-rotation-alignment': 'map', 'text-size': 12, visibility: 'none',
            },
        });
        // A layer which names roads at this zoom, and one which is not of roads, are as they were.
        expect(major).toMatchObject({source: 'a.pmtiles', 'source-layer': 'roads', minzoom: 11});
        expect(address).toMatchObject({source: 'a.pmtiles', minzoom: 18});
        // The map's own style is as it was.
        expect(TOWN.layers[1]).toMatchObject({source: 'a.pmtiles', minzoom: 15});
        expect(TOWN.layers[1].layout['symbol-placement']).toBe('line');
    });

    test('a layer whose names could not be read is drawn as the map draws it', () => {
        const exported = exportStyle(TOWN, [], {zoom: 13.2, roadNames: {}});
        expect(exported.layers.map(l => l.id)).toEqual(TOWN.layers.map(l => l.id));
        expect(exported.layers[1]).toMatchObject({source: 'a.pmtiles', minzoom: 15});
    });
});

// A town: its small roads are named from zoom 15, its large ones from 11.
const TOWN = {
    version: 8,
    sources: {'a.pmtiles': {type: 'vector', url: 'pmtiles://a'}},
    layers: [
        {id: 'roads_minor', type: 'line', source: 'a.pmtiles', 'source-layer': 'roads'},
        {
            id: 'roads_labels_minor', type: 'symbol', source: 'a.pmtiles', 'source-layer': 'roads', minzoom: 15,
            filter: ['in', 'kind', 'minor_road'], layout: {'symbol-placement': 'line', 'text-size': 12},
        },
        {id: 'roads_labels_major', type: 'symbol', source: 'a.pmtiles', 'source-layer': 'roads', minzoom: 11},
        {id: 'address_label', type: 'symbol', source: 'a.pmtiles', 'source-layer': 'pois', minzoom: 18},
    ],
};
const POINTS = {type: 'FeatureCollection', features: []};

// A tile as @mapbox/vector-tile reads it, of roads which go east from the given longitude.
function fakeTile(roads) {
    return {
        layers: {
            roads: {
                length: roads.length,
                feature: i => ({
                    properties: roads[i].properties,
                    toGeoJSON: (x, y, z) => ({
                        type: 'Feature', id: 7, properties: roads[i].properties,
                        geometry: {type: 'LineString', coordinates: roads[i].coordinates, tile: [z, x, y]},
                    }),
                }),
            },
        },
    };
}

describe('the names of small roads', () => {
    test('are of the layers which name roads, but not at the zoom of the sheet', () => {
        expect(unnamedRoadLayers(TOWN, 13.2).map(l => l.id)).toEqual(['roads_labels_minor']);
        expect(unnamedRoadLayers(TOWN, 10).map(l => l.id)).toEqual(['roads_labels_minor', 'roads_labels_major']);
        expect(unnamedRoadLayers(TOWN, 15)).toEqual([]);
        expect(unnamedRoadLayers({}, 13)).toEqual([]);
    });

    test('are read from the tiles which the quadrangle is in', () => {
        // One tile of zoom 1 is a quarter of the world.
        expect(tilesOfBounds([-90, 10, -80, 20], 1)).toEqual([{z: 1, x: 0, y: 0}]);
        expect(tilesOfBounds([-10, -10, 10, 10], 1)).toEqual([
            {z: 1, x: 0, y: 0}, {z: 1, x: 0, y: 1}, {z: 1, x: 1, y: 0}, {z: 1, x: 1, y: 1}]);
        // A tile which only touches the edge has nothing of the quadrangle in it.
        expect(tilesOfBounds([-180, 0, 0, 85.0511287798], 1)).toEqual([{z: 1, x: 0, y: 0}]);
        // A quadrangle is a few tiles of zoom 14 wide, each of them once.
        const tiles = tilesOfBounds([ANCHORAGE.west, ANCHORAGE.south, ANCHORAGE.east, ANCHORAGE.north], 14);
        expect(new Set(tiles.map(t => t.x)).size).toBeLessThanOrEqual(7);
        expect(tiles.every(t => t.z === 14)).toBe(true);
        expect(tiles.length).toBe(new Set(tiles.map(t => `${t.x}/${t.y}`)).size);
    });

    test('are the roads of a tile which have a name, with all that is said of them', () => {
        const tile = fakeTile([
            {properties: {kind: 'minor_road', name: 'Elm Street', ref: '7'}, coordinates: [[0, 0], [1, 0]]},
            {properties: {kind: 'minor_road'}, coordinates: [[0, 1], [1, 1]]},
            {properties: {kind: 'path', 'name:en': 'Ridge Trail'}, coordinates: [[0, 2], [1, 2]]},
        ]);
        const roads = namedRoads(tile, 'roads', {z: 14, x: 3, y: 5});
        expect(roads.map(r => r.properties)).toEqual([
            {kind: 'minor_road', name: 'Elm Street', ref: '7'}, {kind: 'path', 'name:en': 'Ridge Trail'}]);
        // Where the tile says they are, as the tile reader makes that of the tile's place.
        expect(roads[0].geometry).toMatchObject({type: 'LineString', coordinates: [[0, 0], [1, 0]], tile: [14, 3, 5]});
        expect(roads[0]).not.toHaveProperty('id');
        // No such tile, or no such layer in it.
        expect(namedRoads(null, 'roads', {z: 14, x: 3, y: 5})).toEqual([]);
        expect(namedRoads(tile, 'streets', {z: 14, x: 3, y: 5})).toEqual([]);
    });

    // At zoom 13 the world is 4,194,304 pixels around: a degree of longitude is 11,651 of them.
    const piece = (name, from, to, kind = 'minor_road') => ({
        type: 'Feature', properties: {name, kind},
        geometry: {type: 'LineString', coordinates: [[from, 0], [to, 0]]},
    });
    const places = (roads, zoom = 13) => placeRoadNames(roads, zoom).features
        .map(f => [f.properties.name, Math.round(f.geometry.coordinates[0] * 1e6) / 1e6]);

    test('a road is named over its middle, however short it is', () => {
        const {type, features} = placeRoadNames([piece('Elm Street', 0, 0.01), piece('Oak Street', 1, 1.0004)], 13);
        expect(type).toBe('FeatureCollection');
        expect(features).toEqual([{
            type: 'Feature', geometry: {type: 'Point', coordinates: [expect.closeTo(0.005, 9), 0]},
            properties: {kind: 'minor_road', name: 'Elm Street', 'export:angle': 0},
        }, {
            // 5 pixels of road under 66 pixels of name.
            type: 'Feature', geometry: {type: 'Point', coordinates: [expect.closeTo(1.0002, 9), 0]},
            properties: {kind: 'minor_road', name: 'Oak Street', 'export:angle': 0},
        }]);
    });

    test('a long road is named again each time it has gone far enough', () => {
        // 0.1 degrees is 1,165 pixels: two names, each in the middle of half of it.
        expect(places([piece('Elm Street', 0, 0.1)])).toEqual([['Elm Street', 0.025], ['Elm Street', 0.075]]);
        // 699 pixels is not twice as far.
        expect(places([piece('Elm Street', 0, 0.06)])).toEqual([['Elm Street', 0.03]]);
    });

    test('a name is turned as the road goes under it, and never upside down', () => {
        const going = (to, from = [0, 0]) => ({
            type: 'Feature', properties: {name: `${from} to ${to}`},
            geometry: {type: 'LineString', coordinates: [from, to]},
        });
        const angles = roads => placeRoadNames(roads, 13).features.map(f => f.properties['export:angle']);
        // East and west are level; north and south are on their side; a map's y is down.
        expect(angles([going([0.003, 0])])).toEqual([0]);
        expect(angles([going([0, 0], [0.003, 0])])).toEqual([0]);
        expect(angles([going([0, 0.003])])).toEqual([90]);
        expect(angles([going([0, -0.003])])).toEqual([90]);
        expect(angles([going([0.002, 0.002])])).toEqual([-45]);
        expect(angles([going([-0.002, -0.002])])).toEqual([-45]);
        expect(angles([going([0.002, -0.002])])).toEqual([45]);
        // A road which turns a corner far from its middle is named as it goes at its middle.
        const corner = {
            type: 'Feature', properties: {name: 'Elm'},
            geometry: {type: 'LineString', coordinates: [[0, 0], [0.05, 0], [0.05, 0.002]]},
        };
        expect(angles([corner])).toEqual([0]);
    });

    test('a road in pieces is not named twice in one place', () => {
        // A street cut by the edge of a tile: most of it, and a stub at its far end.
        expect(places([piece('Elm Street', 0.02, 0.022), piece('Elm Street', 0, 0.02)], 13.2))
            .toEqual([['Elm Street', 0.01]]);
        // Short pieces end to end: the longest is the one which is named.
        expect(places([piece('Oak Street', 0, 0.002), piece('Oak Street', 0.002, 0.005)]))
            .toEqual([['Oak Street', 0.0035]]);
        // Another road beside it has its own name, and the same name a long way off is another road.
        expect(places([piece('Oak Street', 0, 0.005), piece('Ash Street', 0.002, 0.0045), piece('Oak Street', 0.1, 0.102)]))
            .toEqual([['Oak Street', 0.0025], ['Ash Street', 0.00325], ['Oak Street', 0.101]]);
    });

    test('a piece of another kind of road does not take the name', () => {
        // The layer which names small roads does not draw the large one, however long its piece is.
        const {features} = placeRoadNames(
            [piece('Main Street', 0, 0.004, 'major_road'), piece('Main Street', 0.004, 0.0069, 'minor_road')], 13);
        expect(features.map(f => f.properties.kind)).toEqual(['major_road', 'minor_road']);
    });

    test('the lines of a road of many lines are each a piece of it; what is not a line is not one', () => {
        const {features} = placeRoadNames([
            {
                type: 'Feature', properties: {name: 'Elm Street'},
                geometry: {type: 'MultiLineString', coordinates: [[[0, 0], [0.01, 0]], [[0, 1], [0.003, 1]], [[5, 5]]]},
            },
            {type: 'Feature', properties: {name: 'Elm Square'}, geometry: {type: 'Point', coordinates: [0, 0]}},
        ], 13);
        expect(features.map(f => f.geometry.coordinates)).toEqual([
            [expect.closeTo(0.005, 9), 0], [expect.closeTo(0.0015, 9), 1]]);
    });

    const FRAME = {zoom: 13.2, bounds: [-10, -10, 10, 10]};

    test('are read from each source whose roads would have no names, a tile at a time', async () => {
        const readTile = jest.fn(async (url, {x, y}) => (x === 8191 && y === 8191
            ? fakeTile([{properties: {kind: 'minor_road', name: 'Elm Street'}, coordinates: [[0, 0], [0.01, 0]]}])
            : null));
        const frame = {zoom: 13.2, bounds: [-0.01, 0.001, -0.001, 0.01]};
        const names = await loadRoadNames(TOWN, frame, readTile);
        expect(readTile).toHaveBeenCalledTimes(1);
        expect(readTile).toHaveBeenCalledWith('pmtiles://a', {z: 14, x: 8191, y: 8191});
        expect(Object.keys(names)).toEqual(['a.pmtiles']);
        expect(names['a.pmtiles'].features.map(f => f.properties.name)).toEqual(['Elm Street']);
    });

    test('are not read when there is no need, or no way', async () => {
        const readTile = jest.fn(async () => null);
        // Nothing reads tiles.
        expect(await loadRoadNames(TOWN, FRAME, undefined)).toEqual({});
        // The map is drawn at a zoom at which its style names every road.
        expect(await loadRoadNames(TOWN, {...FRAME, zoom: 15.1}, readTile)).toEqual({});
        // No layer of the map names roads.
        expect(await loadRoadNames({...TOWN, layers: [TOWN.layers[0]]}, FRAME, readTile)).toEqual({});
        // More tiles than a quadrangle is.
        expect(await loadRoadNames(TOWN, {zoom: 13.2, bounds: [-10, -10, 10, 10]}, readTile)).toEqual({});
        expect(readTile).not.toHaveBeenCalled();
        // No tile of the place has a named road.
        expect(await loadRoadNames(TOWN, {zoom: 13.2, bounds: [-0.01, 0.001, -0.001, 0.01]}, readTile)).toEqual({});
    });

    test('are read nearer the equator too, where a quadrangle is drawn at a little over zoom 14', async () => {
        // The style still keeps the names of small roads for zoom 15 there.
        const readTile = jest.fn(async () => fakeTile([
            {properties: {kind: 'minor_road', name: 'Elm Street'}, coordinates: [[-80.95, 25.05], [-80.9499, 25.05]]},
        ]));
        const frame = {zoom: 14.09, bounds: [-80.9501, 25.0499, -80.9499, 25.0501]};
        const names = await loadRoadNames(TOWN, frame, readTile);
        expect(readTile).toHaveBeenCalledWith('pmtiles://a', expect.objectContaining({z: 14}));
        expect(names['a.pmtiles'].features.map(f => f.properties.name)).toEqual(['Elm Street']);
        // And the layer draws them.
        const exported = exportStyle(TOWN, [], {zoom: frame.zoom, roadNames: names});
        expect(exported.layers[1]).not.toHaveProperty('minzoom');
        expect(exported.layers[1].source).toBe('export-road-names:a.pmtiles');
    });

    test('no more is read once the export is cancelled', async () => {
        const two = {
            ...TOWN,
            sources: {...TOWN.sources, 'b.pmtiles': {type: 'vector', url: 'pmtiles://b'}},
            layers: [...TOWN.layers, {...TOWN.layers[1], id: 'b.pmtiles:roads_labels_minor', source: 'b.pmtiles'}],
        };
        let cancelled = false;
        const readTile = jest.fn(async () => {
            cancelled = true;
            return null;
        });
        await loadRoadNames(two, {zoom: 13.2, bounds: [-0.01, 0.001, -0.001, 0.01]}, readTile, () => cancelled);
        expect(readTile).toHaveBeenCalledTimes(1);
        expect(readTile).toHaveBeenCalledWith('pmtiles://a', expect.anything());
    });

    test('a source which can not be read is exported without them', async () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
        const readTile = jest.fn(async () => {
            throw new Error('no such file');
        });
        expect(await loadRoadNames(TOWN, {zoom: 13.2, bounds: [-0.01, 0.001, -0.001, 0.01]}, readTile)).toEqual({});
        expect(warn).toHaveBeenCalledTimes(1);
        warn.mockRestore();
    });
});

// As much of a MapLibre map as an export uses.  It records which layers were visible each time
// its canvas was read.
function fakeMapClass(record, {transparent = true} = {}) {
    return class FakeMap {
        constructor(options) {
            record.options = options;
            record.maps = (record.maps || 0) + 1;
            this.visible = new Set(options.style.layers
                .filter(l => l.layout.visibility !== 'none').map(l => l.id));
            this.layerIds = new Set(options.style.layers.map(l => l.id));
            this.canvas = {
                width: Math.floor(parseInt(options.container.style.width, 10) * options.pixelRatio),
                height: Math.floor(parseInt(options.container.style.height, 10) * options.pixelRatio),
                toBlob: (callback, type) => {
                    record.captures.push({type, visible: [...this.visible]});
                    callback(record.failBlob ? null : {type, layers: [...this.visible]});
                },
            };
        }

        on(event, handler) {
            record.listeners = [...(record.listeners || []), event];
        }

        once(event, handler) {
            if (event === 'idle' && record.neverIdle) return;
            Promise.resolve().then(handler);
        }

        getCanvas() {
            return this.canvas;
        }

        // The edges of what this map draws (not quite those of the quadrangle it was asked for).
        getBounds() {
            const [west, south, east, north] = record.bounds || [-150, 61.12499878, -149.875, 61.25000121];
            return {getWest: () => west, getSouth: () => south, getEast: () => east, getNorth: () => north};
        }

        getLayer(id) {
            return this.layerIds.has(id) ? {id} : undefined;
        }

        setLayoutProperty(id, name, value) {
            if (value === 'visible') this.visible.add(id); else this.visible.delete(id);
        }

        triggerRepaint() {
        }

        remove() {
            record.removed = true;
        }
    };
}

describe('drawing the layers', () => {
    const style = {
        version: 8,
        sources: {basemap: {type: 'vector'}},
        layers: [
            {id: 'water', type: 'fill', source: 'basemap'},
            {id: 'roads_minor', type: 'line', source: 'basemap'},
            {id: 'places', type: 'symbol', source: 'basemap'},
        ],
    };
    const groups = [
        {name: 'Water', ids: ['water'], raster: false},
        {name: 'Roads - Minor', ids: ['roads_minor', 'gone'], raster: false},
        {name: 'Labels', ids: ['places'], raster: false},
    ];
    const frame = exportFrame(ANCHORAGE);
    let getContext;

    beforeEach(() => {
        // The reduced copy which says whether an image has gaps: here, all of it is gaps.
        getContext = jest.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
            clearRect: jest.fn(),
            drawImage: jest.fn(),
            getImageData: () => ({data: new Uint8ClampedArray([0, 0, 0, 0])}),
        }));
    });
    afterEach(() => getContext.mockRestore());

    test('each group is drawn alone, on a map the size of the sheet', async () => {
        const record = {captures: []};
        const progress = [];
        const setup = jest.fn();
        const result = await renderExport({
            MapClass: fakeMapClass(record), style, frame, groups, setup,
            onProgress: (name, index, count) => progress.push(`${name} ${index + 1}/${count}`),
        });

        expect(record.captures).toEqual([
            {type: 'image/png', visible: ['water']},
            {type: 'image/png', visible: ['roads_minor']},
            {type: 'image/png', visible: ['places']},
        ]);
        expect(result.layers.map(l => l.name)).toEqual(['Water', 'Roads - Minor', 'Labels']);
        expect(result.layers[1].blob.layers).toEqual(['roads_minor']);
        expect(result).toMatchObject({width: 3308, height: 6864, dpi: 300});
        // Where the picture is, as the map which drew it has it.
        expect(result.bounds).toEqual([-150, 61.12499878, -149.875, 61.25000121]);
        expect(progress).toEqual(['Water 1/3', 'Roads - Minor 2/3', 'Labels 3/3']);

        expect(record.options).toMatchObject({
            center: frame.center, zoom: frame.zoom, pixelRatio: 2, interactive: false,
            fadeDuration: 0, maxCanvasSize: [6864, 6864],
            // Where this MapLibre reads it from; as an option of the map itself it is ignored.
            canvasContextAttributes: {preserveDrawingBuffer: true},
        });
        expect(record.options).not.toHaveProperty('preserveDrawingBuffer');
        expect(record.options.container.style.width).toBe('1654px');
        expect(record.options.container.style.height).toBe('3432px');
        expect(setup).toHaveBeenCalledTimes(1);
    });

    test('the names of small roads are read, and drawn with the layer they are of', async () => {
        const record = {captures: []};
        const readTile = jest.fn(async () => fakeTile([
            {properties: {kind: 'minor_road', name: 'Elm Street'}, coordinates: [[-149.9, 61.2], [-149.9001, 61.2]]},
        ]));
        const town = {...TOWN, layers: TOWN.layers.map(l => ({...l, layout: {...l.layout, visibility: 'visible'}}))};
        await renderExport({
            MapClass: fakeMapClass(record), style: town, frame, readTile,
            groups: [{name: 'Labels', ids: ['roads_labels_minor', 'roads_labels_major']}],
        });
        expect(readTile).toHaveBeenCalledWith('pmtiles://a', expect.objectContaining({z: 14}));
        expect(record.options.style.sources['export-road-names:a.pmtiles'].data.features).toHaveLength(1);
        expect(record.options.style.layers[1].source).toBe('export-road-names:a.pmtiles');
        expect(record.captures).toEqual([{type: 'image/png', visible: ['roads_labels_minor', 'roads_labels_major']}]);
    });

    test('an edge a hair past the edge of the world is the edge of the world', async () => {
        // What the map's arithmetic makes of the last quadrangle before the antimeridian.
        const east = await renderExport({
            MapClass: fakeMapClass({captures: [], bounds: [179.875, 0, 180.00000000000125, 0.125]}),
            style, frame, groups,
        });
        expect(east.bounds).toEqual([179.875, 0, 180, 0.125]);

        const west = await renderExport({
            MapClass: fakeMapClass({captures: [], bounds: [-180.00000000000125, 0, -179.875, 0.125]}),
            style, frame, groups,
        });
        expect(west.bounds).toEqual([-180, 0, -179.875, 0.125]);

        // A map which is really across the antimeridian is left as it is, for the API to refuse.
        const across = await renderExport({
            MapClass: fakeMapClass({captures: [], bounds: [179.9, 0, 180.1, 0.125]}), style, frame, groups,
        });
        expect(across.bounds).toEqual([179.9, 0, 180.1, 0.125]);
    });

    test('nothing is left behind, whether it works or not', async () => {
        const record = {captures: []};
        await renderExport({MapClass: fakeMapClass(record), style, frame, groups});
        expect(record.removed).toBe(true);
        expect(record.options.container.isConnected).toBe(false);

        const failed = {captures: [], failBlob: true};
        await expect(renderExport({MapClass: fakeMapClass(failed), style, frame, groups}))
            .rejects.toThrow('could not be made into an image');
        expect(failed.removed).toBe(true);
        expect(failed.options.container.isConnected).toBe(false);
    });

    test('a photograph with no gaps is a JPEG, and one with gaps is not', async () => {
        const photo = [{name: 'Satellite', ids: ['water'], raster: true}];
        const gaps = {captures: []};
        await renderExport({MapClass: fakeMapClass(gaps), style, frame, groups: photo});
        expect(gaps.captures[0].type).toBe('image/png');

        const opaque = new Uint8ClampedArray([9, 9, 9, 255, 9, 9, 9, 255]);
        getContext.mockImplementation(() => ({
            clearRect: jest.fn(), drawImage: jest.fn(), getImageData: () => ({data: opaque}),
        }));
        const whole = {captures: []};
        await renderExport({MapClass: fakeMapClass(whole), style, frame, groups: photo});
        expect(whole.captures[0].type).toBe('image/jpeg');

        // A photograph which ends a little inside the map: all of it reduced has no gap to see, and
        // one of its edges, looked at by itself, is all gap.
        const looks = [];
        getContext.mockImplementation(() => ({
            clearRect: jest.fn(),
            drawImage: (canvas, x, y, width, height) => looks.push([x, y, width, height]),
            getImageData: () => ({data: looks.length === 5 ? new Uint8ClampedArray([0, 0, 0, 0]) : opaque}),
        }));
        const strip = {captures: []};
        await renderExport({MapClass: fakeMapClass(strip), style, frame, groups: photo});
        expect(strip.captures[0].type).toBe('image/png');
        // All of it, then its top, bottom, left and right edges.
        const [[, , width, height]] = looks;
        expect(looks).toEqual([
            [0, 0, width, height],
            [0, 0, width, 1], [0, height - 1, width, 1], [0, 0, 1, height], [width - 1, 0, 1, height],
        ]);
        // What is not a photograph is never a JPEG, gaps or none.
        const drawn = {captures: []};
        await renderExport({MapClass: fakeMapClass(drawn), style, frame, groups: groups.slice(0, 1)});
        expect(drawn.captures[0].type).toBe('image/png');
    });

    test('stops before a map is made when it is cancelled while the names of roads are read', async () => {
        const record = {captures: []};
        let cancelled = false;
        const readTile = jest.fn(async () => {
            cancelled = true;
            return null;
        });
        await expect(renderExport({
            MapClass: fakeMapClass(record), style: TOWN, frame, readTile, isCancelled: () => cancelled,
            groups: [{name: 'Labels', ids: ['roads_labels_minor']}],
        })).rejects.toMatchObject({cancelled: true});
        expect(record.maps).toBeUndefined();
    });

    test('stops between two groups when it is cancelled, and leaves nothing behind', async () => {
        const record = {captures: []};
        const progress = [];
        const rendering = renderExport({
            MapClass: fakeMapClass(record), style, frame, groups,
            onProgress: name => progress.push(name),
            // Cancelled while the first group is drawn.
            isCancelled: () => record.captures.length >= 1,
        });
        await expect(rendering).rejects.toMatchObject({cancelled: true});
        // The second group was not drawn, nor said to be.
        expect(record.captures).toHaveLength(1);
        expect(progress).toEqual(['Water']);
        expect(record.removed).toBe(true);
    });

    test('a map which never finishes drawing is given up on', async () => {
        jest.useFakeTimers();
        try {
            const record = {captures: [], neverIdle: true};
            const rendering = renderExport({MapClass: fakeMapClass(record), style, frame, groups});
            const failure = expect(rendering).rejects.toThrow('took too long');
            // Once the map has loaded and is waiting to be drawn, the time runs out.
            for (let i = 0; i < 20; i++) await Promise.resolve();
            // The time the page can not be seen (another tab is in front) is not counted: nothing
            // is drawn then.
            const hidden = jest.spyOn(document, 'hidden', 'get').mockReturnValue(true);
            jest.advanceTimersByTime(600_000);
            hidden.mockRestore();
            jest.advanceTimersByTime(119_000);
            expect(record.removed).toBeFalsy();
            jest.advanceTimersByTime(2_000);
            await failure;
            expect(record.removed).toBe(true);
        } finally {
            jest.useRealTimers();
        }
    });
});

describe('what is written on the sheet', () => {
    const style = {
        sources: {
            basemap: {type: 'vector'},
            satellite: {type: 'raster', attribution: '<a href="https://example.com">Imagery</a> &copy;  Somebody'},
            'overlay:towers': {type: 'vector', attribution: 'Towers by Somebody Else'},
            unused: {type: 'vector', attribution: 'Not on this map'},
        },
        layers: [
            {id: 'background', type: 'background'},
            {id: 'water', type: 'fill', source: 'basemap'},
            {id: 'roads', type: 'line', source: 'basemap'},
            {id: 'satellite', type: 'raster', source: 'satellite'},
            {id: 'overlay:towers:points', type: 'circle', source: 'overlay:towers'},
            {id: 'hidden', type: 'fill', source: 'unused'},
        ],
    };
    // The basemap learns where it is from when its file is read.
    const loaded = {basemap: {attribution: '© OpenStreetMap contributors'}};
    const map = {getStyle: () => style, getSource: id => loaded[id]};
    const groups = [
        {name: 'Background', ids: ['background']},
        {name: 'Water', ids: ['water']},
        {name: 'Roads', ids: ['roads']},
        {name: 'Satellite', ids: ['satellite']},
        {name: 'Towers', ids: ['overlay:towers:points']},
    ];

    test('says where the data of the exported layers is from, once each, as text', () => {
        expect(exportCredits(map, groups)).toEqual([
            '© OpenStreetMap contributors', 'Imagery © Somebody', 'Towers by Somebody Else',
        ]);
        expect(exportCredits(map, groups.slice(0, 1))).toEqual([]);
        expect(exportCredits(map, [])).toEqual([]);
    });

    test('an attribution which names many sources is each of them', () => {
        const many = {
            getStyle: () => ({
                sources: {a: {type: 'vector'}, b: {type: 'vector'}},
                layers: [{id: 'a', type: 'line', source: 'a'}, {id: 'b', type: 'line', source: 'b'}],
            }),
            getSource: id => ({
                a: {attribution: '© OpenStreetMap contributors | © OpenMapTiles |  Somebody'},
                b: {attribution: 'Somebody | <a href="#">Somebody Else</a> | '},
            })[id],
        };
        expect(exportCredits(many, [{name: 'A', ids: ['a', 'b']}])).toEqual([
            '© OpenStreetMap contributors', '© OpenMapTiles', 'Somebody', 'Somebody Else',
        ]);
    });

    test('says the day as the person exporting has it', () => {
        expect(exportDate(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
        expect(exportDate(new Date(2026, 10, 15))).toBe('2026-11-15');
    });

    test('is the name of the quadrangle, its credits and the day', () => {
        expect(exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15))).toEqual({
            name: '61°07′30″N 150°00′W', credits: ['© OpenStreetMap contributors'], date: '2026-11-15',
        });
    });

    test('says how far apart the contour lines are, when the map has them', () => {
        const contours = {interval: 40, unit: 'feet'};
        const sheet = exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15), null, contours);
        expect(sheet.contours).toEqual(contours);
        expect(exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15), null, null))
            .not.toHaveProperty('contours');
    });

    test('has the legend of the map, when the map has one', () => {
        const legend = {ground: [1, 1, 1], lines: [{label: 'Highway', color: [0, 0, 0], width: 1}]};
        const sheet = exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15), null, null, legend);
        expect(sheet.legend).toEqual(legend);
        expect(exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15))).not.toHaveProperty('legend');
    });
});

describe('how far apart the contour lines of an exported map are', () => {
    const exported = [
        {name: 'Water', ids: ['water']},
        {name: 'Contours', ids: ['contour-lines', 'contour-lines-major', 'contour-labels']},
    ];
    const parts = ['contour-lines', 'contour-labels'];

    test('is the least of the two intervals, in the unit the map measures in', () => {
        expect(exportContours(exported, parts, [40, 200], true)).toEqual({interval: 40, unit: 'feet'});
        expect(exportContours(exported, parts, [20, 100], false)).toEqual({interval: 20, unit: 'meters'});
        // The darker lines alone are still contour lines.
        expect(exportContours([{name: 'Contours', ids: ['contour-lines-major']}], parts, [40, 200], true))
            .toEqual({interval: 40, unit: 'feet'});
    });

    test('is nothing when the contours are not exported, or are not drawn', () => {
        expect(exportContours(exported.slice(0, 1), parts, [40, 200], true)).toBeNull();
        expect(exportContours([], parts, [40, 200], true)).toBeNull();
        expect(exportContours(exported, parts, null, true)).toBeNull();
    });
});

describe('what the PDF is called', () => {
    test('says where it is of', () => {
        expect(exportFileName(ANCHORAGE)).toBe('wrolpi-map_24k_N61.125_W150.000.pdf');
        expect(exportFileName(quadAt(151.21, -33.87))).toBe('wrolpi-map_24k_S33.875_E151.125.pdf');
        expect(exportTitle(ANCHORAGE)).toBe('1:24,000 61°07′30″N 150°00′W');
    });

    test('says what the USGS calls it, when it calls it anything', () => {
        const berthoud = {name: 'Berthoud', state: 'Colorado', exact: true};
        const anchorage = {name: 'Anchorage A-8 NW', state: 'Alaska', exact: false};
        expect(exportFileName(BERTHOUD, berthoud)).toBe('wrolpi-map_24k_Berthoud_N40.250_W105.125.pdf');
        expect(exportFileName(ANCHORAGE, anchorage)).toBe('wrolpi-map_24k_Anchorage_A_8_NW_N61.125_W150.000.pdf');
        expect(exportFileName(BERTHOUD, {name: '../Ni‘ihau: “North”?'})).toBe(
            'wrolpi-map_24k_Ni_ihau_North_N40.250_W105.125.pdf');
        // An accent is left off its letter.
        expect(exportFileName(BERTHOUD, {name: 'Cañon City'})).toBe('wrolpi-map_24k_Canon_City_N40.250_W105.125.pdf');
        expect(exportFileName(BERTHOUD, {name: '///'})).toBe('wrolpi-map_24k_N40.250_W105.125.pdf');
        expect(exportTitle(BERTHOUD, berthoud)).toBe('1:24,000 Berthoud, Colorado');
        // A quadrangle of the grid which is not all of the named one is a part of it.
        expect(exportTitle(ANCHORAGE, anchorage)).toBe('1:24,000 Part of Anchorage A-8 NW, Alaska');
        const map = {getStyle: () => ({layers: [], sources: {}}), getSource: () => undefined};
        expect(exportSheet(BERTHOUD, map, [], new Date(2026, 10, 15), berthoud)).toEqual({
            name: 'Berthoud, Colorado', credits: [], date: '2026-11-15',
        });
        expect(exportSheet(BERTHOUD, map, [], new Date(2026, 10, 15), null).name).toBe('40°15′N 105°07′30″W');
    });
});
