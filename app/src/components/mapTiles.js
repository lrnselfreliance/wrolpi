// Reading the tiles of a map file, as the map does not: one at a time, for what is in them.

import {PMTiles} from "pmtiles";
import {VectorTile} from "@mapbox/vector-tile";
import Pbf from "pbf";

const PROTOCOL = "pmtiles://";
const archives = new Map();

function archive(url) {
    const address = url.startsWith(PROTOCOL) ? url.slice(PROTOCOL.length) : url;
    if (!archives.has(address)) archives.set(address, new PMTiles(address));
    return archives.get(address);
}

// A tile of the vector map file which a source of the map's style has as its `url`, or null when
// the file has no such tile (it is not of that place, or does not go that deep).
export async function readVectorTile(url, {z, x, y}) {
    const tile = await archive(url).getZxy(z, x, y);
    return tile?.data ? new VectorTile(new Pbf(new Uint8Array(tile.data))) : null;
}
