import React, {useContext, useEffect, useMemo, useRef, useState} from "react";
import {Button, Checkbox, NumberInput, Progress, Select} from "./ui";
import {decayFromH1, doseGrid, landedGrid, profileFromTable} from "../map-shared/fallout/model.js";
import {loadTerrainGrid} from "./falloutTerrain";
import {formatYield, formatYieldAndFission, WEAPON_GROUPS} from "../map-shared/fallout/weapons.js";
import {
    fieldCovers,
    forecastAge,
    forecastCoversFallout,
    forecastExpired,
    forecastRunsOut,
    nearestHour,
    prepareField,
    rainNear,
} from "../map-shared/fallout/winds.js";
import {combineBursts, CUSTOM_WEAPON, targetWeapon} from "../map-shared/fallout/targets.js";
import {fetchFalloutWinds, getFalloutClimatology, getFalloutClimatologyMonth, getJobs, getLatestFalloutWinds} from "../api";
import {climateDay, dayCounter, gunzip, parseClimatology, reachedCells} from "../map-shared/fallout/climatology.js";
import {runPool, workerCount} from "../map-shared/fallout/pool.js";
import {makeFalloutWorker} from "../map-shared/fallout/falloutWorker.js";
import {burstSpots, burstsFrame, burstWinds, gridPart, gridParts, joinParts, portablePrepared} from "../map-shared/fallout/work.js";
import {isJobFinished, useJob} from "./VideoEditMenu";
import {StatusContext} from "../contexts/contexts";

// The map's fallout view (nuclear mode), in steps: the targets (and how their fallout is carried),
// then the fallout of all the targets at once, saved or only tried out: hour by
// hour as it lands and weakens, or the total dose of the first two weeks.

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
// What the map shows: the dose rate hour by hour, or the total dose of someone outdoors.
const RATE = "rate";
const TOTAL = "total";
// The total dose is over the first two weeks, when fallout does most of its harm.
const TWO_WEEKS = 336;
// The steps of the panel: the targets, the wind which carries their fallout, then what is shown.
// The first step is the nuclear button, which opens the panel.
const TARGETS = "targets";
const WIND = "wind";
const VIEW = "view";

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
const MANUAL = "manual";
const WINDS = [
    {value: FORECAST, label: "Forecast winds aloft"},
    {value: MANUAL, label: "One wind at every height"},
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
// The hours after the bursts the fallout can be watched in: landing in the first hours, then
// weakening over days and weeks.  And how long each is shown (ms) when they play.
export const HOURS = [1, 2, 3, 6, 12, 24, 48, 72, 120, 168, 336];
const FRAME_MS = 900;
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

// The image of the fallout `ran` ({grid, spots, origin}) as shown: the dose rate `after` hours after
// the bursts, of the fallout landed by then; or the total dose outdoors in the first two weeks.
export function frameOf(ran, show, after) {
    const grid = show === TOTAL ? doseGrid(ran.spots, ran.grid, TWO_WEEKS) : landedGrid(ran.spots, ran.grid, after);
    const url = gridImage(grid, ran.origin.lat, show === TOTAL ? TOTAL_BANDS : DOSE_BANDS);
    return {url, coordinates: gridCorners(grid, ran.origin.lon, ran.origin.lat)};
}

// The wind profile the model takes, for a wind not of the forecast: one wind at every height (also
// while there is no forecast).
export function windProfile({direction, speed}) {
    return profileFromTable([[0, direction, speed]], 0);
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

// How often the progress is shown, at most (ms): each time redraws the panel.
const PROGRESS_MS = 100;

// `report(done, total)`, called at most every PROGRESS_MS, but always when all is done.
export function everySoOften(report) {
    let last = -Infinity;
    return (done, total) => {
        const now = Date.now();
        if (done < total && now - last < PROGRESS_MS) return;
        last = now;
        report(done, total);
    };
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
// {grid, spots (as combineBursts gives them, for the fallout hour by hour), origin, terrainStatus}.
// `winds` are the winds over them, as burstWinds takes them.  The bursts are spread over `workers`
// workers (on the page, without them, or if they fail).  `onProgress(done, total)` hears how far it
// has got, `onFlat({grid, spots, origin})` gets the fallout on flat ground while the terrain is read, and it stops
// (null) once `signal` (an AbortSignal) is aborted or `cancelled()`.
export async function simulateBursts(bursts, {winds, useTerrain = true, workers = 0, signal = null,
    cancelled = () => false, onProgress = () => null, onFlat = () => null, makeWorker = makeFalloutWorker}) {
    const stopped = () => cancelled() || !!signal?.aborted;
    const origin = bursts[0];
    const {windsFor, groundOf} = burstWinds(winds);
    const total = useTerrain ? bursts.length * 2 : bursts.length;
    // The bursts before this pass's, of the progress.
    let before = 0;
    const plain = bursts.map(({lat, lon, yieldKt, fissionFraction}) => ({lat, lon, yieldKt, fissionFraction}));
    // The bursts' spots, by the workers: null once stopped, undefined if they cannot.
    const spread = async (terrain) => {
        if (workers <= 0) return undefined;
        try {
            return await runPool({
                tasks: bursts.length, total, count: workers, makeWorker, signal,
                start: {kind: 'bursts', bursts: plain, prepared: portablePrepared(winds.prepared),
                    startMs: winds.startMs || 0, profile: winds.profile || null, terrain},
                onProgress: (done) => onProgress(before + done, total),
            });
        } catch (e) {
            console.error("Fallout: the workers failed; calculating on the page", e);
            return undefined;
        }
    };
    const here = async (terrain) => {
        const pause = yielder();
        const found = [];
        for (const b of bursts) {
            found.push(burstSpots(b, {windsFor, groundOf, terrain}));
            onProgress(before + found.length, total);
            await pause();
            if (stopped()) return null;
        }
        return found;
    };
    // The grid of the bursts' `spots`, its parts made by the workers (or here): null once stopped.
    const gridOf = async (spots) => {
        const frame = burstsFrame(spots, DOSE_BANDS[DOSE_BANDS.length - 1].rate);
        const parts = gridParts(spots);
        let made;
        if (workers > 0) {
            try {
                made = await runPool({
                    tasks: parts.length, total: parts.length, count: workers, makeWorker, signal,
                    start: {kind: 'grid', frame}, payload: (k) => ({spots: parts[k]}),
                });
                if (!made) return null;
            } catch (e) {
                console.error("Fallout: the workers failed; calculating on the page", e);
            }
        }
        if (!made) {
            const pause = yielder();
            made = [];
            for (const part of parts) {
                made.push(gridPart(frame, part));
                await pause();
                if (stopped()) return null;
            }
        }
        return joinParts(frame, made);
    };
    const run = async (terrain) => {
        if (stopped()) return null;
        let found = await spread(terrain);
        if (found === null) return null;
        if (!found) found = await here(terrain);
        if (!found || stopped()) return null;
        before += bursts.length;
        const runs = bursts.map((b, i) => ({burst: b, spots: found[i].spots, yieldKt: b.yieldKt,
            fissionFraction: b.fissionFraction}));
        const offMap = bursts.filter((b, i) => found[i].offMap);
        if (offMap.length) console.warn(`Fallout: some spots of ${offMap.length} bursts were not on the map`, offMap);
        const spots = combineBursts(origin, runs);
        const grid = await gridOf(spots);
        if (!grid || stopped()) return null;
        return {grid, spots};
    };
    // On flat ground first: that is where the plumes are, so the terrain under them can be read.
    let ran = await run(null);
    if (!ran) return null;
    let terrainStatus = "Flat ground (terrain is off).";
    if (useTerrain) {
        onFlat({...ran, origin});
        let loaded = null;
        try {
            loaded = await loadTerrainGrid(plumeBounds(ran.grid, origin.lon, origin.lat), origin.lon, origin.lat);
        } catch (e) {
            console.error("Could not read the terrain", e);
        }
        if (stopped()) return null;
        if (loaded) {
            ran = await run(loaded.grid);
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
// level: the days' winds are read by height above the sea.  The days are spread over `workers`
// workers (on the page, without them, or if they fail); null once `signal` (an AbortSignal) is
// aborted or `cancelled()`.
export async function simulateClimate(bursts, clim, {rate = 1, workers = 0, signal = null, cancelled = () => false,
    onProgress = () => null, makeWorker = makeFalloutWorker} = {}) {
    const stopped = () => cancelled() || !!signal?.aborted;
    if (stopped()) return null;
    let days = null;
    if (workers > 0) {
        try {
            const plain = bursts.map(({lat, lon, yieldKt, fissionFraction}) => ({lat, lon, yieldKt, fissionFraction}));
            days = await runPool({
                tasks: clim.days, total: clim.days * bursts.length, count: workers, makeWorker, signal, onProgress,
                start: {kind: 'days', bytes: clim.bytes, bursts: plain, rate},
            });
            if (!days) return null;
        } catch (e) {
            console.error("Fallout: the workers failed; calculating on the page", e);
            days = null;
        }
    }
    if (!days) {
        days = [];
        const pause = yielder();
        let done = 0;
        const total = clim.days * bursts.length;
        const onBurst = async () => {
            onProgress(++done, total);
            await pause();
        };
        for (let k = 0; k < clim.days; k++) {
            const grid = await climateDay(clim, k, bursts, {stopped, onBurst});
            if (!grid || stopped()) return null;
            days.push(reachedCells(grid, rate));
        }
    }
    if (stopped()) return null;
    // Counted on cells as wide as the coarsest day's: a finer count would leave holes between its cells.
    const counter = dayCounter(rate, Math.max(CLIMATE_CELL, ...days.map((d) => d.cell)));
    for (const day of days) counter.add(day);
    return {grid: counter.grid(CLIMATE_SMOOTH), origin: bursts[0]};
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

// The targets simulated once the saved targets (`saved`, pins) are loaded: those, then the ones
// being tried out (`tried`) which are not saved.
export function withSavedTargets(saved, tried) {
    return [...saved.map((t) => ({...t, key: `saved-${t.id}`})), ...tried.filter((t) => !t.id)];
}

// Whether the targets simulated differ from the saved ones (`saved`), which were loaded or not.
export function targetsUnsaved(targets, saved, loaded) {
    if (!loaded) return targets.length > 0;
    const plain = (list) => JSON.stringify(list.map((t) => [t.id, t.lat, t.lon, t.label, t.weapon, t.yield_kt,
        t.fission_fraction]));
    return plain(targets) !== plain(saved);
}

// A target with `weapon` ({weapon, yield_kt?, fission_fraction?}) in place of its old one.
export function withWeapon(target, weapon) {
    const {weapon: _weapon, yield_kt: _yield, fission_fraction: _fission, ...rest} = target;
    return {...rest, ...weapon};
}

// A button which reads as a link, for small actions beside a target.
const LINK = {background: "none", border: "none", padding: 0, color: "var(--link, #4183c4)", cursor: "pointer",
    font: "inherit"};

// A target in the list: its name and weapon (and whether it is saved), the weapon picker when the
// user asks to change it, and taking it out of the list.
function TargetRow({target, onWeapon, onRemove}) {
    const [changing, setChanging] = useState(false);
    const chosen = targetWeapon(target);
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    return <div style={{marginBottom: "0.375rem"}}>
        <div><span aria-hidden>☢ </span><strong>{target.label}</strong>
            {!target.id && <span style={muted}> (not saved)</span>}</div>
        <div style={muted}>
            {chosen.weapon ? chosen.weapon.name : "A yield of my own"},{" "}
            {formatYieldAndFission(chosen.yieldKt, chosen.fissionFraction)}{" "}
            <button type="button" style={LINK} onClick={() => setChanging(!changing)}>
                {changing ? "done" : "change"}
            </button>
            {" · "}
            <button type="button" style={LINK} onClick={onRemove} aria-label={`Remove ${target.label}`}>remove</button>
        </div>
        {changing && <WeaponPicker value={target} onChange={onWeapon}/>}
    </div>;
}

// The fallout view.  `targets` are those simulated ({key, id (if saved), lat, lon, label, weapon,
// yield_kt?, fission_fraction?}): tried out, and the saved ones once the user loads them
// (`onLoad`; there are `savedCount`, and `loaded` says whether they were).  `onSave` saves them in
// place of the saved ones, which is refused until those are loaded; `unsaved` says whether the list
// differs from what is saved.
// `onTargetWeapon(target, weapon)` keeps a target's weapon.
export default function FalloutPanel({map, targets = [], savedCount = 0, loaded = false, unsaved = false, onLoad,
                                         onSave, onRemoveTarget, onTargetWeapon, onAllTargetsWeapon, onClose}) {
    const [step, setStep] = useState(TARGETS);
    const [saving, setSaving] = useState(false);
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
    // The calculation running (an AbortController), whether the user stopped it, and a count which
    // starts it again.
    const running = useRef(null);
    const [stopped, setStopped] = useState(false);
    const [again, setAgain] = useState(0);
    // The hour after the bursts shown (one of HOURS), and whether the hours play.
    const [after, setAfter] = useState(1);
    const [show, setShow] = useState(RATE);
    const [playing, setPlaying] = useState(false);
    // The fallout last calculated ({grid, spots, origin}), and its images by what is shown.
    const result = useRef(null);
    const frames = useRef(new Map());
    const [calculated, setCalculated] = useState(0);
    const {status} = useContext(StatusContext) || {};
    const online = !!status?.flags?.have_internet;
    const drawn = useRef(null);
    const calculatedFor = useRef(null);

    const bursts = useMemo(() => [
        ...targets.map((t) => ({lat: t.lat, lon: t.lon, ...targetWeapon(t)})),
    ], [targets]);
    // What the fallout depends on, as one value an effect can watch.
    const burstsKey = JSON.stringify(bursts.map((b) => [b.lat, b.lon, b.yieldKt, b.fissionFraction]));

    // With nothing to burst, the targets are needed first.
    useEffect(() => {
        if (!bursts.length) setStep(TARGETS);
    }, [bursts.length]);

    // The forecast fetched most recently.
    useEffect(() => {
        let cancelled = false;
        getFalloutClimatology().then((s) => !cancelled && setClimateStatus(s));
        getLatestFalloutWinds().then((latest) => {
            if (!cancelled) setForecastChecked(true);
            if (cancelled || !latest) return;
            setForecast(latest);
            setHour(nearestHour(latest.hours));
        }).catch(() => !cancelled && setForecastChecked(true));
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
        // What the fallout is calculated from: the same again is drawn as it was.
        const inputs = JSON.stringify([burstsKey, wind, direction, speed, useTerrain, forecast?.fetched_at,
            hour, climateMonth, climateRate, again]);
        // Nothing is calculated until the user has chosen the targets, and the map is clear meanwhile.
        if (!bursts.length || step !== VIEW) {
            if (!bursts.length) {
                drawn.current = null;
                result.current = null;
                frames.current = new Map();
                calculatedFor.current = null;
                setTerrainStatus(null);
            }
            erase();
            setBusy(false);
            setProgress(null);
            return;
        }
        if (calculatedFor.current === inputs && drawn.current) {
            if (result.current) setCalculated((n) => n + 1);
            else draw();
            return;
        }
        calculatedFor.current = null;
        const controller = new AbortController();
        running.current = controller;
        setStopped(false);
        setBusy(true);
        setProgress(null);
        if (wind === CLIMATE) {
            // The bursts in each of the month's past days, counted.  Said at once: not the forecast's terrain while counting.
            setTerrainStatus("Flat ground: the past days' winds are read by height above the sea.");
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
                if (cancelled || controller.signal.aborted) return;
                const ran = await simulateClimate(bursts, clim, {
                    rate: Number(climateRate), workers: workerCount(typeof navigator === "undefined" ? {} : navigator),
                    signal: controller.signal, cancelled: () => cancelled,
                    onProgress: everySoOften((done, total) => !cancelled && setProgress({done, total})),
                });
                if (cancelled || !ran) return;
                setProgress(null);
                result.current = null;
                frames.current = new Map();
                drawn.current = ran.grid ? {url: gridImage(ran.grid, ran.origin.lat, CLIMATE_BANDS),
                    coordinates: gridCorners(ran.grid, ran.origin.lon, ran.origin.lat)} : null;
                calculatedFor.current = inputs;
                if (drawn.current) draw();
                else erase();
                setBusy(false);
            }, 30);
            return () => {
                cancelled = true;
                controller.abort();
                clearTimeout(timer);
            };
        }
        // Each burst is carried by the winds where it is, from the hour chosen; or by one profile.
        const winds = useField
            ? {prepared, startMs: Date.parse(forecast.hours[hour])}
            : {profile: windProfile({direction: Number(direction) || 0, speed: Number(speed) || 0})};
        // Let the panel paint "Calculating" before the model takes the thread.
        const timer = setTimeout(async () => {
            const ran = await simulateBursts(bursts, {
                winds, useTerrain, workers: workerCount(typeof navigator === "undefined" ? {} : navigator),
                signal: controller.signal, cancelled: () => cancelled,
                onProgress: everySoOften((done, total) => !cancelled && setProgress({done, total})),
                // Something to look at while the terrain is read: what is shown, on flat ground.
                onFlat: (flat) => {
                    if (cancelled) return;
                    drawn.current = frameOf(flat, show, after);
                    draw();
                },
            });
            if (cancelled || !ran) return;
            setProgress(null);
            result.current = ran;
            frames.current = new Map();
            calculatedFor.current = inputs;
            // The hour shown is drawn from it.
            setCalculated((n) => n + 1);
            setTerrainStatus(ran.terrainStatus);
            setBusy(false);
        }, 30);
        return () => {
            cancelled = true;
            controller.abort();
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [burstsKey, wind, direction, speed, useTerrain, forecast, hour, climateMonth, climateRate, again, step]);

    // Stop the calculation running (and its workers); what was drawn before stays.
    function cancel() {
        running.current?.abort();
        setBusy(false);
        setProgress(null);
        setStopped(true);
    }

    // The forecast's winds when it has them for bursts now, until all their fallout is down; otherwise
    // one wind at every height.  Chosen once: then the wind is the user's to choose.
    const climateKept = !!climateStatus?.months?.includes(climateMonth);
    useEffect(() => {
        if (chosenForUs.current || !forecastChecked) return;
        chosenForUs.current = true;
        if (!forecastCoversFallout(forecast)) setWind(MANUAL);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [forecastChecked]);

    // What is shown: the fallout landed by the hour, as strong as it is then; or the total dose of
    // someone outdoors in the first two weeks.
    useEffect(() => {
        const ran = result.current;
        if (!ran) return;
        const key = show === TOTAL ? TOTAL : `${RATE}:${after}`;
        if (!frames.current.has(key)) frames.current.set(key, frameOf(ran, show, after));
        drawn.current = frames.current.get(key);
        draw();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [after, show, calculated]);

    // Playing, the next hour is shown after this one; from the last, it starts over.
    useEffect(() => {
        if (!playing) return;
        const timer = setTimeout(() => setAfter((h) => HOURS[(HOURS.indexOf(h) + 1) % HOURS.length]), FRAME_MS);
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
    const panelStyle = {
        position: "absolute", left: "0.75rem", bottom: "2.5rem", zIndex: 1002, width: "20rem",
        maxHeight: "calc(100% - 7rem)", overflowY: "auto",
        background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)", padding: "0.75rem",
        fontSize: "0.8125rem",
    };
    const targetCount = targets.length === 1 ? "1 target" : `${targets.length} targets`;
    // Saving replaces the saved targets, so they must be among these first.
    const mustLoad = savedCount > 0 && !loaded;
    const save = async () => {
        setSaving(true);
        try {
            await onSave?.();
        } finally {
            setSaving(false);
        }
    };
    // How the fallout is carried, in a few words.
    const carried = wind === CLIMATE ? `past ${MONTHS[climateMonth - 1]} days' winds`
        : useField ? `forecast winds, ${hourLabel(forecast.hours[hour], false)}`
            : `one wind from ${Number(direction) || 0}° at ${Number(speed) || 0} mph`;
    const ground = wind === CLIMATE ? "" : useTerrain ? "; the terrain" : "; flat ground";
    const close = <Button role="cancel" size="sm" onClick={onClose}>Close</Button>;

    if (step === TARGETS) return <div style={panelStyle}>
        <FalloutSteps step={step}/>
        <div style={{fontWeight: 600}}>Step 2 of 4: Choose the targets</div>
        <div style={{...muted, marginBottom: "0.5rem"}}>
            Right-click the map and choose Add Target Here. Targets you add are tried out, not saved, until
            you save the targets.
        </div>
        {mustLoad && <Button size="xs" style={{marginBottom: "0.5rem"}} onClick={onLoad}>
            Load Saved Targets ({savedCount})
        </Button>}
        <div style={{marginBottom: "0.25rem"}}>
            <strong>{bursts.length ? targetCount : "No targets yet"}</strong>; surface bursts.
            {unsaved && <span style={muted}> Not saved.</span>}
        </div>
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
            {targets.map((t) => <TargetRow key={t.key} target={t} onRemove={() => onRemoveTarget?.(t)}
                                           onWeapon={(weapon) => onTargetWeapon?.(t, weapon)}/>)}
        </div>
        <div style={{marginBottom: "0.75rem"}}>
            <Button size="xs" onClick={save} disabled={mustLoad || saving || (!loaded && !targets.length)}>
                {saving ? "Saving…" : "Save Targets"}
            </Button>
            {mustLoad && <div style={muted}>
                Saving replaces the saved targets: load them first, to keep them.
            </div>}
        </div>
        <div style={{display: "flex", justifyContent: "space-between"}}>
            {close}
            <Button role="primary" size="sm" disabled={!bursts.length} onClick={() => setStep(WIND)}>
                Next: the wind
            </Button>
        </div>
    </div>;

    if (step === WIND) return <div style={panelStyle}>
        <FalloutSteps step={step}/>
        <div style={{fontWeight: 600}}>Step 3 of 4: The wind</div>
        <div style={{...muted, marginBottom: "0.5rem"}}>The wind carries the fallout from the targets.</div>
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
            forecast={forecast} hour={hour} onHour={setHour} online={online}
            fetching={!!fetchJob} fetchPercent={fetchProgress?.progress || 0} fetchError={fetchError}
            onFetch={fetchForecast}/>}
        {(wind === MANUAL || (wind === FORECAST && !forecast)) && <div style={{display: "flex", gap: "0.5rem"}}>
            <NumberInput label="From (degrees)" size="xs" min={0} max={359} value={direction} onChange={setDirection}/>
            <NumberInput label="Speed (mph)" size="xs" min={0} max={200} value={speed} onChange={setSpeed}/>
        </div>}
        {wind !== CLIMATE && <Checkbox label="Follow the terrain" size="xs" style={{marginTop: "0.5rem"}}
                                       checked={useTerrain} onChange={(e) => setUseTerrain(e.currentTarget.checked)}/>}
        <div style={{display: "flex", justifyContent: "space-between", marginTop: "0.75rem"}}>
            <Button role="cancel" size="sm" onClick={() => setStep(TARGETS)}>Back</Button>
            {close}
            <Button role="primary" size="sm" onClick={() => setStep(VIEW)}>Next: the fallout</Button>
        </div>
    </div>;

    return <div style={panelStyle}>
        <FalloutSteps step={step}/>
        <div style={{fontWeight: 600}}>Step 4 of 4: The fallout</div>
        <div style={{...muted, marginBottom: "0.5rem"}}>{targetCount}; {carried}{ground}.</div>
        <FalloutProgress busy={busy} progress={progress} onCancel={cancel}/>
        {stopped && !busy && <div style={{...muted, display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem"}}>
            Calculation cancelled.
            <Button size="xs" onClick={() => setAgain((n) => n + 1)}>Calculate</Button>
        </div>}
        {terrainStatus && <div style={muted}>{terrainStatus}</div>}
        {wind === FORECAST && prepared && <ForecastWarnings prepared={prepared} bursts={bursts} hour={hour}/>}
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
            <div style={{display: "flex", gap: "0.5rem"}}>
                <Button size="xs" role={show === RATE ? "primary" : "cancel"} aria-pressed={show === RATE}
                        style={{flex: 1}} onClick={() => setShow(RATE)}>Hour by hour</Button>
                <Button size="xs" role={show === TOTAL ? "primary" : "cancel"} aria-pressed={show === TOTAL}
                        style={{flex: 1}} onClick={() => {
                            setPlaying(false);
                            setShow(TOTAL);
                        }}>Total dose</Button>
            </div>
            <div style={{fontWeight: 600, marginTop: "0.5rem"}}>{legendHeading(show, after)}</div>
            {show === RATE && <Timeline after={after} onAfter={(h) => {
                setPlaying(false);
                setAfter(h);
            }} playing={playing} onPlaying={setPlaying}
                                        startMs={useField ? Date.parse(forecast.hours[hour]) : null}/>}
            <div style={muted}>{legendText(show)}</div>
            {(show === TOTAL ? TOTAL_BANDS : DOSE_BANDS).map((b) => <div key={b.rate}
                                                                          style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem", flexShrink: 0,
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {show === TOTAL ? `${b.rate}+ R: ${b.meaning}` : `${b.rate}+ R/hr`}
            </div>)}
        </div>}
        <div style={{...muted, marginBottom: "0.5rem"}}>An estimate, not a forecast.</div>
        <div style={{display: "flex", justifyContent: "space-between"}}>
            <Button role="cancel" size="sm" onClick={() => {
                setPlaying(false);
                setStep(WIND);
            }}>Back</Button>
            {close}
        </div>
    </div>;
}

// Where the user is in the panel's steps: the nuclear button (done once the panel is open), the
// targets, the wind, and the fallout.
export function FalloutSteps({step}) {
    const names = [["Nuclear", null], ["Targets", TARGETS], ["Wind", WIND], ["Fallout", VIEW]];
    const at = names.findIndex(([, s]) => s === step);
    return <ol aria-label="Steps" style={{display: "flex", gap: "0.75rem", listStyle: "none", padding: 0,
        margin: "0 0 0.5rem 0", fontSize: "0.75rem"}}>
        {names.map(([name], k) => <li key={name} aria-current={k === at ? "step" : undefined}
                                      style={{color: k === at ? "var(--text)" : "var(--muted)", fontWeight: k === at ? 600 : 400}}>
            {k < at ? "✓" : `${k + 1}.`} {name}
        </li>)}
    </ol>;
}

// How far the calculation has got, while it runs: a bar filled as far as the bursts are done
// (`progress`: {done, total}), or moving without a count until there is one; and a button which
// stops it (`onCancel`).
export function FalloutProgress({busy, progress, onCancel}) {
    if (!busy) return null;
    return <div style={{display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem"}}>
        <div style={{flex: 1, minWidth: 0}}>
            {progress && progress.total > 0
                ? <Progress percent={100 * progress.done / progress.total}
                            label={`Calculating ${progress.done.toLocaleString()} of ${progress.total.toLocaleString()}`}/>
                : <Progress indeterminate showPercent={false} label="Calculating…"/>}
        </div>
        {onCancel && <Button size="xs" role="cancel" onClick={onCancel}>Cancel</Button>}
    </div>;
}

// `hours` after the bursts, as the user reads it: hours, then days, then weeks.
export function afterLabel(hours) {
    if (hours < 24) return hours === 1 ? "1 hour" : `${hours} hours`;
    if (hours % 168 === 0) return hours === 168 ? "1 week" : `${hours / 168} weeks`;
    return hours === 24 ? "1 day" : `${hours / 24} days`;
}

// How many times weaker fallout is `hours` after the bursts than at H+1, as the user reads it.
export function weakerThanH1(hours) {
    return Number((1 / decayFromH1(hours)).toPrecision(2)).toLocaleString();
}

// The heading of the legend, for what is shown and the hour.
export function legendHeading(show, after) {
    if (show === TOTAL) return "Total dose outdoors in the first two weeks";
    return `Dose rate ${afterLabel(after)} after the bursts`;
}

// What the legend's bands are, for what is shown.
export function legendText(show) {
    if (show === TOTAL) {
        return "R: roentgens, about 10 mSv each. The dose of someone outdoors the whole time, from when the "
            + "fallout arrives, with the usual decay; real fallout can decay faster or slower, which only "
            + "readings can tell. Indoors is less: about 2 to 3 times in a house, 10 or more in a basement.";
    }
    return "R/hr: roentgens an hour, about 10 mSv each. Only the fallout which has landed by then is shown, "
        + "as strong as it is then. Downwind it lands hours after the bursts, and everywhere it weakens: about "
        + "10 times for every 7 times longer since the bursts. That is the usual decay; real fallout can decay "
        + "faster or slower, which only readings can tell.";
}

// Which hour after the bursts is shown (one of HOURS), and playing them in turn.  `startMs` is when
// the bursts are (the forecast hour), if known.
export function Timeline({after, onAfter, playing, onPlaying, startMs}) {
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    const when = startMs !== null && startMs !== undefined
        ? `, ${new Date(startMs + after * 3600000).toLocaleString(undefined, {weekday: "short", hour: "numeric", minute: "2-digit"})}`
        : "";
    const at = Math.max(HOURS.indexOf(after), 0);
    return <div style={{margin: "0.25rem 0"}}>
        <div style={{display: "flex", alignItems: "center", gap: "0.5rem"}}>
            <Button size="xs" onClick={() => onPlaying(!playing)} aria-label={playing ? "Pause" : "Play"}>
                {playing ? "❚❚" : "▶"}
            </Button>
            <input type="range" min={0} max={HOURS.length - 1} step={1} value={at} style={{flex: 1}}
                   aria-label="Time after the bursts" aria-valuetext={afterLabel(after)}
                   onChange={(e) => onAfter(HOURS[Number(e.target.value)])}/>
        </div>
        <div style={muted}>
            H+{after}{when}: the fallout landed by then
            {after > 1 ? `, about ${weakerThanH1(after)} times weaker than at H+1` : ""}.
        </div>
    </div>;
}

// The forecast winds aloft: which hour, how old, where they reach, and fetching a new field.
function ForecastControls({forecast, hour, onHour, online, fetching, fetchPercent, fetchError, onFetch}) {
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    // Not again while the panel shows its progress: the hours' labels are slow to write.
    // Written again at half past each hour, when the hour nearest now moves on.
    const nowHour = Math.round(Date.now() / 3600000);
    const hours = useMemo(() => {
        if (!forecast) return [];
        const nearest = nearestHour(forecast.hours, new Date(nowHour * 3600000));
        return forecast.hours.map((time, i) => ({value: String(i), label: hourLabel(time, i === nearest)}));
    }, [forecast, nowHour]);
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
    const age = forecastAge(forecast);

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
        {fetchButton}
    </div>;
}

// What the user should know of the forecast, beside its fallout: bursts outside its winds, and rain.
function ForecastWarnings({prepared, bursts, hour}) {
    const warning = {color: "var(--warning)", fontSize: "0.75rem"};
    const outside = useMemo(() => bursts.filter((b) => !fieldCovers(prepared, b.lat, b.lon)).length,
        [prepared, bursts]);
    const rainy = useMemo(() => bursts.filter((b) => rainNear(prepared, b.lat, b.lon, hour) >= RAIN_WARNING_MM).length,
        [prepared, bursts, hour]);
    return <>
        {outside > 0 && <div style={warning}>
            {outside === 1 ? "1 burst is" : `${outside} bursts are`} outside the forecast's winds: the nearest
            are used. Fetch again (Back, to the wind) to cover {outside === 1 ? "it" : "them"}.
        </div>}
        {rainy > 0 && <div style={warning}>
            Rain is forecast near {rainy === 1 ? "1 burst" : `${rainy} bursts`} in the 6 hours from then.
            Rain washes fallout out of the air where it falls, which this map shows roughly; real rain is
            patchier than a forecast, and its hot spots may be hotter.
        </div>}
    </>;
}
