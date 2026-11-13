import {
    addOverlaysToStyle,
    buildOverlayLayers,
    buildOverlaySource,
    isOverlayEnabled,
    isOverlayLayerEnabled,
    loadOverlayState,
    overlayColor,
    overlayLabel,
    overlayPopupHtml,
    planMapFiles,
    pmtilesUrl,
    saveOverlayState,
    setAllOverlayLayersEnabled,
    setOverlayEnabled,
    setOverlayLayerEnabled,
    STORAGE_KEY_OVERLAYS,
} from './mapOverlays';

const file = (map_path, extra = {}) => ({
    name: map_path.split('/').pop(), map_path, path: `map/${map_path}`,
    kind: 'overlay', tile_type: 'mvt', visible: true, size: 1, vector_layers: [], ...extra,
});
const layer = (id, geometry = null) => ({id, geometry, minzoom: 0, maxzoom: 8, description: null});

const FEATURES = file('extras/features.pmtiles', {
    title: 'Features',
    vector_layers: [layer('power_lines', 'LineString'), layer('towers', 'Point'), layer('flood_zones', 'Polygon')],
});
const SATELLITE = file('satellite.pmtiles', {tile_type: 'jpeg'});

describe('planMapFiles', () => {
    const planet = file('20260329.pmtiles', {kind: 'basemap', size: 100});
    const region = file('regions/oregon.pmtiles', {kind: 'basemap', size: 5});
    const terrain = file('terrain-planet.pmtiles', {kind: 'terrain', tile_type: 'webp'});
    const unreadable = file('broken.pmtiles', {kind: 'unknown', tile_type: null});

    test('a planet file replaces the regional basemaps, but not the overlays or terrain', () => {
        const plan = planMapFiles([planet, region, terrain, FEATURES, SATELLITE, unreadable]);
        expect(plan.planet).toBe(planet);
        expect(plan.regions).toEqual([]);
        expect(plan.terrain).toBe(terrain);
        expect(plan.overlays).toEqual([FEATURES, SATELLITE]);
    });

    test('without a planet file the regional basemaps are drawn', () => {
        const plan = planMapFiles([region, FEATURES]);
        expect(plan.planet).toBeNull();
        expect(plan.regions).toEqual([region]);
        expect(plan.overlays).toEqual([FEATURES]);
    });

    test('a file which is not a basemap is never drawn as one, whatever it is named', () => {
        // Named like a planet file, but its layers are not the basemap schema.
        const plan = planMapFiles([file('planet-features.pmtiles'), region]);
        expect(plan.planet).toBeNull();
        expect(plan.regions).toEqual([region]);
    });

    test('an ignored file is not drawn at all', () => {
        const plan = planMapFiles([
            {...planet, visible: false}, region,
            {...terrain, visible: false}, {...FEATURES, visible: false}, SATELLITE,
        ]);
        // Ignoring the planet file brings the regional basemaps back.
        expect(plan.planet).toBeNull();
        expect(plan.regions).toEqual([region]);
        expect(plan.terrain).toBeNull();
        expect(plan.overlays).toEqual([SATELLITE]);
    });

    test('no files', () => {
        expect(planMapFiles(undefined)).toEqual({planet: null, regions: [], terrain: null, overlays: []});
    });
});

describe('overlayLabel', () => {
    test('is the name the file gives itself', () => {
        expect(overlayLabel(FEATURES, [FEATURES, SATELLITE])).toBe('Features');
    });

    test('is the file name when the file has no name', () => {
        expect(overlayLabel(SATELLITE, [FEATURES, SATELLITE])).toBe('satellite');
        expect(overlayLabel(file('blank.pmtiles', {title: '  '}))).toBe('blank');
    });

    test('says where a file is when another has the same label', () => {
        const other = file('older/features.pmtiles', {title: 'Features'});
        expect(overlayLabel(FEATURES, [FEATURES, other])).toBe('Features (extras/features.pmtiles)');
        expect(overlayLabel(other, [FEATURES, other])).toBe('Features (older/features.pmtiles)');
    });
});

describe('overlayColor', () => {
    test('is the same for the same layer, and a color', () => {
        expect(overlayColor('power_lines')).toBe(overlayColor('power_lines'));
        expect(overlayColor('power_lines')).toMatch(/^#[0-9a-f]{6}$/);
    });

    test('differs between layers', () => {
        const colors = new Set(['power_lines', 'towers', 'flood_zones', 'water', 'place'].map(overlayColor));
        expect(colors.size).toBeGreaterThan(1);
    });
});

describe('what the user chose to see', () => {
    beforeEach(() => localStorage.clear());

    test('an overlay is hidden until it is turned on', () => {
        expect(isOverlayEnabled({}, FEATURES)).toBe(false);
        expect(isOverlayEnabled(setOverlayEnabled({}, FEATURES, true), FEATURES)).toBe(true);
    });

    test('the layers of a file are on until they are turned off', () => {
        let state = setOverlayEnabled({}, FEATURES, true);
        expect(isOverlayLayerEnabled(state, FEATURES, 'towers')).toBe(true);
        state = setOverlayLayerEnabled(state, FEATURES, 'towers', false);
        expect(isOverlayLayerEnabled(state, FEATURES, 'towers')).toBe(false);
        expect(isOverlayLayerEnabled(state, FEATURES, 'power_lines')).toBe(true);
        // Turning a layer off does not turn the file off.
        expect(isOverlayEnabled(state, FEATURES)).toBe(true);
    });

    test('all the layers of a file can be turned off and on', () => {
        let state = setAllOverlayLayersEnabled(setOverlayEnabled({}, FEATURES, true), FEATURES, false);
        expect(FEATURES.vector_layers.map(l => isOverlayLayerEnabled(state, FEATURES, l.id)))
            .toEqual([false, false, false]);
        expect(isOverlayEnabled(state, FEATURES)).toBe(true);
        state = setAllOverlayLayersEnabled(state, FEATURES, true);
        expect(FEATURES.vector_layers.map(l => isOverlayLayerEnabled(state, FEATURES, l.id)))
            .toEqual([true, true, true]);
    });

    test('is remembered by this browser', () => {
        expect(loadOverlayState()).toEqual({});
        const state = setOverlayLayerEnabled(setOverlayEnabled({}, FEATURES, true), FEATURES, 'towers', false);
        saveOverlayState(state);
        expect(loadOverlayState()).toEqual({
            'extras/features.pmtiles': {enabled: true, layers: {towers: false}},
        });
    });

    test('a broken saved value is forgotten', () => {
        localStorage.setItem(STORAGE_KEY_OVERLAYS, '{not json');
        expect(loadOverlayState()).toEqual({});
        localStorage.setItem(STORAGE_KEY_OVERLAYS, '[1, 2]');
        expect(loadOverlayState()).toEqual({});
    });
});

describe('the style of an overlay', () => {
    test('a file is fetched from where it is in the media directory', () => {
        expect(pmtilesUrl('map/extras/my features.pmtiles')).toBe('pmtiles:///media/map/extras/my%20features.pmtiles');
        expect(buildOverlaySource(FEATURES)).toEqual({type: 'vector', url: 'pmtiles:///media/map/extras/features.pmtiles'});
        expect(buildOverlaySource(SATELLITE)).toEqual({
            type: 'raster', url: 'pmtiles:///media/map/satellite.pmtiles', tileSize: 256,
        });
    });

    test("only the text of a file's attribution reaches the page", () => {
        const source = buildOverlaySource({
            ...FEATURES,
            attribution: '&copy; <a href="https://example.com" onclick="alert(1)">Somebody</a><img src=x onerror=alert(1)>',
        });
        expect(source.attribution).toBe('© Somebody');
        expect(buildOverlaySource({...FEATURES, attribution: '<b>&lt;script&gt;</b>'}).attribution)
            .toBe('&lt;script&gt;');
    });

    test('a layer is drawn the one way its geometry needs', () => {
        const layers = buildOverlayLayers(FEATURES, setOverlayEnabled({}, FEATURES, true));
        expect(layers.map(l => [l.id, l.type, l['source-layer']])).toEqual([
            ['overlay:extras/features.pmtiles:power_lines:line', 'line', 'power_lines'],
            ['overlay:extras/features.pmtiles:towers:circle', 'circle', 'towers'],
            ['overlay:extras/features.pmtiles:flood_zones:fill', 'fill', 'flood_zones'],
        ]);
        expect(layers.every(l => l.source === 'overlay:extras/features.pmtiles' && !l.filter)).toBe(true);
        expect(layers[0].paint['line-color']).toBe(overlayColor('power_lines'));
    });

    test('a layer of unknown geometry is drawn every way, each limited to its geometry', () => {
        const unknown = file('unknown.pmtiles', {vector_layers: [layer('things')]});
        const layers = buildOverlayLayers(unknown, {});
        expect(layers.map(l => [l.type, l.filter])).toEqual([
            ['fill', ['==', '$type', 'Polygon']],
            ['line', ['==', '$type', 'LineString']],
            ['circle', ['==', '$type', 'Point']],
        ]);
    });

    test('a raster file is one layer', () => {
        expect(buildOverlayLayers(SATELLITE, {})).toEqual([{
            id: 'overlay:satellite.pmtiles:raster', type: 'raster', source: 'overlay:satellite.pmtiles',
            layout: {visibility: 'none'},
        }]);
    });

    test('layers are visible only as the user chose', () => {
        const visibility = state => buildOverlayLayers(FEATURES, state).map(l => l.layout.visibility);
        // A new overlay starts hidden.
        expect(visibility({})).toEqual(['none', 'none', 'none']);
        let state = setOverlayEnabled({}, FEATURES, true);
        expect(visibility(state)).toEqual(['visible', 'visible', 'visible']);
        state = setOverlayLayerEnabled(state, FEATURES, 'towers', false);
        expect(visibility(state)).toEqual(['visible', 'none', 'visible']);
        // Turning the file off hides every layer, and remembers which were on.
        state = setOverlayEnabled(state, FEATURES, false);
        expect(visibility(state)).toEqual(['none', 'none', 'none']);
        expect(visibility(setOverlayEnabled(state, FEATURES, true))).toEqual(['visible', 'none', 'visible']);
    });

    test('a raster overlay goes under the basemap labels, vector overlays on top', () => {
        const sources = {basemap: {}};
        const layers = [
            {id: 'earth', type: 'fill'}, {id: 'roads', type: 'line'},
            {id: 'places', type: 'symbol'}, {id: 'pois', type: 'symbol'},
        ];
        addOverlaysToStyle(sources, layers, [FEATURES, SATELLITE], {});
        expect(Object.keys(sources)).toEqual(['basemap', 'overlay:extras/features.pmtiles', 'overlay:satellite.pmtiles']);
        expect(layers.map(l => l.id)).toEqual([
            'earth', 'roads',
            'overlay:satellite.pmtiles:raster',
            'places', 'pois',
            // Fills under lines under points.
            'overlay:extras/features.pmtiles:flood_zones:fill',
            'overlay:extras/features.pmtiles:power_lines:line',
            'overlay:extras/features.pmtiles:towers:circle',
        ]);
    });

    test('a raster overlay is drawn last when the basemap has no labels', () => {
        const layers = [{id: 'earth', type: 'fill'}];
        addOverlaysToStyle({}, layers, [SATELLITE], {});
        expect(layers.map(l => l.id)).toEqual(['earth', 'overlay:satellite.pmtiles:raster']);
    });
});

describe('overlayPopupHtml', () => {
    const feature = (sourceLayer, properties) => ({sourceLayer, properties});

    test('nothing was clicked', () => {
        expect(overlayPopupHtml([])).toBeNull();
        expect(overlayPopupHtml(undefined)).toBeNull();
    });

    test('names the feature and lists its attributes', () => {
        const html = overlayPopupHtml([feature('towers', {name: 'Big Tower', height_m: 120, owner: ''})]);
        expect(html).toContain('<strong>Big Tower</strong>');
        expect(html).toContain('<small>towers</small>');
        expect(html).toContain('<small>height_m: 120</small>');
        // An empty attribute says nothing.
        expect(html).not.toContain('owner');
    });

    test('a feature without a name is called by its layer', () => {
        const html = overlayPopupHtml([feature('power_lines', {voltage: 230000})]);
        expect(html).toContain('<strong>power_lines</strong>');
        expect(html).toContain('<small>voltage: 230000</small>');
    });

    test("a file's text cannot add markup to the page", () => {
        const html = overlayPopupHtml([feature('<b>layer</b>', {name: '<img src=x onerror=alert(1)>', '<i>k</i>': '<u>v</u>'})]);
        expect(html).not.toContain('<img');
        expect(html).not.toContain('<b>');
        expect(html).not.toContain('<i>');
        expect(html).not.toContain('<u>');
        expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    });

    test('the same feature drawn twice is listed once, and a long list is cut short', () => {
        const tower = feature('towers', {name: 'Big Tower'});
        expect(overlayPopupHtml([tower, {...tower}]).match(/Big Tower/g)).toHaveLength(1);

        const many = [1, 2, 3, 4, 5].map(i => feature('towers', {name: `Tower ${i}`}));
        const html = overlayPopupHtml(many);
        expect(html).toContain('Tower 3');
        expect(html).not.toContain('Tower 4');

        const properties = Object.fromEntries([...Array(20).keys()].map(i => [`key${i}`, i]));
        const long = overlayPopupHtml([feature('towers', properties)]);
        expect(long).toContain('key11: 11');
        expect(long).not.toContain('key12: 12');
        expect(long).toContain('8 more');
    });
});
