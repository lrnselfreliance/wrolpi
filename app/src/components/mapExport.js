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
// How often it is asked whether the map has been too long in drawing.
const RENDER_WATCH_MS = 1000;

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

// The kinds of layer which are drawn over what is under them without hiding it: a line, a name.
const THIN_LAYER_TYPES = new Set(["line", "symbol", "circle"]);

// The layers of the PDF: the visible layers of the map's style, gathered as the layer control
// gathers them, from the bottom up.  Each is {name, ids, raster}.  An overlay is one layer, or two
// when it has both ground and labels (see orderOverlayLayers).
//
// A layer of the PDF is drawn as images, and an image is in one place among the others.  The layers
// of a group are not always together in the style: the parks of Land Cover are under the water and
// its piers are over it, and a second basemap file has all of its layers over the first's.  So a
// group is as many images as it must be, each with the name of the group (they are one layer of the
// PDF): a part of it which fills an area stays where it is, because moved over what was above it,
// it would hide that; a part which is only lines or names is drawn with the group's next part.
//
// styleLayers: the layers of the map's style, as the map has them now.
// layerGroups: {name: [part of a layer id, ...]}, the basemap groups of the layer control.
// overlayLabels: {source id: label} of the overlay files.
export function exportGroups(styleLayers, {layerGroups = {}, overlayLabels = {}} = {}) {
    const groupNames = Object.keys(layerGroups);
    // What each visible layer is of: {key, name, overlay}.
    const groupOf = layer => {
        if (isOverlayLayerId(layer.id)) {
            // An overlay is drawn in two places: its ground under the basemap's labels, and its own
            // labels over them.  Each is a layer of the PDF.
            const part = isOverlayLabelLayer(layer) ? "labels" : "ground";
            return {
                key: `overlay ${part} ${layer.source}`, name: overlayLabels[layer.source] || layer.source,
                overlay: {source: layer.source, part},
            };
        }
        const name = basemapLayerName(layer.id);
        // A layer in more than one group (a water label) is of the last, which is the labels.
        const group = [...groupNames].reverse().find(g => layerGroups[g].some(part => name.includes(part)));
        // What is in no group is the ground everything else is drawn on.
        return group ? {key: `group ${group}`, name: group} : {key: "background", name: BACKGROUND_GROUP};
    };

    // The style from the bottom up, as runs of layers which are of one group and are together.
    const runs = [];
    for (const layer of styleLayers) {
        if (layer.layout?.visibility === "none") continue;
        const group = groupOf(layer);
        let run = runs[runs.length - 1];
        if (run?.key !== group.key) {
            run = {...group, ids: [], raster: true, thin: true};
            runs.push(run);
        }
        run.ids.push(layer.id);
        run.raster = run.raster && layer.type === "raster";
        run.thin = run.thin && THIN_LAYER_TYPES.has(layer.type);
    }
    // A run of lines is drawn with the next run of its group, when there is one.
    const waiting = new Map();
    const placed = [];
    for (const [index, run] of runs.entries()) {
        const ids = [...(waiting.get(run.key) || []), ...run.ids];
        waiting.delete(run.key);
        if (run.thin && runs.slice(index + 1).some(later => later.key === run.key)) {
            waiting.set(run.key, ids);
        } else {
            placed.push({...run, ids});
        }
    }

    // The labels of an overlay are named as its labels when its ground is a layer too.
    const grounds = new Set(placed.filter(g => g.overlay?.part === "ground").map(g => g.overlay.source));
    // Two groups of one name are told apart; the images of one group have one name.
    const used = new Set();
    const names = new Map();
    return placed.map(({key, name, ids, raster, overlay}) => {
        if (!names.has(key)) {
            if (overlay?.part === "labels" && grounds.has(overlay.source)) name = `${name} (labels)`;
            let unique = name;
            for (let n = 2; used.has(unique); n++) unique = `${name} (${n})`;
            used.add(unique);
            names.set(key, unique);
        }
        return {name: names.get(key), ids, raster};
    });
}

// The sources of a style whose map file has nothing of an area: a map of another state.  Their
// layers are not drawn, each of which would be an image of nothing, counted against how sharp the
// map may be.  A source is only left out when its file says where it is of, and that is elsewhere.
//
// bounds: the west, south, east and north edges of the area.
// readBounds(url): the edges of the map file a source has as its `url`, or null (see mapTiles.js).
export async function sourcesOutside(style, bounds, readBounds) {
    const [west, south, east, north] = bounds;
    const outside = new Set();
    await Promise.all(Object.entries(style.sources || {}).map(async ([id, source]) => {
        if (typeof source.url !== "string" || !source.url.startsWith("pmtiles://")) return;
        try {
            const edges = await readBounds(source.url);
            if (!edges) return;
            const [fileWest, fileSouth, fileEast, fileNorth] = edges;
            if (fileEast <= west || fileWest >= east || fileNorth <= south || fileSouth >= north) outside.add(id);
        } catch (e) {
            // A file which can not be asked is drawn, as it was going to be.
            console.warn("Could not read where a map file is of:", source.url, e);
        }
    }));
    return outside;
}

// A basemap's tiles name its small roads from this zoom on.  A quadrangle is drawn at about zoom 13,
// from tiles in which the streets of a town are lines with no names.
export const EXPORT_DETAIL_ZOOM = 14;
// The layers of a basemap which name roads.
const ROAD_LABELS = "roads_labels";
const ROAD_NAMES_SOURCE = "export-road-names:";
// More room (ems) than the name of a road is long: a name is one line.
const ROAD_NAME_MAX_EMS = 1000;
// Which way the name of a road is turned (degrees, clockwise), in what is said of the road.
const NAME_ANGLE = "export:angle";
const ROAD_TEXT_SIZE = 12;
// About how wide a letter is, in its own height.
const LETTER_WIDTH = 0.55;
// A long road is named again each time it has gone this far (CSS pixels: 2.7 inches of a sheet).
const NAME_EVERY = 400;
// Two names of one road are never nearer than this (CSS pixels).
const SAME_NAME_APART = 150;
// The most tiles names are read from.  A quadrangle is 20 to 40 of them, and more only where it is a
// sliver near a pole (455 at 85 degrees); more than this is not a quadrangle.
const MAX_DETAIL_TILES = 512;

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

// What two pieces of one road have in common: its name, and what kind of road it is.  The layers
// which name roads each name some kinds of them, so a piece of another kind may not be named at all.
function roadOf(properties) {
    return `${properties.kind ?? ""}\n${nameOf(properties)}`;
}

function nameOf(properties) {
    return String(properties.name ?? Object.entries(properties).find(([key]) => key.startsWith("name:"))?.[1] ?? "");
}

// Where a line (of points, with the length of each of its parts) is when it has gone `along`.
function pointAlong(points, lengths, along) {
    let i = 0;
    while (i < lengths.length - 1 && along > lengths[i]) along -= lengths[i++];
    const part = lengths[i] ? Math.min(1, Math.max(0, along / lengths[i])) : 0;
    const [from, to] = [points[i], points[i + 1]];
    return [from[0] + (to[0] - from[0]) * part, from[1] + (to[1] - from[1]) * part];
}

// Where named roads (of namedRoads) are named on a map drawn at `zoom` with text of `textSize` CSS
// pixels: a GeoJSON FeatureCollection of points, each with all that is said of its road, and which
// way the road goes there (NAME_ANGLE).
//
// A map writes a name along a road only where the road is longer than the name and bends little,
// and at the scale of a sheet most streets of a town are shorter than their names.  So the names
// are placed here, as a map maker places them: over the middle of the road, turned as the road goes
// under the name, and over its ends when it is short; again every NAME_EVERY of a long road.
//
// A road is in pieces where two tiles meet, and where what is said of it changes.  The longest
// pieces are named first, and a piece is not named near where its road already is.
export function placeRoadNames(features, zoom, textSize = ROAD_TEXT_SIZE) {
    const world = TILE_SIZE * 2 ** zoom;
    const pixel = ([longitude, latitude]) => [
        (longitude + 180) / 360 * world, (1 - mercatorY(latitude) / Math.PI) / 2 * world];
    const pieces = [];
    for (const {geometry, properties} of features) {
        const parts = geometry.type === "MultiLineString" ? geometry.coordinates
            : geometry.type === "LineString" ? [geometry.coordinates] : [];
        for (const coordinates of parts) {
            if (coordinates.length < 2) continue;
            const pixels = coordinates.map(pixel);
            const lengths = pixels.slice(1).map((point, i) => Math.hypot(point[0] - pixels[i][0], point[1] - pixels[i][1]));
            const length = lengths.reduce((sum, n) => sum + n, 0);
            if (length) pieces.push({coordinates, pixels, lengths, length, properties});
        }
    }
    const named = new Map();
    const points = [];
    for (const {coordinates, pixels, lengths, length, properties} of pieces.sort((a, b) => b.length - a.length)) {
        const road = roadOf(properties);
        if (!named.has(road)) named.set(road, []);
        const places = named.get(road);
        const width = nameOf(properties).length * textSize * LETTER_WIDTH;
        const count = Math.max(1, Math.floor(length / NAME_EVERY));
        for (let n = 0; n < count; n++) {
            const along = (n + 0.5) * length / count;
            const at = pointAlong(pixels, lengths, along);
            if (places.some(other => Math.hypot(other[0] - at[0], other[1] - at[1]) < SAME_NAME_APART)) continue;
            places.push(at);
            // From where the name begins to where it ends, and never upside down.
            const first = pointAlong(pixels, lengths, Math.max(0, along - width / 2));
            const last = pointAlong(pixels, lengths, Math.min(length, along + width / 2));
            let angle = Math.atan2(last[1] - first[1], last[0] - first[0]) * 180 / Math.PI;
            if (angle > 90) angle -= 180;
            if (angle <= -90) angle += 180;
            points.push({
                type: "Feature",
                geometry: {type: "Point", coordinates: pointAlong(coordinates, lengths, along)},
                properties: {...properties, [NAME_ANGLE]: Math.round(angle * 10) / 10},
            });
        }
    }
    return {type: "FeatureCollection", features: points};
}

// The names of the roads of the map which a map drawn for `frame` would not have: {source id: where
// they are named (see placeRoadNames)}, for exportStyle.  They are read from tiles of EXPORT_DETAIL_ZOOM.
//
// readTile(url, {z, x, y}): resolves to a tile of the source with that URL (as @mapbox/vector-tile
// reads it), or to nothing when the source has no such tile.
//
// They are read wherever a layer would not name roads, whatever tiles the map itself is drawn from:
// nearer the equator a quadrangle is drawn at a little over zoom 14, from tiles which have the names,
// but its streets are as short there as anywhere.
//
// isCancelled(): asked before each source is read; when it is so no more is read.
//
// A source whose names can not be read is left out, and the map is exported without them.
export async function loadRoadNames(style, frame, readTile, isCancelled) {
    const names = {};
    // Each source once: the layers which name its roads are of one layer of its tiles.
    const unnamed = new Map(unnamedRoadLayers(style, frame.zoom).map(layer => [layer.source, layer]));
    if (!readTile || !unnamed.size) return names;
    const tiles = tilesOfBounds(frame.bounds, EXPORT_DETAIL_ZOOM);
    if (tiles.length > MAX_DETAIL_TILES) return names;
    for (const [sourceId, layer] of unnamed) {
        if (isCancelled && isCancelled()) break;
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
// at that zoom names those instead, in its own style, where placeRoadNames put the names.
export function exportStyle(style, ignoredPrefixes = [], {zoom = null, roadNames = {}} = {}) {
    const ignored = id => ignoredPrefixes.some(prefix => String(id).startsWith(prefix));
    const sources = Object.fromEntries(Object.entries(style.sources || {}).filter(([id]) => !ignored(id)));
    for (const [id, data] of Object.entries(roadNames)) {
        if (sources[id]) sources[ROAD_NAMES_SOURCE + id] = {type: "geojson", data};
    }
    const unnamed = new Set(zoom === null ? [] : unnamedRoadLayers(style, zoom).map(layer => layer.id));
    const layers = (style.layers || [])
        .filter(layer => !ignored(layer.id))
        .map(layer => {
            if (!unnamed.has(layer.id) || !sources[ROAD_NAMES_SOURCE + layer.source]) {
                const hidden = {...layer, layout: {...layer.layout, visibility: "none"}};
                // What a basemap draws from a zoom a little deeper than the map is drawn at (a
                // stream, a service road) is on a map of this scale, and is in the tiles it is
                // drawn from: it is drawn.  Not names, of which there would be too many.
                if (zoom !== null && layer.type !== "symbol" && layer.minzoom > zoom
                    && layer.minzoom <= EXPORT_DETAIL_ZOOM) {
                    hidden.minzoom = Math.floor(zoom);
                }
                return hidden;
            }
            const {minzoom, "source-layer": sourceLayer, ...named} = layer;
            return {
                ...named,
                source: ROAD_NAMES_SOURCE + layer.source,
                layout: {
                    ...layer.layout,
                    "symbol-placement": "point",
                    "text-rotate": ["get", NAME_ANGLE],
                    "text-rotation-alignment": "map",
                    // A name along a line is one line; a name at a point is broken into several
                    // unless it is told it has the room.
                    "text-max-width": ROAD_NAME_MAX_EMS,
                    visibility: "none",
                },
            };
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

// Only the time the page can be seen is counted: a browser does not draw a page which can not be
// seen (another tab is in front of it), and the map is not slow for that.
function once(map, event, timeoutMs = RENDER_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
        let seenMs = 0;
        const timer = setInterval(() => {
            if (typeof document !== "undefined" && document.hidden) return;
            seenMs += RENDER_WATCH_MS;
            if (seenMs >= timeoutMs) {
                clearInterval(timer);
                reject(new Error("The map took too long to draw"));
            }
        }, RENDER_WATCH_MS);
        map.once(event, () => {
            clearInterval(timer);
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
// is slow, and a part too small to survive the reduction is too small to matter.  Its four edges are
// looked at by themselves: a photograph which ends a little inside the map leaves a strip along an
// edge, which is narrow enough to be lost in the reduction and wide enough to be seen.
export function isOpaque(canvas) {
    const small = document.createElement("canvas");
    small.width = 64;
    small.height = Math.max(1, Math.round(64 * canvas.height / canvas.width));
    const context = small.getContext("2d");
    if (!context) return false;
    const {width, height} = canvas;
    const parts = [
        [0, 0, width, height],
        [0, 0, width, 1], [0, height - 1, width, 1], [0, 0, 1, height], [width - 1, 0, 1, height],
    ];
    for (const [x, y, w, h] of parts) {
        context.clearRect(0, 0, small.width, small.height);
        context.drawImage(canvas, x, y, w, h, 0, 0, small.width, small.height);
        const {data} = context.getImageData(0, 0, small.width, small.height);
        for (let i = 3; i < data.length; i += 4) {
            if (data[i] !== 255) return false;
        }
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
    const cancelled = () => Object.assign(new Error("The export was cancelled"), {cancelled: true});
    const roadNames = await loadRoadNames(style, frame, readTile, isCancelled);
    // Reading the names is the first of the work, and may be the slowest of it.
    if (isCancelled && isCancelled()) throw cancelled();
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
                throw cancelled();
            }
            if (onProgress) onProgress(group.name, index, groups.length);
            const show = visibility => {
                for (const id of group.ids) {
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
//
// contours: {interval, unit} ("feet" or "meters"): how far apart the contour lines of the exported
// map are, when it has them.
//
// legend: the lines of the map as they are drawn (of exportLegend), when it has any.
export function exportSheet(quad, map, groups, now = new Date(), named = null, contours = null, legend = null) {
    return {
        name: quadTitle(named) || quadLabel(quad),
        credits: exportCredits(map, groups),
        date: exportDate(now),
        ...(contours ? {contours} : {}),
        ...(legend ? {legend} : {}),
    };
}

// How far apart the contour lines of an exported map are, for exportSheet; null when no layer of
// `contourLayers` (parts of ids, as the layer control has them) is among the `groups` which are
// exported, or no line is drawn at the zoom.
//
// interval: [minor, major] at the zoom the map is exported at (see contourInterval).
export function exportContours(groups, contourLayers, interval, imperial) {
    const exported = groups.some(group => group.ids.some(id => contourLayers.some(part => id.includes(part))));
    if (!exported || !interval) return null;
    return {interval: interval[0], unit: imperial ? "feet" : "meters"};
}

// "N40.250_W105.125": where a quadrangle's southwest corner is, in a form a file can be named.
function quadFileStem(quad) {
    const part = (value, positive, negative) => `${value < 0 ? negative : positive}${Math.abs(value).toFixed(3)}`;
    return `${part(quad.south, "N", "S")}_${part(quad.west, "E", "W")}`;
}

// A name as a part of a file's: "Berthoud".
function fileNamePart(name) {
    // An accent is left off its letter (Cañon is Canon), not made a gap in the name.
    return String(name).normalize("NFKD").replace(/\p{M}+/gu, "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);
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
