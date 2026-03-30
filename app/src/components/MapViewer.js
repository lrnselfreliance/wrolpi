import React, {useCallback, useContext, useEffect, useRef, useState} from "react";
import {useSearchParams} from "react-router";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {Protocol} from "pmtiles";
import layers from "protomaps-themes-base";
import mlcontour from "@acalcutt/maplibre-contour-pmtiles";
import {addMapPin, deleteMapPin, getMapFiles, getMapPins} from "../api";
import {MAP_VIEWER_URI} from "./Vars";
import {Checkbox, Icon, Segment} from "semantic-ui-react";
import {Header} from "./Theme";
import {ThemeContext} from "../contexts/contexts";

// Terrain DEM file prefix for hillshade and contours.
const TERRAIN_PREFIX = "terrain-";

// Detect full planet files: "planet-20260329.pmtiles" or bare date like "20260329.pmtiles".
function isPlanetFile(name) {
    if (name.startsWith("planet-")) return true;
    return /^\d{8}\.pmtiles$/.test(name);
}

// Layer groups matching the standalone viewer.
const LAYER_GROUPS = {
    "Hillshade": ["hillshade"],
    "Contours": ["contour-lines", "contour-labels"],
    "Water": ["water"],
    "Land Cover": [
        "landcover", "landuse_park", "landuse_urban_green", "landuse_beach",
        "landuse_aerodrome", "landuse_hospital", "landuse_industrial",
        "landuse_pedestrian", "landuse_pier", "landuse_school", "landuse_zoo",
    ],
    "Buildings": ["buildings"],
    "Roads - Highway": ["roads_highway"],
    "Roads - Major": ["roads_major", "roads_link"],
    "Roads - Minor": ["roads_minor", "roads_other"],
    "Roads - Tunnels": ["roads_tunnels"],
    "Roads - Bridges": ["roads_bridges"],
    "Rail & Runways": ["roads_rail", "roads_runway", "roads_taxiway", "landuse_runway"],
    "Boundaries": ["boundaries"],
    "Labels": ["roads_labels", "places_", "address_label", "pois", "water_label", "water_waterway_label"],
};

// Register PMTiles protocol once.
const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

// Planet overview blob — provides global basemap at zoom 0-6.
const MAP_OVERVIEW_URL = "/blobs/map-overview.pmtiles";

// Layers to skip from non-primary sources (they would paint over the primary source's content).
const SKIP_SECONDARY = new Set(["background", "earth"]);

// Set up contour DEM source (must be called once before buildStyle).
let demSource = null;
let terrainUrl = null;
function initContourSource(filename) {
    terrainUrl = `/media/map/${filename}`;
    if (demSource) return;
    demSource = new mlcontour.DemSource({
        url: `pmtiles://${window.location.origin}${terrainUrl}`,
        encoding: "terrarium",
        maxzoom: 8,
        worker: true,
    });
    demSource.setupMaplibre(maplibregl);
}

// sources: [{name, url}] where name is used as the MapLibre source ID and url is the pmtiles:// URL.
// hasTerrain: whether to include hillshade and contour layers.
// scaleUnit: "metric" or "imperial" — affects contour intervals and labels.
function buildStyle(sources, flavor = "light", hasTerrain = false, scaleUnit = "metric") {
    const styleSources = {};
    const allLayers = [];

    for (let i = 0; i < sources.length; i++) {
        const {name, url} = sources[i];
        styleSources[name] = {type: "vector", url};
        const fileLayers = layers(name, flavor);
        if (i === 0) {
            // Primary source: use layer IDs as-is.
            allLayers.push(...fileLayers);
        } else {
            // Additional sources: prefix layer IDs and skip background/earth.
            for (const layer of fileLayers) {
                if (SKIP_SECONDARY.has(layer.id)) continue;
                allLayers.push({...layer, id: `${name}:${layer.id}`});
            }
        }
    }

    // Add terrain sources and layers if available.
    if (hasTerrain && demSource) {
        // Read saved visibility to set initial layer state correctly.
        const savedVis = getInitialVisibility();
        const hillshadeVis = savedVis["Hillshade"] ? "visible" : "none";
        const contourVis = savedVis["Contours"] ? "visible" : "none";

        // Hillshade from raster-dem source.
        styleSources["terrain-dem"] = {
            type: "raster-dem",
            url: `pmtiles://${terrainUrl}`,
            encoding: "terrarium",
            tileSize: 512,
        };

        // Insert hillshade early (after earth/landcover, before roads).
        const hillshadeSearch = allLayers.findIndex(l => l.id === "buildings");
        const hillshadeIdx = hillshadeSearch === -1 ? allLayers.length : hillshadeSearch;
        allLayers.splice(hillshadeIdx, 0, {
            id: "hillshade",
            type: "hillshade",
            source: "terrain-dem",
            layout: {visibility: hillshadeVis},
            paint: {
                "hillshade-shadow-color": "#000000",
                "hillshade-illumination-anchor": "viewport",
                "hillshade-exaggeration": 0.3,
            },
        });

        // Contour lines from on-the-fly generation.
        const isImperial = scaleUnit === "imperial";
        const contourUrl = demSource.contourProtocolUrl({
            overzoom: 1,
            contourLayer: "contours",
            elevationKey: "ele",
            levelKey: "level",
            multiplier: isImperial ? 3.28084 : 1, // meters to feet conversion
            thresholds: isImperial ? {
                // [minor, major] contour intervals in feet per zoom level.
                4: [1000, 5000],
                5: [500, 2500],
                6: [200, 1000],
                7: [200, 1000],
                8: [100, 500],
            } : {
                // [minor, major] contour intervals in meters per zoom level.
                4: [500, 2500],
                5: [200, 1000],
                6: [100, 500],
                7: [100, 500],
                8: [50, 200],
            },
        });
        const elevUnit = isImperial ? "ft" : "m";
        styleSources["contours"] = {
            type: "vector",
            tiles: [contourUrl],
            maxzoom: 8,
        };

        allLayers.push(
            {
                id: "contour-lines",
                type: "line",
                source: "contours",
                "source-layer": "contours",
                filter: ["!=", ["get", "level"], 1],
                layout: {visibility: contourVis},
                paint: {"line-color": "rgba(150,100,50,0.3)", "line-width": 0.5},
            },
            {
                id: "contour-lines-major",
                type: "line",
                source: "contours",
                "source-layer": "contours",
                filter: ["==", ["get", "level"], 1],
                layout: {visibility: contourVis},
                paint: {"line-color": "rgba(150,100,50,0.5)", "line-width": 1},
            },
            {
                id: "contour-labels",
                type: "symbol",
                source: "contours",
                "source-layer": "contours",
                filter: ["==", ["get", "level"], 1],
                layout: {
                    visibility: contourVis,
                    "symbol-placement": "line",
                    "text-field": ["concat", ["get", "ele"], elevUnit],
                    "text-size": 10,
                },
                paint: {
                    "text-color": flavor === "dark" ? "rgba(210,180,140,0.9)" : "rgba(150,100,50,0.8)",
                    "text-halo-color": flavor === "dark" ? "rgba(0,0,0,0.8)" : "rgba(255,255,255,0.8)",
                    "text-halo-width": 1,
                },
            },
        );
    }

    return {
        version: 8,
        glyphs: "/map-assets/fonts/{fontstack}/{range}.pbf",
        sprite: `${window.location.origin}/map-assets/sprites/${flavor}`,
        sources: styleSources,
        layers: allLayers,
    };
}

// Groups that start hidden by default (used when no saved state exists).
const DEFAULT_HIDDEN = new Set(["Hillshade", "Contours"]);
const STORAGE_KEY_LAYERS = "wrolpi-map-layers";
const STORAGE_KEY_SCALE = "wrolpi-map-scale";

function getInitialVisibility() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY_LAYERS);
        if (saved) return JSON.parse(saved);
    } catch (e) { /* ignore */ }
    const v = {};
    for (const g of Object.keys(LAYER_GROUPS)) v[g] = !DEFAULT_HIDDEN.has(g);
    return v;
}

function LayerControl({map, scaleUnit, onScaleUnitChange, visibilityRef}) {
    const [visibility, setVisibility] = useState(() => {
        const v = getInitialVisibility();
        if (visibilityRef) visibilityRef.current = v;
        return v;
    });
    const [collapsed, setCollapsed] = useState(true);

    const toggleGroup = useCallback((groupName, checked) => {
        if (!map) return;
        const prefixes = LAYER_GROUPS[groupName];
        const allMapLayers = map.getStyle()?.layers || [];
        for (const layer of allMapLayers) {
            // Match both plain IDs and prefixed IDs (e.g., "water" and "file.pmtiles:water").
            const baseId = layer.id.includes(":") ? layer.id.split(":").slice(1).join(":") : layer.id;
            if (prefixes.some(p => baseId.includes(p))) {
                map.setLayoutProperty(layer.id, "visibility", checked ? "visible" : "none");
            }
        }
        setVisibility(prev => {
            const next = {...prev, [groupName]: checked};
            if (visibilityRef) visibilityRef.current = next;
            try { localStorage.setItem(STORAGE_KEY_LAYERS, JSON.stringify(next)); } catch (e) { /* ignore */ }
            return next;
        });
    }, [map, visibilityRef]);

    const panelStyle = {
        position: "absolute",
        top: 10,
        left: 10,
        zIndex: 1000,
        background: "white",
        borderRadius: 8,
        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
        maxHeight: "calc(100vh - 120px)",
        overflowY: "auto",
        minWidth: 200,
        fontSize: 13,
    };

    return <div style={panelStyle}>
        <div
            style={{
                padding: "8px 12px", cursor: "pointer", fontWeight: 600,
                display: "flex", justifyContent: "space-between", alignItems: "center",
                borderBottom: collapsed ? "none" : "1px solid #eee", userSelect: "none",
            }}
            onClick={() => setCollapsed(c => !c)}
        >
            <span>Layers</span>
            <Icon name={collapsed ? "chevron right" : "chevron down"} size="small"/>
        </div>
        {!collapsed && <div style={{padding: "4px 12px 8px"}}>
            {Object.keys(LAYER_GROUPS).map(name =>
                <div key={name} style={{padding: "2px 0"}}>
                    <Checkbox
                        label={name}
                        checked={visibility[name]}
                        onChange={(e, {checked}) => toggleGroup(name, checked)}
                    />
                </div>
            )}
            <div style={{borderTop: "1px solid #eee", marginTop: 6, paddingTop: 6}}>
                <Checkbox
                    toggle
                    label={scaleUnit === "imperial" ? "Imperial" : "Metric"}
                    checked={scaleUnit === "imperial"}
                    onChange={(e, {checked}) => onScaleUnitChange(checked ? "imperial" : "metric")}
                />
            </div>
        </div>}
    </div>;
}

const PIN_COLORS = ["red", "blue", "green", "yellow", "orange", "purple"];

function AddPinDialog({lat, lon, onSubmit, onCancel}) {
    const [label, setLabel] = useState("");
    const [color, setColor] = useState("red");

    return <div style={{
        position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
        zIndex: 1002, background: "white", borderRadius: 8, boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
        padding: 16, minWidth: 250,
    }}>
        <div style={{fontWeight: 600, marginBottom: 8}}>Add Pin</div>
        <div style={{fontSize: 12, color: "#666", marginBottom: 8}}>{lat.toFixed(4)}, {lon.toFixed(4)}</div>
        <input
            type="text"
            placeholder="Label"
            value={label}
            onChange={e => setLabel(e.target.value)}
            autoFocus
            onKeyDown={e => e.key === "Enter" && label.trim() && onSubmit(label.trim(), color)}
            style={{width: "100%", padding: "6px 8px", marginBottom: 8, border: "1px solid #ccc", borderRadius: 4}}
        />
        <div style={{display: "flex", gap: 6, marginBottom: 12}}>
            {PIN_COLORS.map(c =>
                <div
                    key={c}
                    onClick={() => setColor(c)}
                    style={{
                        width: 24, height: 24, borderRadius: "50%", background: c, cursor: "pointer",
                        border: color === c ? "3px solid #333" : "2px solid #ccc",
                    }}
                />
            )}
        </div>
        <div style={{display: "flex", gap: 8, justifyContent: "flex-end"}}>
            <button onClick={onCancel} style={{padding: "4px 12px", cursor: "pointer"}}>Cancel</button>
            <button
                onClick={() => label.trim() && onSubmit(label.trim(), color)}
                disabled={!label.trim()}
                style={{padding: "4px 12px", cursor: "pointer", background: "#6435c9", color: "white", border: "none", borderRadius: 4}}
            >
                Add
            </button>
        </div>
    </div>;
}

export default function MapViewer() {
    const mapContainer = useRef(null);
    const mapRef = useRef(null);
    const scaleControlRef = useRef(null);
    const activeFilesRef = useRef([]);
    const hasTerrainRef = useRef(false);
    const layerVisibilityRef = useRef(null);
    const [mapReady, setMapReady] = useState(false);
    const [error, setError] = useState(null);
    const [contextMenu, setContextMenu] = useState(null);
    const [addingPin, setAddingPin] = useState(null); // {lat, lon} when pin dialog is open
    const markersRef = useRef([]);
    const pinsVisibleRef = useRef(true);
    const [scaleUnit, setScaleUnit] = useState(() => {
        try { return localStorage.getItem(STORAGE_KEY_SCALE) || "metric"; } catch (e) { return "metric"; }
    });
    const [searchParams, setSearchParams] = useSearchParams();
    const {theme} = useContext(ThemeContext);

    // Parse initial coordinates from URL.
    const initialLat = parseFloat(searchParams.get("lat")) || 0;
    const initialLon = parseFloat(searchParams.get("lon")) || 0;
    const initialZoom = parseFloat(searchParams.get("z")) || 2;

    useEffect(() => {
        if (!mapContainer.current) return;

        let map;
        let destroyed = false;

        const init = async () => {
            const mapSources = [];

            // Fetch user's PMTiles files first to determine what base layer is needed.
            let hasTerrain = false;
            let terrainFileName = null;
            let planetFile = null;
            try {
                const data = await getMapFiles();
                if (data?.files) {
                    const regionFiles = [];
                    for (const f of data.files) {
                        if (f.name.startsWith(TERRAIN_PREFIX) && f.name.endsWith('.pmtiles')) {
                            hasTerrain = true;
                            terrainFileName = f.name;
                        } else if (isPlanetFile(f.name)) {
                            if (!planetFile || f.size > planetFile.size) {
                                planetFile = f;
                            }
                        } else {
                            regionFiles.push(f);
                        }
                    }

                    if (planetFile) {
                        // Planet covers everything — sole vector source, no overview needed.
                        mapSources.push({name: planetFile.name, url: `pmtiles:///media/map/${planetFile.name}`});
                    } else {
                        // Use regional extracts.
                        for (const f of regionFiles) {
                            mapSources.push({name: f.name, url: `pmtiles:///media/map/${f.name}`});
                        }
                        // Add planet overview blob as low-zoom base layer (if available).
                        try {
                            const resp = await fetch(MAP_OVERVIEW_URL, {method: "HEAD"});
                            if (resp.ok) {
                                mapSources.unshift({name: "map-overview", url: `pmtiles://${MAP_OVERVIEW_URL}`});
                            }
                        } catch (e) {
                            console.debug("Planet overview not available:", e);
                        }
                    }
                }
            } catch (e) {
                console.error("Failed to fetch map files:", e);
            }

            if (destroyed) return;
            activeFilesRef.current = mapSources;
            hasTerrainRef.current = hasTerrain;

            // Initialize contour source if terrain data is available.
            if (hasTerrain) {
                initContourSource(terrainFileName);
            }

            try {
                map = new maplibregl.Map({
                    container: mapContainer.current,
                    style: buildStyle(mapSources, theme, hasTerrain, scaleUnit),
                    center: [initialLon, initialLat],
                    zoom: initialZoom,
                    attributionControl: true,
                    preserveDrawingBuffer: true,
                });

                map.addControl(new maplibregl.NavigationControl(), "top-right");
                map.addControl(new maplibregl.FullscreenControl(), "top-right");
                const sc = new maplibregl.ScaleControl({maxWidth: 200, unit: scaleUnit});
                map.addControl(sc, "bottom-left");
                scaleControlRef.current = sc;
                map.addControl(new maplibregl.GeolocateControl({
                    positionOptions: {enableHighAccuracy: true},
                    trackUserLocation: true,
                    showUserHeading: true,
                    showAccuracyCircle: true,
                }), "top-right");

                // Pin toggle button.
                const pinToggle = document.createElement("button");
                pinToggle.type = "button";
                pinToggle.title = "Toggle pins";
                pinToggle.textContent = "📍";
                pinToggle.style.cssText = "font-size:18px;width:29px;height:29px;border:none;cursor:pointer;background:white;border-radius:4px;display:flex;align-items:center;justify-content:center;";
                pinToggle.addEventListener("click", () => {
                    pinsVisibleRef.current = !pinsVisibleRef.current;
                    const display = pinsVisibleRef.current ? "" : "none";
                    pinToggle.style.opacity = pinsVisibleRef.current ? "1" : "0.5";
                    for (const m of markersRef.current) {
                        m.getElement().style.display = display;
                    }
                });
                const pinControl = {
                    onAdd: () => {
                        const container = document.createElement("div");
                        container.className = "maplibregl-ctrl maplibregl-ctrl-group";
                        container.appendChild(pinToggle);
                        return container;
                    },
                    onRemove: () => {},
                };
                map.addControl(pinControl, "top-right");

                // Right-click context menu (desktop).
                map.on("contextmenu", (e) => {
                    if (destroyed) return;
                    setContextMenu({
                        x: e.point.x,
                        y: e.point.y,
                        lat: e.lngLat.lat,
                        lon: e.lngLat.lng,
                    });
                });
                map.on("click", () => setContextMenu(null));
                map.on("movestart", () => setContextMenu(null));

                // Long-press context menu (mobile).
                let longPressTimer = null;
                let touchStartPos = null;
                const canvas = map.getCanvas();
                canvas.addEventListener("touchstart", (e) => {
                    if (e.touches.length !== 1) return;
                    touchStartPos = {x: e.touches[0].clientX, y: e.touches[0].clientY};
                    longPressTimer = setTimeout(() => {
                        const rect = canvas.getBoundingClientRect();
                        const point = {x: touchStartPos.x - rect.left, y: touchStartPos.y - rect.top};
                        const lngLat = map.unproject(point);
                        setContextMenu({x: point.x, y: point.y, lat: lngLat.lat, lon: lngLat.lng});
                    }, 500);
                }, {passive: true});
                canvas.addEventListener("touchmove", (e) => {
                    if (longPressTimer && touchStartPos) {
                        const dx = e.touches[0].clientX - touchStartPos.x;
                        const dy = e.touches[0].clientY - touchStartPos.y;
                        if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
                            clearTimeout(longPressTimer);
                            longPressTimer = null;
                        }
                    }
                });
                canvas.addEventListener("touchend", () => {
                    clearTimeout(longPressTimer);
                    longPressTimer = null;
                });

                // Update URL on pan/zoom (only while mounted).
                map.on("moveend", () => {
                    if (destroyed) return;
                    const center = map.getCenter();
                    const zoom = map.getZoom();
                    window.history.replaceState(null, '',
                        `${window.location.pathname}?lat=${center.lat.toFixed(4)}&lon=${center.lng.toFixed(4)}&z=${zoom.toFixed(1)}`
                    );
                });

                map.on("load", () => {
                    if (!destroyed) {
                        mapRef.current = map;
                        // Apply saved layer visibility on initial load.
                        const savedVis = getInitialVisibility();
                        const allMapLayers = map.getStyle()?.layers || [];
                        for (const [groupName, visible] of Object.entries(savedVis)) {
                            const prefixes = LAYER_GROUPS[groupName];
                            if (!prefixes) continue;
                            for (const layer of allMapLayers) {
                                const baseId = layer.id.includes(":") ? layer.id.split(":").slice(1).join(":") : layer.id;
                                if (prefixes.some(p => baseId.includes(p))) {
                                    map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
                                }
                            }
                        }
                        setMapReady(true);
                    }
                });
            } catch (e) {
                console.error("MapLibre failed to initialize:", e);
                if (!destroyed) setError(e.message);
            }
        };

        init();

        return () => {
            destroyed = true;
            if (map) {
                map.remove();
            }
            mapRef.current = null;
            setMapReady(false);
            // Clean up map params from URL so they don't leak to other pages.
            const url = new URL(window.location);
            url.searchParams.delete("lat");
            url.searchParams.delete("lon");
            url.searchParams.delete("z");
            window.history.replaceState(null, '', url.pathname + url.search);
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Rebuild style when theme changes.
    useEffect(() => {
        const map = mapRef.current;
        if (!map || !mapReady) return;

        const center = map.getCenter();
        const zoom = map.getZoom();
        map.setStyle(buildStyle(activeFilesRef.current, theme, hasTerrainRef.current, scaleUnit));
        map.once("style.load", () => {
            map.setCenter(center);
            map.setZoom(zoom);
            // Re-apply layer visibility state after style rebuild.
            const vis = layerVisibilityRef.current;
            if (vis) {
                const allMapLayers = map.getStyle()?.layers || [];
                for (const [groupName, visible] of Object.entries(vis)) {
                    const prefixes = LAYER_GROUPS[groupName];
                    if (!prefixes) continue;
                    for (const layer of allMapLayers) {
                        const baseId = layer.id.includes(":") ? layer.id.split(":").slice(1).join(":") : layer.id;
                        if (prefixes.some(p => baseId.includes(p))) {
                            map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
                        }
                    }
                }
            }
        });
    }, [theme, mapReady, scaleUnit]);

    const handleScaleUnitChange = useCallback((unit) => {
        const map = mapRef.current;
        const sc = scaleControlRef.current;
        if (map && sc) {
            map.removeControl(sc);
            const newSc = new maplibregl.ScaleControl({maxWidth: 200, unit});
            map.addControl(newSc, "bottom-left");
            scaleControlRef.current = newSc;
        }
        try { localStorage.setItem(STORAGE_KEY_SCALE, unit); } catch (e) { /* ignore */ }
        setScaleUnit(unit);
    }, []);

    const handleCopyCoords = useCallback(() => {
        if (!contextMenu) return;
        // Match decimal precision to current zoom level so pasting into search doesn't over-zoom.
        const map = mapRef.current;
        const zoom = map ? map.getZoom() : 10;
        const decimals = zoom < 4 ? 1 : zoom < 8 ? 2 : zoom < 12 ? 3 : 4;
        const text = `${contextMenu.lat.toFixed(decimals)}, ${contextMenu.lon.toFixed(decimals)}`;
        navigator.clipboard.writeText(text).catch(() => {
            window.prompt("Copy coordinates:", text);
        });
        setContextMenu(null);
    }, [contextMenu]);

    const handleExportPng = useCallback(() => {
        const map = mapRef.current;
        if (!map) return;
        setContextMenu(null);
        // Force a fresh render, then capture.
        map.once("render", function() {
            const c = map.getCenter();
            const z = map.getZoom();
            const filename = `wrolpi-map_${c.lat.toFixed(4)}_${c.lng.toFixed(4)}_z${z.toFixed(0)}.png`;
            map.getCanvas().toBlob(function(blob) {
                if (!blob) return;
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename;
                a.click();
                URL.revokeObjectURL(url);
            });
        });
        map.triggerRepaint();
    }, []);

    // --- Pins ---
    const loadPins = useCallback(async () => {
        const map = mapRef.current;
        if (!map) return;

        // Remove existing markers.
        for (const m of markersRef.current) m.remove();
        markersRef.current = [];

        const data = await getMapPins();
        if (!data?.pins) return;

        data.pins.forEach((pin, index) => {
            const el = document.createElement("div");
            el.style.width = "24px";
            el.style.height = "24px";
            el.style.borderRadius = "50% 50% 50% 0";
            el.style.background = pin.color || "red";
            el.style.border = "2px solid white";
            el.style.boxShadow = "0 1px 4px rgba(0,0,0,0.4)";
            el.style.transform = "rotate(-45deg)";
            el.style.cursor = "pointer";

            const popup = new maplibregl.Popup({offset: 15}).setHTML(
                `<div style="font-size:13px">` +
                `<strong>${pin.label || "Pin"}</strong><br/>` +
                `<small>${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}</small><br/>` +
                `<button onclick="window.__deleteMapPin(${pin.id})" ` +
                `style="margin-top:4px;padding:2px 8px;cursor:pointer;color:red;border:1px solid red;background:none;border-radius:3px;">` +
                `Delete</button></div>`
            );

            const marker = new maplibregl.Marker({element: el})
                .setLngLat([pin.lon, pin.lat])
                .setPopup(popup)
                .addTo(map);

            if (!pinsVisibleRef.current) {
                marker.getElement().style.display = "none";
            }
            markersRef.current.push(marker);
        });
    }, []);

    // Global callback for popup delete buttons.
    useEffect(() => {
        window.__deleteMapPin = async (pinId) => {
            await deleteMapPin(pinId);
            await loadPins();
        };
        return () => { delete window.__deleteMapPin; };
    }, [loadPins]);

    // Load pins when map is ready.
    useEffect(() => {
        if (mapReady) loadPins();
    }, [mapReady, loadPins]);

    const handleAddPin = useCallback(() => {
        if (!contextMenu) return;
        setAddingPin({lat: contextMenu.lat, lon: contextMenu.lon});
        setContextMenu(null);
    }, [contextMenu]);

    const handleSubmitPin = useCallback(async (label, color) => {
        if (!addingPin) return;
        const {lat, lon} = addingPin;
        setAddingPin(null);  // Prevent double-submit.
        await addMapPin(lat, lon, label, color);
        await loadPins();
    }, [addingPin, loadPins]);

    if (error) {
        return <Segment>
            <Header as="h3">Map failed to load</Header>
            <p>Your browser may not support WebGL. You can access the standalone map viewer
                at <a href={MAP_VIEWER_URI}>{MAP_VIEWER_URI}</a></p>
            <p>Error: {error}</p>
        </Segment>;
    }

    return <div ref={mapContainer} style={{position: "relative", width: "100%", height: "85vh"}}>
        {mapReady && <LayerControl map={mapRef.current} scaleUnit={scaleUnit} onScaleUnitChange={handleScaleUnitChange} visibilityRef={layerVisibilityRef}/>}
        {contextMenu && <div
            style={{
                position: "absolute",
                left: contextMenu.x,
                top: contextMenu.y,
                zIndex: 1001,
                background: "white",
                borderRadius: 6,
                boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                padding: "4px 0",
                fontSize: 13,
                minWidth: 180,
            }}
        >
            <div style={{padding: "6px 12px", color: "#666", fontSize: 12, borderBottom: "1px solid #eee"}}>
                {(() => {
                    const map = mapRef.current;
                    const zoom = map ? map.getZoom() : 10;
                    const d = zoom < 4 ? 1 : zoom < 8 ? 2 : zoom < 12 ? 3 : 4;
                    return `${contextMenu.lat.toFixed(d)}, ${contextMenu.lon.toFixed(d)}`;
                })()}
            </div>
            <div
                style={{padding: "8px 12px", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleCopyCoords}
            >
                Copy GPS coordinates
            </div>
            <div
                style={{padding: "8px 12px", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleExportPng}
            >
                Export as PNG
            </div>
            <div
                style={{padding: "8px 12px", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleAddPin}
            >
                Add Pin Here
            </div>
        </div>}
        {addingPin && <AddPinDialog
            lat={addingPin.lat}
            lon={addingPin.lon}
            onSubmit={handleSubmitPin}
            onCancel={() => setAddingPin(null)}
        />}
    </div>;
}
