// The air a fallout particle falls through, and how fast it falls.  Shared by the app's map viewer
// and the standalone viewer: no imports from the app, no dependencies.
//
// The air is the U.S. Standard Atmosphere, 1976, up to 32 km, which is above the top of the cloud
// of any weapon in the list.  A particle is a sphere of fused soil, and falls at the speed at which
// the drag of the air holds up its weight.

const GRAVITY = 9.80665;
// The gas constant of dry air, J/(kg K).
const AIR_GAS_CONSTANT = 287.053;
// Fallout particles are mostly fused soil and glass.
export const PARTICLE_DENSITY = 2600;

// The temperature (K) and pressure (Pa) of the air `altitude` meters above sea level.
export function standardAir(altitude) {
    const h = Math.max(0, Math.min(altitude, 32000));
    if (h <= 11000) {
        const temperature = 288.15 - 0.0065 * h;
        return {temperature, pressure: 101325 * Math.pow(temperature / 288.15, 5.255877)};
    }
    if (h <= 20000) {
        return {temperature: 216.65, pressure: 22632.06 * Math.exp(-0.00015768852 * (h - 11000))};
    }
    const temperature = 216.65 + 0.001 * (h - 20000);
    return {temperature, pressure: 5474.889 * Math.pow(temperature / 216.65, -34.163195)};
}

// The density (kg/m^3) and viscosity (Pa s, by Sutherland's law) of the air at `altitude`.
export function airProperties(altitude) {
    const {temperature, pressure} = standardAir(altitude);
    return {
        density: pressure / (AIR_GAS_CONSTANT * temperature),
        viscosity: 1.458e-6 * Math.pow(temperature, 1.5) / (temperature + 110.4),
    };
}

// The drag coefficient of a sphere at Reynolds number `re` (Clift and Gauvin), good from creeping
// flow up to the drag crisis, which no fallout particle reaches.
export function sphereDrag(re) {
    return 24 / re * (1 + 0.15 * Math.pow(re, 0.687)) + 0.42 / (1 + 42500 * Math.pow(re, -1.16));
}

// The speed (m/s) at which a particle of `diameter` meters falls at `altitude` meters above sea
// level, once it has stopped speeding up (which takes it well under a second).
export function settlingSpeed(diameter, altitude) {
    const {density, viscosity} = airProperties(altitude);
    // The Best number: drag coefficient times the Reynolds number squared, which does not depend on
    // the speed; the Reynolds number which matches it is found by bisection, since Cd Re^2 only grows.
    const best = 4 / 3 * density * (PARTICLE_DENSITY - density) * GRAVITY * diameter ** 3 / viscosity ** 2;
    let low = 1e-12, high = 1e6;
    for (let i = 0; i < 80; i++) {
        const re = Math.sqrt(low * high);
        if (sphereDrag(re) * re * re < best) low = re; else high = re;
    }
    return Math.sqrt(low * high) * viscosity / (density * diameter);
}
