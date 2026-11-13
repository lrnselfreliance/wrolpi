import {
    adaptOverlayStyle,
    bundledFont,
    loadOverlayStyle,
    loadOverlayStyles,
    overlaySpriteUrl,
} from './mapOverlayStyle';
import {buildOverlayLayers, overlayToggleLayers, setOverlayEnabled, setOverlayLayerEnabled} from './mapOverlays';

// A style written for another map is adapted to draw one overlay file on this map.

const layer = (id) => ({id, geometry: null, minzoom: 0, maxzoom: 13, description: null});
const FILE = {
    name: 'features.pmtiles', map_path: 'extras/features.pmtiles', path: 'map/extras/features.pmtiles',
    kind: 'overlay', tile_type: 'mvt', visible: true, has_sprite: true,
    style_path: 'map/extras/style.json',
    vector_layers: [layer('repeaters'), layer('roads'), layer('parks')],
};
const SOURCE = 'overlay:extras/features.pmtiles';

// As a style arrives: its own source names and URLs, and layers of sources which are not this file.
const STYLE = {
    version: 8,
    sprite: 'https://example.com/sprites/topo',
    glyphs: 'https://example.com/glyphs/{fontstack}/{range}.pbf',
    sources: {
        features: {type: 'vector', url: 'https://example.com/features.json'},
        relief: {type: 'raster', tiles: ['https://example.com/relief/{z}/{x}/{y}.png']},
        contours: {type: 'vector', url: 'https://example.com/contours.json'},
    },
    layers: [
        {id: 'background', type: 'background', paint: {'background-color': '#fff'}},
        {id: 'relief', type: 'raster', source: 'relief'},
        {id: 'parks', type: 'fill', source: 'features', 'source-layer': 'parks', paint: {'fill-color': '#9c9'}},
        {id: 'contours', type: 'line', source: 'contours', 'source-layer': 'contours'},
        {id: 'roads', type: 'line', source: 'features', 'source-layer': 'roads', paint: {'line-color': '#c60'}},
        // A layer of the file's source which this file does not have.
        {id: 'buildings', type: 'fill', source: 'features', 'source-layer': 'buildings'},
        {
            id: 'repeaters', type: 'symbol', source: 'features', 'source-layer': 'repeaters', minzoom: 10,
            layout: {
                'icon-image': 'ham_radio',
                'text-field': ['get', 'callsign'],
                'text-font': ['Roboto Condensed Bold'],
            },
        },
    ],
};

const adapted = (style = STYLE, file = FILE) => adaptOverlayStyle(style, file);
const byId = (result, id) => result.layers.find(l => l.id.endsWith(`:${id}`));

describe('adaptOverlayStyle', () => {
    test("keeps the layers which draw this file, in the style's order", () => {
        const result = adapted();
        expect(result.layers.map(l => l.id)).toEqual([
            `${SOURCE}:parks:parks`, `${SOURCE}:roads:roads`, `${SOURCE}:repeaters:repeaters`,
        ]);
        expect(result.skipped).toBe(0);
        // What the style said of a layer is kept.
        expect(byId(result, 'roads').paint).toEqual({'line-color': '#c60'});
        expect(byId(result, 'repeaters').minzoom).toBe(10);
    });

    test('draws from the overlay file, and names nothing the style would have fetched', () => {
        const result = adapted();
        expect(new Set(result.layers.map(l => l.source))).toEqual(new Set([SOURCE]));
        expect(JSON.stringify(result)).not.toContain('example.com');
        // The style given is not changed.
        expect(STYLE.layers[2].source).toBe('features');
    });

    test('the source which is this file is the one most of its layers use', () => {
        const style = {
            ...STYLE,
            layers: [
                // Another source has a layer of the same name.
                {id: 'other-roads', type: 'line', source: 'contours', 'source-layer': 'roads'},
                ...STYLE.layers,
            ],
        };
        expect(adapted(style).layers.map(l => l.id)).toEqual([
            `${SOURCE}:parks:parks`, `${SOURCE}:roads:roads`, `${SOURCE}:repeaters:repeaters`,
        ]);
    });

    test('the style can name the source which is this file', () => {
        const style = {...STYLE, metadata: {'wrolpi:source': 'contours'}};
        const file = {...FILE, vector_layers: [layer('contours')]};
        expect(adapted(style, file).layers.map(l => l.id)).toEqual([`${SOURCE}:contours:contours`]);
    });

    test('the style can say the zoom it is meant to be seen from', () => {
        const result = adapted({...STYLE, metadata: {'wrolpi:minzoom': 9}});
        // A layer which already starts later keeps its own zoom.
        expect(result.layers.map(l => l.minzoom)).toEqual([9, 9, 10]);
        // Without it, layers are as the style has them.
        expect(adapted().layers.map(l => l.minzoom)).toEqual([undefined, undefined, 10]);
        expect(adapted({...STYLE, metadata: {'wrolpi:minzoom': 'soon'}}).layers.map(l => l.minzoom))
            .toEqual([undefined, undefined, 10]);
    });

    test('a style of other files draws nothing', () => {
        expect(adapted(STYLE, {...FILE, vector_layers: [layer('towers')]})).toEqual({layers: [], skipped: 0});
        expect(adapted({version: 8}, FILE)).toEqual({layers: [], skipped: 0});
        expect(adapted(null, FILE)).toEqual({layers: [], skipped: 0});
    });

    test('a layer the map could not draw is skipped, and the rest are kept', () => {
        const style = {
            ...STYLE,
            layers: [
                {id: 'bad-paint', type: 'line', source: 'features', 'source-layer': 'roads', paint: {'line-width': 'wide'}},
                {id: 'bad-type', type: 'sparkles', source: 'features', 'source-layer': 'roads'},
                ...STYLE.layers,
            ],
        };
        const result = adapted(style);
        expect(result.skipped).toBe(2);
        expect(result.layers.map(l => l.id)).toEqual([
            `${SOURCE}:parks:parks`, `${SOURCE}:roads:roads`, `${SOURCE}:repeaters:repeaters`,
        ]);
    });

    test('a second layer of the same id is skipped', () => {
        const style = {...STYLE, layers: [...STYLE.layers, STYLE.layers[4]]};
        const result = adapted(style);
        expect(result.skipped).toBe(1);
        expect(result.layers).toHaveLength(3);
    });
});

describe('fonts', () => {
    test('a font the map does not have is replaced by the nearest it has', () => {
        expect(bundledFont('Roboto Condensed Bold')).toBe('Noto Sans Medium');
        expect(bundledFont('Roboto Slab Semibold')).toBe('Noto Sans Medium');
        expect(bundledFont('Roboto Condensed Italic')).toBe('Noto Sans Italic');
        expect(bundledFont('Roboto Condensed Bold Italic')).toBe('Noto Sans Italic');
        expect(bundledFont('Open Sans Regular')).toBe('Noto Sans Regular');
        expect(bundledFont('Noto Sans Regular')).toBe('Noto Sans Regular');
    });

    test('a list of fonts', () => {
        expect(byId(adapted(), 'repeaters').layout['text-font']).toEqual(['Noto Sans Medium']);
        const style = {
            ...STYLE,
            layers: [{
                ...STYLE.layers[6],
                layout: {'text-field': 'x', 'text-font': ['Roboto Bold', 'Arial Unicode MS Bold', 'Roboto Regular']},
            }],
        };
        // Two fonts which become the same one are listed once.
        expect(byId(adapted(style), 'repeaters').layout['text-font']).toEqual(['Noto Sans Medium', 'Noto Sans Regular']);
    });

    test('fonts chosen by an expression', () => {
        const style = {
            ...STYLE,
            layers: [{
                ...STYLE.layers[6],
                layout: {
                    'text-field': 'x',
                    'text-font': ['match', ['get', 'class'],
                        ['city', 'town'], ['literal', ['Roboto Condensed Bold']],
                        ['locality'], ['literal', ['Roboto Condensed Italic']],
                        ['literal', ['Roboto Condensed Regular']]],
                },
            }],
        };
        const result = adapted(style);
        expect(result.skipped).toBe(0);
        expect(byId(result, 'repeaters').layout['text-font']).toEqual(['match', ['get', 'class'],
            ['city', 'town'], ['literal', ['Noto Sans Medium']],
            ['locality'], ['literal', ['Noto Sans Italic']],
            ['literal', ['Noto Sans Regular']]]);
    });
});

describe('icons', () => {
    const withIcon = (icon, file = FILE) => {
        const style = {...STYLE, layers: [{...STYLE.layers[6], layout: {'icon-image': icon}}]};
        return adapted(style, file);
    };

    test("an image is one of the overlay's own sprite", () => {
        expect(byId(adapted(), 'repeaters').layout['icon-image']).toBe(`${SOURCE}:ham_radio`);
        expect(byId(withIcon('{class}_11'), 'repeaters').layout['icon-image']).toBe(`${SOURCE}:{class}_11`);
    });

    test('an image chosen by an expression: what it evaluates to is renamed, not its strings', () => {
        const icon = ['match', ['get', 'class'], 'hospital', 'hospital', 'pin'];
        const result = withIcon(icon);
        expect(result.skipped).toBe(0);
        const value = byId(result, 'repeaters').layout['icon-image'];
        // The expression is intact inside the wrapping: the label "hospital" still matches the class.
        expect(JSON.stringify(value)).toContain(JSON.stringify(icon));
        expect(JSON.stringify(value)).toContain(`"${SOURCE}:"`);
    });

    test('a pattern is an image too', () => {
        const style = {
            ...STYLE,
            layers: [{
                id: 'parks', type: 'fill', source: 'features', 'source-layer': 'parks',
                paint: {'fill-pattern': 'forest', 'fill-opacity': 0.5},
            }],
        };
        expect(byId(adapted(style), 'parks').paint).toEqual({'fill-pattern': `${SOURCE}:forest`, 'fill-opacity': 0.5});
    });

    test('without a sprite sheet there are no images, and the text is still drawn', () => {
        const result = adapted(STYLE, {...FILE, has_sprite: false});
        expect(byId(result, 'repeaters').layout).toEqual({
            'text-field': ['get', 'callsign'], 'text-font': ['Noto Sans Medium'],
        });
        expect(result.skipped).toBe(0);
    });

    test("the sprite is asked of this WROLPi, by the file's path", () => {
        expect(overlaySpriteUrl({map_path: 'extras/my features.pmtiles'}))
            .toBe(`${window.location.origin}/api/map/files/sprite/extras/my%20features.pmtiles`);
    });
});

describe('loadOverlayStyle', () => {
    const respond = (body, ok = true) => {
        global.fetch = jest.fn().mockResolvedValue({ok, json: async () => body});
    };

    test('fetches the style beside the file', async () => {
        respond(STYLE);
        const result = await loadOverlayStyle(FILE);
        expect(global.fetch).toHaveBeenCalledWith('/media/map/extras/style.json');
        expect(result.layers).toHaveLength(3);
    });

    test('a file without a style is not asked for one', async () => {
        respond(STYLE);
        expect(await loadOverlayStyle({...FILE, style_path: null})).toBeNull();
        expect(global.fetch).not.toHaveBeenCalled();
    });

    test('a style which cannot be used is no style', async () => {
        jest.spyOn(console, 'error').mockImplementation(() => {
        });
        respond(STYLE, false);
        expect(await loadOverlayStyle(FILE)).toBeNull();
        // Draws none of this file's layers.
        respond({version: 8, layers: [{id: 'background', type: 'background'}]});
        expect(await loadOverlayStyle(FILE)).toBeNull();
        // Not JSON.
        global.fetch = jest.fn().mockResolvedValue({
            ok: true, json: async () => {
                throw new SyntaxError('Unexpected token');
            },
        });
        expect(await loadOverlayStyle(FILE)).toBeNull();
        global.fetch = jest.fn().mockRejectedValue(new Error('offline'));
        expect(await loadOverlayStyle(FILE)).toBeNull();
    });

    test('each overlay gets its own style, or stays as it was', async () => {
        respond(STYLE);
        const plain = {...FILE, map_path: 'plain.pmtiles', style_path: null};
        const [styled, same] = await loadOverlayStyles([FILE, plain]);
        expect(styled.styleLayers).toHaveLength(3);
        expect(styled.styleSkipped).toBe(0);
        expect(same).toBe(plain);
    });
});

describe('a styled overlay on the map', () => {
    const styled = {...FILE, styleLayers: adapted().layers};
    const visibility = state => buildOverlayLayers(styled, state).map(l => l.layout.visibility);

    test('is drawn with its style, not the generic colors', () => {
        const layers = buildOverlayLayers(styled, setOverlayEnabled({}, styled, true));
        expect(layers.map(l => [l.id, l.type])).toEqual([
            [`${SOURCE}:parks:parks`, 'fill'], [`${SOURCE}:roads:roads`, 'line'],
            [`${SOURCE}:repeaters:repeaters`, 'symbol'],
        ]);
        expect(layers[2].layout['icon-image']).toBe(`${SOURCE}:ham_radio`);
    });

    test('starts hidden, and its layers are shown and hidden by the layer of the file they draw', () => {
        expect(visibility({})).toEqual(['none', 'none', 'none']);
        let state = setOverlayEnabled({}, styled, true);
        expect(visibility(state)).toEqual(['visible', 'visible', 'visible']);
        state = setOverlayLayerEnabled(state, styled, 'roads', false);
        expect(visibility(state)).toEqual(['visible', 'none', 'visible']);
    });

    test('a layer the style hides stays hidden', () => {
        const hidden = {
            ...styled,
            styleLayers: styled.styleLayers.map(l => l.type === 'fill' ? {...l, layout: {visibility: 'none'}} : l),
        };
        const layers = buildOverlayLayers(hidden, setOverlayEnabled({}, hidden, true));
        expect(layers.map(l => l.layout.visibility)).toEqual(['none', 'visible', 'visible']);
    });

    test('only the layers its style draws can be chosen', () => {
        const file = {...styled, vector_layers: [...FILE.vector_layers, layer('buildings')]};
        expect(overlayToggleLayers(file).map(l => l.id)).toEqual(['repeaters', 'roads', 'parks']);
        // Without a style, every layer of the file is drawn.
        expect(overlayToggleLayers({...file, styleLayers: undefined}).map(l => l.id))
            .toEqual(['repeaters', 'roads', 'parks', 'buildings']);
    });
});
