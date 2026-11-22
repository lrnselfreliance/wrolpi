import React, {useEffect, useRef, useState} from "react";
import {Button, Checkbox, NumberInput, Select} from "./ui";
import {
    depositionGrid,
    landingSpots,
    profileFromTable,
    stabilizedCloud,
} from "../map-shared/fallout/model.js";
import shots from "../map-shared/fallout/nts-shots.json";
import {terrainAround} from "../map-shared/fallout/terrain.js";
import {loadTerrainGrid} from "./falloutTerrain";

// A prototype of the fallout simulator (fallout-plan.md): one surface burst where the user clicked,
// drawn as the dose rate at H+1 hour.  Nothing is saved.

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

const YIELDS = [1, 10, 100, 300, 1000].map((kt) => ({value: String(kt), label: kt >= 1000 ? `${kt / 1000} Mt` : `${kt} kt`}));
const WINDS = [
    {value: "manual", label: "One wind at every height"},
    ...shots.shots.map((s) => ({value: s.name, label: `Winds aloft of ${s.name} (${s.date.slice(0, 10)})`})),
];

// The grid as an image: each cell colored by the highest band it reaches, transparent below them.
export function gridImage(grid) {
    const canvas = document.createElement("canvas");
    canvas.width = grid.nx;
    canvas.height = grid.ny;
    const context = canvas.getContext("2d");
    const image = context.createImageData(grid.nx, grid.ny);
    for (let j = 0; j < grid.ny; j++) {
        // The grid's rows run from the south; the image's from the top.
        const row = (grid.ny - 1 - j) * grid.nx;
        for (let i = 0; i < grid.nx; i++) {
            const band = DOSE_BANDS.find((b) => grid.values[j * grid.nx + i] >= b.rate);
            if (!band) continue;
            const p = (row + i) * 4;
            image.data[p] = band.color[0];
            image.data[p + 1] = band.color[1];
            image.data[p + 2] = band.color[2];
            image.data[p + 3] = 255;
        }
    }
    context.putImageData(image, 0, 0);
    return canvas.toDataURL();
}

// The corners of the grid (top-left, top-right, bottom-right, bottom-left) as [lon, lat], around a
// burst at `lon`, `lat`.
export function gridCorners(grid, lon, lat) {
    const toLon = (x) => lon + x / (METERS_PER_DEGREE * Math.cos(lat * Math.PI / 180));
    const toLat = (y) => lat + y / METERS_PER_DEGREE;
    const west = toLon(grid.x0), east = toLon(grid.x0 + grid.nx * grid.cell);
    const south = toLat(grid.y0), north = toLat(grid.y0 + grid.ny * grid.cell);
    return [[west, north], [east, north], [east, south], [west, south]];
}

export function windProfile({wind, direction, speed}) {
    const rows = wind === "manual"
        ? [[0, direction, speed]]
        : shots.shots.find((s) => s.name === wind).wind.map(([z, d, s], _, all) => [z - all[0][0], d, s]);
    return profileFromTable(rows, 0);
}

export function simulate({yieldKt, fissionFraction, profile, terrain = null}) {
    const spots = landingSpots({
        cloud: stabilizedCloud(yieldKt), profile, terrain,
        siteElevation: terrain ? Math.max(terrain.elevation, 0) : 0,
    });
    return depositionGrid(spots, {yieldKt, fissionFraction});
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

export default function FalloutPanel({map, lat, lon, onClose}) {
    const [yieldKt, setYieldKt] = useState("100");
    const [fission, setFission] = useState(50);
    const [wind, setWind] = useState("manual");
    const [direction, setDirection] = useState(270);
    const [speed, setSpeed] = useState(20);
    const [busy, setBusy] = useState(false);
    const [useTerrain, setUseTerrain] = useState(true);
    const [terrainStatus, setTerrainStatus] = useState(null);
    const drawn = useRef(null);

    useEffect(() => {
        let cancelled = false;
        setBusy(true);
        // Let the panel paint "Calculating" before the model takes the thread.
        const timer = setTimeout(async () => {
            const options = {yieldKt: Number(yieldKt), fissionFraction: fission / 100,
                profile: windProfile({wind, direction: Number(direction) || 0, speed: Number(speed) || 0})};
            // On flat ground first: that is where the plume is, so the terrain under it can be read.
            let grid = simulate(options);
            let status = "Flat ground (terrain is off).";
            if (useTerrain) {
                let loaded = null;
                try {
                    loaded = await loadTerrainGrid(plumeBounds(grid, lon, lat), lon, lat);
                } catch (e) {
                    console.error("Could not read the terrain", e);
                }
                if (cancelled) return;
                if (loaded) {
                    grid = simulate({...options, terrain: terrainAround(loaded.grid, lon, lat)});
                    const covered = Math.round(loaded.coverage * 100);
                    status = `Follows the terrain (zoom ${loaded.zoom}${covered < 100 ? `, ${covered}% of the area` : ""}).`;
                } else {
                    status = "No terrain file covers this place: flat ground.";
                }
            }
            if (cancelled) return;
            drawn.current = {url: gridImage(grid), coordinates: gridCorners(grid, lon, lat)};
            draw();
            setTerrainStatus(status);
            setBusy(false);
        }, 30);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [yieldKt, fission, wind, direction, speed, useTerrain, lat, lon]);

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

    useEffect(() => {
        if (!map) return;
        const restore = () => draw();
        map.on("style.load", restore);
        return () => {
            map.off("style.load", restore);
            try {
                if (map.getLayer(LAYER)) map.removeLayer(LAYER);
                if (map.getSource(SOURCE)) map.removeSource(SOURCE);
            } catch (e) {
                // The map is gone.
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [map]);

    return <div style={{
        position: "absolute", left: "0.75rem", bottom: "2.5rem", zIndex: 1002, width: "19rem",
        background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)", padding: "0.75rem",
        fontSize: "0.8125rem",
    }}>
        <div style={{fontWeight: 600}}>Fallout (prototype)</div>
        <div style={{color: "var(--muted)", marginBottom: "0.5rem"}}>
            Surface burst at {lat.toFixed(3)}, {lon.toFixed(3)}
        </div>
        <Select label="Yield" size="xs" data={YIELDS} value={yieldKt} onChange={(v) => v && setYieldKt(v)}
                allowDeselect={false}/>
        <NumberInput label="Fission fraction (%)" size="xs" min={1} max={100} value={fission}
                     onChange={(v) => setFission(Math.min(100, Math.max(1, Number(v) || 1)))}/>
        <Select label="Wind" size="xs" data={WINDS} value={wind} onChange={(v) => v && setWind(v)}
                allowDeselect={false}/>
        {wind === "manual" && <div style={{display: "flex", gap: "0.5rem"}}>
            <NumberInput label="From (degrees)" size="xs" min={0} max={359} value={direction} onChange={setDirection}/>
            <NumberInput label="Speed (mph)" size="xs" min={0} max={200} value={speed} onChange={setSpeed}/>
        </div>}
        <Checkbox label="Follow the terrain" size="xs" style={{marginTop: "0.5rem"}} checked={useTerrain}
                  onChange={(e) => setUseTerrain(e.currentTarget.checked)}/>
        {terrainStatus && <div style={{color: "var(--muted)", fontSize: "0.75rem"}}>{terrainStatus}</div>}
        <div style={{margin: "0.5rem 0"}}>
            <div style={{fontWeight: 600}}>Dose rate 1 hour after the burst</div>
            {DOSE_BANDS.map((b) => <div key={b.rate} style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem",
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {b.rate}+ R/hr
            </div>)}
        </div>
        <div style={{color: "var(--muted)", fontSize: "0.75rem", marginBottom: "0.5rem"}}>
            An estimate, not a forecast. Prototype: how much activity lands is uncertain by about
            a factor of two, and below 10 kt the dose near ground zero is likely too low.
            {busy && " Calculating…"}
        </div>
        <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button role="cancel" size="sm" onClick={onClose}>Close</Button>
        </div>
    </div>;
}
