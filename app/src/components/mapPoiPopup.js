// Popup content for a clicked map POI, built only from attributes already in the pmtiles file.
// The Protomaps basemap keeps name, kind, kind_detail and elevation; there is no address,
// phone or opening hours to show.

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// "american_football" -> "American football"
function humanize(value) {
    const s = String(value).replace(/_/g, " ").trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatCoordinates(lon, lat) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

// Returns the popup HTML for the clicked POI features, or null when nothing useful was clicked.
// The same POI is often present at several min_zoom levels in one tile, so features are deduped
// by name and kind.  Coordinates come from the feature's own point when it has one, otherwise
// from where the user clicked (clickLngLat is {lng, lat}).
export function poiPopupHtml(features, clickLngLat = null) {
    const seen = new Set();
    const items = [];
    for (const feature of features || []) {
        const p = feature?.properties || {};
        const name = p.name || p["name:en"];
        if (!name && !p.kind) continue;
        const key = `${name}|${p.kind}`;
        if (seen.has(key)) continue;
        seen.add(key);

        const rows = [];
        if (p.kind) {
            const detail = p.kind_detail && p.kind_detail !== "none" ? ` (${humanize(p.kind_detail)})` : "";
            rows.push(`${humanize(p.kind)}${detail}`);
        }
        if (p.elevation !== undefined && p.elevation !== null && p.elevation !== ""
            && Number.isFinite(Number(p.elevation))) {
            const meters = Math.round(Number(p.elevation));
            const feet = Math.round(meters * 3.28084);
            rows.push(`Elevation: ${meters} m / ${feet} ft`);
        }
        const geometry = feature?.geometry;
        const point = geometry?.type === "Point" && Array.isArray(geometry.coordinates)
            ? geometry.coordinates : null;
        const coordinates = point
            ? formatCoordinates(Number(point[0]), Number(point[1]))
            : clickLngLat && formatCoordinates(Number(clickLngLat.lng), Number(clickLngLat.lat));
        if (coordinates) rows.push(coordinates);

        items.push(
            `<div style="margin-bottom:6px">` +
            `<strong>${escapeHtml(name || humanize(p.kind))}</strong>` +
            rows.map(r => `<br/><small>${escapeHtml(r)}</small>`).join("") +
            `</div>`
        );
    }
    if (!items.length) return null;
    return `<div style="font-size:13px;padding-right:12px">${items.join("")}</div>`;
}
