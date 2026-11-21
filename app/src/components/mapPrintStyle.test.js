import layers, {namedTheme} from 'protomaps-themes-base';
import {
    chosenColors, EXPORT_LOOKS, lookStyle, mix, PRINT_COLORS, PRINT_CONTOURS, PRINT_LOOK, PRINT_PAINT, PRINT_SWATCHES,
    printContours, printLayers, printTheme, savedExportLook, savedPrintColors, saveExportLook, savePrintColors,
} from './mapPrintStyle';

describe('the printed map', () => {
    const printed = printLayers('a.pmtiles');
    const byId = Object.fromEntries(printed.map(layer => [layer.id, layer]));

    test('has every layer the light map has, of the same source', () => {
        const light = layers('a.pmtiles', 'light');
        expect(printed.map(layer => layer.id)).toEqual(light.map(layer => layer.id));
        expect(new Set(printed.map(layer => layer.source).filter(Boolean))).toEqual(new Set(['a.pmtiles']));
    });

    test('is drawn on white, in dark lines', () => {
        expect(byId.background.paint['background-color']).toBe('#ffffff');
        expect(byId.earth.paint['fill-color']).toBe('#ffffff');
        // The edge of a road is what is seen of it on paper.
        expect(byId.roads_minor_casing.paint['line-color']).toBe('#4d4d4d');
        expect(byId.roads_highway.paint['line-color']).toBe(PRINT_COLORS.highway);
        expect(byId.roads_labels_minor.paint['text-color']).toBe('#1a1a1a');
        expect(byId.roads_labels_minor.paint['text-halo-color']).toBe('#ffffff');
    });

    test('has lines which are wide enough to see', () => {
        // A stream is not the color of a lake, nor half a pixel.
        expect(byId.water_stream.paint['line-width']).toBeGreaterThan(1);
        expect(byId.water_stream.paint['line-color']).not.toBe(byId.water.paint['fill-color']);
        // A path is drawn however deep the map is, and is still a broken line.
        expect(byId.roads_other.paint['line-width']).toBe(1.2);
        expect(byId.roads_other.paint['line-dasharray']).toEqual([4, 2]);
        expect(byId.roads_rail.paint['line-opacity']).toBe(1);
    });

    test('changes only layers a basemap has, and colors it has', () => {
        for (const id of Object.keys(PRINT_PAINT)) expect(Object.keys(byId)).toContain(id);
        const light = namedTheme('light');
        for (const color of Object.keys(PRINT_COLORS)) expect(Object.keys(light)).toContain(color);
        expect(Object.keys(printTheme()).sort()).toEqual(Object.keys(light).sort());
        expect(Object.keys(PRINT_COLORS.pois).sort()).toEqual(Object.keys(light.pois).sort());
        expect(Object.keys(PRINT_COLORS.landcover).sort()).toEqual(Object.keys(light.landcover).sort());
    });
});

describe('the look a map is exported in', () => {
    beforeEach(() => localStorage.clear());

    test('is the printed map until another is chosen, and is remembered', () => {
        expect(savedExportLook()).toBe(PRINT_LOOK);
        saveExportLook('dark');
        expect(savedExportLook()).toBe('dark');
        // What is not a look is not remembered as one.
        localStorage.setItem('wrolpi-map-export-look', 'sepia');
        expect(savedExportLook()).toBe(PRINT_LOOK);
        expect(EXPORT_LOOKS.map(look => look.value)).toEqual([PRINT_LOOK, 'light', 'dark']);
    });

    test('says how the map is drawn', () => {
        // The printed map has the icons of the light one.
        expect(lookStyle(PRINT_LOOK)).toEqual({flavor: PRINT_LOOK, sprite: 'light'});
        expect(lookStyle('light')).toEqual({flavor: 'light', sprite: 'light'});
        expect(lookStyle('dark')).toEqual({flavor: 'dark', sprite: 'dark'});
        // With no look chosen, the map is as the screen has it: nothing is said.
        expect(lookStyle(null)).toEqual({});
    });
});

describe('the colors a person chooses for the printed map', () => {
    beforeEach(() => localStorage.clear());

    test('each is a color the printed map has until another is chosen', () => {
        const theme = printTheme();
        const paints = Object.fromEntries(printLayers('a.pmtiles').map(layer => [layer.id, layer.paint]));
        for (const swatch of PRINT_SWATCHES) {
            // Choosing the color it has changes nothing: what it stands for is what the map has.
            const same = {[swatch.id]: swatch.color};
            expect(chosenColors(same)).toEqual({});
            // Every color and layer it speaks of is one a basemap has.
            for (const key of Object.keys(swatch.colors?.(swatch.color) || {})) expect(Object.keys(theme)).toContain(key);
            for (const id of Object.keys(swatch.paint?.(swatch.color) || {})) expect(Object.keys(paints)).toContain(id);
            for (const key of Object.keys(swatch.contours?.(swatch.color) || {})) {
                expect(Object.keys(PRINT_CONTOURS)).toContain(key);
            }
        }
        // No two have one name, and none speaks of a color another does.
        expect(new Set(PRINT_SWATCHES.map(swatch => swatch.id)).size).toBe(PRINT_SWATCHES.length);
        const spoken = PRINT_SWATCHES.flatMap(swatch => Object.keys(swatch.colors?.(swatch.color) || {}));
        expect(new Set(spoken).size).toBe(spoken.length);
    });

    test('a chosen color is the color of all it stands for', () => {
        const byId = Object.fromEntries(
            printLayers('a.pmtiles', {water: '#ff00ff', minor: '#00ff00'}).map(layer => [layer.id, layer]));
        expect(byId.water.paint['fill-color']).toBe('#ff00ff');
        // A line of water is darker than an area of it, and as wide as the printed map has it.
        expect(byId.water_stream.paint['line-color']).toBe(mix('#ff00ff', '#000000', 0.4));
        expect(byId.water_stream.paint['line-width']).toBe(PRINT_PAINT.water_stream['line-width']);
        expect(JSON.stringify(byId.roads_minor.paint['line-color'])).toContain('#00ff00');
        // The edge of a road is not chosen.
        expect(byId.roads_bridges_link.paint['line-color']).toBe(PRINT_COLORS.major);
        expect(byId.roads_minor_casing.paint['line-color']).toBe('#4d4d4d');
        // What was not chosen is as it was.
        expect(byId.roads_highway.paint['line-color']).toBe(PRINT_COLORS.highway);
    });

    test('a ramp is the color of a major road, on a bridge as off one', () => {
        const ramps = colors => {
            const byId = Object.fromEntries(printLayers('a.pmtiles', colors).map(layer => [layer.id, layer]));
            return [byId.roads_link.paint['line-color'], byId.roads_bridges_link.paint['line-color']];
        };
        expect(ramps({})).toEqual([PRINT_COLORS.major, PRINT_COLORS.major]);
        expect(ramps({major: '#123456'})).toEqual(['#123456', '#123456']);
        // The color of a minor road is not a ramp's.
        expect(ramps({minor: '#00ff00'})).toEqual([PRINT_COLORS.major, PRINT_COLORS.major]);
    });

    test('several colors of a basemap are shades of the one chosen', () => {
        const theme = printTheme({vegetation: '#008000'});
        expect(theme.park_b).toBe('#008000');
        expect(theme.park_a).toBe(mix('#008000', '#ffffff', 0.4));
        expect(theme.wood_b).not.toBe(theme.park_b);
        expect(mix('#000000', '#ffffff', 0.5)).toBe('#808080');
    });

    test('contours are the color chosen for them, and their heights have the halo of names', () => {
        expect(printContours()).toEqual(PRINT_CONTOURS);
        const contours = printContours({contours: '#102030', halo: '#fffacd'});
        expect(contours.minor).toEqual({'line-color': 'rgba(16, 32, 48, 0.55)', 'line-width': 0.6});
        expect(contours.major['line-color']).toBe('rgba(16, 32, 48, 0.9)');
        expect(contours.label['text-halo-color']).toBe('rgba(255, 250, 205, 0.9)');
    });

    test('what is not a choice is not kept', () => {
        expect(chosenColors({water: '#FF00FF', sky: '#0000ff', minor: 'green', highway: 7, major: '#fff'}))
            .toEqual({water: '#ff00ff'});
        expect(chosenColors(null)).toEqual({});
    });

    test('are remembered in the browser, and forgotten when there are none', () => {
        expect(savedPrintColors()).toEqual({});
        expect(savePrintColors({water: '#ff00ff', sky: '#0000ff'})).toEqual({water: '#ff00ff'});
        expect(savedPrintColors()).toEqual({water: '#ff00ff'});
        savePrintColors({});
        expect(localStorage.getItem('wrolpi-map-print-colors')).toBeNull();
        // What was kept is not what this keeps.
        localStorage.setItem('wrolpi-map-print-colors', 'not JSON');
        expect(savedPrintColors()).toEqual({});
    });
});
