import layers, {namedTheme} from 'protomaps-themes-base';
import {
    EXPORT_LOOKS, lookStyle, PRINT_COLORS, PRINT_LOOK, PRINT_PAINT, printLayers, printTheme, savedExportLook,
    saveExportLook,
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
