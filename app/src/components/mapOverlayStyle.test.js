import {
    adaptOverlayStyle,
    bundledFont,
    loadOverlayStyle,
    loadOverlayStyles,
    addMissingOverlayIcon,
    missingOverlayIcon,
    OVERLAY_ICONS_SPRITE_ID,
} from './mapOverlayStyle';
import {buildOverlayLayers, overlayToggleLayers, setOverlayEnabled, setOverlayLayerEnabled} from './mapOverlays';

// A style written for another map is adapted to draw one overlay file on this map.

const layer = (id) => ({id, geometry: null, minzoom: 0, maxzoom: 13, description: null});
const FILE = {
    name: 'features.pmtiles', map_path: 'extras/features.pmtiles', path: 'map/extras/features.pmtiles',
    kind: 'overlay', tile_type: 'mvt', visible: true,
    style_path: 'map/extras/style.json',
    vector_layers: [layer('repeaters'), layer('roads'), layer('parks')],
};
const SOURCE = 'overlay:extras/features.pmtiles';
// The map's own icons: every image a style names is one of these.
const ICONS = 'overlay-icons';

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

    test('the font of a part of the text', () => {
        const style = {
            ...STYLE,
            layers: [{
                ...STYLE.layers[6],
                layout: {
                    'text-font': ['Roboto Condensed Regular'],
                    'text-field': ['format',
                        ['get', 'name'], {'text-font': ['literal', ['Roboto Condensed Italic']]},
                        '\n', {},
                        ['get', 'ele'], {'text-font': ['literal', ['Atkinson Hyperlegible Mono Bold']], 'font-scale': 0.8}],
                },
            }],
        };
        const result = adapted(style);
        expect(result.skipped).toBe(0);
        expect(byId(result, 'repeaters').layout['text-field']).toEqual(['format',
            ['get', 'name'], {'text-font': ['literal', ['Noto Sans Italic']]},
            '\n', {},
            ['get', 'ele'], {'text-font': ['literal', ['Noto Sans Medium']], 'font-scale': 0.8}]);
    });

    test('text without a font is given one the map has', () => {
        const style = {...STYLE, layers: [{...STYLE.layers[6], layout: {'text-field': ['get', 'callsign']}}]};
        expect(byId(adapted(style), 'repeaters').layout['text-font']).toEqual(['Noto Sans Regular']);
        // A layer without text is not given a font.
        expect(byId(adapted(), 'roads').layout).toBeUndefined();
    });
});

describe('icons', () => {
    const withIcon = (icon, file = FILE) => {
        const style = {...STYLE, layers: [{...STYLE.layers[6], layout: {'icon-image': icon}}]};
        return adapted(style, file);
    };

    test("an image is one of the map's overlay icons, never of the style's own sprite", () => {
        expect(OVERLAY_ICONS_SPRITE_ID).toBe(ICONS);
        expect(byId(adapted(), 'repeaters').layout['icon-image']).toBe(`${ICONS}:ham_radio`);
        expect(byId(withIcon('{class}_11'), 'repeaters').layout['icon-image']).toBe(`${ICONS}:{class}_11`);
    });

    test('an image chosen by an expression: what it evaluates to is renamed, not its strings', () => {
        const icon = ['match', ['get', 'class'], 'hospital', 'hospital', 'pin'];
        const result = withIcon(icon);
        expect(result.skipped).toBe(0);
        const value = byId(result, 'repeaters').layout['icon-image'];
        // The expression is intact inside the wrapping: the label "hospital" still matches the class.
        expect(JSON.stringify(value)).toContain(JSON.stringify(icon));
        expect(JSON.stringify(value)).toContain(`"${ICONS}:"`);
    });

    describe('an image named by a property function', () => {
        // The wrapping every image gets; `expression` is what gives the name.
        const wrapped = expression => ['image', ['let', 'wrolpi_image', ['to-string', expression],
            ['case', ['==', ['var', 'wrolpi_image'], ''], '',
                ['concat', `${ICONS}:`, ['var', 'wrolpi_image']]]]];
        const iconOf = (fn) => {
            const result = withIcon(fn);
            // The layer is kept: its text is drawn whatever becomes of its image.
            expect(result.skipped).toBe(0);
            expect(result.layers).toHaveLength(1);
            return byId(result, 'repeaters').layout['icon-image'];
        };

        test('the value of a property', () => {
            expect(iconOf({type: 'identity', property: 'icon'}))
                .toEqual(wrapped(['coalesce', ['get', 'icon'], '']));
            expect(iconOf({type: 'identity', property: 'icon', default: 'pin'}))
                .toEqual(wrapped(['coalesce', ['get', 'icon'], 'pin']));
        });

        test('a name for each value of a property', () => {
            expect(iconOf({property: 'class', type: 'categorical', stops: [['hospital', 'cross'], ['fuel', 'pump']]}))
                .toEqual(wrapped(['match', ['get', 'class'], 'hospital', 'cross', 'fuel', 'pump', '']));
            expect(iconOf({property: 'rank', type: 'categorical', stops: [[1, 'big'], [2, 'small']], default: 'pin'}))
                .toEqual(wrapped(['match', ['get', 'rank'], 1, 'big', 2, 'small', 'pin']));
        });

        test('a name for each range of a numeric property', () => {
            expect(iconOf({property: 'height', stops: [[0, 'low'], [100, 'tall']]}))
                .toEqual(wrapped(['step', ['to-number', ['get', 'height'], 0], 'low', 100, 'tall']));
            // A single stop is one name.
            expect(iconOf({property: 'height', type: 'interval', stops: [[10, 'only']]})).toBe(`${ICONS}:only`);
            expect(iconOf({stops: [[10, 'only']]})).toBe(`${ICONS}:only`);
        });

        test('a name for each range of the zoom: each name is renamed, the zoom stays outermost', () => {
            expect(iconOf({stops: [[0, 'dot'], [12, 'tower'], [15, '{class}_big']]}))
                .toEqual(['step', ['zoom'], `${ICONS}:dot`, 12, `${ICONS}:tower`, 15, `${ICONS}:{class}_big`]);
        });

        test('a function which cannot be rewritten: the layer is drawn without the image', () => {
            for (const fn of [
                // By zoom and property at once.
                {property: 'rank', stops: [[{zoom: 0, value: 1}, 'a'], [{zoom: 10, value: 1}, 'b']]},
                {property: 'on', type: 'categorical', stops: [[true, 'a'], [false, 'b']]},
                {property: 'height', type: 'exponential', stops: [[0, 'a'], [1, 'b']]},
                {property: 'height', stops: [[5, 'a'], [1, 'b']]},
                {stops: []},
                {},
            ]) {
                const style = {
                    ...STYLE,
                    layers: [{...STYLE.layers[6], layout: {'icon-image': fn, 'text-field': ['get', 'callsign']}}],
                };
                const result = adapted(style);
                expect(result.layers).toHaveLength(1);
                expect(byId(result, 'repeaters').layout['icon-image']).toBeUndefined();
                expect(byId(result, 'repeaters').layout['text-field']).toEqual(['get', 'callsign']);
            }
        });
    });

    test('an image chosen by the zoom in an expression: the zoom stays outermost', () => {
        const result = withIcon(['step', ['zoom'], 'dot', 12, ['match', ['get', 'class'], 'tower', 'tower', 'pin']]);
        expect(result.skipped).toBe(0);
        const value = byId(result, 'repeaters').layout['icon-image'];
        expect(value.slice(0, 4)).toEqual(['step', ['zoom'], `${ICONS}:dot`, 12]);
        expect(JSON.stringify(value[4])).toContain(JSON.stringify(['match', ['get', 'class'], 'tower', 'tower', 'pin']));
    });

    test("an icon is drawn at its own size, not at a scale of the style's artwork", () => {
        const style = {
            ...STYLE,
            layers: [{
                ...STYLE.layers[6],
                layout: {'icon-image': 'ham_radio', 'icon-size': 0.59, 'icon-anchor': 'bottom'},
            }],
        };
        expect(byId(adapted(style), 'repeaters').layout).toEqual({
            'icon-image': `${ICONS}:ham_radio`, 'icon-anchor': 'bottom',
        });
    });

    test('an icon is dark with a light edge unless its style says otherwise', () => {
        expect(byId(adapted(), 'repeaters').paint).toEqual({
            'icon-color': '#222222', 'icon-halo-color': '#ffffff', 'icon-halo-width': 1,
        });
        const style = {
            ...STYLE,
            layers: [{...STYLE.layers[6], paint: {'icon-color': '#c00', 'text-color': '#00c'}}],
        };
        expect(byId(adapted(style), 'repeaters').paint).toEqual({
            'icon-color': '#c00', 'icon-halo-color': '#ffffff', 'icon-halo-width': 1, 'text-color': '#00c',
        });
        // A layer without an icon is not given an icon's paint.
        expect(byId(adapted(), 'roads').paint).toEqual({'line-color': '#c60'});
    });
});

describe('patterns', () => {
    // A pattern is an image of the style's own sprite, which the map does not use.
    const pattern = (paint, type = 'fill') => {
        const style = {
            ...STYLE,
            layers: [{id: 'parks', type, source: 'features', 'source-layer': 'parks', paint}],
        };
        const result = adapted(style);
        expect(result.skipped).toBe(0);
        return byId(result, 'parks').paint;
    };

    test('a patterned fill is a translucent color, never the opaque black MapLibre would fill it with', () => {
        expect(pattern({'fill-pattern': 'marsh'})).toEqual({'fill-color': '#808080', 'fill-opacity': 0.25});
        // By an expression, or a function, too.
        expect(pattern({'fill-pattern': ['match', ['get', 'class'], 'wet', 'marsh', 'sand']}))
            .toEqual({'fill-color': '#808080', 'fill-opacity': 0.25});
        expect(pattern({'fill-pattern': {type: 'identity', property: 'pattern'}}))
            .toEqual({'fill-color': '#808080', 'fill-opacity': 0.25});
    });

    test("the fill keeps the style's own color and opacity", () => {
        expect(pattern({'fill-pattern': 'marsh', 'fill-color': '#9cf'}))
            .toEqual({'fill-color': '#9cf', 'fill-opacity': 0.25});
        expect(pattern({'fill-pattern': 'marsh', 'fill-color': '#9cf', 'fill-opacity': 0.6}))
            .toEqual({'fill-color': '#9cf', 'fill-opacity': 0.6});
    });

    test('a fill without a pattern is as its style has it', () => {
        expect(pattern({'fill-color': '#9c9'})).toEqual({'fill-color': '#9c9'});
    });

    test('a patterned extrusion is a translucent color too, and keeps its shape', () => {
        expect(pattern({'fill-extrusion-pattern': 'brick'}, 'fill-extrusion'))
            .toEqual({'fill-extrusion-color': '#808080', 'fill-extrusion-opacity': 0.25});
        expect(pattern({'fill-extrusion-pattern': 'brick', 'fill-extrusion-height': ['get', 'height']}, 'fill-extrusion'))
            .toEqual({
                'fill-extrusion-color': '#808080', 'fill-extrusion-opacity': 0.25,
                'fill-extrusion-height': ['get', 'height'],
            });
        // The style's own color and opacity are kept.
        expect(pattern({
            'fill-extrusion-pattern': 'brick', 'fill-extrusion-color': '#a52', 'fill-extrusion-opacity': 0.8,
        }, 'fill-extrusion')).toEqual({'fill-extrusion-color': '#a52', 'fill-extrusion-opacity': 0.8});
        // An extrusion without a pattern is as its style has it.
        expect(pattern({'fill-extrusion-height': 10}, 'fill-extrusion')).toEqual({'fill-extrusion-height': 10});
    });

    test('a patterned line is a plain line', () => {
        expect(pattern({'line-pattern': 'ruling', 'line-width': 2}, 'line'))
            .toEqual({'line-color': '#808080', 'line-width': 2});
        expect(pattern({'line-pattern': 'ruling', 'line-color': '#c00'}, 'line')).toEqual({'line-color': '#c00'});
    });
});

describe('a name the overlay icons do not have', () => {
    class FakeMap {
        images = {};

        hasImage(id) {
            return id in this.images;
        }

        addImage(id, image, options) {
            this.images[id] = {image, options};
        }
    }

    test('is drawn as a dot: a signed distance field, as the icons are', () => {
        const {width, height, data} = missingOverlayIcon();
        expect(data).toHaveLength(width * height * 4);
        const alpha = (x, y) => data[(y * width + x) * 4 + 3];
        const middle = Math.floor(width / 2);
        // Full in the middle, three quarters at the edge of the dot, less beyond it.
        expect(alpha(middle, middle)).toBe(255);
        expect(alpha(0, 0)).toBeLessThan(alpha(middle + 6, middle));
        expect(alpha(middle + 4, middle)).toBeGreaterThan(191);
        expect(alpha(middle + 6, middle)).toBeLessThan(191);
    });

    test('is supplied when the map asks for it', () => {
        const map = new FakeMap();
        expect(addMissingOverlayIcon(map, `${ICONS}:wreck`)).toBe(true);
        expect(map.images[`${ICONS}:wreck`].options).toEqual({sdf: true});
        // Once.
        expect(addMissingOverlayIcon(map, `${ICONS}:wreck`)).toBe(false);
    });

    test("an image of the basemap's is not the overlay icons' to supply", () => {
        const map = new FakeMap();
        expect(addMissingOverlayIcon(map, 'townspot')).toBe(false);
        expect(addMissingOverlayIcon(map, 'default:townspot')).toBe(false);
        expect(map.images).toEqual({});
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
        expect(layers[2].layout['icon-image']).toBe(`${ICONS}:ham_radio`);
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
