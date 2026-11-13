// A style a person put beside a PMTiles file says how that overlay is drawn, in place of the generic
// colors.  It is an ordinary MapLibre style document written for some other map, so only what is
// safe and meaningful here is taken from it: the layers which draw this file.  Its sources, sprite
// and glyph URLs are never used, so a style cannot make the map ask another host for anything.

import {validateStyleMin} from "@maplibre/maplibre-gl-style-spec";
import {mediaUrl, overlaySourceId} from "./mapOverlays";

// The fonts the map has glyphs for (modules/map/static/fonts).  The map has one glyph URL, so a
// style's own fonts cannot be loaded; each is replaced by the nearest of these.
const FONT_REGULAR = "Noto Sans Regular";
const FONT_MEDIUM = "Noto Sans Medium";
const FONT_ITALIC = "Noto Sans Italic";

// Properties whose value names an image of the sprite.
const IMAGE_PROPERTIES = {
    layout: ["icon-image"],
    paint: ["fill-pattern", "line-pattern", "fill-extrusion-pattern"],
};

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

// The id of an overlay's sprite; MapLibre knows its images as `<sprite id>:<image name>`.
export function overlaySpriteId(file) {
    return overlaySourceId(file);
}

// The sprite sheet of an overlay, as MapLibre asks for it (it appends `@2x` and the extension).
export function overlaySpriteUrl(file) {
    const path = String(file.map_path).split("/").map(encodeURIComponent).join("/");
    return `${window.location.origin}/api/map/files/sprite/${path}`;
}

// Point an image name at the overlay's sprite.  The value is wrapped, not rewritten: the strings of
// an expression are not all image names (the labels of a `match` are not), but whatever it
// evaluates to is.  An empty name stays empty: no image.
function adaptImage(value, spriteId) {
    if (typeof value === "string") {
        return value ? `${spriteId}:${value}` : value;
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

function validationErrors(layer, source, spriteId) {
    return validateStyleMin({
        version: 8,
        sources: {[source]: {type: "vector", url: "pmtiles://overlay"}},
        sprite: [{id: "default", url: "https://localhost/default"}, {id: spriteId, url: "https://localhost/overlay"}],
        glyphs: "https://localhost/{fontstack}/{range}.pbf",
        layers: [layer],
    });
}

// Turn a style written for another map into the layers which draw `file` on this one.
// Returns {layers, skipped}: `skipped` counts the layers of this file which were not usable.
export function adaptOverlayStyle(style, file) {
    if (!style || !Array.isArray(style.layers)) return {layers: [], skipped: 0};

    const fileLayerIds = new Set((file.vector_layers || []).map(l => l.id));
    const styleSource = chooseSource(style, fileLayerIds);
    const source = overlaySourceId(file);
    const spriteId = overlaySpriteId(file);
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
        for (const [group, properties] of Object.entries(IMAGE_PROPERTIES)) {
            for (const property of properties) {
                if (layer[group]?.[property] === undefined) continue;
                if (file.has_sprite) {
                    layer[group][property] = adaptImage(layer[group][property], spriteId);
                } else {
                    // No sprite sheet came with the style: there are no images to draw.
                    delete layer[group][property];
                }
            }
        }

        // One bad layer must not stop the map: MapLibre refuses a whole style over it.
        let errors;
        try {
            errors = validationErrors(layer, source, spriteId);
        } catch (e) {
            errors = [e];
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
export async function loadOverlayStyle(file) {
    if (!file.style_path) return null;
    try {
        const response = await fetch(mediaUrl(file.style_path));
        if (!response.ok) return null;
        const adapted = adaptOverlayStyle(await response.json(), file);
        return adapted.layers.length ? adapted : null;
    } catch (e) {
        console.error(`Could not use the style of ${file.map_path}:`, e);
        return null;
    }
}

// Attach its style to each overlay file which has one (`styleLayers`, `styleSkipped`).
export async function loadOverlayStyles(overlays) {
    return Promise.all((overlays || []).map(async file => {
        const adapted = await loadOverlayStyle(file);
        return adapted ? {...file, styleLayers: adapted.layers, styleSkipped: adapted.skipped} : file;
    }));
}
