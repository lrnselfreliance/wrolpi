// The map viewer's side of the sidecar style code: the shared logic
// (../map-shared/overlayStyle.js) with this app's URLs, and with each layer checked by MapLibre's
// style validator before it reaches the map.

import {validateStyleMin} from "@maplibre/maplibre-gl-style-spec";
import * as shared from "../map-shared/overlayStyle.js";
import {MAP_URLS} from "./mapOverlays";

export * from "../map-shared/overlayStyle.js";

// The errors of one layer, as part of a style which has its source and sprites.
function validateLayer(layer, source, spriteId) {
    return validateStyleMin({
        version: 8,
        sources: {[source]: {type: "vector", url: "pmtiles://overlay"}},
        sprite: [{id: "default", url: "https://localhost/default"}, {id: spriteId, url: "https://localhost/overlay"}],
        glyphs: "https://localhost/{fontstack}/{range}.pbf",
        layers: [layer],
    });
}

const OPTIONS = {urls: MAP_URLS, validateLayer};

export function adaptOverlayStyle(style, file) {
    return shared.adaptOverlayStyle(style, file, OPTIONS);
}

export function loadOverlayStyle(file) {
    return shared.loadOverlayStyle(file, OPTIONS);
}

export function loadOverlayStyles(overlays) {
    return shared.loadOverlayStyles(overlays, OPTIONS);
}
