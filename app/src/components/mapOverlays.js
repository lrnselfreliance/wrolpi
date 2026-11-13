// Which map files the viewer draws, and how it draws the ones that are not a Protomaps basemap.
//
// The API says what each PMTiles file is (`kind`): a `basemap` is drawn with the basemap theme,
// `terrain` becomes hillshade and contours, and an `overlay` is any other vector or raster file.
// An overlay has no style of its own, so its layers are drawn generically: one color per layer,
// as fills, lines or circles.

import {escapeHtml} from "./mapPoiPopup";

// Every MapLibre source and layer of an overlay starts with this, so the basemap's layer groups
// (which match layer names like "water") never touch them.
export const OVERLAY_PREFIX = "overlay:";
export const STORAGE_KEY_OVERLAYS = "wrolpi-map-overlays";

const RASTER_SUFFIX = "raster";
const VECTOR_TYPES = ["fill", "line", "circle"];
// Readable on both the light and dark basemaps.
const OVERLAY_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#b455e0", "#17a2a2",
    "#f032e6", "#b07a3b", "#d1495b", "#8a9a1b", "#5b7fff", "#e6a700",
];
const POPUP_MAX_FEATURES = 3;
const POPUP_MAX_PROPERTIES = 12;

// Detect full planet files: "planet-20260329.pmtiles" or bare date like "20260329.pmtiles".
export function isPlanetFile(name) {
    if (name.startsWith("planet-")) return true;
    return /^\d{8}\.pmtiles$/.test(name);
}

// The URL path of a file in the media directory (`path` is relative to the media directory).
export function mediaUrl(path) {
    return "/media/" + String(path).split("/").map(encodeURIComponent).join("/");
}

export function pmtilesUrl(path) {
    return `pmtiles://${mediaUrl(path)}`;
}

// Sort the map files into what the viewer does with each.  Ignored files (`visible: false`) and
// unreadable files are left out.  A planet file covers everything, so it replaces the regional
// extracts; overlays and terrain are drawn either way.
export function planMapFiles(files) {
    const visible = (files || []).filter(f => f.visible !== false);
    const basemaps = visible.filter(f => f.kind === "basemap");
    let planet = null;
    for (const f of basemaps) {
        if (isPlanetFile(f.name) && (!planet || f.size > planet.size)) planet = f;
    }
    const terrains = visible.filter(f => f.kind === "terrain");
    return {
        planet,
        regions: planet ? [] : basemaps,
        terrain: terrains.length ? terrains[terrains.length - 1] : null,
        overlays: visible.filter(f => f.kind === "overlay"),
    };
}

export function isRasterOverlay(file) {
    return file.tile_type !== "mvt";
}

function fileStem(name) {
    return String(name).replace(/\.pmtiles$/, "");
}

// What to call an overlay: the name the file gives itself, else its file name.  Files which would
// share a label also show where they are.
export function overlayLabel(file, files = []) {
    const base = f => (f.title && f.title.trim()) || fileStem(f.name);
    const label = base(file);
    const shared = files.some(f => f.map_path !== file.map_path && base(f) === label);
    return shared ? `${label} (${file.map_path})` : label;
}

// A stable color for a layer: the same layer name is the same color in every file and session.
export function overlayColor(layerId) {
    let hash = 5381;
    for (const c of String(layerId)) hash = ((hash * 33) ^ c.charCodeAt(0)) >>> 0;
    return OVERLAY_COLORS[hash % OVERLAY_COLORS.length];
}

// --- What the user chose to see.  {[map_path]: {enabled: bool, layers: {[layerId]: bool}}} ---

export function loadOverlayState() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY_OVERLAYS));
        if (saved && typeof saved === "object" && !Array.isArray(saved)) return saved;
    } catch (e) { /* ignore */ }
    return {};
}

export function saveOverlayState(state) {
    try { localStorage.setItem(STORAGE_KEY_OVERLAYS, JSON.stringify(state)); } catch (e) { /* ignore */ }
}

// An overlay is hidden until the user turns it on.
export function isOverlayEnabled(state, file) {
    return state?.[file.map_path]?.enabled === true;
}

// Once a file is on, each of its layers is drawn until the user turns that layer off.
export function isOverlayLayerEnabled(state, file, layerId) {
    return state?.[file.map_path]?.layers?.[layerId] !== false;
}

export function setOverlayEnabled(state, file, enabled) {
    return {...state, [file.map_path]: {...state?.[file.map_path], enabled}};
}

export function setOverlayLayerEnabled(state, file, layerId, enabled) {
    const entry = state?.[file.map_path] || {};
    return {...state, [file.map_path]: {...entry, layers: {...entry.layers, [layerId]: enabled}}};
}

export function setAllOverlayLayersEnabled(state, file, enabled) {
    const layers = {};
    for (const l of file.vector_layers || []) layers[l.id] = enabled;
    return {...state, [file.map_path]: {...state?.[file.map_path], layers}};
}

// --- MapLibre style ---

export function overlaySourceId(file) {
    return `${OVERLAY_PREFIX}${file.map_path}`;
}

export function isOverlayLayerId(layerId) {
    return String(layerId).startsWith(OVERLAY_PREFIX);
}

// MapLibre puts a source's attribution in the page as HTML, and this text comes from a file
// someone downloaded: only its text is kept.
function attributionText(attribution) {
    if (!attribution) return undefined;
    const text = new DOMParser().parseFromString(String(attribution), "text/html").body.textContent || "";
    return text.trim() ? escapeHtml(text.trim()) : undefined;
}

export function buildOverlaySource(file) {
    const source = {type: isRasterOverlay(file) ? "raster" : "vector", url: pmtilesUrl(file.path)};
    if (isRasterOverlay(file)) source.tileSize = 256;
    const attribution = attributionText(file.attribution);
    if (attribution) source.attribution = attribution;
    return source;
}

// The geometry a generator recorded for a layer ("Point", "LineString", "Polygon") names the one
// way to draw it.  Without that, the layer is drawn all three ways, each limited to its geometry.
const TYPE_OF_GEOMETRY = {Polygon: "fill", LineString: "line", Point: "circle"};
const GEOMETRY_OF_TYPE = {fill: "Polygon", line: "LineString", circle: "Point"};

function paintOf(type, color) {
    if (type === "fill") return {"fill-color": color, "fill-opacity": 0.25, "fill-outline-color": color};
    if (type === "line") return {"line-color": color, "line-width": 1.5};
    return {
        "circle-color": color, "circle-radius": 4,
        "circle-stroke-color": "#ffffff", "circle-stroke-width": 1,
    };
}

// The style layers of an overlay file, each already visible or hidden as `state` says; a source
// with no visible layer requests no tiles.
export function buildOverlayLayers(file, state) {
    const source = overlaySourceId(file);
    const enabled = isOverlayEnabled(state, file);
    const visibility = on => (on ? "visible" : "none");

    if (isRasterOverlay(file)) {
        return [{
            id: `${source}:${RASTER_SUFFIX}`, type: "raster", source,
            layout: {visibility: visibility(enabled)},
        }];
    }

    const styleLayers = [];
    for (const layer of file.vector_layers || []) {
        const color = overlayColor(layer.id);
        const known = TYPE_OF_GEOMETRY[layer.geometry];
        for (const type of known ? [known] : VECTOR_TYPES) {
            const styleLayer = {
                id: `${source}:${layer.id}:${type}`,
                type,
                source,
                "source-layer": layer.id,
                layout: {visibility: visibility(enabled && isOverlayLayerEnabled(state, file, layer.id))},
                paint: paintOf(type, color),
            };
            if (!known) styleLayer.filter = ["==", "$type", GEOMETRY_OF_TYPE[type]];
            styleLayers.push(styleLayer);
        }
    }
    return styleLayers;
}

// Add the overlays to a style's sources and layers (the basemap's are already there).  A raster
// overlay goes under the basemap's labels so the map stays readable; vector overlays go on top,
// fills under lines under points.
export function addOverlaysToStyle(styleSources, allLayers, overlays, state) {
    const rasters = [];
    const vectors = {fill: [], line: [], circle: []};
    for (const file of overlays || []) {
        styleSources[overlaySourceId(file)] = buildOverlaySource(file);
        for (const layer of buildOverlayLayers(file, state)) {
            if (layer.type === "raster") rasters.push(layer);
            else vectors[layer.type].push(layer);
        }
    }
    const firstLabel = allLayers.findIndex(l => l.type === "symbol");
    allLayers.splice(firstLabel === -1 ? allLayers.length : firstLabel, 0, ...rasters);
    allLayers.push(...vectors.fill, ...vectors.line, ...vectors.circle);
}

// --- Popup ---

// The popup HTML of the overlay features under a click, or null when there are none.  An overlay's
// attributes are whatever its author chose, so they are listed as they are.
export function overlayPopupHtml(features) {
    const seen = new Set();
    const blocks = [];
    for (const feature of features || []) {
        const layerId = feature.sourceLayer || feature.layer?.["source-layer"];
        const properties = feature.properties || {};
        if (!layerId) continue;
        const key = JSON.stringify([layerId, properties]);
        if (seen.has(key)) continue;
        seen.add(key);
        if (blocks.length >= POPUP_MAX_FEATURES) break;

        const entries = Object.entries(properties).filter(([, v]) => v !== null && v !== undefined && v !== "");
        const name = properties.name;
        const rows = entries
            .filter(([k]) => k !== "name")
            .slice(0, POPUP_MAX_PROPERTIES)
            .map(([k, v]) => `<br/><small>${escapeHtml(k)}: ${escapeHtml(v)}</small>`);
        const more = entries.length - (name !== undefined ? 1 : 0) - rows.length;
        blocks.push(
            `<div style="font-size:13px">` +
            `<strong>${escapeHtml(name !== undefined && name !== "" ? name : layerId)}</strong>` +
            (name !== undefined && name !== "" ? `<br/><small>${escapeHtml(layerId)}</small>` : "") +
            rows.join("") +
            (more > 0 ? `<br/><small>… ${more} more</small>` : "") +
            `</div>`
        );
    }
    return blocks.length ? blocks.join('<hr style="margin:4px 0"/>') : null;
}
