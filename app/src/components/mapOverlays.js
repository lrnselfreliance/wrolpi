// The map viewer's side of the overlay code: the shared logic (../map-shared/overlays.js, which
// the standalone viewer uses too) with the URLs of this app, where a map file is fetched from the
// media directory.

import * as shared from "../map-shared/overlays.js";

export * from "../map-shared/overlays.js";

// The URL path of a file in the media directory (`path` is relative to the media directory).
export function mediaUrl(path) {
    return "/media/" + shared.encodePath(path);
}

export function pmtilesUrl(path) {
    return `pmtiles://${mediaUrl(path)}`;
}

export const MAP_URLS = {
    pmtiles: file => pmtilesUrl(file.path),
    style: file => mediaUrl(file.style_path),
};

export function buildOverlaySource(file) {
    return shared.buildOverlaySource(file, MAP_URLS);
}

export function addOverlaysToStyle(styleSources, allLayers, overlays, state) {
    return shared.addOverlaysToStyle(styleSources, allLayers, overlays, state, MAP_URLS);
}
