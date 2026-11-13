// A style a person put beside a PMTiles file says how that overlay is drawn, in place of the generic
// colors.  It is an ordinary MapLibre style document written for some other map, so only what is
// safe and meaningful here is taken from it: the layers which draw this file.  Its sources, sprite
// and glyph URLs are never used, so a style cannot make the map ask another host for anything.

//
// SHARED by the map viewer of the app and the standalone viewer; see overlays.js for the rules
// this file keeps.  A viewer which can check a layer before giving it to MapLibre passes
// `validateLayer(layer, sourceId, spriteId)`, which returns the layer's errors.

import {overlaySourceId} from "./overlays.js";

// The fonts the map has glyphs for (modules/map/static/fonts).  The map has one glyph URL, so a
// style's own fonts cannot be loaded; each is replaced by the nearest of these.
const FONT_REGULAR = "Noto Sans Regular";
const FONT_MEDIUM = "Noto Sans Medium";
const FONT_ITALIC = "Noto Sans Italic";

// The map's own icons for overlays (see wrolpi/scripts/build_map_icons.py): a sprite beside the
// basemap's.  MapLibre knows its images as `<sprite id>:<image name>`.  Its index lists each icon
// under every name a style may call it, so pointing an image at this sprite is the whole
// translation; the artwork a style was made for is never used.
export const OVERLAY_ICONS_SPRITE_ID = "overlay-icons";

// How an icon is drawn when its style does not say: dark, with a light edge, to be seen on any
// basemap.  (The icons are signed distance fields, which take a color and a halo.)
const ICON_PAINT_DEFAULTS = {"icon-color": "#222222", "icon-halo-color": "#ffffff", "icon-halo-width": 1};

// A pattern is an image the map does not have; what it filled is drawn in a translucent color.
const PATTERN_PROPERTIES = ["fill-pattern", "line-pattern", "fill-extrusion-pattern"];
const PATTERN_COLOR = "#808080";
const PATTERN_OPACITY = 0.25;

// Expression operators a `text-font` value can start with; anything else is a plain list of fonts.
const FONT_EXPRESSIONS = new Set(["literal", "match", "case", "step", "coalesce", "let", "var", "get"]);

export function bundledFont(name) {
    if (/italic|oblique/i.test(name)) return FONT_ITALIC;
    if (/bold|medium|black|heavy/i.test(name)) return FONT_MEDIUM;
    return FONT_REGULAR;
}

const fontList = fonts => [...new Set(fonts.map(f => bundledFont(String(f))))];

// Inside an expression only a `literal` list is a list of fonts; other lists are not (the labels
// of a `match` are a list of strings too).
function adaptFontExpression(value) {
    if (!Array.isArray(value)) return value;
    if (value[0] === "literal" && Array.isArray(value[1])) return ["literal", fontList(value[1])];
    return value.map(adaptFontExpression);
}

// Replace every font a `text-font` value names, as a plain list or as the literal lists of an
// expression.
function adaptFonts(value) {
    if (!Array.isArray(value)) return value;
    return FONT_EXPRESSIONS.has(value[0]) ? adaptFontExpression(value) : fontList(value);
}

// A `text-field` can set the font of a part of the text (the options of a `format` section); those
// fonts are replaced too.
function adaptTextFieldFonts(value) {
    if (Array.isArray(value)) return value.map(adaptTextFieldFonts);
    if (value && typeof value === "object") {
        const options = {};
        for (const [key, option] of Object.entries(value)) {
            options[key] = key === "text-font" ? adaptFonts(option) : adaptTextFieldFonts(option);
        }
        return options;
    }
    return value;
}

// The image MapLibre is given for a name the overlay icons do not have: a plain dot, so that a
// feature is marked on the map whatever its style calls its icon.  A signed distance field, as
// the icons are.
export function missingOverlayIcon() {
    const size = 25, radius = 5;
    const data = new Uint8Array(size * size * 4);
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const outside = Math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2) - radius;
            data[(y * size + x) * 4 + 3] = Math.max(0, Math.min(255, Math.round(255 - 255 * (outside / 8 + 0.25))));
        }
    }
    return {width: size, height: size, data};
}

// For a map's `styleimagemissing` event: supply the dot for a name the overlay icons do not have.
export function addMissingOverlayIcon(map, id) {
    if (!String(id).startsWith(`${OVERLAY_ICONS_SPRITE_ID}:`) || map.hasImage(id)) return false;
    map.addImage(id, missingOverlayIcon(), {sdf: true});
    return true;
}

const isZoom = value => Array.isArray(value) && value.length === 1 && value[0] === "zoom";

// An image may be named by a property function (the older form of an expression: an object with
// `stops`, or `type: "identity"`).  It is rewritten as the expression which gives the same name,
// so that the name can be pointed at the overlay's sprite.  Returns undefined for a function
// this does not know how to rewrite.
function imageFunctionExpression(fn) {
    const fallback = typeof fn.default === "string" ? fn.default : "";
    if (fn.type === "identity" && typeof fn.property === "string") {
        return ["coalesce", ["get", fn.property], fallback];
    }

    const stops = fn.stops;
    if (!Array.isArray(stops) || !stops.length || !stops.every(i => Array.isArray(i) && i.length === 2)) {
        return undefined;
    }
    const inputs = stops.map(i => i[0]);
    const outputs = stops.map(i => i[1]);
    if (!outputs.every(i => typeof i === "string")) return undefined;

    if (fn.type === "categorical") {
        // One name per value of the property.
        const labels = inputs.every(i => typeof i === "string") || inputs.every(i => typeof i === "number");
        if (typeof fn.property !== "string" || !labels || new Set(inputs).size !== inputs.length) return undefined;
        return ["match", ["get", fn.property], ...stops.flat(), fallback];
    }
    if (fn.type !== undefined && fn.type !== "interval") return undefined;
    if (!inputs.every(i => typeof i === "number") || inputs.some((v, i) => i > 0 && v <= inputs[i - 1])) {
        return undefined;
    }
    // A single stop is one name, whatever the input.
    if (stops.length === 1) return outputs[0];
    // One name per range of the zoom, or of a numeric property; below the first stop is the first.
    const input = fn.property === undefined ? ["zoom"]
        : typeof fn.property === "string" ? ["to-number", ["get", fn.property], inputs[0]] : undefined;
    if (!input) return undefined;
    return ["step", input, outputs[0], ...stops.slice(1).flat()];
}

// Point an image name at the overlay's sprite.  The value is wrapped, not rewritten: the strings of
// an expression are not all image names (the labels of a `match` are not), but whatever it
// evaluates to is.  An empty name stays empty: no image.  Returns undefined when the value is one
// this cannot point at the sprite.
function adaptImage(value, spriteId) {
    if (typeof value === "string") {
        return value ? `${spriteId}:${value}` : value;
    }
    if (value && typeof value === "object" && !Array.isArray(value)) {
        const expression = imageFunctionExpression(value);
        return expression === undefined ? undefined : adaptImage(expression, spriteId);
    }
    if (!Array.isArray(value)) return undefined;
    if (value[0] === "step" && isZoom(value[1])) {
        // The zoom may only be the input of the outermost expression, so each name it chooses
        // between is wrapped, not the whole.
        const adapted = value.map((part, index) =>
            (index >= 2 && index % 2 === 0) ? adaptImage(part, spriteId) : part);
        return adapted.includes(undefined) ? undefined : adapted;
    }
    return ["image", ["let", "wrolpi_image", ["to-string", value],
        ["case", ["==", ["var", "wrolpi_image"], ""], "",
            ["concat", `${spriteId}:`, ["var", "wrolpi_image"]]]]];
}

// The source of the style which is this file: the one the style names for us, else the one most of
// the layers which draw this file's layers use.
function chooseSource(style, fileLayerIds) {
    const named = style.metadata?.["wrolpi:source"];
    if (named) return named;
    const counts = {};
    for (const layer of style.layers) {
        if (layer && layer.source && fileLayerIds.has(layer["source-layer"])) {
            counts[layer.source] = (counts[layer.source] || 0) + 1;
        }
    }
    return Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
}

// Turn a style written for another map into the layers which draw `file` on this one.
// Returns {layers, skipped}: `skipped` counts the layers of this file which were not usable.
export function adaptOverlayStyle(style, file, {validateLayer} = {}) {
    if (!style || !Array.isArray(style.layers)) return {layers: [], skipped: 0};

    const fileLayerIds = new Set((file.vector_layers || []).map(l => l.id));
    const styleSource = chooseSource(style, fileLayerIds);
    const source = overlaySourceId(file);
    const spriteId = OVERLAY_ICONS_SPRITE_ID;
    // A style drawn for one scale (a printed map, say) is unreadable zoomed out; it can say the zoom
    // it is meant to be seen from.
    const minZoom = Number(style.metadata?.["wrolpi:minzoom"]);
    const layers = [];
    const ids = new Set();
    let skipped = 0;

    for (const original of style.layers) {
        // Only layers which draw this file: not the background, nor another source (hillshade, contours).
        if (!original || original.source !== styleSource || !fileLayerIds.has(original["source-layer"])) continue;

        const layer = JSON.parse(JSON.stringify(original));
        layer.id = `${source}:${layer["source-layer"]}:${original.id}`;
        layer.source = source;
        if (Number.isFinite(minZoom) && minZoom > (layer.minzoom || 0)) {
            layer.minzoom = minZoom;
        }

        if (layer.layout?.["text-font"] !== undefined) {
            layer.layout["text-font"] = adaptFonts(layer.layout["text-font"]);
        }
        if (layer.layout?.["text-field"] !== undefined) {
            layer.layout["text-field"] = adaptTextFieldFonts(layer.layout["text-field"]);
            // MapLibre's own default font is not one the map has.
            if (layer.layout["text-font"] === undefined) {
                layer.layout["text-font"] = [FONT_REGULAR];
            }
        }
        if (layer.layout?.["icon-image"] !== undefined) {
            // An image this cannot point at the overlay icons would be looked for among the
            // basemap's; the layer is drawn without it (its text still is).
            const image = adaptImage(layer.layout["icon-image"], spriteId);
            if (image === undefined) {
                delete layer.layout["icon-image"];
            } else {
                layer.layout["icon-image"] = image;
                // A size is a scale of the artwork the style was made for; ours has its own size.
                delete layer.layout["icon-size"];
                layer.paint = {...ICON_PAINT_DEFAULTS, ...layer.paint};
            }
        }
        const patterns = PATTERN_PROPERTIES.filter(property => layer.paint?.[property] !== undefined);
        for (const property of patterns) {
            delete layer.paint[property];
        }
        if (patterns.includes("fill-pattern")) {
            // Without its pattern MapLibre would fill the area in opaque black.
            layer.paint = {"fill-color": PATTERN_COLOR, "fill-opacity": PATTERN_OPACITY, ...layer.paint};
        }
        if (patterns.includes("line-pattern")) {
            layer.paint = {"line-color": PATTERN_COLOR, ...layer.paint};
        }

        // One bad layer must not stop the map: MapLibre refuses a whole style over it.
        let errors = [];
        if (validateLayer) {
            try {
                errors = validateLayer(layer, source, spriteId) || [];
            } catch (e) {
                errors = [e];
            }
        }
        if (errors.length || ids.has(layer.id)) {
            skipped += 1;
            continue;
        }
        ids.add(layer.id);
        layers.push(layer);
    }
    return {layers, skipped};
}

// Fetch and adapt the style beside an overlay file.  Returns null when the file has none, or it
// cannot be used; the overlay is then drawn generically.
export async function loadOverlayStyle(file, {urls, validateLayer} = {}) {
    if (!file.style_path) return null;
    try {
        const response = await fetch(urls.style(file));
        if (!response.ok) return null;
        const adapted = adaptOverlayStyle(await response.json(), file, {validateLayer});
        return adapted.layers.length ? adapted : null;
    } catch (e) {
        console.error(`Could not use the style of ${file.map_path}:`, e);
        return null;
    }
}

// Attach its style to each overlay file which has one (`styleLayers`, `styleSkipped`).
export async function loadOverlayStyles(overlays, options) {
    return Promise.all((overlays || []).map(async file => {
        const adapted = await loadOverlayStyle(file, options);
        return adapted ? {...file, styleLayers: adapted.layers, styleSkipped: adapted.skipped} : file;
    }));
}
