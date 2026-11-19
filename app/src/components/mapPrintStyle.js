// The map as it is printed.  The light and dark maps are made for a screen, which is lit: their
// roads are white on pale gray and their streams half a pixel of pale blue, which is nothing on
// paper.  The printed map is drawn on white, with dark lines and names, in the colors a topographic
// sheet has: black for what was built, blue for water, green for what grows, brown for the land.

import {layersWithCustomTheme, namedTheme} from "protomaps-themes-base";

// What the map is called where a look is chosen and remembered.
export const PRINT_LOOK = "print";
// The looks a map may be exported in: the printed map, and the two a screen has.
export const EXPORT_LOOKS = [
    {value: PRINT_LOOK, label: "Print"},
    {value: "light", label: "Light"},
    {value: "dark", label: "Dark"},
];
const STORAGE_KEY_LOOK = "wrolpi-map-export-look";

const BLACK = "#1a1a1a";
const CASING = "#4d4d4d";
const WHITE = "#ffffff";
const WATER = "#a9d4f2";
// Water which is a line (a stream) or a name is darker than water which is an area: a thin pale
// line is not seen.
const WATER_LINE = "#2f7fc4";
const WATER_NAME = "#1b5fa3";
const HIGHWAY = "#e2725b";
const MAJOR = "#f2c14e";
const TUNNEL = "#e6e6e6";
const TUNNEL_CASING = "#9a9a9a";

// The colors of the printed map which are not the light map's.  A basemap is drawn in some seventy
// colors (see `namedTheme`), and these are every one which is seen at the scale of a quadrangle.
export const PRINT_COLORS = {
    background: WHITE,
    earth: WHITE,
    park_a: "#dcefd0",
    park_b: "#c2e2b0",
    wood_a: "#d3ebc6",
    wood_b: "#b5dca4",
    scrub_a: "#e3edcd",
    scrub_b: "#cfe0b3",
    hospital: "#f3e3e0",
    school: "#f1ead9",
    industrial: "#e6e4ec",
    pedestrian: "#efefef",
    glacier: "#eef7fd",
    sand: "#f4ecd2",
    beach: "#f4ecd2",
    aerodrome: "#e7e7ee",
    runway: "#a9a9b3",
    zoo: "#d6ecd6",
    military: "#eedddd",
    water: WATER,
    pier: "#d9d9d9",
    buildings: "#6e6e6e",

    tunnel_other_casing: TUNNEL_CASING,
    tunnel_minor_casing: TUNNEL_CASING,
    tunnel_link_casing: TUNNEL_CASING,
    tunnel_major_casing: TUNNEL_CASING,
    tunnel_highway_casing: TUNNEL_CASING,
    tunnel_other: TUNNEL,
    tunnel_minor: TUNNEL,
    tunnel_link: TUNNEL,
    tunnel_major: TUNNEL,
    tunnel_highway: TUNNEL,

    minor_service_casing: CASING,
    minor_casing: CASING,
    link_casing: CASING,
    major_casing_late: BLACK,
    major_casing_early: BLACK,
    highway_casing_late: BLACK,
    highway_casing_early: BLACK,
    other: CASING,
    minor_service: WHITE,
    minor_a: WHITE,
    minor_b: WHITE,
    link: MAJOR,
    major: MAJOR,
    highway: HIGHWAY,

    bridges_other_casing: CASING,
    bridges_minor_casing: CASING,
    bridges_link_casing: CASING,
    bridges_major_casing: BLACK,
    bridges_highway_casing: BLACK,
    bridges_other: CASING,
    bridges_minor: WHITE,
    bridges_link: MAJOR,
    bridges_major: MAJOR,
    bridges_highway: HIGHWAY,

    railway: BLACK,
    boundaries: "#5b4b8a",

    waterway_label: WATER_NAME,
    ocean_label: WATER_NAME,
    peak_label: "#6b4423",
    roads_label_minor: BLACK,
    roads_label_minor_halo: WHITE,
    roads_label_major: BLACK,
    roads_label_major_halo: WHITE,
    subplace_label: "#333333",
    subplace_label_halo: WHITE,
    city_label: "#000000",
    city_label_halo: WHITE,
    state_label: "#555555",
    state_label_halo: WHITE,
    country_label: "#555555",
    address_label: "#444444",
    address_label_halo: WHITE,
    pois: {
        blue: "#12648a",
        green: "#17643a",
        lapis: "#24449c",
        pink: "#b02f85",
        red: "#b5304f",
        slategray: "#4b3f69",
        tangerine: "#9a4e03",
        turquoise: "#00808c",
    },
    landcover: {
        grassland: "rgba(228, 242, 216, 1)",
        barren: "rgba(248, 241, 222, 1)",
        urban_area: "rgba(240, 240, 240, 1)",
        farmland: "rgba(234, 243, 216, 1)",
        glacier: "rgba(238, 247, 253, 1)",
        scrub: "rgba(229, 238, 208, 1)",
        forest: "rgba(205, 232, 194, 1)",
    },
};

// What a color does not say of a layer of the printed map: how wide its line is, and how much of
// it is seen.  {layer id: paint which is the layer's on paper}.
export const PRINT_PAINT = {
    // A stream is half a pixel on a screen, and a river is the color of a lake.
    water_stream: {"line-color": WATER_LINE, "line-width": 1.2},
    water_river: {"line-color": WATER_LINE},
    // A path is not drawn on a screen until the map is deeper than a quadrangle is drawn.
    roads_other: {"line-width": 1.2, "line-dasharray": [4, 2]},
    roads_bridges_other: {"line-width": 1.2, "line-dasharray": [4, 2]},
    roads_rail: {"line-opacity": 1},
    boundaries: {"line-width": 1.2},
    boundaries_country: {"line-width": 1.6},
    buildings: {"fill-opacity": 0.75},
};

// The contour lines and their heights, which are not of a basemap: brown, and dark enough to follow.
export const PRINT_CONTOURS = {
    minor: {"line-color": "rgba(140, 85, 35, 0.55)", "line-width": 0.6},
    major: {"line-color": "rgba(140, 85, 35, 0.9)", "line-width": 1.1},
    label: {"text-color": "rgba(110, 65, 25, 1)", "text-halo-color": "rgba(255, 255, 255, 0.9)"},
};

// Every color of the printed map.
export function printTheme() {
    return {...namedTheme("light"), ...PRINT_COLORS};
}

// The layers of a basemap file (a source of the map's style) as they are printed.
export function printLayers(source, lang = undefined) {
    return layersWithCustomTheme(source, printTheme(), lang).map(layer => {
        const paint = PRINT_PAINT[layer.id];
        return paint ? {...layer, paint: {...layer.paint, ...paint}} : layer;
    });
}

// The look a map was last exported in, in this browser: the printed map until another is chosen.
export function savedExportLook() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY_LOOK);
        if (EXPORT_LOOKS.some(look => look.value === saved)) return saved;
    } catch (e) { /* ignore */ }
    return PRINT_LOOK;
}

export function saveExportLook(look) {
    try { localStorage.setItem(STORAGE_KEY_LOOK, look); } catch (e) { /* ignore */ }
}

// The flavor and the sprite of the map's style for a look: {flavor, sprite}.  Nothing for no look,
// which is the map as the screen has it.
export function lookStyle(look) {
    if (look === PRINT_LOOK) return {flavor: PRINT_LOOK, sprite: "light"};
    if (look === "light" || look === "dark") return {flavor: look, sprite: look};
    return {};
}
