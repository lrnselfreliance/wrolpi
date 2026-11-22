// Several bursts at once: each target's weapon, and the fallout of all of them on one map.  Shared by
// the app's map viewer and the standalone viewer: no imports from the app, no dependencies.

import {weaponByKey} from './weapons.js';

const METERS_PER_DEGREE = 111320;

// The weapon a target has when none was chosen for it.
export const DEFAULT_WEAPON = 'w87-0';
export const CUSTOM_WEAPON = 'custom';

// What a target (a pin of kind "target", or any {weapon, yield_kt, fission_fraction}) will be
// burst with: {key, yieldKt, fissionFraction, weapon (as weapons.json has it, or null for a yield
// of the user's own)}.  A target's own fission share is kept over its weapon's.
export function targetWeapon(target) {
    const key = target?.weapon || DEFAULT_WEAPON;
    if (key === CUSTOM_WEAPON) {
        return {
            key, weapon: null,
            yieldKt: target.yield_kt > 0 ? target.yield_kt : 100,
            fissionFraction: target.fission_fraction > 0 ? target.fission_fraction : 0.5,
        };
    }
    const weapon = weaponByKey(key) || weaponByKey(DEFAULT_WEAPON);
    return {
        key: weapon.key, weapon,
        yieldKt: weapon.yield_kt,
        fissionFraction: target?.fission_fraction > 0 ? target.fission_fraction : weapon.fission_fraction,
    };
}

// Where `point` ({lat, lon}) is from `origin`: [m east, m north].
export function offsetFrom(origin, point) {
    const perLon = METERS_PER_DEGREE * Math.cos(origin.lat * Math.PI / 180);
    return [(point.lon - origin.lon) * perLon, (point.lat - origin.lat) * METERS_PER_DEGREE];
}

// The middle of `points` ({lat, lon}).
export function middleOf(points) {
    const lat = points.reduce((a, p) => a + p.lat, 0) / points.length;
    const lon = points.reduce((a, p) => a + p.lon, 0) / points.length;
    return {lat, lon};
}

// The landing spots of several bursts on one map, around `origin`: runs are [{burst ({lat, lon}),
// spots (as landingSpots gives them, around the burst), yieldKt, fissionFraction}].  Each spot is
// moved to where it is from `origin`, and carries its burst's fission yield (kt), so the spots of
// every burst go on one grid as if of a single kiloton of fission (depositionGrid with yieldKt 1).
//
// The grid's meters east are degrees of longitude at the origin's latitude (as offsetFrom, and the
// map image, take them); a burst's own meters east are shorter or longer there by how much a degree
// is at its latitude, so they are scaled to the grid's.
export function combineBursts(origin, runs) {
    const combined = [];
    for (const {burst, spots, yieldKt, fissionFraction} of runs) {
        const [dx, dy] = offsetFrom(origin, burst);
        const east = Math.cos(origin.lat * Math.PI / 180) / Math.cos(burst.lat * Math.PI / 180);
        const kt = yieldKt * fissionFraction;
        for (const s of spots) combined.push({...s, x: dx + s.x * east, y: s.y + dy, activity: s.activity * kt});
    }
    return combined;
}
