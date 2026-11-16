import {
    BACKGROUND_GROUP,
    exportFileName,
    exportCredits,
    exportDate,
    exportFrame,
    exportGroups,
    exportSheet,
    exportStyle,
    exportTitle,
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

        getContext.mockImplementation(() => ({
            drawImage: jest.fn(),
            getImageData: () => ({data: new Uint8ClampedArray([9, 9, 9, 255, 9, 9, 9, 255])}),
        }));
        const whole = {captures: []};
        await renderExport({MapClass: fakeMapClass(whole), style, frame, groups: photo});
        expect(whole.captures[0].type).toBe('image/jpeg');
        // What is not a photograph is never a JPEG, gaps or none.
        const drawn = {captures: []};
        await renderExport({MapClass: fakeMapClass(drawn), style, frame, groups: groups.slice(0, 1)});
        expect(drawn.captures[0].type).toBe('image/png');
    });

    test('a map which never finishes drawing is given up on', async () => {
        jest.useFakeTimers();
        try {
            const record = {captures: [], neverIdle: true};
            const rendering = renderExport({MapClass: fakeMapClass(record), style, frame, groups});
            const failure = expect(rendering).rejects.toThrow('took too long');
            // Once the map has loaded and is waiting to be drawn, the time runs out.
            for (let i = 0; i < 20; i++) await Promise.resolve();
            jest.advanceTimersByTime(121_000);
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

    test('says the day as the person exporting has it', () => {
        expect(exportDate(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
        expect(exportDate(new Date(2026, 10, 15))).toBe('2026-11-15');
    });

    test('is the name of the quadrangle, its credits and the day', () => {
        expect(exportSheet(ANCHORAGE, map, groups.slice(1, 2), new Date(2026, 10, 15))).toEqual({
            name: '61°07′30″N 150°00′W', credits: ['© OpenStreetMap contributors'], date: '2026-11-15',
        });
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
