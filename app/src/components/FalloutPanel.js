import React, {useContext, useEffect, useRef, useState} from "react";
import {Button, Checkbox, NumberInput, Select} from "./ui";
import {depositionGrid, landingSpots, profileFromTable} from "../map-shared/fallout/model.js";
import shots from "../map-shared/fallout/nts-shots.json";
import {terrainAround} from "../map-shared/fallout/terrain.js";
import {loadTerrainGrid} from "./falloutTerrain";
import {formatYield, WEAPON_GROUPS} from "../map-shared/fallout/weapons.js";
import {forecastAge, forecastExpired, forecastProfile, nearestHour, rainAhead} from "../map-shared/fallout/winds.js";
import {combineBursts, CUSTOM_WEAPON, DEFAULT_WEAPON, middleOf, targetWeapon} from "../map-shared/fallout/targets.js";
import {fetchFalloutWinds, getLatestFalloutWinds} from "../api";
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

// The weapons, grouped by country, then a yield of the user's own.
export const WEAPON_CHOICES = [
    ...WEAPON_GROUPS.map((g) => ({
        group: g.name,
        items: g.weapons.map((w) => ({value: w.key, label: `${w.name}, ${formatYield(w.yield_kt)}`})),
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
export function gridImage(grid, lat) {
    const canvas = document.createElement("canvas");
    canvas.width = grid.nx;
    canvas.height = grid.ny;
    const context = canvas.getContext("2d");
    const image = context.createImageData(grid.nx, grid.ny);
    const rows = imageRows(grid, lat, grid.ny);
    for (let r = 0; r < grid.ny; r++) {
        const from = rows[r] * grid.nx, to = r * grid.nx;
        for (let i = 0; i < grid.nx; i++) {
            const band = DOSE_BANDS.find((b) => grid.values[from + i] >= b.rate);
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

// The wind profile the model takes, for the wind chosen: a forecast hour (heights above ground zero,
// `groundElevation` m above sea level), one wind at every height, or a sample.
export function windProfile({wind, direction, speed, forecast, hour, groundElevation}) {
    if (wind === FORECAST && forecast) return forecastProfile(forecast.hours[hour], groundElevation);
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
// {grid, origin, terrainStatus}.  `profileFor(groundElevation)` gives the winds over a burst.
// `onProgress(done, total)` hears how far it has got, `onFlat(grid)` gets the fallout on flat ground
// while the terrain is read, and `cancelled()` stops it.
export async function simulateBursts(bursts, {profileFor, forecastElevation = 0, useTerrain = true,
    cancelled = () => false, onProgress = () => null, onFlat = () => null}) {
    const origin = bursts[0];
    const pause = yielder();
    const total = useTerrain ? bursts.length * 2 : bursts.length;
    let done = 0;
    const run = async (terrainOf) => {
        const runs = [], offMap = [];
        for (const b of bursts) {
            const terrain = terrainOf ? terrainOf(b) : null;
            const ground = terrain ? terrain.elevation : forecastElevation;
            const spots = landingSpots({
                yieldKt: b.yieldKt, profile: profileFor(ground), terrain, siteElevation: Math.max(ground, 0),
            });
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
        return depositionGrid(combineBursts(origin, runs), {yieldKt: 1, boundsFloor: floor});
    };
    // On flat ground first: that is where the plumes are, so the terrain under them can be read.
    let grid = await run(null);
    if (!grid) return null;
    let terrainStatus = "Flat ground (terrain is off).";
    if (useTerrain) {
        onFlat(grid);
        let loaded = null;
        try {
            loaded = await loadTerrainGrid(plumeBounds(grid, origin.lon, origin.lat), origin.lon, origin.lat);
        } catch (e) {
            console.error("Could not read the terrain", e);
        }
        if (cancelled()) return null;
        if (loaded) {
            grid = await run((b) => terrainAround(loaded.grid, b.lon, b.lat));
            if (!grid) return null;
            const covered = Math.round(loaded.coverage * 100);
            terrainStatus = `Follows the terrain (zoom ${loaded.zoom}${covered < 100 ? `, ${covered}% of the area` : ""}).`;
        } else {
            terrainStatus = "No terrain file covers this place: flat ground.";
        }
    }
    return {grid, origin, terrainStatus};
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
            {chosen.weapon ? chosen.weapon.name : "A yield of my own"}, {formatYield(chosen.yieldKt)}{" "}
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
    const [direction, setDirection] = useState(270);
    const [speed, setSpeed] = useState(20);
    const [forecast, setForecast] = useState(null);
    const [hour, setHour] = useState(0);
    const [fetching, setFetching] = useState(false);
    const [busy, setBusy] = useState(false);
    const [useTerrain, setUseTerrain] = useState(true);
    const [terrainStatus, setTerrainStatus] = useState(null);
    const [progress, setProgress] = useState(null);
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
        getLatestFalloutWinds().then((latest) => {
            if (cancelled || !latest) return;
            setForecast(latest);
            setHour(nearestHour(latest));
        });
        return () => {
            cancelled = true;
        };
    }, []);

    const fetchForecast = async () => {
        // For the middle of the bursts, or of the map when there are none.
        const place = bursts.length ? middleOf(bursts) : (() => {
            const c = map.getCenter();
            return {lat: c.lat, lon: c.lng};
        })();
        setFetching(true);
        const fetched = await fetchFalloutWinds(place.lat, place.lon);
        setFetching(false);
        if (!fetched) return;
        setForecast(fetched);
        setHour(nearestHour(fetched));
        setWind(FORECAST);
    };

    useEffect(() => {
        let cancelled = false;
        if (!bursts.length) {
            drawn.current = null;
            erase();
            setTerrainStatus(null);
            return;
        }
        setBusy(true);
        const winds = {wind, direction: Number(direction) || 0, speed: Number(speed) || 0, forecast, hour};
        // Until the terrain is read, ground zero is as high as the forecast's ground.
        const forecastElevation = forecast && wind === FORECAST ? forecast.elevation : 0;
        // Let the panel paint "Calculating" before the model takes the thread.
        const timer = setTimeout(async () => {
            const result = await simulateBursts(bursts, {
                profileFor: (groundElevation) => windProfile({...winds, groundElevation}),
                forecastElevation, useTerrain, cancelled: () => cancelled,
                onProgress: (done, total) => !cancelled && setProgress({done, total}),
                // Something to look at while the terrain is read.
                onFlat: (grid) => {
                    if (cancelled) return;
                    drawn.current = {url: gridImage(grid, bursts[0].lat), coordinates: gridCorners(grid, bursts[0].lon, bursts[0].lat)};
                    draw();
                },
            });
            if (cancelled || !result) return;
            setProgress(null);
            drawn.current = {url: gridImage(result.grid, result.origin.lat), coordinates: gridCorners(result.grid, result.origin.lon, result.origin.lat)};
            draw();
            setTerrainStatus(result.terrainStatus);
            setBusy(false);
        }, 30);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [burstsKey, wind, direction, speed, useTerrain, forecast, hour]);

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
        <Select label="Wind" size="xs" data={WINDS} value={wind} onChange={(v) => v && setWind(v)}
                allowDeselect={false} comboboxProps={DROPDOWN}/>
        {wind === FORECAST && <ForecastControls
            forecast={forecast} hour={hour} onHour={setHour} online={online} fetching={fetching}
            onFetch={fetchForecast}/>}
        {(wind === "manual" || (wind === FORECAST && !forecast)) && <div style={{display: "flex", gap: "0.5rem"}}>
            <NumberInput label="From (degrees)" size="xs" min={0} max={359} value={direction} onChange={setDirection}/>
            <NumberInput label="Speed (mph)" size="xs" min={0} max={200} value={speed} onChange={setSpeed}/>
        </div>}
        <Checkbox label="Follow the terrain" size="xs" style={{marginTop: "0.5rem"}} checked={useTerrain}
                  onChange={(e) => setUseTerrain(e.currentTarget.checked)}/>
        {terrainStatus && <div style={muted}>{terrainStatus}</div>}
        <div style={{margin: "0.5rem 0"}}>
            <div style={{fontWeight: 600}}>Dose rate 1 hour after the bursts</div>
            {DOSE_BANDS.map((b) => <div key={b.rate} style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem",
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {b.rate}+ R/hr
            </div>)}
        </div>
        <div style={{...muted, marginBottom: "0.5rem"}}>
            An estimate, not a forecast. Prototype: against fallout measured after test bursts it
            is within about 2 to 4 times, and tends to show more than was measured.
            {busy && (progress ? ` Calculating ${progress.done} of ${progress.total}…` : " Calculating…")}
        </div>
        <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button role="cancel" size="sm" onClick={onClose}>Close</Button>
        </div>
    </div>;
}

// The forecast winds aloft: which hour, how old, and fetching a new one.
function ForecastControls({forecast, hour, onHour, online, fetching, onFetch}) {
    const muted = {color: "var(--muted)", fontSize: "0.75rem"};
    const fetchButton = <Button size="xs" onClick={onFetch} disabled={!online || fetching}
                                style={{marginTop: "0.25rem"}}>
        {fetching ? "Fetching…" : forecast ? "Fetch again" : "Fetch winds aloft"}
    </Button>;
    if (!forecast) {
        return <div style={muted}>
            No forecast has been fetched
            {online ? "; until one is, this wind is used at every height:" : ", and WROLPi has no Internet to fetch one. This wind is used at every height:"}
            <div>{fetchButton}</div>
        </div>;
    }
    const nearest = nearestHour(forecast);
    const hours = forecast.hours.map((h, i) => ({value: String(i), label: hourLabel(h.time, i === nearest)}));
    const age = forecastAge(forecast);
    const rain = rainAhead(forecast, hour);
    return <div>
        <Select label="Hour of the bursts" size="xs" data={hours} value={String(hour)}
                onChange={(v) => v !== null && onHour(Number(v))} allowDeselect={false}
                maxDropdownHeight={240} comboboxProps={DROPDOWN}/>
        <div style={muted}>
            {forecast.source}, for {Math.abs(forecast.lat)}°{forecast.lat >= 0 ? "N" : "S"}{" "}
            {Math.abs(forecast.lon)}°{forecast.lon >= 0 ? "E" : "W"}, fetched{" "}
            {age < 1 ? "within the hour" : `${Math.round(age)} hours ago`}.
            {forecastExpired(forecast) && " It has run out: its last hour is shown."}
        </div>
        {rain >= RAIN_WARNING_MM && <div style={{...muted, color: "var(--warning)"}}>
            Rain is forecast ({rain.toFixed(1)} mm in the 6 hours from then). Rain brings fallout down
            in concentrated places this map does not show.
        </div>}
        {fetchButton}
    </div>;
}
