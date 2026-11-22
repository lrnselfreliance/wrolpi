// The weapons the fallout simulator offers (weapons.json): deployed or stockpiled today, each with
// its yield as a cited source gives it.  Shared by the app's map viewer and the standalone viewer: no
// imports from the app, no dependencies.

import data from './weapons.json';

// [{name (of the country, or kind), weapons: [{key, name, yield_kt, yield_range_kt?,
// fission_fraction, status, source, quote}]}], in the order they are offered.
export const WEAPON_GROUPS = data.groups;

// The sources the weapons cite: {key: citation}.
export const WEAPON_SOURCES = data.sources;

const BY_KEY = new Map(WEAPON_GROUPS.flatMap((g) => g.weapons.map((w) => [w.key, {...w, group: g.name}])));

// The weapon with `key` (with the name of its group), or undefined.
export function weaponByKey(key) {
    return BY_KEY.get(key);
}

// A yield as it is written: kilotons, or megatons from 1000 kt up.
export function formatYield(kt) {
    if (kt >= 1000) return `${+(kt / 1000).toFixed(2)} Mt`;
    return `${+kt.toFixed(1)} kt`;
}
