// Exporting a quadrangle of the map as a PDF.
//
// The browser draws the map, because nothing else draws it as the user sees it.  A second map, off
// the screen and the size of the printed sheet, is drawn once for each layer the user has turned on,
// with only that layer showing; the API puts the images in a PDF, each in a layer of its own, and
// (when it is asked to) on a sheet: with a margin, a grid, scale bars and notes around the map.

import {QUAD_DEGREES, QUAD_SCALE, quadLabel, quadSize} from "./mapQuads";
import {isOverlayLayerId} from "./mapOverlays";

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
        center: [(quad.west + quad.east) / 2, latitudeOfMercatorY((south + north) / 2)],
    };
}

// The name of a basemap layer without the source it is of ("oregon.pmtiles:water" is "water").
function basemapLayerName(layerId) {
    return layerId.includes(":") ? layerId.split(":").slice(1).join(":") : layerId;
}

// The layers of the PDF: the visible layers of the map's style, gathered as the layer control
// gathers them, from the bottom up.  Each is {name, ids, raster}.
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
            add(`overlay ${layer.source}`, overlayLabels[layer.source] || layer.source, index, layer);
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
    const used = new Set();
    return ordered.map(({name, ids, raster}) => {
        let unique = name;
        for (let n = 2; used.has(unique); n++) unique = `${name} (${n})`;
        used.add(unique);
        return {name: unique, ids, raster};
    });
}

// A copy of the map's style in which nothing is drawn, for the map which is exported from; the
// layers are shown a group at a time.  Layers which are of the app and not of the map (those whose
// id starts with one of `ignoredPrefixes`) are not in it.
export function exportStyle(style, ignoredPrefixes = []) {
    const ignored = id => ignoredPrefixes.some(prefix => String(id).startsWith(prefix));
    const sources = Object.fromEntries(Object.entries(style.sources || {}).filter(([id]) => !ignored(id)));
    const layers = (style.layers || [])
        .filter(layer => !ignored(layer.id))
        .map(layer => ({...layer, layout: {...layer.layout, visibility: "none"}}));
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
// onProgress(name, index, count): called before each group is drawn.
export async function renderExport({MapClass, style, frame, groups, setup, onProgress, ignoredPrefixes = []}) {
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
            style: exportStyle(style, ignoredPrefixes),
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
        // An attribution is HTML: links, mostly.
        const html = new DOMParser().parseFromString(String(attribution), "text/html");
        const text = (html.body.textContent || "").replace(/\s+/g, " ").trim();
        if (text && !credits.includes(text)) credits.push(text);
    }
    return credits;
}

// The day, as the person exporting the map has it: 2026-11-15.
export function exportDate(now = new Date()) {
    const pad = value => String(value).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// What is written on the sheet a quadrangle is printed on.
export function exportSheet(quad, map, groups, now = new Date()) {
    return {name: quadLabel(quad), credits: exportCredits(map, groups), date: exportDate(now)};
}

// "N40.250_W112.000": where a quadrangle's southwest corner is, in a form a file can be named.
function quadFileStem(quad) {
    const part = (value, positive, negative) => `${value < 0 ? negative : positive}${Math.abs(value).toFixed(3)}`;
    return `${part(quad.south, "N", "S")}_${part(quad.west, "E", "W")}`;
}

export function exportFileName(quad) {
    return `wrolpi-map_${QUAD_SCALE / 1000}k_${quadFileStem(quad)}.pdf`;
}

export function exportTitle(quad) {
    return `1:${QUAD_SCALE.toLocaleString("en-US")} ${quadLabel(quad)}`;
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
