// Pure calculation functions for the Solar calculator.  No React here; SolarCalculator.js is the UI.
//
// The model estimates a typical year from 12 monthly averages, the standard approach when hourly
// typical-year weather files are not available:
//
//   1. Sun geometry for Klein's representative day of each month (Duffie & Beckman ch. 1).
//   2. Monthly global horizontal irradiation (GHI) is split into diffuse and beam (Erbs monthly
//      correlation), then spread across the day (Collares-Pereira & Rabl for total, Liu & Jordan
//      for diffuse).
//   3. Each step is transposed onto the panel with the HDKR sky model, for a fixed, single-axis or
//      dual-axis array.
//   4. PVWatts' models turn plane-of-array irradiance into energy: ASHRAE angle-of-incidence loss,
//      SAPM cell temperature, linear temperature-corrected DC power, multiplicative system losses,
//      and an optional inverter efficiency curve with clipping.
//
// Angles are in degrees at the API boundary.  Azimuths are compass bearings (0 = north, 90 = east,
// 180 = south, 270 = west); internally the Duffie & Beckman convention is used (0 = south, east
// negative, west positive).  Energy is kWh, irradiation kWh/m², irradiance W/m², power kW.

export const SOLAR_CONSTANT = 1361; // W/m²

const RAD = Math.PI / 180;
const sin = deg => Math.sin(deg * RAD);
const cos = deg => Math.cos(deg * RAD);
const tan = deg => Math.tan(deg * RAD);
const acos = x => Math.acos(Math.min(1, Math.max(-1, x))) / RAD;
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

export const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

// Klein's recommended average day of each month: the day whose extraterrestrial radiation is
// closest to the month's mean.  Day of the year, 1-365.
export const KLEIN_DAYS = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344];

// ---------------------------------------------------------------------------
// Sun geometry
// ---------------------------------------------------------------------------

// Solar declination (Cooper), degrees.
export function declination(dayOfYear) {
    return 23.45 * sin(360 * (284 + dayOfYear) / 365);
}

// Sunset hour angle on a horizontal surface, degrees.  0 during polar night, 180 during polar day.
export function sunsetHourAngle(latitude, decl) {
    return acos(-tan(latitude) * tan(decl));
}

// Orbit eccentricity correction to the solar constant.
export function eccentricity(dayOfYear) {
    return 1 + 0.033 * cos(360 * dayOfYear / 365);
}

// Daily extraterrestrial irradiation on a horizontal surface, kWh/m²/day (D&B eq. 1.10.3).
export function extraterrestrialDaily(latitude, dayOfYear) {
    const decl = declination(dayOfYear);
    const ws = sunsetHourAngle(latitude, decl);
    const wh = (24 / Math.PI) * SOLAR_CONSTANT * eccentricity(dayOfYear)
        * (cos(latitude) * cos(decl) * sin(ws) + (Math.PI * ws / 180) * sin(latitude) * sin(decl));
    return Math.max(0, wh / 1000);
}

// Day length in hours.
export function dayLength(latitude, decl) {
    return 2 * sunsetHourAngle(latitude, decl) / 15;
}

// Sun elevation at solar noon, degrees.  Negative means the sun does not rise.
export function noonElevation(latitude, decl) {
    return 90 - Math.abs(latitude - decl);
}

// Sun position for an hour angle (degrees, 15° per hour from solar noon, afternoon positive).
// Returns cosine of the zenith angle and the azimuth in the D&B convention (0 = south).
export function sunPosition(latitude, decl, hourAngle) {
    const cosZenith = cos(latitude) * cos(decl) * cos(hourAngle) + sin(latitude) * sin(decl);
    const sinZenith = Math.sqrt(Math.max(0, 1 - cosZenith * cosZenith));
    let azimuth = 0;
    if (sinZenith > 1e-9 && Math.abs(cos(latitude)) > 1e-9) {
        azimuth = acos((cosZenith * sin(latitude) - sin(decl)) / (sinZenith * cos(latitude)));
        azimuth = hourAngle < 0 ? -azimuth : azimuth;
    }
    return {cosZenith, zenith: acos(cosZenith), azimuth};
}

// Cosine of the angle of incidence on a surface of tilt `tilt` and D&B azimuth `surfaceAzimuth`.
export function cosIncidence(zenith, sunAzimuth, tilt, surfaceAzimuth) {
    return cos(zenith) * cos(tilt) + sin(zenith) * sin(tilt) * cos(sunAzimuth - surfaceAzimuth);
}

// Compass bearing (0 = north) to the D&B azimuth convention (0 = south, east negative).
export function compassToSolarAzimuth(compass) {
    let a = ((compass % 360) + 360) % 360 - 180;
    return a === -180 ? 180 : a;
}

// Default panel azimuth: face the equator.
export function defaultAzimuth(latitude) {
    return latitude < 0 ? 0 : 180;
}

// ---------------------------------------------------------------------------
// Monthly irradiation to sub-daily steps
// ---------------------------------------------------------------------------

// Monthly average diffuse fraction Hd/H from the clearness index (Erbs, Klein & Duffie 1982).
// The correlation was fit for 0.3 <= KT <= 0.8, so KT is clamped to that range.
export function erbsMonthlyDiffuseFraction(kt, sunsetAngle) {
    const k = clamp(kt, 0.3, 0.8);
    if (sunsetAngle <= 81.4) {
        return 1.391 - 3.560 * k + 4.189 * k * k - 2.137 * k * k * k;
    }
    return 1.311 - 3.022 * k + 3.427 * k * k - 1.821 * k * k * k;
}

// Ratio of hourly to daily total irradiation at hour angle `w` (Collares-Pereira & Rabl).
export function totalHourlyRatio(w, sunsetAngle) {
    if (Math.abs(w) >= sunsetAngle) {
        return 0;
    }
    const a = 0.409 + 0.5016 * sin(sunsetAngle - 60);
    const b = 0.6609 - 0.4767 * sin(sunsetAngle - 60);
    return diffuseHourlyRatio(w, sunsetAngle) * (a + b * cos(w));
}

// Ratio of hourly to daily diffuse irradiation at hour angle `w` (Liu & Jordan).
export function diffuseHourlyRatio(w, sunsetAngle) {
    if (Math.abs(w) >= sunsetAngle) {
        return 0;
    }
    const denominator = sin(sunsetAngle) - (Math.PI * sunsetAngle / 180) * cos(sunsetAngle);
    return (Math.PI / 24) * (cos(w) - cos(sunsetAngle)) / denominator;
}

// Number of evenly spaced steps between sunrise and sunset.  Steps adapt to the day length, so a
// short polar-edge day is still sampled.
export const STEPS_PER_DAY = 48;

// The average day of a month as a list of steps, each with its hour angle, duration (hours), and
// the horizontal irradiances (W/m²) for global, beam and diffuse.  The two hourly ratios are
// normalized over the day so the steps add back up to exactly the monthly GHI and diffuse given.
export function averageDaySteps(latitude, monthIndex, ghi, diffuse = null) {
    const n = KLEIN_DAYS[monthIndex];
    const decl = declination(n);
    const ws = sunsetHourAngle(latitude, decl);
    const h0 = extraterrestrialDaily(latitude, n);
    if (!(ghi > 0) || !(ws > 0) || !(h0 > 0)) {
        return {decl, sunsetAngle: ws, kt: null, diffuseFraction: null, steps: []};
    }

    const kt = ghi / h0;
    const hd = diffuse != null && diffuse >= 0
        ? Math.min(diffuse, ghi)
        : ghi * erbsMonthlyDiffuseFraction(kt, ws);

    const dw = 2 * ws / STEPS_PER_DAY;
    const dt = dw / 15;
    const raw = [];
    let totalSum = 0, diffuseSum = 0;
    for (let i = 0; i < STEPS_PER_DAY; i++) {
        const w = -ws + (i + 0.5) * dw;
        const rt = totalHourlyRatio(w, ws);
        const rd = diffuseHourlyRatio(w, ws);
        raw.push({w, rt, rd});
        totalSum += rt * dt;
        diffuseSum += rd * dt;
    }

    const steps = raw.map(({w, rt, rd}) => {
        // kWh/m² per hour is numerically kW/m², so x1000 gives the step's mean irradiance in W/m².
        const global = totalSum > 0 ? (rt / totalSum) * ghi * 1000 : 0;
        const diff = Math.min(global, diffuseSum > 0 ? (rd / diffuseSum) * hd * 1000 : 0);
        return {hourAngle: w, hours: dt, global, diffuse: diff, beam: global - diff};
    });
    return {decl, sunsetAngle: ws, kt, diffuseFraction: hd / ghi, steps};
}

// ---------------------------------------------------------------------------
// Panel orientation and plane-of-array irradiance
// ---------------------------------------------------------------------------

export const TRACKING = {
    fixed: {label: 'Fixed'},
    single: {label: 'Single-axis (N–S axis)'},
    dual: {label: 'Dual-axis'},
};

// Single-axis trackers are limited to this rotation either side of flat.
export const SINGLE_AXIS_LIMIT = 60;

// Panel tilt and D&B azimuth for a step.  `tilt`/`azimuth` are only used for fixed arrays.
export function panelOrientation(tracking, sun, tilt, azimuth) {
    if (tracking === 'dual') {
        return {tilt: sun.zenith, azimuth: sun.azimuth};
    }
    if (tracking === 'single') {
        // Horizontal north-south axis rotating east-west (Marion & Dobos ideal rotation).
        const rotation = clamp(
            Math.atan(Math.tan(sun.zenith * RAD) * Math.sin(sun.azimuth * RAD)) / RAD,
            -SINGLE_AXIS_LIMIT, SINGLE_AXIS_LIMIT);
        return {tilt: Math.abs(rotation), azimuth: rotation >= 0 ? 90 : -90};
    }
    return {tilt, azimuth};
}

// Plane-of-array irradiance for one step with the HDKR (Hay-Davies-Klucher-Reindl) sky model.
// Returns the beam (direct plus circumsolar), sky diffuse and ground-reflected parts in W/m², and
// the angle of incidence.
export function poaIrradiance({global, beam, diffuse}, sun, orientation, albedo, dayOfYear) {
    const {tilt, azimuth} = orientation;
    const cosTheta = cosIncidence(sun.zenith, sun.azimuth, tilt, azimuth);

    // Beam normal irradiance, capped at the extraterrestrial value; near sunrise the division by a
    // tiny cos(zenith) would otherwise blow up.
    const extraNormal = SOLAR_CONSTANT * eccentricity(dayOfYear);
    const cosZ = Math.max(sun.cosZenith, 0.01745);
    const dni = Math.min(beam / cosZ, extraNormal);
    const rb = Math.max(0, cosTheta) / cosZ;

    const anisotropy = clamp(dni / extraNormal, 0, 1);
    const horizonFactor = global > 0 ? Math.sqrt(beam / global) : 0;
    const beamPoa = dni * Math.max(0, cosTheta) + diffuse * anisotropy * rb;
    const skyPoa = diffuse * (1 - anisotropy) * ((1 + cos(tilt)) / 2)
        * (1 + horizonFactor * Math.pow(sin(tilt / 2), 3));
    const groundPoa = global * albedo * (1 - cos(tilt)) / 2;
    return {beam: beamPoa, sky: skyPoa, ground: groundPoa, total: beamPoa + skyPoa + groundPoa, cosTheta};
}

// ASHRAE incidence angle modifier for the glass cover; applied to the beam part.
export function ashraeIam(cosTheta, b0 = 0.05) {
    if (cosTheta <= 0) {
        return 0;
    }
    return clamp(1 - b0 * (1 / cosTheta - 1), 0, 1);
}

// ---------------------------------------------------------------------------
// Temperature, DC power, losses, inverter
// ---------------------------------------------------------------------------

// Sandia (SAPM) cell temperature coefficients by mounting.
export const MOUNTINGS = {
    open: {label: 'Open rack (ground or pole)', a: -3.56, b: -0.075, deltaT: 3},
    roof: {label: 'Close roof mount', a: -2.98, b: -0.0471, deltaT: 1},
    flush: {label: 'Insulated back / flush', a: -2.81, b: -0.0455, deltaT: 0},
};

// PVWatts v8 temperature coefficients of power, %/°C.
export const MODULE_TYPES = {
    standard: {label: 'Standard (crystalline)', gamma: -0.37},
    premium: {label: 'Premium (high efficiency)', gamma: -0.35},
    thinFilm: {label: 'Thin film', gamma: -0.32},
};

export const DEFAULT_WIND_SPEED = 1; // m/s; deliberately low, so cell temperatures are not optimistic.

// SAPM cell temperature, °C.
export function cellTemperature(poa, ambient, mounting = 'open', windSpeed = DEFAULT_WIND_SPEED) {
    const m = MOUNTINGS[mounting] || MOUNTINGS.open;
    const moduleTemp = poa * Math.exp(m.a + m.b * windSpeed) + ambient;
    return moduleTemp + (poa / 1000) * m.deltaT;
}

// Daily air temperature swing, used when only a monthly mean is known: the mean +/- this amount.
export const DEFAULT_DAILY_SWING = 5;

// Air temperature at an hour angle, peaking mid-afternoon (3 pm).
export function ambientTemperature(mean, hourAngle, swing = DEFAULT_DAILY_SWING) {
    return mean + swing * cos(hourAngle - 45);
}

// DC power, kW, for an array of `kwp` kilowatts (STC rating) and temperature coefficient `gamma` (%/°C).
export function dcPower(effectiveIrradiance, cellTemp, kwp, gamma) {
    return Math.max(0, kwp * (effectiveIrradiance / 1000) * (1 + (gamma / 100) * (cellTemp - 25)));
}

// PVWatts system loss categories and their default percentages.
export const LOSS_CATEGORIES = [
    {key: 'soiling', label: 'Soiling', default: 2},
    {key: 'shading', label: 'Shading', default: 3},
    {key: 'snow', label: 'Snow', default: 0},
    {key: 'mismatch', label: 'Mismatch', default: 2},
    {key: 'wiring', label: 'Wiring', default: 2},
    {key: 'connections', label: 'Connections', default: 0.5},
    {key: 'lid', label: 'Light-induced degradation', default: 1.5},
    {key: 'nameplate', label: 'Nameplate rating', default: 1},
    {key: 'age', label: 'Age', default: 0},
    {key: 'availability', label: 'Availability', default: 3},
];

export const DEFAULT_LOSSES = LOSS_CATEGORIES.map(c => c.default);

// Combine loss percentages multiplicatively, as PVWatts does.  Returns a percentage.
export function totalLoss(percentages) {
    const kept = percentages.reduce((acc, p) => acc * (1 - clamp(Number(p) || 0, 0, 100) / 100), 1);
    return 100 * (1 - kept);
}

export const INVERTER_NOMINAL_EFFICIENCY = 96;
const INVERTER_REFERENCE_EFFICIENCY = 0.9637;

// AC power, kW, from the PVWatts inverter model: part-load efficiency curve, clipped at the AC rating.
export function inverterOutput(pdc, acRating, nominalEfficiency = INVERTER_NOMINAL_EFFICIENCY) {
    if (!(pdc > 0) || !(acRating > 0)) {
        return 0;
    }
    const etaNom = nominalEfficiency / 100;
    const pdc0 = acRating / etaNom;
    const zeta = pdc / pdc0;
    const eta = (etaNom / INVERTER_REFERENCE_EFFICIENCY) * (-0.0162 * zeta - 0.0059 / zeta + 0.9858);
    return Math.min(Math.max(0, eta * pdc), acRating);
}

// ---------------------------------------------------------------------------
// The whole model
// ---------------------------------------------------------------------------

export const DEFAULT_ALBEDO = 0.2;

/**
 * Estimate monthly and annual production.
 *
 * @param {Object} system
 * @param {number} system.latitude         degrees, north positive
 * @param {number[]} system.ghi            12 monthly average GHI values, kWh/m²/day
 * @param {number[]} [system.diffuse]      12 monthly diffuse values, kWh/m²/day; estimated when absent
 * @param {number[]} [system.temperature]  12 monthly mean air temperatures, °C; 20 when absent
 * @param {number[]} [system.albedo]       ground reflectance, one value or 12 monthly values
 * @param {number} system.kwp              array STC rating, kW
 * @param {number} [system.tilt]           degrees from horizontal (fixed arrays)
 * @param {number} [system.azimuth]        compass degrees (fixed arrays)
 * @param {string} [system.tracking]       'fixed' | 'single' | 'dual'
 * @param {string} [system.mounting]       key of MOUNTINGS
 * @param {number} [system.gamma]          temperature coefficient of power, %/°C
 * @param {number[]} [system.losses]       system loss percentages, see LOSS_CATEGORIES
 * @param {Object} [system.inverter]       {acRating (kW), efficiency (%)}; null for DC output
 */
export function estimateProduction({
                                       latitude,
                                       ghi,
                                       diffuse = null,
                                       temperature = null,
                                       albedo = DEFAULT_ALBEDO,
                                       kwp,
                                       tilt = 0,
                                       azimuth = defaultAzimuth(latitude),
                                       tracking = 'fixed',
                                       mounting = 'open',
                                       gamma = MODULE_TYPES.standard.gamma,
                                       losses = DEFAULT_LOSSES,
                                       inverter = null,
                                   }) {
    const lossFactor = 1 - totalLoss(losses) / 100;
    const surfaceAzimuth = compassToSolarAzimuth(azimuth);

    const months = MONTH_NAMES.map((name, m) => {
        const n = KLEIN_DAYS[m];
        const givenAlbedo = Array.isArray(albedo) ? albedo[m] : albedo;
        const monthAlbedo = Number.isFinite(givenAlbedo) ? givenAlbedo : DEFAULT_ALBEDO;
        const meanTemp = temperature && Number.isFinite(temperature[m]) ? temperature[m] : 20;
        const day = averageDaySteps(latitude, m, ghi[m], diffuse ? diffuse[m] : null);

        let poaDaily = 0, energyDaily = 0;
        for (const step of day.steps) {
            const sun = sunPosition(latitude, day.decl, step.hourAngle);
            if (sun.cosZenith <= 0) {
                continue;
            }
            const orientation = panelOrientation(tracking, sun, tilt, surfaceAzimuth);
            const poa = poaIrradiance(step, sun, orientation, monthAlbedo, n);
            const effective = poa.beam * ashraeIam(poa.cosTheta) + poa.sky + poa.ground;
            const tc = cellTemperature(poa.total, ambientTemperature(meanTemp, step.hourAngle), mounting);
            let power = dcPower(effective, tc, kwp, gamma) * lossFactor;
            if (inverter) {
                power = inverterOutput(power, inverter.acRating, inverter.efficiency);
            }
            poaDaily += poa.total * step.hours / 1000;
            energyDaily += power * step.hours;
        }

        return {
            month: name,
            ghi: ghi[m],
            kt: day.kt,
            diffuseFraction: day.diffuseFraction,
            // Plane-of-array kWh/m²/day: the honest "peak sun hours" for this panel.
            poa: poaDaily,
            energyDaily,
            energy: energyDaily * DAYS_IN_MONTH[m],
            dayLength: dayLength(latitude, day.decl),
            noonElevation: noonElevation(latitude, day.decl),
        };
    });

    const annual = months.reduce((acc, m) => acc + m.energy, 0);
    const worst = months.reduce((a, b) => (b.energyDaily < a.energyDaily ? b : a));
    const best = months.reduce((a, b) => (b.energyDaily > a.energyDaily ? b : a));
    return {
        months,
        annual,
        specificYield: kwp > 0 ? annual / kwp : null,
        capacityFactor: kwp > 0 ? annual / (kwp * 8760) : null,
        worst,
        best,
        totalLoss: totalLoss(losses),
    };
}

// Sweep fixed tilts 0-90° at the given azimuth and return the best one.  `goal` is 'annual' (most
// energy in a year) or 'winter' (most energy in the worst month, which sizes off-grid systems).
export function optimalTilt(system, goal = 'annual') {
    let best = {tilt: 0, value: -1};
    for (let tilt = 0; tilt <= 90; tilt++) {
        const result = estimateProduction({...system, tilt, tracking: 'fixed'});
        const value = goal === 'winter' ? result.worst.energyDaily : result.annual;
        if (value > best.value + 1e-9) {
            best = {tilt, value};
        }
    }
    return best.tilt;
}

// ---------------------------------------------------------------------------
// Input parsing
// ---------------------------------------------------------------------------

// Parse latitude/longitude text: decimal ("40.015", "-105.27") or degrees-minutes-seconds
// ("40°0'54\"N", "105 16 12 W").  Returns null when unparseable or out of range.
export function parseCoordinate(text, kind = 'lat') {
    if (text === null || text === undefined) {
        return null;
    }
    const s = `${text}`.trim().toUpperCase();
    if (!s) {
        return null;
    }
    const hemisphere = s.match(/[NSEW]/);
    const parts = s.replace(/[NSEW]/g, ' ').match(/-?\d+(\.\d+)?/g);
    if (!parts || parts.length > 3) {
        return null;
    }
    const [d, m = 0, sec = 0] = parts.map(Number);
    if (m < 0 || m >= 60 || sec < 0 || sec >= 60) {
        return null;
    }
    let value = Math.abs(d) + m / 60 + sec / 3600;
    if (d < 0 || s.trim().startsWith('-')) {
        value = -value;
    }
    if (hemisphere) {
        const h = hemisphere[0];
        if ((kind === 'lat' && (h === 'E' || h === 'W')) || (kind === 'lon' && (h === 'N' || h === 'S'))) {
            return null;
        }
        if (h === 'S' || h === 'W') {
            value = -Math.abs(value);
        }
    }
    const limit = kind === 'lat' ? 90 : 180;
    return Math.abs(value) <= limit ? value : null;
}

// Parse a comma separated list of 12 monthly numbers.  Blank entries become null.
export function parseMonthly(text) {
    const values = (text || '').split(',').map(v => (v.trim() === '' ? null : Number(v)));
    return MONTH_NAMES.map((_, i) => (Number.isFinite(values[i]) ? values[i] : null));
}

export function formatMonthly(values) {
    return values.map(v => (v === null || v === undefined || v === '' ? '' : `${v}`)).join(',');
}

// Link to the Solar calculator for a location, e.g. from the map.  4 decimals (about 11 m) is far finer
// than the 1° data and keeps the shared URL short.  MapLibre reports longitudes past ±180° once the map
// has been panned around the world, so those are wrapped back.
export function solarCalculatorPath(latitude, longitude) {
    const lon = longitude >= -180 && longitude <= 180 ? longitude : ((longitude + 180) % 360 + 360) % 360 - 180;
    const round = value => Number(value.toFixed(4));
    return `/more/calculators?calc=solar&lat=${round(latitude)}&lon=${round(lon)}`;
}
