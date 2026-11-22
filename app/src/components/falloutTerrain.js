import {PMTiles} from "pmtiles";
import {getMapFiles} from "../api";
import {mediaUrl} from "./mapOverlays";

// The ground under a fallout plume, read from the terrain files the user has downloaded (terrarium
// elevation tiles), as an elevation grid the model reads (map-shared/fallout/terrain.js).

// No more tiles than this are read for one plume; a wider plume is read at a coarser zoom.
const MAX_TILES = 36;
// Deeper than this adds nothing: a spot of fallout is at least a kilometer across.
const DEEPEST_ZOOM = 9;
// How many samples the grid has along its longer side.
const GRID_SAMPLES = 600;

function tileX(lon, z) {
    return Math.floor((lon + 180) / 360 * 2 ** z);
}

function tileY(lat, z) {
    const r = lat * Math.PI / 180;
    return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * 2 ** z);
}

async function decodeTile(data) {
    const bitmap = await createImageBitmap(new Blob([data]));
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d", {willReadFrequently: true});
    context.drawImage(bitmap, 0, 0);
    return context.getImageData(0, 0, bitmap.width, bitmap.height);
}

let terrainFiles = null;

// The terrain files, finest first: [{tiles (PMTiles), header}].
async function openTerrainFiles() {
    if (terrainFiles) return terrainFiles;
    const data = await getMapFiles();
    const files = (data?.files || []).filter((f) => f.kind === "terrain");
    const opened = await Promise.all(files.map(async (f) => {
        const tiles = new PMTiles(`${window.location.origin}${mediaUrl(f.path)}`);
        return {tiles, header: await tiles.getHeader()};
    }));
    terrainFiles = opened.sort((a, b) => b.header.maxZoom - a.header.maxZoom);
    return terrainFiles;
}

// The terrarium elevation (m) at `lon`, `lat` of the read tiles, or null where none was read.
function sample(tiles, n, lon, lat) {
    const r = lat * Math.PI / 180;
    const fx = (lon + 180) / 360 * n;
    const fy = (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n;
    const image = tiles.get(`${Math.floor(fx)}/${Math.floor(fy)}`);
    if (!image) return null;
    const px = Math.min(Math.floor((fx % 1) * image.width), image.width - 1);
    const py = Math.min(Math.floor((fy % 1) * image.height), image.height - 1);
    const p = (py * image.width + px) * 4;
    const d = image.data;
    // Terrarium: meters = R * 256 + G + B / 256 - 32768.  Below sea level is the sea floor, mostly:
    // fallout lands on the water.
    return Math.max(0, d[p] * 256 + d[p + 1] + d[p + 2] / 256 - 32768);
}

// An elevation grid over `bounds` ([west, south, east, north], degrees) around ground zero at `lon`,
// `lat`, or null when no terrain file covers ground zero.  Where no file covers the grid, it is as
// high as ground zero (flat ground, as the model takes it without terrain).  {grid, zoom, coverage
// (share of samples read from a file)}.
export async function loadTerrainGrid(bounds, lon, lat) {
    const files = await openTerrainFiles();
    if (!files.length) return null;
    const [west, south, east, north] = bounds;
    const covering = files.filter(({header: h}) =>
        h.minLon < east && h.maxLon > west && h.minLat < north && h.maxLat > south);
    if (!covering.length) return null;

    let zoom = Math.min(DEEPEST_ZOOM, Math.max(...covering.map((f) => f.header.maxZoom)));
    const count = (z) => (tileX(east, z) - tileX(west, z) + 1) * (tileY(south, z) - tileY(north, z) + 1);
    while (zoom > 0 && count(zoom) > MAX_TILES) zoom--;

    // Each tile from the finest file which has it.
    const tiles = new Map();
    const reads = [];
    for (let x = tileX(west, zoom); x <= tileX(east, zoom); x++) {
        for (let y = tileY(north, zoom); y <= tileY(south, zoom); y++) {
            reads.push((async () => {
                for (const {tiles: file, header} of covering) {
                    if (header.maxZoom < zoom) continue;
                    const tile = await file.getZxy(zoom, x, y);
                    if (tile?.data) {
                        tiles.set(`${x}/${y}`, await decodeTile(tile.data));
                        return;
                    }
                }
            })());
        }
    }
    await Promise.all(reads);
    if (!tiles.size) return null;

    const n = 2 ** zoom;
    const groundZero = sample(tiles, n, lon, lat);
    if (groundZero === null) return null;

    const step = Math.max(east - west, north - south) / GRID_SAMPLES;
    const nx = Math.ceil((east - west) / step) + 1;
    const ny = Math.ceil((north - south) / step) + 1;
    const values = new Float32Array(nx * ny);
    let read = 0;
    for (let j = 0; j < ny; j++) {
        for (let i = 0; i < nx; i++) {
            const v = sample(tiles, n, west + i * step, south + j * step);
            values[j * nx + i] = v === null ? groundZero : v;
            if (v !== null) read++;
        }
    }
    return {grid: {west, south, step, nx, ny, values}, zoom, coverage: read / (nx * ny)};
}
