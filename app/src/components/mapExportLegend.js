// The legend of an exported map: what its lines are, each as the map draws it.
//
// The map's style says how a road is drawn at each zoom, and a sheet is drawn at one.  The lines are
// described here, where the style can be read, and drawn on the sheet by the API.

import {expression, latest} from "@maplibre/maplibre-gl-style-spec";
import {EXPORT_CSS_DPI} from "./mapExport";

const POINTS_PER_INCH = 72;
const WHITE = [1, 1, 1];

// The lines a legend may have, from the top: what each is called, the layer of the basemap (or of
// the contours) which draws it, and the layers which may draw its edges under it.
export const LEGEND_LINES = [
    {label: "Highway", line: "roads_highway", casings: ["roads_highway_casing_late", "roads_highway_casing_early"]},
    {label: "Major road", line: "roads_major", casings: ["roads_major_casing_late", "roads_major_casing_early"]},
    {label: "Minor road", line: "roads_minor", casings: ["roads_minor_casing"]},
    {label: "Path or track", line: "roads_other"},
    {label: "Railway", line: "roads_rail"},
    {label: "Boundary", line: "boundaries"},
    {label: "Index contour", line: "contour-lines-major"},
    {label: "Contour", line: "contour-lines"},
];

// The name of a basemap layer without the source it is of ("oregon.pmtiles:water" is "water").
function layerName(layerId) {
    const id = String(layerId);
    return id.includes(":") ? id.split(":").slice(1).join(":") : id;
}

// What a property of a layer is at a zoom; the style's own default when the layer does not say.
function valueAt(layer, group, property, zoom) {
    const spec = latest[`${group}_${layer.type}`]?.[property];
    if (!spec) return undefined;
    const value = layer[group]?.[property] ?? spec.default;
    if (value === undefined) return undefined;
    try {
        return expression.normalizePropertyExpression(value, spec).evaluate({zoom});
    } catch (e) {
        return undefined;
    }
}

// A color of the style as red, green and blue from 0 to 1, and how opaque it is.
function colorParts(color) {
    if (!color || !Number.isFinite(color.a) || color.a <= 0) return null;
    // The style keeps a color multiplied by its opacity.
    const part = n => Math.round(Math.min(1, Math.max(0, n / color.a)) * 1000) / 1000;
    return {color: [part(color.r), part(color.g), part(color.b)], opacity: color.a};
}

function drawnAt(layer, zoom) {
    return (layer.minzoom === undefined || zoom >= layer.minzoom) && (layer.maxzoom === undefined || zoom < layer.maxzoom);
}

const round = n => Math.round(n * 100) / 100;

// The legend of a map which is exported: {ground, lines}, for the sheet (see `Sheet.legend` in
// modules/map/sheet.py), or null when the map has none of the lines a legend is of.
//
// style: the map's style.  groups: the layers which are exported (of exportGroups).  zoom: the zoom
// the map is exported at.  cssDpi: how many CSS pixels of the style are an inch of the sheet.
//
// A line is in the legend when its layer is exported and draws something at that zoom: a path which
// the style only draws from zoom 14 is not on a sheet drawn at 13, nor in its legend.
export function exportLegend(style, groups, zoom, cssDpi = EXPORT_CSS_DPI) {
    const exported = new Set(groups.flatMap(group => group.ids));
    const layers = (style.layers || []).filter(layer => exported.has(layer.id) && drawnAt(layer, zoom));
    const points = POINTS_PER_INCH / cssDpi;
    const find = name => layers.find(layer => layer.type === "line" && layerName(layer.id) === name);

    const lines = [];
    for (const {label, line, casings = []} of LEGEND_LINES) {
        const layer = find(line);
        if (!layer) continue;
        const width = valueAt(layer, "paint", "line-width", zoom);
        const parts = colorParts(valueAt(layer, "paint", "line-color", zoom));
        if (!parts || !(width > 0)) continue;
        const entry = {
            label,
            color: parts.color,
            width: round(width * points),
            opacity: round(parts.opacity * (valueAt(layer, "paint", "line-opacity", zoom) ?? 1)),
        };
        // The lengths of a dash are in widths of its line.
        const dash = valueAt(layer, "paint", "line-dasharray", zoom);
        if (Array.isArray(dash) && dash.length > 1) entry.dash = dash.map(n => round(n * width * points));
        // The edges of a road are a wider line under it, drawn as two lines with a gap between them.
        const casing = casings.map(find).find(Boolean);
        if (casing) {
            const edge = valueAt(casing, "paint", "line-width", zoom);
            const gap = valueAt(casing, "paint", "line-gap-width", zoom) ?? 0;
            const color = colorParts(valueAt(casing, "paint", "line-color", zoom));
            if (color && edge > 0) {
                entry.casing_color = color.color;
                entry.casing_width = round((gap + 2 * edge) * points);
            }
        }
        lines.push(entry);
    }
    if (!lines.length) return null;

    // The land the lines are on: the topmost of the layers which color all of it.
    let ground = WHITE;
    for (const layer of layers) {
        const name = layerName(layer.id);
        const color = layer.type === "background" ? valueAt(layer, "paint", "background-color", zoom)
            : layer.type === "fill" && name === "earth" ? valueAt(layer, "paint", "fill-color", zoom) : null;
        const parts = colorParts(color);
        if (parts) ground = parts.color;
    }
    return {ground, lines};
}
