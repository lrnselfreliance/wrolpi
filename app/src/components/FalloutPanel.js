import React, {useContext, useEffect, useMemo, useRef, useState} from "react";
import {Button, Checkbox, NumberInput, Select} from "./ui";
import {depositionGrid, doseGrid, landedGrid, landingSpots, profileFromTable, sharpenGrid} from "../map-shared/fallout/model.js";
import shots from "../map-shared/fallout/nts-shots.json";
import {terrainAround} from "../map-shared/fallout/terrain.js";
import {loadTerrainGrid} from "./falloutTerrain";
import {formatYield, formatYieldAndFission, WEAPON_GROUPS} from "../map-shared/fallout/weapons.js";
import {
    fieldCovers,
    fieldWinds,
    forecastAge,
    forecastExpired,
    forecastRunsOut,
    nearestHour,
    nearestPoint,
    prepareField,
    rainNear,
} from "../map-shared/fallout/winds.js";
import {combineBursts, CUSTOM_WEAPON, DEFAULT_WEAPON, targetWeapon} from "../map-shared/fallout/targets.js";
import {fetchFalloutWinds, getFalloutClimatology, getFalloutClimatologyMonth, getJobs, getLatestFalloutWinds} from "../api";
import {burstBounds, dayCounter, dayField, gunzip, parseClimatology} from "../map-shared/fallout/climatology.js";
import {isJobFinished, useJob} from "./VideoEditMenu";
import {StatusContext} from "../contexts/contexts";

// The map's fallout view (nuclear mode): the fallout of every saved target at once, and of a burst
// the user is trying out, in the most recently fetched winds aloft.  Drawn as the dose rate at H+1
// hour.

const SOURCE = "fallout-dose";
const LAYER = "fallout-dose";
const METERS_PER_DEGREE = 111320;

// The dose-rate bands drawn (R/hr at H+1), from the highest.
export const DOSE_BANDS = [
    {rate: 1000, color: [110, 0, 30]},
    {rate: 100, color: [200, 20, 40]},
    {rate: 10, color: [240, 110, 20]},
    {rate: 1, color: [250, 200, 40]},
    {rate: 0.1, color: [250, 240, 150]},
];

// The total dose bands drawn (R, outdoors), from the highest, with what such a dose, taken over
// days, does to a person [Glasstone and Dolan, Table 12.108].
export const TOTAL_BANDS = [
    {rate: 1000, color: DOSE_BANDS[0].color, meaning: "nearly everyone dies"},
    {rate: 450, color: DOSE_BANDS[1].color, meaning: "about half die without care"},
    {rate: 100, color: DOSE_BANDS[2].color, meaning: "radiation sickness"},
    {rate: 25, color: DOSE_BANDS[3].color, meaning: "no sickness; a higher cancer risk"},
    {rate: 5, color: DOSE_BANDS[4].color, meaning: "a radiation worker's yearly limit"},
];
// What the map shows: the dose rate, or the total dose of someone outdoors.
const RATE = "rate";
const TOTAL = "total";
const SHOW = [
    {value: RATE, label: "Dose rate (R/hr)"},
    {value: TOTAL, label: "Total dose, outdoors (R)"},
];
// The total dose with the timeline at its start: over the first two weeks, when fallout does most
// of its harm.
const TWO_WEEKS = 336;

// The weapons, grouped by country, then a yield of the user's own.
export const WEAPON_CHOICES = [
    ...WEAPON_GROUPS.map((g) => ({
        group: g.name,
        items: g.weapons.map((w) => ({value: w.key, label: `${w.name}, ${formatYieldAndFission(w.yield_kt, w.fission_fraction)}`})),
    })),
    {group: "Other", items: [{value: CUSTOM_WEAPON, label: "A yield of my own"}]},
];
// The panel floats over the map (z-index 1002); its dropdowns open above it.
const DROPDOWN = {zIndex: 1100};
const FORECAST = "forecast";
const WINDS = [
    {value: FORECAST, label: "Forecast winds aloft"},
    {value: "manual", label: "One wind at every height"},
    ...shots.shots.map((s) => ({value: s.name, label: `Sample: winds over Nevada, ${s.date.slice(0, 10)}`})),
];
// Winds of past days: the climatology, the share of a month's days fallout reached each place.
const CLIMATE = "climate";
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December"];
// The shares of days drawn, from the most; the last is "any of the days".
export const CLIMATE_BANDS = [
    {rate: 0.5, color: DOSE_BANDS[0].color, label: "half the days or more"},
    {rate: 0.25, color: DOSE_BANDS[1].color, label: "a quarter of the days or more"},
    {rate: 0.1, color: DOSE_BANDS[2].color, label: "a tenth of the days or more"},
    {rate: 1e-6, color: DOSE_BANDS[4].color, label: "any of the days"},
];
// The dose rates (R/hr at H+1) a day may be counted at.
const CLIMATE_RATES = [1000, 100, 10, 1].map((r) => ({value: String(r), label: `${r}+ R/hr at H+1`}));
// The cells days are counted on are at least this wide (m), and each is shown as the average of
// itself and its neighbors this many cells around.
const CLIMATE_CELL = 4000;
const CLIMATE_SMOOTH = 1;

// The Job which fetches a field of winds.
const WINDS_JOB = "fallout_winds";
// The hours after the bursts the fallout can be watched landing in, and how long each is shown (ms)
// when it plays.
const LAST_HOUR = 48;
const FRAME_MS = 700;
// Rain this heavy in the hours ahead (mm) is worth a warning.
const RAIN_WARNING_MM = 0.5;

// Web Mercator's y of `lat` (degrees), and back.
const mercatorY = (lat) => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
const mercatorLat = (y) => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI;
// The map takes no latitude past the poles' edge of the Web Mercator world.
const clampLat = (lat) => Math.min(Math.max(lat, -85), 85);

// The grid's row (from the south) under each of `height` image rows (from the top), for a grid
// around `lat`.  The map stretches an image evenly in Web Mercator between its corners, but the
// grid's rows are evenly apart in latitude: over many degrees they part ways, so each image row
// takes the grid row at its own latitude.
export function imageRows(grid, lat, height) {
    const north = clampLat(lat + (grid.y0 + grid.ny * grid.cell) / METERS_PER_DEGREE);
    const south = clampLat(lat + grid.y0 / METERS_PER_DEGREE);
    const top = mercatorY(north), bottom = mercatorY(south);
    const rows = new Int32Array(height);
    for (let r = 0; r < height; r++) {
        const rowLat = mercatorLat(top + (r + 0.5) / height * (bottom - top));
        const j = Math.floor(((rowLat - lat) * METERS_PER_DEGREE - grid.y0) / grid.cell);
        rows[r] = Math.min(Math.max(j, 0), grid.ny - 1);
    }
    return rows;
}

// The grid as an image for a map, around `lat`: each cell colored by the highest band it reaches,
// transparent below them.
export function gridImage(grid, lat, bands = DOSE_BANDS) {
    const canvas = document.createElement("canvas");
    canvas.width = grid.nx;
    canvas.height = grid.ny;
    const context = canvas.getContext("2d");
    const image = context.createImageData(grid.nx, grid.ny);
    const rows = imageRows(grid, lat, grid.ny);
    for (let r = 0; r < grid.ny; r++) {
        const from = rows[r] * grid.nx, to = r * grid.nx;
        for (let i = 0; i < grid.nx; i++) {
            const band = bands.find((b) => grid.values[from + i] >= b.rate);
            if (!band) continue;
            const p = (to + i) * 4;
            image.data[p] = band.color[0];
            image.data[p + 1] = band.color[1];
            image.data[p + 2] = band.color[2];
            image.data[p + 3] = 255;
        }
    }
    context.putImageData(image, 0, 0);
    return canvas.toDataURL();
}

// The corners of the grid (top-left, top-right, bottom-right, bottom-left) as [lon, lat], around
// `lon`, `lat`.
export function gridCorners(grid, lon, lat) {
    const toLon = (x) => lon + x / (METERS_PER_DEGREE * Math.cos(lat * Math.PI / 180));
    const toLat = (y) => clampLat(lat + y / METERS_PER_DEGREE);
    const west = toLon(grid.x0), east = toLon(grid.x0 + grid.nx * grid.cell);
    const south = toLat(grid.y0), north = toLat(grid.y0 + grid.ny * grid.cell);
    return [[west, north], [east, north], [east, south], [west, south]];
}

// The wind profile the model takes, for a wind not of the forecast: one wind at every height (also
// while there is no forecast), or a sample.
export function windProfile({wind, direction, speed}) {
    const rows = wind === "manual" || wind === FORECAST
        ? [[0, direction, speed]]
        : shots.shots.find((s) => s.name === wind).wind.map(([z, d, s], _, all) => [z - all[0][0], d, s]);
    return profileFromTable(rows, 0);
}

// The area ([west, south, east, north], degrees) where the grid reaches the lowest band, with a margin.
export function plumeBounds(grid, lon, lat) {
    const lowest = DOSE_BANDS[DOSE_BANDS.length - 1].rate;
    let x0 = 0, x1 = 0, y0 = 0, y1 = 0;
    for (let j = 0; j < grid.ny; j++) {
        for (let i = 0; i < grid.nx; i++) {
            if (grid.values[j * grid.nx + i] < lowest) continue;
            const x = grid.x0 + (i + 0.5) * grid.cell, y = grid.y0 + (j + 0.5) * grid.cell;
            x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        }
    }
    const margin = Math.max(0.25 * Math.max(x1 - x0, y1 - y0), 20000);
    const perLon = METERS_PER_DEGREE * Math.cos(lat * Math.PI / 180);
    return [lon + (x0 - margin) / perLon, lat + (y0 - margin) / METERS_PER_DEGREE,
        lon + (x1 + margin) / perLon, lat + (y1 + margin) / METERS_PER_DEGREE];
}

// A forecast hour as the user reads it: the day and time where they are.
export function hourLabel(time, nearest) {
    const label = new Date(time).toLocaleString(undefined, {weekday: "short", hour: "numeric", minute: "2-digit"});
    return nearest ? `${label} (now)` : label;
}

// Let the page draw and answer the user when the model has had the thread for a while.  A message
// channel, not a timer: a browser holds a hidden tab's timers back to one a second.
const SLICE_MS = 40;
function yielder() {
    let since = performance.now();
    return async () => {
        if (performance.now() - since < SLICE_MS) return;
        await new Promise((resolve) => {
            if (typeof MessageChannel === "undefined") {
                setTimeout(resolve, 0);
                return;
            }
            const channel = new MessageChannel();
            channel.port1.onmessage = () => resolve();
            channel.port2.postMessage(null);
        });
        since = performance.now();
    };
}

// The fallout of `bursts` ([{lat, lon, yieldKt, fissionFraction}]) on one grid around the first:
// {grid, spots (as combineBursts gives them, for the fallout hour by hour), origin, terrainStatus}.  `windsFor(burst, groundElevation)` gives the winds over a burst, as
// landingSpots takes them ({profile} or {winds}), or `profileFor(groundElevation)` its profile.
// `groundOf(burst)` is how high (m) its ground is until the terrain is read.  `onProgress(done,
// total)` hears how far it has got, `onFlat(grid)` gets the fallout on flat ground while the terrain
// is read, and `cancelled()` stops it.
export async function simulateBursts(bursts, {windsFor = null, profileFor = null, groundOf = () => 0,
    useTerrain = true, cancelled = () => false, onProgress = () => null, onFlat = () => null}) {
    const origin = bursts[0];
    const pause = yielder();
    const total = useTerrain ? bursts.length * 2 : bursts.length;
    let done = 0;
    const run = async (terrainOf) => {
        const runs = [], offMap = [];
        for (const b of bursts) {
            const terrain = terrainOf ? terrainOf(b) : null;
            const ground = terrain ? terrain.elevation : groundOf(b);
            const winds = windsFor ? windsFor(b, ground) : {profile: profileFor(ground)};
            const spots = landingSpots({yieldKt: b.yieldKt, ...winds, terrain, siteElevation: Math.max(ground, 0)});
            // A spot not on the map (from ground with no number under it) would break the whole grid.
            const finite = spots.filter((s) => Number.isFinite(s.x) && Number.isFinite(s.y) && s.sigma > 0);
            if (finite.length < spots.length) offMap.push(b);
            runs.push({burst: b, spots: finite, yieldKt: b.yieldKt, fissionFraction: b.fissionFraction});
            onProgress(++done, total);
            await pause();
            if (cancelled()) return null;
        }
        if (offMap.length) console.warn(`Fallout: some spots of ${offMap.length} bursts were not on the map`, offMap);
        // As far as the faintest band drawn: no further, where nothing would show.
        const floor = DOSE_BANDS[DOSE_BANDS.length - 1].rate;
        const spots = combineBursts(origin, runs);
        // The hot fallout close to a small burst is not averaged away in a grid over them all.
        const grid = sharpenGrid(depositionGrid(spots, {yieldKt: 1, boundsFloor: floor}), spots);
        return {grid, spots};
    };
    // On flat ground first: that is where the plumes are, so the terrain under them can be read.
    let ran = await run(null);
    if (!ran) return null;
    let terrainStatus = "Flat ground (terrain is off).";
    if (useTerrain) {
        onFlat(ran.grid);
        let loaded = null;
        try {
            loaded = await loadTerrainGrid(plumeBounds(ran.grid, origin.lon, origin.lat), origin.lon, origin.lat);
        } catch (e) {
            console.error("Could not read the terrain", e);
        }
        if (cancelled()) return null;
        if (loaded) {
            ran = await run((b) => terrainAround(loaded.grid, b.lon, b.lat));
            if (!ran) return null;
            const covered = Math.round(loaded.coverage * 100);
            terrainStatus = `Follows the terrain (zoom ${loaded.zoom}${covered < 100 ? `, ${covered}% of the area` : ""}).`;
        } else {
            terrainStatus = "No terrain file covers this place: flat ground.";
        }
    }
    return {grid: ran.grid, spots: ran.spots, origin, terrainStatus};
}

// The fallout of `bursts` in each day of `clim` (as parseClimatology gives it): on what share of the
// days each place had `rate` R/hr at H+1 or more, as a grid ({x0, y0, cell, nx, ny, values (0..1),
// days}) around the first burst, smoothed; and that burst ({grid, origin}).  On flat ground at sea
// level: the days' winds are read by height above the sea.
export async function simulateClimate(bursts, clim, {rate = 1, cancelled = () => false, onProgress = () => null} = {}) {
    const bounds = burstBounds(bursts);
    let counter = null;
    for (let k = 0; k < clim.days; k++) {
        const prepared = prepareField(dayField(clim, k, bounds));
        const startMs = Date.parse(prepared.field.hours[0]);
        const ran = await simulateBursts(bursts, {
            windsFor: (b, groundElevation) => ({winds: fieldWinds(prepared, {lat0: b.lat, lon0: b.lon, groundElevation, startMs})}),
            useTerrain: false, cancelled,
            onProgress: (done, total) => onProgress(k * total + done, clim.days * total),
        });
        if (!ran || cancelled()) return null;
        if (!counter) counter = dayCounter(rate, Math.max(CLIMATE_CELL, ran.grid.cell));
        counter.add(ran.grid);
    }
    return counter ? {grid: counter.grid(CLIMATE_SMOOTH), origin: bursts[0]} : null;
}

// A weapon to burst with: one of those offered, or a yield of one's own.  `value` and onChange's
// argument are {weapon, yield_kt?, fission_fraction?}, as a target keeps them.
export function WeaponPicker({value, onChange, label}) {
    const chosen = targetWeapon(value);
    const [customYield, setCustomYield] = useState(chosen.yieldKt);
    const [customFission, setCustomFission] = useState(Math.round(chosen.fissionFraction * 100));
    useEffect(() => {
        setCustomYield(chosen.yieldKt);
        setCustomFission(Math.round(chosen.fissionFraction * 100));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value?.weapon, value?.yield_kt, value?.fission_fraction]);
    const choose = (key) => {
        if (!key || key === chosen.key) return;
        if (key === CUSTOM_WEAPON) {
            onChange({weapon: key, yield_kt: chosen.yieldKt, fission_fraction: chosen.fissionFraction});
        } else {
            onChange({weapon: key, fission_fraction: targetWeapon({weapon: key}).fissionFraction});
        }
    };
    // A yield of one's own is kept when the user has finished typing it.
    const keepCustom = () => {
        const kt = Number(customYield), fission = Number(customFission) / 100;
        if (!(kt > 0) || !(fission > 0 && fission <= 1)) return;
        if (kt === chosen.yieldKt && fission === chosen.fissionFraction) return;
        onChange({weapon: CUSTOM_WEAPON, yield_kt: kt, fission_fraction: fission});
    };
    return <div>
        <Select label={label} size="xs" data={WEAPON_CHOICES} value={chosen.key} onChange={choose} searchable
                allowDeselect={false} maxDropdownHeight={320} comboboxProps={DROPDOWN} aria-label="Weapon"/>
        {chosen.weapon && chosen.weapon.yield_range_kt && <div style={{color: "var(--muted)", fontSize: "0.75rem"}}>
            Estimates range from {formatYield(chosen.weapon.yield_range_kt[0])} to{" "}
            {formatYield(chosen.weapon.yield_range_kt[1])}.
        </div>}
        {!chosen.weapon && <div style={{display: "flex", gap: "0.5rem"}}>
            <NumberInput label="Yield (kt)" size="xs" min={0.01} max={100000} value={customYield}
                         onChange={setCustomYield} onBlur={keepCustom}/>
            <NumberInput label="Fission (%)" size="xs" min={1} max={100} value={customFission}
                         onChange={setCustomFission} onBlur={keepCustom}/>
        </div>}
    </div>;
}

// A target in the list: its name and weapon, and the weapon picker when the user asks to change it.
function TargetRow({target, onWeapon}) {
    const [changing, setChanging] = useState(false);
    const chosen = targetWeapon(target);
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    return <div style={{marginBottom: "0.375rem"}}>
        <div><span aria-hidden>☢ </span><strong>{target.label}</strong></div>
        <div style={muted}>
            {chosen.weapon ? chosen.weapon.name : "A yield of my own"},{" "}
            {formatYieldAndFission(chosen.yieldKt, chosen.fissionFraction)}{" "}
            <a href="#" onClick={(e) => {
                e.preventDefault();
                setChanging(!changing);
            }}>{changing ? "done" : "change"}</a>
        </div>
        {changing && <WeaponPicker value={target} onChange={onWeapon}/>}
    </div>;
}

// The fallout view.  `targets` are the saved targets (pins of kind "target"); `burst` ({lat, lon}),
// if given, is a burst the user is trying out, which `onSaveBurst(burst, weapon)` saves as a target.
// `onTargetWeapon(target, weapon)` keeps a target's weapon.
export default function FalloutPanel({map, targets = [], burst = null, onSaveBurst, onTargetWeapon,
                                         onAllTargetsWeapon, onClose}) {
    const [burstWeapon, setBurstWeapon] = useState({weapon: DEFAULT_WEAPON});
    const [wind, setWind] = useState(FORECAST);
    // The climatology: which months are kept, the month and dose rate shown, and the months read.
    const [climateStatus, setClimateStatus] = useState(null);
    const [climateMonth, setClimateMonth] = useState(new Date().getMonth() + 1);
    const [climateRate, setClimateRate] = useState("1");
    const climates = useRef(new Map());
    const [forecastChecked, setForecastChecked] = useState(false);
    const chosenForUs = useRef(false);
    const [direction, setDirection] = useState(270);
    const [speed, setSpeed] = useState(20);
    // The field of forecast winds over the targets fetched most recently.
    const [forecast, setForecast] = useState(null);
    const [hour, setHour] = useState(0);
    // The Job fetching a field of winds, and how it is going.
    const [fetchJob, setFetchJob] = useState(null);
    const [fetchError, setFetchError] = useState(null);
    const [busy, setBusy] = useState(false);
    const [useTerrain, setUseTerrain] = useState(true);
    const [terrainStatus, setTerrainStatus] = useState(null);
    const [progress, setProgress] = useState(null);
    // The hour after the bursts shown, or 0 for all the fallout as at H+1; and whether the hours play.
    const [after, setAfter] = useState(0);
    const [show, setShow] = useState(RATE);
    const [playing, setPlaying] = useState(false);
    // The fallout last calculated ({grid, spots, origin}), and its images by the hour (0: all of it).
    const result = useRef(null);
    const frames = useRef(new Map());
    const [calculated, setCalculated] = useState(0);
    const {status} = useContext(StatusContext) || {};
    const online = !!status?.flags?.have_internet;
    const drawn = useRef(null);

    const bursts = [
        ...targets.map((t) => ({lat: t.lat, lon: t.lon, ...targetWeapon(t)})),
        ...(burst ? [{lat: burst.lat, lon: burst.lon, ...targetWeapon(burstWeapon)}] : []),
    ];
    // What the fallout depends on, as one value an effect can watch.
    const burstsKey = JSON.stringify(bursts.map((b) => [b.lat, b.lon, b.yieldKt, b.fissionFraction]));

    // The forecast fetched most recently.
    useEffect(() => {
        let cancelled = false;
        getFalloutClimatology().then((s) => !cancelled && setClimateStatus(s));
        getLatestFalloutWinds().then((latest) => {
            if (!cancelled) setForecastChecked(true);
            if (cancelled || !latest) return;
            setForecast(latest);
            setHour(nearestHour(latest.hours));
        });
        return () => {
            cancelled = true;
        };
    }, []);

    // A fetch started before the panel was opened is followed too.
    useEffect(() => {
        getJobs().then((jobs) => {
            const running = jobs.filter((j) => j.name === WINDS_JOB && !isJobFinished(j)).pop();
            if (running) setFetchJob(running.id);
        }).catch(() => null);
    }, []);

    const {job: fetchProgress} = useJob(fetchJob, async (job) => {
        setFetchJob(null);
        if (job.status !== "complete") {
            setFetchError(job.error || `The fetch was ${job.status}.`);
            return;
        }
        const latest = await getLatestFalloutWinds();
        if (!latest) return;
        setForecast(latest);
        setHour(nearestHour(latest.hours));
        setWind(FORECAST);
    }, () => {
        setFetchJob(null);
        setFetchError("The fetch was lost: WROLPi restarted.");
    });

    const prepared = useMemo(() => forecast ? prepareField(forecast) : null, [forecast]);
    const useField = wind === FORECAST && !!prepared;

    const fetchForecast = async () => {
        // Over the bursts, or the middle of the map when there are none.
        const places = bursts.length ? bursts.map((b) => [b.lat, b.lon]) : (() => {
            const c = map.getCenter();
            return [[c.lat, c.lng]];
        })();
        setFetchError(null);
        const started = await fetchFalloutWinds(places);
        if (started) setFetchJob(started.job_id);
    };

    useEffect(() => {
        let cancelled = false;
        if (!bursts.length) {
            drawn.current = null;
            result.current = null;
            frames.current = new Map();
            erase();
            setTerrainStatus(null);
            return;
        }
        setBusy(true);
        if (wind === CLIMATE) {
            // The bursts in each of the month's past days, counted.
            const timer = setTimeout(async () => {
                let clim = climates.current.get(climateMonth);
                if (!clim) {
                    const zipped = await getFalloutClimatologyMonth(climateMonth);
                    if (cancelled) return;
                    if (!zipped) {
                        setBusy(false);
                        return;
                    }
                    clim = parseClimatology(await gunzip(zipped));
                    climates.current.set(climateMonth, clim);
                }
                const ran = await simulateClimate(bursts, clim, {
                    rate: Number(climateRate), cancelled: () => cancelled,
                    onProgress: (done, total) => !cancelled && setProgress({done, total}),
                });
                if (cancelled || !ran) return;
                setProgress(null);
                result.current = null;
                frames.current = new Map();
                drawn.current = ran.grid ? {url: gridImage(ran.grid, ran.origin.lat, CLIMATE_BANDS),
                    coordinates: gridCorners(ran.grid, ran.origin.lon, ran.origin.lat)} : null;
                if (drawn.current) draw();
                else erase();
                setTerrainStatus("Flat ground: the past days' winds are read by height above the sea.");
                setBusy(false);
            }, 30);
            return () => {
                cancelled = true;
                clearTimeout(timer);
            };
        }
        const profile = windProfile({wind, direction: Number(direction) || 0, speed: Number(speed) || 0});
        const startMs = useField ? Date.parse(forecast.hours[hour]) : 0;
        // Each burst is carried by the winds where it is, from the hour chosen.
        const windsFor = useField
            ? (b, groundElevation) => ({winds: fieldWinds(prepared, {lat0: b.lat, lon0: b.lon, groundElevation, startMs})})
            : () => ({profile});
        // Until the terrain is read, ground zero is as high as the forecast's ground near it.
        const groundOf = useField ? (b) => forecast.points[nearestPoint(prepared, b.lat, b.lon)].elevation : () => 0;
        // Let the panel paint "Calculating" before the model takes the thread.
        const timer = setTimeout(async () => {
            const ran = await simulateBursts(bursts, {
                windsFor, groundOf, useTerrain, cancelled: () => cancelled,
                onProgress: (done, total) => !cancelled && setProgress({done, total}),
                // Something to look at while the terrain is read.
                onFlat: (grid) => {
                    if (cancelled) return;
                    drawn.current = {url: gridImage(grid, bursts[0].lat), coordinates: gridCorners(grid, bursts[0].lon, bursts[0].lat)};
                    draw();
                },
            });
            if (cancelled || !ran) return;
            setProgress(null);
            result.current = ran;
            frames.current = new Map([[`${RATE}:0`, {url: gridImage(ran.grid, ran.origin.lat), coordinates: gridCorners(ran.grid, ran.origin.lon, ran.origin.lat)}]]);
            // The hour shown is drawn from it.
            setCalculated((n) => n + 1);
            setTerrainStatus(ran.terrainStatus);
            setBusy(false);
        }, 30);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [burstsKey, wind, direction, speed, useTerrain, forecast, hour, climateMonth, climateRate]);

    // With no forecast to go on (none fetched, or run out), the past days' winds, if they are kept.
    const climateKept = !!climateStatus?.months?.includes(climateMonth);
    useEffect(() => {
        if (chosenForUs.current || !forecastChecked || !climateKept || wind !== FORECAST) return;
        if (!forecast || forecastExpired(forecast)) {
            chosenForUs.current = true;
            setWind(CLIMATE);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [forecastChecked, climateKept, forecast]);

    // The hour shown: all the fallout, or what has landed by then, as strong as it is then; or the
    // total dose of someone outdoors by then (by two weeks, at the start).
    useEffect(() => {
        const ran = result.current;
        if (!ran) return;
        const key = `${show}:${after}`;
        if (!frames.current.has(key)) {
            const grid = show === TOTAL
                ? doseGrid(ran.spots, ran.grid, after || TWO_WEEKS)
                : landedGrid(ran.spots, ran.grid, after);
            const url = gridImage(grid, ran.origin.lat, show === TOTAL ? TOTAL_BANDS : DOSE_BANDS);
            frames.current.set(key, {url, coordinates: gridCorners(grid, ran.origin.lon, ran.origin.lat)});
        }
        drawn.current = frames.current.get(key);
        draw();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [after, show, calculated]);

    // Playing, the next hour is shown after this one; from the last, it starts over.
    useEffect(() => {
        if (!playing) return;
        const timer = setTimeout(() => setAfter((h) => (h >= LAST_HOUR ? 1 : h + 1)), FRAME_MS);
        return () => clearTimeout(timer);
    }, [playing, after, calculated]);

    // The layer is of the map's style, which a change of style removes: it is put back when the
    // style has loaded.
    function draw() {
        if (!map || !drawn.current) return;
        const source = map.getSource(SOURCE);
        if (source) {
            source.updateImage(drawn.current);
        } else {
            map.addSource(SOURCE, {type: "image", ...drawn.current});
            map.addLayer({id: LAYER, type: "raster", source: SOURCE, paint: {"raster-opacity": 0.6, "raster-resampling": "nearest"}});
        }
    }

    function erase() {
        try {
            if (map.getLayer(LAYER)) map.removeLayer(LAYER);
            if (map.getSource(SOURCE)) map.removeSource(SOURCE);
        } catch (e) {
            // The map is gone.
        }
    }

    useEffect(() => {
        if (!map) return;
        const restore = () => draw();
        map.on("style.load", restore);
        return () => {
            map.off("style.load", restore);
            erase();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [map]);

    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    return <div style={{
        position: "absolute", left: "0.75rem", bottom: "2.5rem", zIndex: 1002, width: "20rem",
        maxHeight: "calc(100% - 7rem)", overflowY: "auto",
        background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)", padding: "0.75rem",
        fontSize: "0.8125rem",
    }}>
        <div style={{fontWeight: 600}}>Fallout</div>
        <div style={{...muted, marginBottom: "0.5rem"}}>
            {targets.length === 1 ? "1 target" : `${targets.length} targets`}
            {burst ? ", and a burst not saved" : ""}; surface bursts.
        </div>
        {!targets.length && !burst && <div style={muted}>
            No targets yet: right-click the map and choose Add Target Here.
        </div>}
        {targets.length > 1 && <div style={{marginBottom: "0.5rem"}}>
            {/* Empty until chosen, and always applied: the targets may have any weapons now. */}
            <Select label="Set every target's weapon" size="xs" data={WEAPON_CHOICES.slice(0, -1)} value={null}
                    placeholder="Choose a weapon for every target" searchable maxDropdownHeight={320}
                    comboboxProps={DROPDOWN} aria-label="Every target's weapon"
                    onChange={(key) => key && onAllTargetsWeapon?.({
                        weapon: key, fission_fraction: targetWeapon({weapon: key}).fissionFraction,
                    })}/>
        </div>}
        <div style={{maxHeight: "14rem", overflowY: "auto", marginBottom: "0.5rem"}}>
            {targets.map((t) => <TargetRow key={t.id} target={t} onWeapon={(weapon) => onTargetWeapon?.(t, weapon)}/>)}
        </div>
        {burst && <div style={{marginBottom: "0.5rem"}}>
            <div><strong>Burst</strong>{" "}
                <span style={muted}>{burst.lat.toFixed(3)}, {burst.lon.toFixed(3)}, not saved</span></div>
            <WeaponPicker value={burstWeapon} onChange={setBurstWeapon}/>
            <Button size="xs" style={{marginTop: "0.25rem"}} onClick={() => onSaveBurst?.(burst, burstWeapon)}>
                Save as target
            </Button>
        </div>}
        <Select label="Wind" size="xs" value={wind} onChange={(v) => v && setWind(v)}
                data={climateStatus?.months?.length
                    ? [WINDS[0], {value: CLIMATE, label: "Past days of a month (no forecast needed)"}, ...WINDS.slice(1)]
                    : WINDS}
                allowDeselect={false} comboboxProps={DROPDOWN}/>
        {wind === CLIMATE && <div style={{display: "flex", gap: "0.5rem"}}>
            <Select label="Month" size="xs" value={String(climateMonth)} allowDeselect={false} comboboxProps={DROPDOWN}
                    data={MONTHS.map((name, k) => ({value: String(k + 1), label: name,
                        disabled: !climateStatus?.months?.includes(k + 1)}))}
                    onChange={(v) => v && setClimateMonth(Number(v))}/>
            <Select label="Count days with" size="xs" value={climateRate} data={CLIMATE_RATES}
                    allowDeselect={false} comboboxProps={DROPDOWN} onChange={(v) => v && setClimateRate(v)}/>
        </div>}
        {wind === CLIMATE && !climateKept && <div style={{...muted, color: "var(--warning)"}}>
            {MONTHS[climateMonth - 1]}'s past winds are not on this WROLPi yet: they are fetched once, while
            there is the Internet.
        </div>}
        {wind === FORECAST && <ForecastControls
            forecast={forecast} prepared={prepared} bursts={bursts} hour={hour} onHour={setHour} online={online}
            fetching={!!fetchJob} fetchPercent={fetchProgress?.progress || 0} fetchError={fetchError}
            onFetch={fetchForecast}/>}
        {(wind === "manual" || (wind === FORECAST && !forecast)) && <div style={{display: "flex", gap: "0.5rem"}}>
            <NumberInput label="From (degrees)" size="xs" min={0} max={359} value={direction} onChange={setDirection}/>
            <NumberInput label="Speed (mph)" size="xs" min={0} max={200} value={speed} onChange={setSpeed}/>
        </div>}
        {wind !== CLIMATE && <Checkbox label="Follow the terrain" size="xs" style={{marginTop: "0.5rem"}}
                                       checked={useTerrain} onChange={(e) => setUseTerrain(e.currentTarget.checked)}/>}
        {terrainStatus && <div style={muted}>{terrainStatus}</div>}
        {wind === CLIMATE ? <div style={{margin: "0.5rem 0"}}>
            <div style={{fontWeight: 600}}>Typical {MONTHS[climateMonth - 1]}: not today's winds</div>
            <div style={muted}>
                On how many of 30 past {MONTHS[climateMonth - 1]} days (one from each year, 1991 to 2020) the
                fallout of these bursts reached {climateRate} R/hr or more at H+1. Real winds vary from day to day:
                a place outside the bands can still be reached.
            </div>
            {CLIMATE_BANDS.map((b) => <div key={b.rate} style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem", flexShrink: 0,
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {b.label}
            </div>)}
        </div> : <div style={{margin: "0.5rem 0"}}>
            <Select label="Show" size="xs" data={SHOW} value={show} onChange={(v) => v && setShow(v)}
                    allowDeselect={false} comboboxProps={DROPDOWN}/>
            <div style={{fontWeight: 600, marginTop: "0.25rem"}}>{legendHeading(show, after)}</div>
            <Timeline show={show} after={after} onAfter={(h) => {
                setPlaying(false);
                setAfter(h);
            }} playing={playing} onPlaying={(p) => {
                setPlaying(p);
                if (p && !after) setAfter(1);
            }} startMs={wind === FORECAST && forecast ? Date.parse(forecast.hours[hour]) : null}/>
            <div style={muted}>{legendText(show, after)}</div>
            {(show === TOTAL ? TOTAL_BANDS : DOSE_BANDS).map((b) => <div key={b.rate}
                                                                          style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem", flexShrink: 0,
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {show === TOTAL ? `${b.rate}+ R: ${b.meaning}` : `${b.rate}+ R/hr`}
            </div>)}
        </div>}
        <div style={{...muted, marginBottom: "0.5rem"}}>
            An estimate, not a forecast. Prototype: on six Nevada test bursts it showed about 4
            times the areas measured (from 2 to 8 times), more than was measured on every one.
            {busy && (progress ? ` Calculating ${progress.done} of ${progress.total}…` : " Calculating…")}
        </div>
        <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button role="cancel" size="sm" onClick={onClose}>Close</Button>
        </div>
    </div>;
}

// The heading of the legend, for what is shown and the hour.
export function legendHeading(show, after) {
    const hours = after === 1 ? "1 hour" : `${after} hours`;
    if (show === TOTAL) return after ? `Total dose by ${hours} after the bursts` : "Total dose in the first two weeks";
    return after ? `Dose rate ${hours} after the bursts` : "Dose rate, as at 1 hour after the bursts";
}

// What the legend's bands are, for what is shown and the hour.
export function legendText(show, after) {
    if (show === TOTAL) {
        return "R: roentgens, about 10 mSv each. The dose of someone outdoors the whole time, from when the "
            + "fallout arrives, with the usual decay; real fallout can decay faster or slower, which only "
            + "readings can tell. Indoors is less: about 2 to 3 times in a house, 10 or more in a basement.";
    }
    return "R/hr: roentgens an hour, about 10 mSv each. " + (after
        ? "Only the fallout which has landed by then is shown, as strong as it is then: it weakens about 10 times for every 7 times longer since the bursts. That is the usual decay; real fallout can decay faster or slower, which only readings can tell."
        : "All the fallout is shown as if it were already down 1 hour after the bursts. Downwind it arrives hours later, and has weakened by then: about 10 times less 7 hours after the bursts.");
}

// Which hour after the bursts is shown, 0 for all the fallout as at H+1, and playing them in turn.
// `startMs` is when the bursts are (the forecast hour), if known.
export function Timeline({show = RATE, after, onAfter, playing, onPlaying, startMs}) {
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    const when = after && startMs !== null
        ? `, ${new Date(startMs + after * 3600000).toLocaleString(undefined, {weekday: "short", hour: "numeric", minute: "2-digit"})}`
        : "";
    return <div style={{margin: "0.25rem 0"}}>
        <div style={{display: "flex", alignItems: "center", gap: "0.5rem"}}>
            <Button size="xs" onClick={() => onPlaying(!playing)} aria-label={playing ? "Pause" : "Play"}>
                {playing ? "❚❚" : "▶"}
            </Button>
            <input type="range" min={0} max={LAST_HOUR} step={1} value={after} style={{flex: 1}}
                   aria-label="Hours after the bursts" onChange={(e) => onAfter(Number(e.target.value))}/>
        </div>
        <div style={muted}>
            {show === TOTAL
                ? (after ? `H+${after}${when}: the dose by then` : "The first two weeks. Play to watch the dose build.")
                : (after ? `H+${after}${when}: the fallout landed by then` : "All the fallout, as at H+1. Play to watch it land.")}
        </div>
    </div>;
}

// The forecast winds aloft: which hour, how old, where they reach, and fetching a new field.
function ForecastControls({forecast, prepared, bursts, hour, onHour, online, fetching, fetchPercent, fetchError,
                              onFetch}) {
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    const fetchButton = <div>
        <Button size="xs" onClick={onFetch} disabled={!online || fetching} style={{marginTop: "0.25rem"}}>
            {fetching ? `Fetching… ${Math.round(fetchPercent)}%` : forecast ? "Fetch again" : "Fetch winds aloft"}
        </Button>
        {/* The forecast service allows so many places a minute. */}
        {fetching && <div style={muted}>About a minute for every 90 places of the forecast.</div>}
        {fetchError && <div style={{...muted, color: "var(--warning)"}}>{fetchError}</div>}
    </div>;
    if (!forecast) {
        return <div style={muted}>
            No forecast has been fetched
            {online ? "; until one is, this wind is used at every height:" : ", and WROLPi has no Internet to fetch one. This wind is used at every height:"}
            {fetchButton}
        </div>;
    }
    const nearest = nearestHour(forecast.hours);
    const hours = forecast.hours.map((time, i) => ({value: String(i), label: hourLabel(time, i === nearest)}));
    const age = forecastAge(forecast);
    const outside = bursts.filter((b) => !fieldCovers(prepared, b.lat, b.lon)).length;
    const rainy = bursts.filter((b) => rainNear(prepared, b.lat, b.lon, hour) >= RAIN_WARNING_MM).length;
    const points = forecast.points.length;
    return <div>
        <Select label="Hour of the bursts" size="xs" data={hours} value={String(hour)}
                onChange={(v) => v !== null && onHour(Number(v))} allowDeselect={false}
                maxDropdownHeight={240} comboboxProps={DROPDOWN}/>
        <div style={muted}>
            {forecast.source}, {points === 1 ? "1 place" : `${points} places`} {forecast.spacing}° apart,
            fetched {age < 1 ? "within the hour" : `${Math.round(age)} hours ago`}. Fallout is carried by
            the wind where it is, as it changes hour by hour.
            {forecastExpired(forecast) && " It has run out: its last hour is used from then on."}
            {!forecastExpired(forecast) && forecastRunsOut(forecast, hour) !== null && ` It ends at ${hourLabel(
                forecast.hours[forecast.hours.length - 1], false)}, before all the fallout is down: its last hour's winds are held from then on.`}
        </div>
        {outside > 0 && <div style={{...muted, color: "var(--warning)"}}>
            {outside === 1 ? "1 burst is" : `${outside} bursts are`} outside these winds: the nearest are
            used. Fetch again to cover {outside === 1 ? "it" : "them"}.
        </div>}
        {rainy > 0 && <div style={{...muted, color: "var(--warning)"}}>
            Rain is forecast near {rainy === 1 ? "1 burst" : `${rainy} bursts`} in the 6 hours from then.
            Rain washes fallout out of the air where it falls, which this map shows roughly; real rain is
            patchier than a forecast, and its hot spots may be hotter.
        </div>}
        {fetchButton}
    </div>;
}
