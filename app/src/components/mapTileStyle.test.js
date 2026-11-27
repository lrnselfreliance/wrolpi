// The tile service (tiles/) draws the map for ATAK and iTAK with the basemap layers the web map
// draws with (MapViewer's buildStyle).  It runs no JavaScript, so it reads them from a file made
// from protomaps-themes-base; this keeps that file the same as what the web map uses.
//
// After upgrading protomaps-themes-base, write the file again:
//   cd app && UPDATE_TILE_STYLE=1 CI=true npm test -- --watchAll=false mapTileStyle
import fs from "fs";
import path from "path";
import layers from "protomaps-themes-base";

const FILE = path.resolve(__dirname, "../../../tiles/basemap-light.json");
// The name of the source in the file; the tile service gives each map file a source of its own.
const SOURCE = "protomaps";

it("the tile service's basemap is the web map's light basemap", () => {
    const expected = JSON.stringify(layers(SOURCE, "light"), null, 1) + "\n";
    if (process.env.UPDATE_TILE_STYLE) fs.writeFileSync(FILE, expected);
    expect(fs.readFileSync(FILE, "utf8")).toEqual(expected);
});
