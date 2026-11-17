import {exportLegend, LEGEND_LINES} from './mapExportLegend';

// A basemap as the map's style has it: roads with edges under them, at widths which change with
// the zoom; and the contours of the terrain.
const grows = (...stops) => ['interpolate', ['exponential', 1.6], ['zoom'], ...stops];
const STYLE = {
    layers: [
        {id: 'background', type: 'background', paint: {'background-color': '#cccccc'}},
        {id: 'earth', type: 'fill', paint: {'fill-color': '#e2dfda'}},
        {id: 'roads_minor_casing', type: 'line', paint: {
            'line-color': '#e0e0e0', 'line-gap-width': grows(11, 0, 12.5, 0.5, 15, 2), 'line-width': grows(12, 0, 12.5, 1),
        }},
        {id: 'roads_highway_casing_late', type: 'line', minzoom: 12, paint: {
            'line-color': '#e0e0e0', 'line-gap-width': 2, 'line-width': 1,
        }},
        {id: 'roads_highway_casing_early', type: 'line', maxzoom: 12, paint: {
            'line-color': '#000000', 'line-gap-width': 1, 'line-width': 0.5,
        }},
        {id: 'roads_other', type: 'line', paint: {'line-color': '#ebebeb', 'line-dasharray': [3, 1], 'line-width': grows(14, 0, 20, 7)}},
        {id: 'roads_minor', type: 'line', paint: {
            'line-color': grows(11, '#ebebeb', 16, '#ffffff'), 'line-width': grows(11, 0, 12.5, 0.5, 15, 2),
        }},
        {id: 'roads_highway', type: 'line', paint: {'line-color': '#ffffff', 'line-width': 2}},
        {id: 'roads_rail', type: 'line', paint: {
            'line-dasharray': [0.3, 0.75], 'line-opacity': 0.5, 'line-color': '#a7b1b3', 'line-width': 1,
        }},
        {id: 'boundaries', type: 'line', paint: {
            'line-color': '#adadad', 'line-width': 0.4, 'line-dasharray': ['step', ['zoom'], ['literal', [2]], 4, ['literal', [2, 1]]],
        }},
        {id: 'roads_labels_minor', type: 'symbol'},
        {id: 'contour-lines', type: 'line', paint: {'line-color': 'rgba(150,100,50,0.3)', 'line-width': 0.5}},
        {id: 'contour-lines-major', type: 'line', paint: {'line-color': 'rgba(150,100,50,0.5)', 'line-width': 1}},
    ],
};
const ALL = [{name: 'Everything', ids: STYLE.layers.map(layer => layer.id)}];
const only = (...ids) => [{name: 'Some', ids}];
const labels = legend => legend.lines.map(line => line.label);

describe('the legend of an exported map', () => {
    test('is of the lines which are exported and drawn at the zoom of the sheet, from the top', () => {
        const legend = exportLegend(STYLE, ALL, 13.2);
        // A path is drawn only from zoom 14: it is not on this sheet.
        expect(labels(legend)).toEqual(['Highway', 'Minor road', 'Railway', 'Boundary', 'Index contour', 'Contour']);
        expect(labels(exportLegend(STYLE, ALL, 15))).toContain('Path or track');
        // In the order they are listed, whatever order the style has them in.
        const order = LEGEND_LINES.map(line => line.label);
        expect(labels(legend)).toEqual(order.filter(label => labels(legend).includes(label)));
    });

    test('a line is as wide on the sheet as the map draws it: 150 pixels of the style are an inch', () => {
        const {lines} = exportLegend(STYLE, ALL, 13.2);
        const highway = lines.find(line => line.label === 'Highway');
        // 2 pixels are 0.96 points; its edges are a pixel each side of it.
        expect(highway).toEqual({
            label: 'Highway', color: [1, 1, 1], width: 0.96, opacity: 1,
            casing_color: [0.878, 0.878, 0.878], casing_width: 1.92,
        });
        // At another scale of the style it is as much wider.
        expect(exportLegend(STYLE, ALL, 13.2, 75).lines[0].width).toBe(1.92);
    });

    test('a color and a width which change with the zoom are those of the zoom', () => {
        const at = zoom => exportLegend(STYLE, ALL, zoom).lines.find(line => line.label === 'Minor road');
        expect(at(13.2).width).toBeGreaterThan(at(12.6).width);
        expect(at(13.2).width).toBeLessThan(at(15).width);
        expect(at(15).width).toBe(0.96);
        expect(at(11.5).color[0]).toBeLessThan(at(15.9).color[0]);
        // The edges of a road are those of the layer which draws them at that zoom.
        const highway = zoom => exportLegend(STYLE, ALL, zoom).lines[0];
        expect(highway(13).casing_color).toEqual([0.878, 0.878, 0.878]);
        expect(highway(11).casing_color).toEqual([0, 0, 0]);
        expect(highway(11).casing_width).toBe(0.96);
    });

    test('a broken line has its dashes, and a faint one how faint it is', () => {
        const {lines} = exportLegend(STYLE, ALL, 13.2);
        const line = label => lines.find(i => i.label === label);
        // The dashes of a style are in widths of the line: 0.3 and 0.75 of 0.48 points.
        expect(line('Railway')).toMatchObject({dash: [0.14, 0.36], opacity: 0.5, width: 0.48});
        expect(line('Boundary').dash).toEqual([0.38, 0.19]);
        // A color which can be seen through is that color, and how much of it.
        expect(line('Contour')).toEqual({label: 'Contour', color: [0.588, 0.392, 0.196], width: 0.24, opacity: 0.3});
        expect(line('Index contour')).toMatchObject({width: 0.48, opacity: 0.5});
        expect(line('Highway')).not.toHaveProperty('dash');
    });

    test('is on the color of the land which is exported', () => {
        expect(exportLegend(STYLE, ALL, 13.2).ground).toEqual([0.886, 0.875, 0.855]);
        // Without the land the lines are on the color under it, and without that on paper.
        expect(exportLegend(STYLE, only('background', 'roads_highway'), 13.2).ground).toEqual([0.8, 0.8, 0.8]);
        expect(exportLegend(STYLE, only('roads_highway'), 13.2).ground).toEqual([1, 1, 1]);
    });

    test('has only what is exported', () => {
        const legend = exportLegend(STYLE, only('roads_highway', 'contour-lines'), 13.2);
        expect(labels(legend)).toEqual(['Highway', 'Contour']);
        // The road without its edges.
        expect(legend.lines[0]).not.toHaveProperty('casing_color');
        // A map with none of the lines has no legend.
        expect(exportLegend(STYLE, only('earth', 'roads_labels_minor'), 13.2)).toBeNull();
        expect(exportLegend(STYLE, [], 13.2)).toBeNull();
        expect(exportLegend({}, ALL, 13.2)).toBeNull();
    });

    test('the layers of a second basemap file are the same lines', () => {
        const style = {layers: STYLE.layers.map(layer => ({...layer, id: `b.pmtiles:${layer.id}`}))};
        const groups = [{name: 'Everything', ids: style.layers.map(layer => layer.id)}];
        expect(labels(exportLegend(style, groups, 13.2))).toEqual(labels(exportLegend(STYLE, ALL, 13.2)));
    });

    test('a layer which says nothing of its line is drawn as a style draws one', () => {
        const style = {layers: [{id: 'roads_highway', type: 'line'}]};
        expect(exportLegend(style, only('roads_highway'), 13).lines).toEqual([
            {label: 'Highway', color: [0, 0, 0], width: 0.48, opacity: 1}]);
        // What can not be made a color or a width of is left out.
        const broken = {layers: [{id: 'roads_highway', type: 'line', paint: {'line-color': ['nonsense'], 'line-width': 1}}]};
        expect(exportLegend(broken, only('roads_highway'), 13)).toBeNull();
    });
});
