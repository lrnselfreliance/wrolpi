import React, {useEffect, useRef, useState} from "react";
import {Button, NumberInput, Select} from "./ui";
import {
    depositionGrid,
    landingSpots,
    profileFromTable,
    stabilizedCloud,
} from "../map-shared/fallout/model.js";
import shots from "../map-shared/fallout/nts-shots.json";

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

export function simulate({yieldKt, fissionFraction, wind, direction, speed}) {
    const rows = wind === "manual"
        ? [[0, direction, speed]]
        : shots.shots.find((s) => s.name === wind).wind.map(([z, d, s], _, all) => [z - all[0][0], d, s]);
    const profile = profileFromTable(rows, 0);
    const spots = landingSpots({cloud: stabilizedCloud(yieldKt), profile});
    return depositionGrid(spots, {yieldKt, fissionFraction});
}

export default function FalloutPanel({map, lat, lon, onClose}) {
    const [yieldKt, setYieldKt] = useState("100");
    const [fission, setFission] = useState(50);
    const [wind, setWind] = useState("manual");
    const [direction, setDirection] = useState(270);
    const [speed, setSpeed] = useState(20);
    const [busy, setBusy] = useState(false);
    const drawn = useRef(null);

    useEffect(() => {
        let cancelled = false;
        setBusy(true);
        // Let the panel paint "Calculating" before the model takes the thread.
        const timer = setTimeout(() => {
            const grid = simulate({
                yieldKt: Number(yieldKt), fissionFraction: fission / 100, wind,
                direction: Number(direction) || 0, speed: Number(speed) || 0,
            });
            if (cancelled) return;
            drawn.current = {url: gridImage(grid), coordinates: gridCorners(grid, lon, lat)};
            draw();
            setBusy(false);
        }, 30);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [yieldKt, fission, wind, direction, speed, lat, lon]);

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
        <div style={{margin: "0.5rem 0"}}>
            <div style={{fontWeight: 600}}>Dose rate 1 hour after the burst</div>
            {DOSE_BANDS.map((b) => <div key={b.rate} style={{display: "flex", alignItems: "center", gap: "0.375rem"}}>
                <span style={{display: "inline-block", width: "0.875rem", height: "0.875rem",
                    background: `rgb(${b.color.join(",")})`, opacity: 0.8}}/>
                {b.rate}+ R/hr
            </div>)}
        </div>
        <div style={{color: "var(--muted)", fontSize: "0.75rem", marginBottom: "0.5rem"}}>
            An estimate, not a forecast. Prototype: dose rates near ground zero are too low (no
            stem or early fallout yet).{busy && " Calculating…"}
        </div>
        <div style={{display: "flex", justifyContent: "flex-end"}}>
            <Button role="cancel" size="sm" onClick={onClose}>Close</Button>
        </div>
    </div>;
}
