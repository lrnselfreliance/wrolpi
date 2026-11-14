import React, {useEffect, useRef, useState} from "react";
import {Button} from "./ui";
import {
    EMPTY_FEATURES,
    QUAD_MIN_ZOOM,
    quadAt,
    quadGridLines,
    quadLabel,
    quadPolygon,
    quadSize,
} from "./mapQuads";

const GRID_SOURCE = "quad-grid";
const SELECTED_SOURCE = "quad-selected";
// The picker's own layers, in the order they are drawn (all above the map's).
const QUAD_LAYERS = [
    {
        id: "quad-grid-lines", type: "line", source: GRID_SOURCE,
        paint: {"line-color": "#e8590c", "line-width": 1.5, "line-opacity": 0.8},
    },
    {
        id: "quad-selected-fill", type: "fill", source: SELECTED_SOURCE,
        paint: {"fill-color": "#e8590c", "fill-opacity": 0.2},
    },
    {
        id: "quad-selected-outline", type: "line", source: SELECTED_SOURCE,
        paint: {"line-color": "#e8590c", "line-width": 3.5},
    },
];

export function formatDistance(meters, scaleUnit) {
    return scaleUnit === "imperial"
        ? `${(meters / 1609.344).toFixed(1)} mi`
        : `${(meters / 1000).toFixed(1)} km`;
}

export function formatSheet(millimeters, scaleUnit) {
    return scaleUnit === "imperial"
        ? `${(millimeters / 25.4).toFixed(1)} in`
        : `${(millimeters / 10).toFixed(1)} cm`;
}

function selectedFeatures(quad) {
    return quad ? {type: "FeatureCollection", features: [quadPolygon(quad)]} : EMPTY_FEATURES;
}

// Draws the grid of 1:24,000 quadrangles over the map while the user chooses one to export.
//
// The grid and the chosen quadrangle are layers of the map, which a change of its style removes; they
// are put back whenever the style has loaded.
export default function MapQuadPicker({map, scaleUnit, initialQuad = null, onExport, onClose}) {
    const [selected, setSelected] = useState(initialQuad);
    const selectedRef = useRef(initialQuad);
    // Whether the map is zoomed in far enough for the grid to be drawn.
    const [gridShown, setGridShown] = useState(true);

    useEffect(() => {
        if (!map) return;

        const drawGrid = () => {
            const source = map.getSource(GRID_SOURCE);
            if (!source) return;
            const bounds = map.getBounds();
            const grid = map.getZoom() >= QUAD_MIN_ZOOM
                ? quadGridLines({
                    west: bounds.getWest(), south: bounds.getSouth(),
                    east: bounds.getEast(), north: bounds.getNorth(),
                })
                : null;
            source.setData(grid || EMPTY_FEATURES);
            setGridShown(grid !== null);
        };

        const drawSelected = () => {
            const source = map.getSource(SELECTED_SOURCE);
            if (source) source.setData(selectedFeatures(selectedRef.current));
        };

        const addLayers = () => {
            if (!map.getSource(GRID_SOURCE)) map.addSource(GRID_SOURCE, {type: "geojson", data: EMPTY_FEATURES});
            if (!map.getSource(SELECTED_SOURCE)) {
                map.addSource(SELECTED_SOURCE, {type: "geojson", data: EMPTY_FEATURES});
            }
            for (const layer of QUAD_LAYERS) {
                if (!map.getLayer(layer.id)) map.addLayer(layer);
            }
            drawGrid();
            drawSelected();
        };

        const choose = (e) => {
            const quad = quadAt(e.lngLat.lng, e.lngLat.lat);
            // Choosing the chosen quadrangle again lets go of it.
            const next = quad && selectedRef.current?.id === quad.id ? null : quad;
            selectedRef.current = next;
            setSelected(next);
            drawSelected();
        };

        addLayers();
        map.on("style.load", addLayers);
        map.on("moveend", drawGrid);
        map.on("click", choose);

        return () => {
            map.off("style.load", addLayers);
            map.off("moveend", drawGrid);
            map.off("click", choose);
            try {
                for (const layer of [...QUAD_LAYERS].reverse()) {
                    if (map.getLayer(layer.id)) map.removeLayer(layer.id);
                }
                for (const source of [GRID_SOURCE, SELECTED_SOURCE]) {
                    if (map.getSource(source)) map.removeSource(source);
                }
            } catch (e) {
                // The map itself is gone, and its layers with it.
            }
        };
    }, [map]);

    const size = selected ? quadSize(selected) : null;

    // Part of the app's interface over the map, like the layer control: plain, token-colored chrome.
    const panelStyle = {
        position: "absolute",
        bottom: "2.5rem",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        background: "var(--panel)",
        border: "1px solid var(--border)",
        color: "var(--text)",
        padding: "0.625rem 0.75rem",
        fontSize: "0.8125rem",
        width: "max-content",
        maxWidth: "calc(100% - 1.25rem)",
    };

    return <div style={panelStyle} role="region" aria-label="Export a 1:24,000 map">
        <div style={{fontWeight: 600, paddingBottom: "0.25rem"}}>Export a 1:24,000 map</div>
        {selected
            ? <div>
                <div data-testid="quad-label">{quadLabel(selected)}</div>
                <div style={{color: "var(--muted)"}} data-testid="quad-size">
                    {formatDistance(size.widthMeters, scaleUnit)} × {formatDistance(size.heightMeters, scaleUnit)}
                    {" on the ground, "}
                    {formatSheet(size.sheetWidthMm, scaleUnit)} × {formatSheet(size.sheetHeightMm, scaleUnit)}
                    {" printed"}
                </div>
            </div>
            : <div>
                {gridShown
                    ? "Click a quadrangle on the map to choose it."
                    : "Zoom in to see the quadrangles."}
            </div>}
        <div style={{display: "flex", gap: "0.5rem", justifyContent: "flex-end", paddingTop: "0.5rem"}}>
            <Button role="cancel" size="xs" onClick={onClose}>Cancel</Button>
            <Button
                role="primary"
                size="xs"
                disabled={!selected || !onExport}
                onClick={() => onExport(selected)}
            >Export PDF</Button>
        </div>
    </div>;
}
