// Exporting a quadrangle of the map as a PDF.
//
// The browser draws the map, because nothing else draws it as the user sees it.  A second map, off
// the screen and the size of the printed sheet, is drawn once for each layer the user has turned on,
// with only that layer showing; the API puts the images in a PDF, each in a layer of its own, and
// (when it is asked to) on a sheet: with a margin, a grid, scale bars and notes around the map.

import {QUAD_DEGREES, QUAD_SCALE, quadLabel, quadSize, quadTitle} from "./mapQuads";
import {isOverlayLabelLayer, isOverlayLayerId} from "./mapOverlays";

export const EXPORT_DPI = 300;
// How sharp a map may be asked for.  More is four times the work for twice the sharpness: a
// quadrangle at 600 is more than a browser will draw, or a Raspberry Pi will make a PDF of.
export const EXPORT_DPIS = [300, 400];
// The most the API makes a PDF of: the pixels of one layer, and of all the layers of a map together
// (MAX_PIXELS and MAX_TOTAL_PIXELS in modules/map/export.py).
const MAX_LAYER_PIXELS = 64_000_000;
const MAX_TOTAL_PIXELS = 1_000_000_000;
// The map's style is made for a screen, where its sizes (of text, of lines) are in CSS pixels.  This
// is how many of those are an inch of paper: fewer is larger text and less detail.  At 150 a 12 pixel
// label prints at about 6 points, which is what a topographic map uses, and a quadrangle is drawn at
// about zoom 13 to 14.
export const EXPORT_CSS_DPI = 150;
// No browser makes a canvas larger than this, and few need to be asked for more.
const MAX_CANVAS_SIDE = 16384;
const FALLBACK_CANVAS_SIDE = 4096;
const MILLIMETERS_PER_INCH = 25.4;
const TILE_SIZE = 512;
const RENDER_TIMEOUT_MS = 120_000;

export const BACKGROUND_GROUP = "Background";

// The largest canvas (in pixels a side) this browser will draw a map on.
export function maxCanvasSide() {
    try {
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
        if (!gl) return FALLBACK_CANVAS_SIDE;
        const viewport = gl.getParameter(gl.MAX_VIEWPORT_DIMS) || [];
        const side = Math.min(gl.getParameter(gl.MAX_TEXTURE_SIZE), viewport[0], viewport[1], MAX_CANVAS_SIDE);
        gl.getExtension("WEBGL_lose_context")?.loseContext();
        return Number.isFinite(side) && side > 0 ? side : FALLBACK_CANVAS_SIDE;
    } catch (e) {
        return FALLBACK_CANVAS_SIDE;
    }
}

// The most pixels each layer of a map of `layerCount` layers may be.
export function maxExportPixels(layerCount) {
    return Math.min(MAX_LAYER_PIXELS, Math.floor(MAX_TOTAL_PIXELS / Math.max(1, layerCount)));
}

function mercatorY(latitude) {
    return Math.log(Math.tan(Math.PI / 4 + latitude * Math.PI / 360));
}

function latitudeOfMercatorY(y) {
    return (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI;
}

// How to draw a quadrangle at 1:24,000: the size of the map to make (in CSS pixels), where to put it
// (center, zoom), and how many real pixels each CSS pixel is.
//
// The map is Web Mercator, in which a quadrangle is exactly a rectangle.  It is as wide as the sheet
// is at the quadrangle's middle, and as tall as Mercator makes that.
//
// The map is as sharp as was asked for (`dpi`), or as sharp as it can be: no side of it longer than
// `maxSide` (the browser's largest canvas), and no more of it than `maxPixels` (what the API takes).
export function exportFrame(quad, {
    dpi = EXPORT_DPI, cssDpi = EXPORT_CSS_DPI, maxSide = MAX_CANVAS_SIDE, maxPixels = Infinity,
} = {}) {
    const widthInches = quadSize(quad).sheetWidthMm / MILLIMETERS_PER_INCH;
    const cssWidth = Math.round(widthInches * cssDpi);
    // The width of the whole world at the zoom where the quadrangle is `cssWidth` wide.
    const world = cssWidth * 360 / QUAD_DEGREES;
    const [south, north] = [mercatorY(quad.south), mercatorY(quad.north)];
    const cssHeight = Math.round((north - south) / (2 * Math.PI) * world);

    // A hair under what the pixels allow: each side of the canvas is rounded to a whole pixel.
    const pixelRatio = Math.min(
        dpi / cssDpi,
        maxSide / Math.max(cssWidth, cssHeight),
        Math.sqrt(maxPixels / (cssWidth * cssHeight)) * 0.999);
    return {
        cssWidth,
        cssHeight,
        pixelRatio,
        dpi: pixelRatio * cssDpi,
        zoom: Math.log2(world / TILE_SIZE),
        bounds: [quad.west, quad.south, quad.east, quad.north],
        center: [(quad.west + quad.east) / 2, latitudeOfMercatorY((south + north) / 2)],
    };
}

// The name of a basemap layer without the source it is of ("oregon.pmtiles:water" is "water").
function basemapLayerName(layerId) {
    return layerId.includes(":") ? layerId.split(":").slice(1).join(":") : layerId;
}

// The layers of the PDF: the visible layers of the map's style, gathered as the layer control
// gathers them, from the bottom up.  Each is {name, ids, raster}.  An overlay is one layer, or two
// when it has both ground and labels (see orderOverlayLayers).
//
// styleLayers: the layers of the map's style, as the map has them now.
// layerGroups: {name: [part of a layer id, ...]}, the basemap groups of the layer control.
// overlayLabels: {source id: label} of the overlay files.
export function exportGroups(styleLayers, {layerGroups = {}, overlayLabels = {}} = {}) {
    const groupNames = Object.keys(layerGroups);
    const groups = new Map();
    const add = (key, name, index, layer) => {
        if (!groups.has(key)) groups.set(key, {name, ids: [], top: index, raster: true});
        const group = groups.get(key);
        group.ids.push(layer.id);
        group.top = index;
        group.raster = group.raster && layer.type === "raster";
    };

    styleLayers.forEach((layer, index) => {
        if (layer.layout?.visibility === "none") return;
        if (isOverlayLayerId(layer.id)) {
            // An overlay is drawn in two places: its ground under the basemap's labels, and its own
            // labels over them.  A layer of the PDF is in one place, so each is a layer of the PDF.
            const part = isOverlayLabelLayer(layer) ? "labels" : "ground";
            const key = `overlay ${part} ${layer.source}`;
            add(key, overlayLabels[layer.source] || layer.source, index, layer);
            groups.get(key).overlay = {source: layer.source, part};
            return;
        }
        const name = basemapLayerName(layer.id);
        // A layer in more than one group (a water label) is of the last, which is the labels.
        const group = [...groupNames].reverse().find(g => layerGroups[g].some(part => name.includes(part)));
        if (group) {
            add(`group ${group}`, group, index, layer);
        } else {
            // The ground everything else is drawn on.
            add("background", BACKGROUND_GROUP, -1, layer);
        }
    });

    // A layer of the PDF is one image, so the layers of a group are drawn together: where the
    // topmost of them is.
    const ordered = [...groups.values()].sort((a, b) => a.top - b.top);
    // The labels of an overlay are named as its labels when its ground is a layer too.
    const grounds = new Set(ordered.filter(g => g.overlay?.part === "ground").map(g => g.overlay.source));
    const used = new Set();
    return ordered.map(({name, ids, raster, overlay}) => {
        if (overlay?.part === "labels" && grounds.has(overlay.source)) name = `${name} (labels)`;
        let unique = name;
        for (let n = 2; used.has(unique); n++) unique = `${name} (${n})`;
        used.add(unique);
        return {name: unique, ids, raster};
    });
}

// A basemap's tiles name its small roads from this zoom on.  A quadrangle is drawn at about zoom 13,
// from tiles in which the streets of a town are lines with no names.
export const EXPORT_DETAIL_ZOOM = 14;
// The layers of a basemap which name roads.
const ROAD_LABELS = "roads_labels";
const ROAD_NAMES_SOURCE = "export-road-names:";
const SHORT_ROAD_NAMES_SOURCE = "export-short-road-names:";
// The layer which names the roads too short for their names, after the id of the layer it is made of.
export const SHORT_ROAD_SUFFIX = ":short";
// Which way the name of a short road is turned (degrees, clockwise), in what is said of the road.
const NAME_ANGLE = "export:angle";
const ROAD_TEXT_SIZE = 12;
// About how wide a letter is, in its own height; and how much longer than its name a road is to be
// for the name to be written along it.
const LETTER_WIDTH = 0.55;
const NAME_ROOM = 1.2;
// Two short pieces of one road nearer than this (CSS pixels) are named once.
const SAME_NAME_APART = 150;
// More tiles of names than any quadrangle has: something is wrong with what was asked for.
const MAX_DETAIL_TILES = 256;

// The layers of `style` which name roads, but not on a map drawn at `zoom`: their style keeps the
// names for a zoom at which a street is inches long on a screen.  On a sheet a road is found by its
// name.
export function unnamedRoadLayers(style, zoom) {
    return (style.layers || []).filter(layer => layer.type === "symbol" && layer["source-layer"]
        && String(layer.id).includes(ROAD_LABELS) && layer.minzoom > zoom);
}

// The tiles of `zoom` which have part of `bounds` (west, south, east, north) in them: [{z, x, y}].
export function tilesOfBounds([west, south, east, north], zoom) {
    const count = 2 ** zoom;
    const column = longitude => (longitude + 180) / 360 * count;
    const row = latitude => (1 - mercatorY(latitude) / Math.PI) / 2 * count;
    const clamp = n => Math.min(count - 1, Math.max(0, n));
    // A tile whose edge is the edge of the bounds has nothing of them in it.
    const [left, right] = [clamp(Math.floor(column(west))), clamp(Math.ceil(column(east)) - 1)];
    const [top, bottom] = [clamp(Math.floor(row(north))), clamp(Math.ceil(row(south)) - 1)];
    const tiles = [];
    for (let x = left; x <= right; x++) {
        for (let y = top; y <= bottom; y++) tiles.push({z: zoom, x, y});
    }
    return tiles;
}

// The roads of one layer of a tile which have a name, as GeoJSON features with all that the tile says
// of them: what a layer of the style draws a name from is whatever its style asks for.
//
// tile: a tile as @mapbox/vector-tile reads it.
export function namedRoads(tile, sourceLayer, {z, x, y}) {
    const layer = tile?.layers?.[sourceLayer];
    const features = [];
    for (let i = 0; layer && i < layer.length; i++) {
        const feature = layer.feature(i);
        if (!Object.keys(feature.properties).some(key => key === "name" || key.startsWith("name:"))) continue;
        const {geometry, properties} = feature.toGeoJSON(x, y, z);
        features.push({type: "Feature", geometry, properties});
    }
    return features;
}

function nameOf(properties) {
    return String(properties.name ?? Object.entries(properties).find(([key]) => key.startsWith("name:"))?.[1] ?? "");
}

// Named roads (of namedRoads), as they are to be named on a map drawn at `zoom` with text of
// `textSize` CSS pixels: {lines, points}, each a GeoJSON FeatureCollection.
//
// A map writes a name along a road only where the road is longer than the name, and at the scale of
// a sheet most streets of a town are not.  Such a road is in `points`: its middle, and which way it
// goes there (NAME_ANGLE), where its name is written over its ends as a map maker would.
export function placeRoadNames(features, zoom, textSize = ROAD_TEXT_SIZE) {
    const world = TILE_SIZE * 2 ** zoom;
    const pixel = ([longitude, latitude]) => [
        (longitude + 180) / 360 * world, (1 - mercatorY(latitude) / Math.PI) / 2 * world];
    const lines = [];
    const short = [];
    for (const {geometry, properties} of features) {
        const parts = geometry.type === "MultiLineString" ? geometry.coordinates
            : geometry.type === "LineString" ? [geometry.coordinates] : [];
        for (const coordinates of parts) {
            if (coordinates.length < 2) continue;
            const pixels = coordinates.map(pixel);
            const lengths = pixels.slice(1).map((point, i) => Math.hypot(point[0] - pixels[i][0], point[1] - pixels[i][1]));
            const length = lengths.reduce((sum, n) => sum + n, 0);
            if (!length) continue;
            if (length >= nameOf(properties).length * textSize * LETTER_WIDTH * NAME_ROOM) {
                lines.push({type: "Feature", geometry: {type: "LineString", coordinates}, properties});
                continue;
            }
            // The middle of the road, and the piece of it the middle is on.
            let [along, i] = [length / 2, 0];
            while (i < lengths.length - 1 && along > lengths[i]) along -= lengths[i++];
            const part = lengths[i] ? along / lengths[i] : 0;
            const [from, to] = [coordinates[i], coordinates[i + 1]];
            const middle = [from[0] + (to[0] - from[0]) * part, from[1] + (to[1] - from[1]) * part];
            // From one end to the other, and never upside down.
            const [first, last] = [pixels[0], pixels[pixels.length - 1]];
            let angle = Math.atan2(last[1] - first[1], last[0] - first[0]) * 180 / Math.PI;
            if (angle > 90) angle -= 180;
            if (angle <= -90) angle += 180;
            short.push({length, at: pixel(middle), middle, angle, properties});
        }
    }
    // A road is in pieces where two tiles meet, and where what is said of it changes.  The longest of
    // the pieces near each other is the one which is named.
    const points = [];
    const kept = [];
    for (const road of short.sort((a, b) => b.length - a.length)) {
        const name = nameOf(road.properties);
        if (kept.some(other => other.name === name
            && Math.hypot(other.at[0] - road.at[0], other.at[1] - road.at[1]) < SAME_NAME_APART)) continue;
        kept.push({name, at: road.at});
        points.push({
            type: "Feature",
            geometry: {type: "Point", coordinates: road.middle},
            properties: {...road.properties, [NAME_ANGLE]: Math.round(road.angle * 10) / 10},
        });
    }
    return {
        lines: {type: "FeatureCollection", features: lines},
        points: {type: "FeatureCollection", features: points},
    };
}

// The names of the roads of the map which a map drawn for `frame` would not have: {source id:
// {lines, points}} (see placeRoadNames), for exportStyle.  They are read from tiles of EXPORT_DETAIL_ZOOM.
//
// readTile(url, {z, x, y}): resolves to a tile of the source with that URL (as @mapbox/vector-tile
// reads it), or to nothing when the source has no such tile.
//
// A source whose names can not be read is left out, and the map is exported without them.
export async function loadRoadNames(style, frame, readTile) {
    const names = {};
    if (!readTile || frame.zoom >= EXPORT_DETAIL_ZOOM) return names;
    const tiles = tilesOfBounds(frame.bounds, EXPORT_DETAIL_ZOOM);
    if (tiles.length > MAX_DETAIL_TILES) return names;
    // Each source once: the layers which name its roads are of one layer of its tiles.
    const unnamed = new Map(unnamedRoadLayers(style, frame.zoom).map(layer => [layer.source, layer]));
    for (const [sourceId, layer] of unnamed) {
        const sourceLayer = layer["source-layer"];
        const textSize = Number.isFinite(layer.layout?.["text-size"]) ? layer.layout["text-size"] : ROAD_TEXT_SIZE;
        const url = style.sources?.[sourceId]?.url;
        if (!url) continue;
        try {
            const read = await Promise.all(tiles.map(async tile => namedRoads(await readTile(url, tile), sourceLayer, tile)));
            const features = read.flat();
            if (features.length) names[sourceId] = placeRoadNames(features, frame.zoom, textSize);
        } catch (e) {
            console.warn(`The road names of ${sourceId} could not be read`, e);
        }
    }
    return names;
}

// A copy of the map's style in which nothing is drawn, for the map which is exported from; the
// layers are shown a group at a time.  Layers which are of the app and not of the map (those whose
// id starts with one of `ignoredPrefixes`) are not in it.
//
// roadNames: what loadRoadNames gave for a map drawn at `zoom`.  A layer which would not name roads
// at that zoom names those instead, as its style says to; and after it is a layer like it (its id
// and SHORT_ROAD_SUFFIX) which names the roads too short for their names.
export function exportStyle(style, ignoredPrefixes = [], {zoom = null, roadNames = {}} = {}) {
    const ignored = id => ignoredPrefixes.some(prefix => String(id).startsWith(prefix));
    const sources = Object.fromEntries(Object.entries(style.sources || {}).filter(([id]) => !ignored(id)));
    for (const [id, {lines, points}] of Object.entries(roadNames)) {
        if (!sources[id]) continue;
        sources[ROAD_NAMES_SOURCE + id] = {type: "geojson", data: lines};
        sources[SHORT_ROAD_NAMES_SOURCE + id] = {type: "geojson", data: points};
    }
    const unnamed = new Set(zoom === null ? [] : unnamedRoadLayers(style, zoom).map(layer => layer.id));
    const layers = (style.layers || [])
        .filter(layer => !ignored(layer.id))
        .flatMap(layer => {
            if (!unnamed.has(layer.id) || !sources[ROAD_NAMES_SOURCE + layer.source]) {
                return [{...layer, layout: {...layer.layout, visibility: "none"}}];
            }
            const {minzoom, "source-layer": sourceLayer, ...named} = layer;
            return [{
                ...named,
                source: ROAD_NAMES_SOURCE + layer.source,
                layout: {...layer.layout, visibility: "none"},
            }, {
                ...named,
                id: layer.id + SHORT_ROAD_SUFFIX,
                source: SHORT_ROAD_NAMES_SOURCE + layer.source,
                layout: {
                    ...layer.layout,
                    "symbol-placement": "point",
                    "text-rotate": ["get", NAME_ANGLE],
                    "text-rotation-alignment": "map",
                    visibility: "none",
                },
            }];
        });
    return {...style, sources, layers};
}

// The map's arithmetic can put the edge of the world a hair past where it is (180.00000000000125
// degrees).  Such an edge is the edge of the world; one further past it is of a map which crosses the
// antimeridian, and is left as it is.
const LONGITUDE_SLIVER = 1e-8;

function edgeLongitude(longitude) {
    if (Math.abs(longitude) > 180 && Math.abs(longitude) - 180 < LONGITUDE_SLIVER) return Math.sign(longitude) * 180;
    return longitude;
}

function once(map, event, timeoutMs = RENDER_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("The map took too long to draw")), timeoutMs);
        map.once(event, () => {
            clearTimeout(timer);
            resolve();
        });
    });
}

function canvasBlob(canvas, type, quality) {
    return new Promise((resolve, reject) => canvas.toBlob(
        blob => (blob ? resolve(blob) : reject(new Error("The map could not be made into an image"))),
        type, quality));
}

// Whether a canvas has no transparent part.  It is reduced first: looking at every pixel of a sheet
// is slow, and a part too small to survive the reduction is too small to matter.
export function isOpaque(canvas) {
    const small = document.createElement("canvas");
    small.width = 64;
    small.height = Math.max(1, Math.round(64 * canvas.height / canvas.width));
    const context = small.getContext("2d");
    if (!context) return false;
    context.drawImage(canvas, 0, 0, small.width, small.height);
    const {data} = context.getImageData(0, 0, small.width, small.height);
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 255) return false;
    }
    return true;
}

// Draw each group of layers of `style` on a map of its own, and return the images:
// {width, height, dpi, bounds, layers: [{name, blob}]}.  `bounds` is the west, south, east and north
// edges of the images (degrees), which is what says where the PDF is on the Earth: they are read
// from the map which was drawn, so they are of the picture and not of what was asked for.
//
// MapClass: maplibregl.Map.  setup(map): called with the new map before it draws anything.
// readTile: how to read a tile of a source (see loadRoadNames); without it small roads have no names.
// onProgress(name, index, count): called before each group is drawn.  isCancelled(): asked before
// each group whether to stop; when it is so nothing more is drawn, and this rejects with an error
// whose `cancelled` is true.
export async function renderExport({
    MapClass, style, frame, groups, setup, onProgress, isCancelled, readTile, ignoredPrefixes = [],
}) {
    const roadNames = await loadRoadNames(style, frame, readTile);
    const container = document.createElement("div");
    // Off the screen, but laid out and drawn as any element is.
    container.style.cssText = `position:fixed;left:-100000px;top:0;width:${frame.cssWidth}px;`
        + `height:${frame.cssHeight}px;pointer-events:none;`;
    document.body.appendChild(container);

    let map;
    try {
        const side = Math.ceil(Math.max(frame.cssWidth, frame.cssHeight) * frame.pixelRatio);
        map = new MapClass({
            container,
            style: exportStyle(style, ignoredPrefixes, {zoom: frame.zoom, roadNames}),
            center: frame.center,
            zoom: frame.zoom,
            interactive: false,
            attributionControl: false,
            pixelRatio: frame.pixelRatio,
            maxCanvasSize: [side, side],
            // The canvas is read after it is drawn, so what was drawn must still be in it.
            canvasContextAttributes: {preserveDrawingBuffer: true},
            // A label is all there at once: nothing is caught half faded in.
            fadeDuration: 0,
        });
        if (setup) setup(map);
        await once(map, "load");

        const canvas = map.getCanvas();
        const layers = [];
        for (const [index, group] of groups.entries()) {
            if (isCancelled && isCancelled()) {
                throw Object.assign(new Error("The export was cancelled"), {cancelled: true});
            }
            if (onProgress) onProgress(group.name, index, groups.length);
            const show = visibility => {
                // A layer, and the layer of short roads which was made of it (see exportStyle).
                for (const id of group.ids.flatMap(i => [i, i + SHORT_ROAD_SUFFIX])) {
                    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
                }
            };
            show("visible");
            const idle = once(map, "idle");
            map.triggerRepaint();
            await idle;
            // A photograph with no gaps is far smaller as a JPEG; anything else needs to be seen through.
            const blob = group.raster && isOpaque(canvas)
                ? await canvasBlob(canvas, "image/jpeg", 0.9)
                : await canvasBlob(canvas, "image/png");
            layers.push({name: group.name, blob});
            show("none");
        }
        const edges = map.getBounds();
        return {
            width: canvas.width,
            height: canvas.height,
            bounds: [edgeLongitude(edges.getWest()), edges.getSouth(), edgeLongitude(edges.getEast()), edges.getNorth()],
            dpi: canvas.width / frame.cssWidth * (frame.dpi / frame.pixelRatio),
            layers,
        };
    } finally {
        if (map) map.remove();
        container.remove();
    }
}

// Where the data of the exported layers is from: what each of their sources says of itself, once
// each, as text.
//
// map: the map on the screen, whose sources have been loaded (a source may only learn its
// attribution from its file).
export function exportCredits(map, groups) {
    const style = map.getStyle();
    const exported = new Set(groups.flatMap(group => group.ids));
    const credits = [];
    for (const layer of style.layers || []) {
        if (!layer.source || !exported.has(layer.id)) continue;
        const attribution = map.getSource(layer.source)?.attribution || style.sources?.[layer.source]?.attribution;
        if (!attribution) continue;
        // An attribution is HTML: links, mostly.  One may name many sources, with a bar between them.
        const html = new DOMParser().parseFromString(String(attribution), "text/html");
        for (const part of (html.body.textContent || "").split("|")) {
            const text = part.replace(/\s+/g, " ").trim();
            if (text && !credits.includes(text)) credits.push(text);
        }
    }
    return credits;
}

// The day, as the person exporting the map has it: 2026-11-15.
export function exportDate(now = new Date()) {
    const pad = value => String(value).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// What is written on the sheet a quadrangle is printed on.  `named` is what the USGS calls the
// quadrangle ({name, state, exact}), when it calls it anything: else it goes by where it is.
export function exportSheet(quad, map, groups, now = new Date(), named = null) {
    return {
        name: quadTitle(named) || quadLabel(quad),
        credits: exportCredits(map, groups),
        date: exportDate(now),
    };
}

// "N40.250_W105.125": where a quadrangle's southwest corner is, in a form a file can be named.
function quadFileStem(quad) {
    const part = (value, positive, negative) => `${value < 0 ? negative : positive}${Math.abs(value).toFixed(3)}`;
    return `${part(quad.south, "N", "S")}_${part(quad.west, "E", "W")}`;
}

// A name as a part of a file's: "Berthoud".
function fileNamePart(name) {
    return String(name).normalize("NFKD").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);
}

export function exportFileName(quad, named = null) {
    const name = named?.name ? fileNamePart(named.name) : "";
    return `wrolpi-map_${QUAD_SCALE / 1000}k_${name ? `${name}_` : ""}${quadFileStem(quad)}.pdf`;
}

export function exportTitle(quad, named = null) {
    return `1:${QUAD_SCALE.toLocaleString("en-US")} ${quadTitle(named) || quadLabel(quad)}`;
}

// Give the user a file to keep.
export function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Not at once: a large file is still being read when the click returns.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
