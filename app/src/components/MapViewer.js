import React, {useCallback, useContext, useEffect, useRef, useState} from "react";
import {useNavigate, useSearchParams} from "react-router";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {Protocol} from "pmtiles";
import layers from "protomaps-themes-base";
import mlcontour from "@acalcutt/maplibre-contour-pmtiles";
import {
    addMapPin,
    deleteMapPin,
    exportMapPdf,
    getMapQuadName,
    getMapFiles,
    getMapPins,
    searchMap,
    updateMapTargetWeapon,
    setMapDefaultLocation,
} from "../api";
import {MAP_VIEWER_URI} from "./Vars";
import {readTileBounds, readVectorTile} from "./mapTiles";
import {
    lookStyle, PRINT_LOOK, PRINT_SWATCHES, printContours, printLayers, savedExportLook, savedPrintColors,
    saveExportLook, savePrintColors,
} from "./mapPrintStyle";
import {exportLegend} from "./mapExportLegend";
import {Button, Checkbox, Header, Icon, Panel, TextInput, Toggle} from "./ui";
import {SettingsContext, ThemeContext} from "../contexts/contexts";
import {mapFlavor, mapSprite} from "../themes/names";
import {poiPopupHtml} from "./mapPoiPopup";
import {solarCalculatorPath} from "./calculators/solar";
import {
    escapeHtml,
    addOverlaysToStyle,
    labelsOverGround,
    buildOverlayLayers,
    isOverlayEnabled,
    isOverlayLayerEnabled,
    isOverlayLayerId,
    isStyledOverlay,
    overlaySourceId,
    loadOverlayState,
    mediaUrl,
    overlayColor,
    overlayLabel,
    overlayPopupHtml,
    overlayToggleLayers,
    planMapFiles,
    pmtilesUrl,
    saveOverlayState,
    setAllOverlayLayersEnabled,
    setOverlayEnabled,
    setOverlayLayerEnabled,
} from "./mapOverlays";
import {addMissingOverlayIcon, loadOverlayStyles, OVERLAY_ICONS_SPRITE_ID} from "./mapOverlayStyle";
import MapQuadPicker, {QUAD_LAYER_PREFIX} from "./MapQuadPicker";
import FalloutPanel, {WeaponPicker} from "./FalloutPanel";
import {DEFAULT_WEAPON} from "../map-shared/fallout/targets.js";
import {contourInterval, contourThresholds, DEFAULT_TERRAIN_MAX_ZOOM, terrainMaxZoom} from "../map-shared/terrain.js";
import {quadAt} from "./mapQuads";
import {
    EXPORT_DPI,
    exportFileName,
    exportFrame,
    exportGroups,
    exportContours,
    exportSheet,
    exportTitle,
    maxCanvasSide,
    maxExportPixels,
    renderExport,
    sourcesOutside,
    saveBlob,
} from "./mapExport";

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
// How deep the terrain file goes: contours are drawn from as deep as it does.
let terrainZoom = DEFAULT_TERRAIN_MAX_ZOOM;
function initContourSource(file) {
    terrainUrl = mediaUrl(file.path);
    if (demSource) return;
    terrainZoom = terrainMaxZoom(file);
    demSource = new mlcontour.DemSource({
        url: `pmtiles://${window.location.origin}${terrainUrl}`,
        encoding: "terrarium",
        maxzoom: terrainZoom,
        worker: true,
    });
    demSource.setupMaplibre(maplibregl);
}

// sources: [{name, url}] where name is used as the MapLibre source ID and url is the pmtiles:// URL.
// hasTerrain: whether to include hillshade and contour layers.
// scaleUnit: "metric" or "imperial" — affects contour intervals and labels.
// `sprite` is deliberately separate from `flavor`: we ship two sprite sets (light, dark)
// and the monochrome themes draw a `black` basemap, which has no sprites of its own.
// overlays: the map files which are not a basemap; overlayState: which of them (and of their
// layers) the user turned on.  printColors: the colors a person chose for the printed map.
function buildStyle(sources, flavor = "light", hasTerrain = false, scaleUnit = "metric",
                    sprite = "light", overlays = [], overlayState = {}, printColors = {}) {
    const styleSources = {};
    // The contour lines of the printed map, in the colors a person chose for it.
    const contours = printContours(printColors);
    const allLayers = [];

    for (let i = 0; i < sources.length; i++) {
        const {name, url} = sources[i];
        styleSources[name] = {type: "vector", url};
        // The printed map is not a flavor a basemap has: it is the map's own (see mapPrintStyle.js).
        const fileLayers = flavor === PRINT_LOOK ? printLayers(name, printColors) : layers(name, flavor);
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

    // The labels of every basemap file are over the ground of every file.
    allLayers.splice(0, allLayers.length, ...labelsOverGround(allLayers));

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
            // [minor, major] contour intervals per zoom level, as fine as the terrain file can bear.
            thresholds: contourThresholds(isImperial, terrainZoom),
        });
        const elevUnit = isImperial ? "ft" : "m";
        styleSources["contours"] = {
            type: "vector",
            tiles: [contourUrl],
            maxzoom: terrainZoom,
        };

        allLayers.push(
            {
                id: "contour-lines",
                type: "line",
                source: "contours",
                "source-layer": "contours",
                filter: ["!=", ["get", "level"], 1],
                layout: {visibility: contourVis},
                paint: flavor === PRINT_LOOK
                    ? contours.minor : {"line-color": "rgba(150,100,50,0.3)", "line-width": 0.5},
            },
            {
                id: "contour-lines-major",
                type: "line",
                source: "contours",
                "source-layer": "contours",
                filter: ["==", ["get", "level"], 1],
                layout: {visibility: contourVis},
                paint: flavor === PRINT_LOOK
                    ? contours.major : {"line-color": "rgba(150,100,50,0.5)", "line-width": 1},
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
                    // A font the map has glyphs for; MapLibre's default is not one of them.
                    "text-font": ["Noto Sans Regular"],
                    "text-size": 10,
                },
                paint: {
                    "text-color": flavor === "light" ? "rgba(150,100,50,0.8)" : "rgba(210,180,140,0.9)",
                    "text-halo-color": flavor === "light" ? "rgba(255,255,255,0.8)" : "rgba(0,0,0,0.8)",
                    "text-halo-width": 1,
                    ...(flavor === PRINT_LOOK ? contours.label : {}),
                },
            },
        );
    }

    addOverlaysToStyle(styleSources, allLayers, overlays, overlayState);

    // An overlay drawn with a style of its own names icons: the map's overlay icons, a second
    // sprite beside the basemap's.  It is only asked for when there is such an overlay.
    const basemapSprite = `${window.location.origin}/map-assets/sprites/${sprite}`;
    const overlayIcons = {
        id: OVERLAY_ICONS_SPRITE_ID,
        url: `${window.location.origin}/map-assets/sprites/${OVERLAY_ICONS_SPRITE_ID}`,
    };
    const styled = overlays.some(isStyledOverlay);

    return {
        version: 8,
        glyphs: "/map-assets/fonts/{fontstack}/{range}.pbf",
        sprite: styled ? [{id: "default", url: basemapSprite}, overlayIcons] : basemapSprite,
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

// Show or hide the basemap layers of a layer group.  Layer IDs are plain ("water") or prefixed
// with their source ("oregon.pmtiles:water"); an overlay's layers belong to no group, whatever
// they are named.
function setGroupVisibility(map, groupName, visible) {
    const prefixes = LAYER_GROUPS[groupName];
    if (!prefixes) return;
    for (const layer of map.getStyle()?.layers || []) {
        if (isOverlayLayerId(layer.id)) continue;
        const baseId = layer.id.includes(":") ? layer.id.split(":").slice(1).join(":") : layer.id;
        if (prefixes.some(p => baseId.includes(p))) {
            map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
        }
    }
}

function applyGroupVisibility(map, visibility) {
    for (const [groupName, visible] of Object.entries(visibility || {})) {
        setGroupVisibility(map, groupName, visible);
    }
}

// One overlay file in the layer control: a checkbox for the file, and (for a vector file) one per
// layer behind a chevron.
function OverlayControl({file, label, state, onToggleFile, onToggleLayer, onToggleAllLayers}) {
    const [expanded, setExpanded] = useState(false);
    const enabled = isOverlayEnabled(state, file);
    const vectorLayers = overlayToggleLayers(file);
    const styled = isStyledOverlay(file);
    const zooms = Number.isFinite(file.min_zoom) && Number.isFinite(file.max_zoom)
        ? `z${file.min_zoom}–${file.max_zoom}` : null;
    const title = [file.description, file.path].filter(Boolean).join("\n");
    const linkStyle = {cursor: "pointer", textDecoration: "underline", color: "var(--muted)"};

    return <div style={{padding: "0.125rem 0"}}>
        <div style={{display: "flex", alignItems: "center", gap: "0.375rem"}} title={title}>
            <Checkbox
                label={label}
                checked={enabled}
                onChange={(e) => onToggleFile(file, e.currentTarget.checked)}
            />
            {zooms && <span style={{color: "var(--muted)", fontSize: "0.6875rem"}}>{zooms}</span>}
            {vectorLayers.length > 0 && <span
                role="button"
                aria-label={`${expanded ? "Hide" : "Show"} layers of ${label}`}
                aria-expanded={expanded}
                style={{cursor: "pointer", marginLeft: "auto"}}
                onClick={() => setExpanded(x => !x)}
            >
                <Icon name={expanded ? "chevron down" : "chevron right"} size="small"/>
            </span>}
        </div>
        {expanded && <div style={{padding: "0.125rem 0 0.25rem 1.5rem"}}>
            <div style={{fontSize: "0.6875rem", display: "flex", gap: "0.5rem", padding: "0.125rem 0"}}>
                <span role="button" style={linkStyle} onClick={() => onToggleAllLayers(file, true)}>All</span>
                <span role="button" style={linkStyle} onClick={() => onToggleAllLayers(file, false)}>None</span>
            </div>
            {file.styleSkipped > 0 && <div style={{fontSize: "0.6875rem", color: "var(--muted)"}}>
                {file.styleSkipped} style {file.styleSkipped === 1 ? "layer" : "layers"} skipped
            </div>}
            {vectorLayers.map(layer =>
                <div key={layer.id} style={{padding: "0.0625rem 0"}} title={layer.description || undefined}>
                    <Checkbox
                        size="xs"
                        label={<span style={{display: "inline-flex", alignItems: "center", gap: "0.375rem"}}>
                            {/* A generic layer is drawn in one color; a styled one however its style says. */}
                            {!styled && <span style={{
                                width: "0.625rem", height: "0.625rem", flex: "none",
                                background: overlayColor(layer.id), border: "1px solid var(--border)",
                            }}/>}
                            {layer.id}
                        </span>}
                        checked={isOverlayLayerEnabled(state, file, layer.id)}
                        disabled={!enabled}
                        onChange={(e) => onToggleLayer(file, layer.id, e.currentTarget.checked)}
                    />
                </div>
            )}
        </div>}
    </div>;
}

// The colors of the printed map which are of a group of the layer control, each to be chosen.
// colors: what was chosen ({swatch id: "#rrggbb"}); onChange(colors): told what is chosen now.
function PrintSwatches({group, colors, onChange}) {
    const swatches = PRINT_SWATCHES.filter(swatch => swatch.group === group);
    if (!swatches.length) return null;
    return <span style={{display: "inline-flex", gap: "0.25rem", marginLeft: "auto"}}>
        {swatches.map(swatch => <input
            key={swatch.id}
            type="color"
            title={`${swatch.label}: color when printed`}
            aria-label={`${swatch.label}: color when printed`}
            value={colors[swatch.id] || swatch.color}
            onChange={e => onChange({...colors, [swatch.id]: e.target.value})}
            style={{width: "1.25rem", height: "1.25rem", padding: 0, border: "1px solid var(--border)",
                background: "none", cursor: "pointer"}}
        />)}
    </span>;
}

function LayerControl({
                          map, scaleUnit, onScaleUnitChange, visibilityRef,
                          overlays = [], overlayState = {}, onToggleOverlay, onToggleOverlayLayer,
                          onToggleAllOverlayLayers, printColors = null, onPrintColors = null,
                      }) {
    const [visibility, setVisibility] = useState(() => {
        const v = getInitialVisibility();
        if (visibilityRef) visibilityRef.current = v;
        return v;
    });
    const [collapsed, setCollapsed] = useState(true);
    const [isMobile, setIsMobile] = useState(
        () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches
    );

    useEffect(() => {
        if (typeof window === "undefined") return;
        const mq = window.matchMedia("(max-width: 768px)");
        const handler = (e) => setIsMobile(e.matches);
        mq.addEventListener ? mq.addEventListener("change", handler) : mq.addListener(handler);
        return () => {
            mq.removeEventListener ? mq.removeEventListener("change", handler) : mq.removeListener(handler);
        };
    }, []);

    const iconOnly = isMobile && collapsed;

    const toggleGroup = useCallback((groupName, checked) => {
        if (!map) return;
        setGroupVisibility(map, groupName, checked);
        setVisibility(prev => {
            const next = {...prev, [groupName]: checked};
            if (visibilityRef) visibilityRef.current = next;
            try { localStorage.setItem(STORAGE_KEY_LAYERS, JSON.stringify(next)); } catch (e) { /* ignore */ }
            return next;
        });
    }, [map, visibilityRef]);

    // A floating control drawn over the map canvas: it is part of the app's interface,
    // not map data, so it is never filtered — it stays plain, token-colored chrome in
    // every theme, same as the nav bar.
    const panelStyle = {
        position: "absolute",
        top: "0.625rem",
        left: "0.625rem",
        zIndex: 1000,
        background: "var(--panel)",
        border: "1px solid var(--border)",
        color: "var(--text)",
        maxHeight: "calc(100vh - 7.5rem)",
        overflowY: "auto",
        minWidth: iconOnly ? 0 : "12.5rem",
        fontSize: '0.8125rem',
    };

    const headerStyle = iconOnly
        ? {
            padding: 0, cursor: "pointer", userSelect: "none",
            display: "flex", alignItems: "center", justifyContent: "center",
            width: "2.5rem", height: "2.5rem",
        }
        : {
            padding: "0.5rem 0.75rem", cursor: "pointer", fontWeight: 600,
            display: "flex", justifyContent: "space-between", alignItems: "center",
            borderBottom: collapsed ? "none" : "1px solid var(--border)", userSelect: "none",
        };

    return <div style={panelStyle}>
        <div
            style={headerStyle}
            onClick={() => setCollapsed(c => !c)}
            title="Layers"
            aria-label="Layers"
        >
            {iconOnly
                ? <Icon name="map outline" size="large" style={{margin: 0}}/>
                : <>
                    <span>Layers</span>
                    <Icon name={collapsed ? "chevron right" : "chevron down"} size="small"/>
                </>}
        </div>
        {!collapsed && <div style={{padding: "0.25rem 0.75rem 0.5rem"}}>
            {Object.keys(LAYER_GROUPS).map(name =>
                <div key={name} style={{padding: "0.125rem 0", display: "flex", alignItems: "center", gap: "0.375rem"}}>
                    <Checkbox
                        label={name}
                        checked={visibility[name]}
                        onChange={(e) => toggleGroup(name, e.currentTarget.checked)}
                    />
                    {printColors && onPrintColors && <PrintSwatches
                        group={name} colors={printColors} onChange={onPrintColors}/>}
                </div>
            )}
            {printColors && onPrintColors && <div style={{paddingTop: "0.25rem", color: "var(--muted)"}}>
                Colors are of the printed map.{" "}
                {Object.keys(printColors).length > 0 && <button
                    type="button"
                    style={{
                        cursor: "pointer", textDecoration: "underline", background: "none", border: "none",
                        padding: 0, font: "inherit", color: "inherit",
                    }}
                    onClick={() => onPrintColors({})}
                >Reset colors</button>}
            </div>}
            {overlays.length > 0 &&
                <div style={{borderTop: "1px solid var(--border)", marginTop: "0.375rem", paddingTop: "0.375rem"}}>
                    <div style={{fontWeight: 600, paddingBottom: "0.125rem"}}>Overlays</div>
                    {overlays.map(file => <OverlayControl
                        key={file.map_path}
                        file={file}
                        label={overlayLabel(file, overlays)}
                        state={overlayState}
                        onToggleFile={onToggleOverlay}
                        onToggleLayer={onToggleOverlayLayer}
                        onToggleAllLayers={onToggleAllOverlayLayers}
                    />)}
                </div>}
            <div style={{borderTop: "1px solid var(--border)", marginTop: "0.375rem", paddingTop: "0.375rem"}}>
                <Toggle
                    label={scaleUnit === "imperial" ? "Imperial" : "Metric"}
                    checked={scaleUnit === "imperial"}
                    onChange={(e) => onScaleUnitChange(e.currentTarget.checked ? "imperial" : "metric")}
                />
            </div>
        </div>}
    </div>;
}

const PIN_COLORS = ["red", "blue", "green", "yellow", "orange", "purple"];

function AddPinDialog({lat, lon, target = false, weapon: initialWeapon = null, onSubmit, onCancel}) {
    const [label, setLabel] = useState("");
    const [color, setColor] = useState("red");
    // A target's weapon, kept with it.
    const [weapon, setWeapon] = useState(initialWeapon || {weapon: DEFAULT_WEAPON});
    const submit = () => label.trim() && onSubmit(label.trim(), color, target ? weapon : null);

    // A floating dialog over the canvas — page chrome, not map data, so it is never
    // filtered and keeps flat, bordered surfaces like the rest of the app (no shadow).
    return <div style={{
        position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
        zIndex: 1002, background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text)",
        padding: "1rem", minWidth: "15.625rem",
    }}>
        <div style={{fontWeight: 600, marginBottom: "0.5rem"}}>{target ? "Add Target" : "Add Pin"}</div>
        {target && <div style={{fontSize: '0.75rem', color: "var(--muted)", marginBottom: "0.5rem"}}>
            A likely detonation site, shown in nuclear mode.
        </div>}
        <div style={{fontSize: '0.75rem', color: "var(--muted)", marginBottom: "0.5rem"}}>{lat.toFixed(4)}, {lon.toFixed(4)}</div>
        <TextInput
            placeholder="Label"
            value={label}
            onChange={e => setLabel(e.target.value)}
            autoFocus
            onKeyDown={e => e.key === "Enter" && submit()}
            style={{marginBottom: "0.5rem"}}
        />
        {target && <div style={{marginBottom: "0.5rem"}}>
            <WeaponPicker label="Weapon" value={weapon} onChange={setWeapon}/>
        </div>}
        <div style={{display: "flex", gap: "0.375rem", marginBottom: "0.75rem"}}>
            {PIN_COLORS.map(c =>
                <div
                    key={c}
                    onClick={() => setColor(c)}
                    style={{
                        width: "1.5rem", height: "1.5rem", borderRadius: "50%", background: c, cursor: "pointer",
                        border: color === c ? "3px solid var(--text)" : "2px solid var(--border)",
                    }}
                />
            )}
        </div>
        <div style={{display: "flex", gap: "0.5rem", justifyContent: "flex-end"}}>
            <Button role='cancel' size='sm' onClick={onCancel}>Cancel</Button>
            <Button
                role='primary'
                size='sm'
                onClick={submit}
                disabled={!label.trim()}
            >
                Add
            </Button>
        </div>
    </div>;
}

// Coordinate regex: "45.5, -122.6" or "45.5 -122.6"
const COORD_REGEX = /^\s*(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)\s*$/;

function MapSearch({map}) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [showResults, setShowResults] = useState(false);
    const [searchMarker, setSearchMarker] = useState(null);
    const debounceRef = useRef(null);
    const containerRef = useRef(null);

    // Close results when clicking outside.
    useEffect(() => {
        const handler = (e) => {
            if (containerRef.current && !containerRef.current.contains(e.target)) {
                setShowResults(false);
            }
        };
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, []);

    const doSearch = useCallback((q) => {
        if (!q || q.length < 2) {
            setResults([]);
            setShowResults(false);
            return;
        }

        // Check for coordinate input first.
        const coordMatch = q.match(COORD_REGEX);
        if (coordMatch) {
            const lat = parseFloat(coordMatch[1]);
            const lon = parseFloat(coordMatch[2]);
            if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                setResults([{name: `${lat}, ${lon}`, kind: "coordinates", lat, lon, min_zoom: 0, source: "input"}]);
                setShowResults(true);
                return;
            }
        }

        // Get current map center for proximity bias.
        let lat = null, lon = null;
        if (map) {
            const center = map.getCenter();
            lat = center.lat;
            lon = center.lng;
        }

        // A failed search (undefined) shows no dropdown, same as finding nothing: this is an
        // as-you-type suggestion list, not a results page.
        searchMap(q, 8, 0, lat, lon).then(data => {
            const found = data?.results || [];
            setResults(found);
            setShowResults(found.length > 0);
        }).catch(e => console.error(e));
    }, [map]);

    const handleInput = useCallback((e) => {
        const q = e.target.value;
        setQuery(q);
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => doSearch(q), 300);
    }, [doSearch]);

    const handleSelect = useCallback((result) => {
        if (!map) return;

        // Remove old search marker.
        if (searchMarker) {
            searchMarker.remove();
        }

        const zoom = result.kind === "coordinates" ? 14 : Math.max(map.getZoom(), 12);
        map.flyTo({center: [result.lon, result.lat], zoom});

        const marker = new maplibregl.Marker({color: "#6435c9"})
            .setLngLat([result.lon, result.lat])
            .setPopup(new maplibregl.Popup({offset: 25}).setText(result.name))
            .addTo(map);
        marker.togglePopup();
        setSearchMarker(marker);

        setShowResults(false);
        setQuery(result.name);
    }, [map, searchMarker]);

    const handleKeyDown = useCallback((e) => {
        if (e.key === "Escape") {
            setShowResults(false);
            e.target.blur();
        }
    }, []);

    const formatPopulation = (pop) => {
        if (!pop) return "";
        if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
        if (pop >= 1_000) return `${(pop / 1_000).toFixed(0)}K`;
        return `${pop}`;
    };

    const resultSubtext = (r) => {
        if (r.kind === "coordinates") return "";
        const parts = [];
        if (r.region) parts.push(r.region);
        const detail = r.kind_detail || r.kind || "";
        if (detail && !r.region) parts.push(detail.replace(/_/g, " "));
        const pop = formatPopulation(r.population);
        if (pop) parts.push(`pop. ${pop}`);
        return parts.join(" \u00b7 ");
    };

    // Floating search chrome over the canvas — page interface, not map data, so it is
    // never filtered.  Flat surfaces: bordered, no box-shadow, token colors only.
    return <div ref={containerRef} style={{
        position: "absolute", top: "0.625rem", left: "50%", transform: "translateX(-50%)",
        zIndex: 5, width: "20rem", maxWidth: "calc(100% - 100px)",
    }}>
        <input
            type="text"
            placeholder="Search places..."
            value={query}
            onChange={handleInput}
            onFocus={() => results.length > 0 && setShowResults(true)}
            onKeyDown={handleKeyDown}
            style={{
                width: "100%", padding: "0.5rem 0.75rem", border: "1px solid var(--border)",
                fontSize: '0.875rem', background: "var(--panel)", color: "var(--text)",
            }}
        />
        {showResults && results.length > 0 && <div style={{
            background: "var(--panel)", border: "1px solid var(--border)", borderTop: "none",
            maxHeight: "18.75rem", overflowY: "auto",
        }}>
            {results.map((r, i) => <div
                key={i}
                onClick={() => handleSelect(r)}
                onMouseEnter={e => e.currentTarget.style.background = "var(--head)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", borderBottom: "1px solid var(--border)"}}
            >
                <div style={{fontWeight: 500}}>{r.name}</div>
                {resultSubtext(r) && <div style={{fontSize: '0.6875rem', color: "var(--muted)"}}>{resultSubtext(r)}</div>}
            </div>)}
        </div>}
    </div>;
}

export default function MapViewer() {
    const mapContainer = useRef(null);
    const mapRef = useRef(null);
    const scaleControlRef = useRef(null);
    const activeFilesRef = useRef([]);
    const hasTerrainRef = useRef(false);
    const layerVisibilityRef = useRef(null);
    // The overlay files, and what the user chose to see of them.  The ref is what the map's own
    // callbacks and a style rebuild read.
    const [overlays, setOverlays] = useState([]);
    const overlaysRef = useRef([]);
    const [overlayState, setOverlayState] = useState(loadOverlayState);
    const overlayStateRef = useRef(overlayState);
    const [mapReady, setMapReady] = useState(false);
    const [error, setError] = useState(null);
    const [contextMenu, setContextMenu] = useState(null);
    const navigate = useNavigate();
    const [addingPin, setAddingPin] = useState(null); // {lat, lon, kind} when pin dialog is open
    // Nuclear mode: targets (likely detonation sites) are shown, pins added are targets, and fallout
    // can be simulated.
    const [nuclear, setNuclear] = useState(false);
    const nuclearRef = useRef(false);
    const nuclearButtonRef = useRef(null);
    // The fallout view (nuclear mode): open or not, and a burst the user is trying out ({lat, lon}).
    const [falloutOpen, setFalloutOpen] = useState(false);
    const [falloutBurst, setFalloutBurst] = useState(null);
    const [pins, setPins] = useState([]);
    const markersRef = useRef([]);
    const pinsVisibleRef = useRef(true);
    // Choosing a quadrangle to export: null, or {quad} (the quadrangle to start with, if any).  While
    // choosing, a click on the map chooses, so the ref tells the map's own click handlers to stand by.
    const [pickingQuad, setPickingQuad] = useState(null);
    const pickingQuadRef = useRef(false);
    // The look a map is exported in.  While a quadrangle is chosen the map is shown in it: what is
    // seen is what the PDF will be.
    const [exportLook, setExportLook] = useState(savedExportLook);
    const handleExportLook = useCallback(look => {
        setExportLook(look);
        saveExportLook(look);
    }, []);
    // The colors a person chose for the printed map: {swatch id: "#rrggbb"}.
    const [printColors, setPrintColors] = useState(savedPrintColors);
    const handlePrintColors = useCallback(colors => setPrintColors(savePrintColors(colors)), []);
    // Exporting the chosen quadrangle: how far along it is, or why it could not be done.
    const [exportStatus, setExportStatus] = useState(null);
    // Whether the person exporting has asked for the export which is being made to stop.
    const exportCancelledRef = useRef(false);
    // Stops the request an export is in the middle of.
    const exportAbortRef = useRef(null);
    // Whether a map is being exported, for what is asked outside of React (the map's own buttons).
    const exportingRef = useRef(false);
    const [exportError, setExportError] = useState(null);
    const [scaleUnit, setScaleUnit] = useState(() => {
        try { return localStorage.getItem(STORAGE_KEY_SCALE) || "metric"; } catch (e) { return "metric"; }
    });
    const [searchParams, setSearchParams] = useSearchParams();
    const {theme} = useContext(ThemeContext);
    const {flavor: lookFlavor, sprite: lookSprite} = lookStyle(pickingQuad ? exportLook : null);
    // The map is shown as it is printed: its colors can be chosen.
    const printing = lookFlavor === PRINT_LOOK;
    const {settings, fetchSettings} = useContext(SettingsContext);

    // Use URL params if provided, otherwise fall back to saved default location, then 0,0,z2.
    const hasUrlParams = searchParams.has("lat") || searchParams.has("lon") || searchParams.has("z");
    const defaultLoc = settings?.map_default_location;
    const initialLat = hasUrlParams
        ? (parseFloat(searchParams.get("lat")) || 0)
        : (parseFloat(defaultLoc?.lat) || 0);
    const initialLon = hasUrlParams
        ? (parseFloat(searchParams.get("lon")) || 0)
        : (parseFloat(defaultLoc?.lon) || 0);
    const initialZoom = hasUrlParams
        ? (parseFloat(searchParams.get("z")) || 2)
        : (parseFloat(defaultLoc?.zoom) || 2);

    useEffect(() => {
        if (!mapContainer.current) return;

        let map;
        let destroyed = false;

        const init = async () => {
            const mapSources = [];

            // Fetch user's PMTiles files first to determine what base layer is needed.
            let hasTerrain = false;
            let terrainFile = null;
            let overlayFiles = [];
            try {
                const data = await getMapFiles();
                if (data?.files) {
                    const {planet, regions, terrain, overlays: foundOverlays} = planMapFiles(data.files);
                    // An overlay which came with a style is drawn with it.
                    overlayFiles = await loadOverlayStyles(foundOverlays);
                    if (terrain) {
                        hasTerrain = true;
                        terrainFile = terrain;
                    }

                    if (planet) {
                        // Planet covers everything — sole basemap source, no overview needed.
                        mapSources.push({name: planet.map_path, url: pmtilesUrl(planet.path)});
                    } else {
                        // Use regional extracts.
                        for (const f of regions) {
                            mapSources.push({name: f.map_path, url: pmtilesUrl(f.path)});
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
            overlaysRef.current = overlayFiles;
            setOverlays(overlayFiles);

            // Initialize contour source if terrain data is available.
            if (hasTerrain) {
                initContourSource(terrainFile);
            }

            try {
                map = new maplibregl.Map({
                    container: mapContainer.current,
                    style: buildStyle(mapSources, mapFlavor(theme), hasTerrain, scaleUnit, mapSprite(theme),
                        overlayFiles, overlayStateRef.current),
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
                    pinToggle.style.opacity = pinsVisibleRef.current ? "1" : "0.5";
                    showPins();
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

                // Choose a quadrangle to export.
                const exportButton = document.createElement("button");
                exportButton.type = "button";
                exportButton.title = "Export a 1:24,000 map";
                exportButton.setAttribute("aria-label", "Export a 1:24,000 map");
                exportButton.textContent = "🖨️";
                exportButton.style.cssText = pinToggle.style.cssText;
                exportButton.addEventListener("click", () => {
                    // Not while a map is being exported: what is said of it, and its Cancel, are there.
                    if (destroyed || exportingRef.current) return;
                    setPickingQuad(picking => (picking ? null : {quad: null}));
                });
                map.addControl({
                    onAdd: () => {
                        const container = document.createElement("div");
                        container.className = "maplibregl-ctrl maplibregl-ctrl-group";
                        container.appendChild(exportButton);
                        return container;
                    },
                    onRemove: () => {},
                }, "top-right");

                // Nuclear mode: targets, and fallout.
                const nuclearButton = document.createElement("button");
                nuclearButton.type = "button";
                nuclearButton.title = "Nuclear mode: targets and fallout";
                nuclearButton.setAttribute("aria-label", "Nuclear mode");
                nuclearButton.setAttribute("aria-pressed", "false");
                nuclearButton.textContent = "☢️";
                nuclearButton.style.cssText = pinToggle.style.cssText;
                nuclearButton.addEventListener("click", () => {
                    if (destroyed) return;
                    setNuclear(on => !on);
                });
                nuclearButtonRef.current = nuclearButton;
                map.addControl({
                    onAdd: () => {
                        const container = document.createElement("div");
                        container.className = "maplibregl-ctrl maplibregl-ctrl-group";
                        container.appendChild(nuclearButton);
                        return container;
                    },
                    onRemove: () => {},
                }, "top-right");

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
                // A name the overlay icons do not have is drawn as a plain dot.
                map.on("styleimagemissing", (e) => addMissingOverlayIcon(map, e.id));
                map.on("movestart", () => setContextMenu(null));

                // Click a POI to see the details the pmtiles file already has (kind, detail, elevation).
                const poiLayerIds = () => (map.getStyle()?.layers || [])
                    .map(l => l.id)
                    .filter(id => id === "pois" || id.endsWith(":pois"))
                    .filter(id => map.getLayer(id));
                // An overlay is drawn over the basemap, so its features are what a click lands on first.
                const overlayLayerIds = () => (map.getStyle()?.layers || [])
                    .filter(l => isOverlayLayerId(l.id) && l.type !== "raster")
                    .map(l => l.id)
                    .filter(id => map.getLayer(id));
                const featuresAt = (point, layers) =>
                    layers.length ? map.queryRenderedFeatures(point, {layers}) : [];
                map.on("click", (e) => {
                    if (destroyed || pickingQuadRef.current) return;
                    const html = overlayPopupHtml(featuresAt(e.point, overlayLayerIds()))
                        || poiPopupHtml(featuresAt(e.point, poiLayerIds()), e.lngLat);
                    if (!html) return;
                    new maplibregl.Popup({offset: 8, maxWidth: "260px", className: "wrolpi-map-popup"})
                        .setLngLat(e.lngLat)
                        .setHTML(html)
                        .addTo(map);
                });
                map.on("mousemove", (e) => {
                    if (destroyed) return;
                    if (pickingQuadRef.current) {
                        map.getCanvas().style.cursor = "crosshair";
                        return;
                    }
                    const hit = featuresAt(e.point, [...overlayLayerIds(), ...poiLayerIds()]).length;
                    map.getCanvas().style.cursor = hit ? "pointer" : "";
                });

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
                        applyGroupVisibility(map, getInitialVisibility());
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
            // An export of this map stops with it: nobody is here to be given the PDF.
            exportCancelledRef.current = true;
            exportAbortRef.current?.abort();
            if (map) {
                map.remove();
            }
            mapRef.current = null;
            setMapReady(false);
            // Clean up map params from URL so they don't leak to other pages.  Only while the URL is
            // still a map page: after navigating away, lat/lon belong to the new page (the Solar
            // calculator, for one).
            const url = new URL(window.location);
            if (url.pathname.startsWith("/map")) {
                url.searchParams.delete("lat");
                url.searchParams.delete("lon");
                url.searchParams.delete("z");
                window.history.replaceState(null, '', url.pathname + url.search);
            }
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Rebuild the style when the theme changes, and when the look the map is shown in does.
    useEffect(() => {
        const map = mapRef.current;
        if (!map || !mapReady) return;

        // What the user turned off is off in the new style too.  Listened for before the style is
        // set: a style which only differs from the one the map has is in place, and has said so,
        // before `setStyle` returns.  The map stays where it is: a style of ours says nothing of that.
        const showAsChosen = () => applyGroupVisibility(map, layerVisibilityRef.current);
        map.once("style.load", showAsChosen);
        // The overlays are part of the style, as the user last set them.
        // In the look a map is exported in while one is chosen; as the theme has it otherwise.
        map.setStyle(buildStyle(activeFilesRef.current, lookFlavor || mapFlavor(theme), hasTerrainRef.current,
            scaleUnit, lookSprite || mapSprite(theme), overlaysRef.current, overlayStateRef.current, printColors));
        return () => map.off("style.load", showAsChosen);
    }, [theme, lookFlavor, lookSprite, mapReady, scaleUnit, printColors]);

    // Remember what the user chose to see of an overlay, and show or hide its layers to match.
    const changeOverlayState = useCallback((file, next) => {
        overlayStateRef.current = next;
        setOverlayState(next);
        saveOverlayState(next);
        const map = mapRef.current;
        if (!map) return;
        for (const layer of buildOverlayLayers(file, next)) {
            if (map.getLayer(layer.id)) {
                map.setLayoutProperty(layer.id, "visibility", layer.layout.visibility);
            }
        }
    }, []);

    const handleToggleOverlay = useCallback((file, enabled) => {
        changeOverlayState(file, setOverlayEnabled(overlayStateRef.current, file, enabled));
    }, [changeOverlayState]);

    const handleToggleOverlayLayer = useCallback((file, layerId, enabled) => {
        changeOverlayState(file, setOverlayLayerEnabled(overlayStateRef.current, file, layerId, enabled));
    }, [changeOverlayState]);

    const handleToggleAllOverlayLayers = useCallback((file, enabled) => {
        changeOverlayState(file, setAllOverlayLayersEnabled(overlayStateRef.current, file, enabled));
    }, [changeOverlayState]);

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

    useEffect(() => {
        pickingQuadRef.current = pickingQuad !== null;
        const map = mapRef.current;
        if (map) map.getCanvas().style.cursor = pickingQuad ? "crosshair" : "";
    }, [pickingQuad]);

    const handleExportQuad = useCallback(() => {
        if (!contextMenu) return;
        // Start with the quadrangle which was clicked; not while another is being exported.
        if (!exportingRef.current) setPickingQuad({quad: quadAt(contextMenu.lon, contextMenu.lat)});
        setContextMenu(null);
    }, [contextMenu]);

    // Make a PDF of a quadrangle: the layers which are on, drawn as they are on the map.
    const handleExportPdf = useCallback(async (quad, {sheet = true, dpi = EXPORT_DPI, name = null} = {}) => {
        const map = mapRef.current;
        if (!map) return;
        exportCancelledRef.current = false;
        exportingRef.current = true;
        const abort = new AbortController();
        exportAbortRef.current = abort;
        // The unit the map measures in is the unit its contour lines are apart in.
        const imperial = scaleUnit === "imperial";
        setExportError(null);
        setExportStatus("Preparing…");
        try {
            const style = map.getStyle();
            const overlayLabels = Object.fromEntries(overlaysRef.current.map(
                file => [overlaySourceId(file), overlayLabel(file, overlaysRef.current)]));
            // A map file which is of somewhere else is not drawn.
            const outside = await sourcesOutside(
                style, [quad.west, quad.south, quad.east, quad.north], readTileBounds);
            const groups = exportGroups(
                style.layers.filter(layer => !layer.id.startsWith(QUAD_LAYER_PREFIX) && !outside.has(layer.source)),
                {layerGroups: LAYER_GROUPS, overlayLabels});
            if (!groups.length) throw new Error("No layer of the map is turned on");
            // How sharp the map may be depends on how many images it is, which is not known until
            // the groups have been looked at: one with nothing in it is no image.
            const maxSide = maxCanvasSide();
            const frameFor = count => exportFrame(quad, {dpi, maxSide, maxPixels: maxExportPixels(count)});
            // The zoom of the map is the same however many images it is.
            const frame = frameFor(groups.length);
            const rendered = await renderExport({
                MapClass: maplibregl.Map,
                style,
                frameFor,
                groups,
                ignoredPrefixes: [QUAD_LAYER_PREFIX],
                readTile: readVectorTile,
                setup: exportMap => exportMap.on("styleimagemissing", e => addMissingOverlayIcon(exportMap, e.id)),
                // Stopped between two layers, as soon as the person exporting asks.
                isCancelled: () => exportCancelledRef.current,
                onLooking: () => setExportStatus("Looking at the map…"),
                // The map is less sharp than was asked for when this browser, or this many layers, can not be.
                onProgress: (name, index, count, drawn) => setExportStatus(
                    `Drawing ${name} (${index + 1} of ${count})`
                    + `${Math.round(drawn.dpi) < dpi ? ` at ${Math.round(drawn.dpi)} DPI` : ""}…`),
            });
            const pdf = await exportMapPdf({
                ...rendered,
                title: exportTitle(quad, name),
                // With a sheet the map has a margin, a grid and scale bars; without, it is the map alone.
                sheet: sheet ? exportSheet(quad, map, groups, new Date(), name, exportContours(
                    groups, LAYER_GROUPS["Contours"], contourInterval(imperial, terrainZoom, frame.zoom), imperial,
                ), exportLegend(style, groups, frame.zoom)) : undefined,
            }, {
                // Once it is being stopped, that is what is said.
                onStatus: text => !exportCancelledRef.current && setExportStatus(text),
                isCancelled: () => exportCancelledRef.current,
                signal: abort.signal,
            });
            // Stopped while the PDF was on its way: it is not wanted.
            if (!exportCancelledRef.current) saveBlob(pdf, exportFileName(quad, name));
        } catch (e) {
            // Stopped by the person exporting: nothing went wrong.
            if (!e?.cancelled) {
                console.error("Map export failed:", e);
                setExportError(e?.message || "The map could not be exported");
            }
        } finally {
            exportingRef.current = false;
            setExportStatus(null);
        }
    }, [scaleUnit]);

    // Stop the export which is being made.  It stops between two steps, and the server stops making the PDF.
    const handleCancelExport = useCallback(() => {
        exportCancelledRef.current = true;
        exportAbortRef.current?.abort();
        setExportStatus("Stopping…");
    }, []);

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
    // Show the pins the toggle and the mode allow: pins while pins are shown, and targets only in
    // nuclear mode too.
    const showPins = useCallback(() => {
        for (const m of markersRef.current) {
            const shown = pinsVisibleRef.current && (!m.wrolpiTarget || nuclearRef.current);
            m.getElement().style.display = shown ? "" : "none";
        }
    }, []);

    const loadPins = useCallback(async () => {
        const map = mapRef.current;
        if (!map) return;

        // Remove existing markers.
        for (const m of markersRef.current) m.remove();
        markersRef.current = [];

        const data = await getMapPins();
        if (!data?.pins) return;
        setPins(data.pins);

        data.pins.forEach((pin) => {
            const target = pin.kind === "target";
            const el = document.createElement("div");
            el.style.cursor = "pointer";
            if (target) {
                el.textContent = "☢";
                el.style.cssText += "width:26px;height:26px;border-radius:50%;background:#ffd43b;color:#000;"
                    + "border:2px solid #000;box-shadow:0 1px 4px rgba(0,0,0,0.4);display:flex;"
                    + "align-items:center;justify-content:center;font-size:18px;line-height:1;";
            } else {
                el.style.width = "24px";
                el.style.height = "24px";
                el.style.borderRadius = "50% 50% 50% 0";
                el.style.background = pin.color || "red";
                el.style.border = "2px solid white";
                el.style.boxShadow = "0 1px 4px rgba(0,0,0,0.4)";
                el.style.transform = "rotate(-45deg)";
            }

            const button = (onclick, text, color) => `<button onclick="${onclick}" `
                + `style="margin-top:4px;margin-right:4px;padding:2px 8px;cursor:pointer;color:${color};`
                + `border:1px solid ${color};background:none;border-radius:3px;">${text}</button>`;
            const popup = new maplibregl.Popup({offset: 15}).setHTML(
                `<div style="font-size:13px">` +
                `<strong>${escapeHtml(pin.label || (target ? "Target" : "Pin"))}</strong><br/>` +
                (target ? `<small>Target</small><br/>` : "") +
                `<small>${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}</small><br/>` +
                (target ? button("window.__showFallout()", "Show fallout", "#333") : "") +
                button(`window.__deleteMapPin(${pin.id})`, "Delete", "red") +
                `</div>`
            );

            const marker = new maplibregl.Marker({element: el})
                .setLngLat([pin.lon, pin.lat])
                .setPopup(popup)
                .addTo(map);
            marker.wrolpiTarget = target;
            markersRef.current.push(marker);
        });
        showPins();
    }, [showPins]);

    // Nuclear mode on or off: the button says so, targets are shown or hidden, and leaving it closes
    // the fallout simulation.
    useEffect(() => {
        nuclearRef.current = nuclear;
        const button = nuclearButtonRef.current;
        if (button) {
            button.style.background = nuclear ? "#ffd43b" : "white";
            button.setAttribute("aria-pressed", String(nuclear));
        }
        showPins();
        // Nuclear mode opens on the fallout of the saved targets; leaving it closes the view.
        setFalloutOpen(nuclear);
        if (!nuclear) setFalloutBurst(null);
    }, [nuclear, showPins]);

    useEffect(() => {
        window.__showFallout = () => setFalloutOpen(true);
        return () => { delete window.__showFallout; };
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
        setAddingPin({lat: contextMenu.lat, lon: contextMenu.lon, kind: nuclear ? "target" : "pin"});
        setContextMenu(null);
    }, [contextMenu, nuclear]);

    const handleSolar = useCallback(() => {
        if (!contextMenu) return;
        setContextMenu(null);
        navigate(solarCalculatorPath(contextMenu.lat, contextMenu.lon));
    }, [contextMenu, navigate]);

    const handleFallout = useCallback(() => {
        if (!contextMenu) return;
        setContextMenu(null);
        setFalloutBurst({lat: contextMenu.lat, lon: contextMenu.lon});
        setFalloutOpen(true);
    }, [contextMenu]);

    const handleSetDefaultLocation = useCallback(async () => {
        const map = mapRef.current;
        if (!map) return;
        const center = map.getCenter();
        const zoom = map.getZoom();
        await setMapDefaultLocation(center.lat, center.lng, zoom);
        await fetchSettings();
        setContextMenu(null);
    }, [fetchSettings]);

    const handleSubmitPin = useCallback(async (label, color, weapon) => {
        if (!addingPin) return;
        const {lat, lon, kind} = addingPin;
        setAddingPin(null);  // Prevent double-submit.
        const added = await addMapPin(lat, lon, label, color, kind, weapon);
        // A burst saved as a target is one of the targets now.
        if (added && falloutBurst && falloutBurst.lat === lat && falloutBurst.lon === lon) setFalloutBurst(null);
        await loadPins();
    }, [addingPin, loadPins, falloutBurst]);

    const handleTargetWeapon = useCallback(async (target, weapon) => {
        if (await updateMapTargetWeapon(target.id, weapon)) await loadPins();
    }, [loadPins]);

    if (error) {
        return <Panel>
            <Header as="h3">Map failed to load</Header>
            <p>Your browser may not support WebGL. You can access the standalone map viewer
                at <a href={MAP_VIEWER_URI}>{MAP_VIEWER_URI}</a></p>
            <p>Error: {error}</p>
        </Panel>;
    }

    return <div ref={mapContainer} style={{position: "relative", width: "100%", height: "85vh"}}>
        {mapReady && <MapSearch map={mapRef.current}/>}
        {mapReady && <LayerControl
            map={mapRef.current}
            scaleUnit={scaleUnit}
            onScaleUnitChange={handleScaleUnitChange}
            visibilityRef={layerVisibilityRef}
            printColors={printing ? printColors : null}
            onPrintColors={handlePrintColors}
            overlays={overlays}
            overlayState={overlayState}
            onToggleOverlay={handleToggleOverlay}
            onToggleOverlayLayer={handleToggleOverlayLayer}
            onToggleAllOverlayLayers={handleToggleAllOverlayLayers}
        />}
        {contextMenu && <div
            style={{
                position: "absolute",
                left: contextMenu.x,
                top: contextMenu.y,
                zIndex: 1001,
                background: "white",
                borderRadius: "0.375rem",
                boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                padding: "0.25rem 0",
                fontSize: '0.8125rem',
                minWidth: "11.25rem",
            }}
        >
            <div style={{padding: "0.375rem 0.75rem", color: "#666", fontSize: '0.75rem', borderBottom: "1px solid #eee"}}>
                {(() => {
                    const map = mapRef.current;
                    const zoom = map ? map.getZoom() : 10;
                    const d = zoom < 4 ? 1 : zoom < 8 ? 2 : zoom < 12 ? 3 : 4;
                    return `${contextMenu.lat.toFixed(d)}, ${contextMenu.lon.toFixed(d)}`;
                })()}
            </div>
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleCopyCoords}
            >
                Copy GPS coordinates
            </div>
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleExportPng}
            >
                Export as PNG
            </div>
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleExportQuad}
            >
                Export a 1:24,000 map
            </div>
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleAddPin}
            >
                {nuclear ? "Add Target Here" : "Add Pin Here"}
            </div>
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleSolar}
            >
                Calculate Solar Performance
            </div>
            {nuclear && <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleFallout}
            >
                Simulate Fallout Here
            </div>}
            <div
                style={{padding: "0.5rem 0.75rem", cursor: "pointer", userSelect: "none"}}
                onMouseEnter={e => e.target.style.background = "#f0f0f0"}
                onMouseLeave={e => e.target.style.background = "transparent"}
                onClick={handleSetDefaultLocation}
            >
                Set as Default View
            </div>
        </div>}
        {mapReady && pickingQuad && <MapQuadPicker
            key={pickingQuad.quad?.id || "none"}
            map={mapRef.current}
            scaleUnit={scaleUnit}
            initialQuad={pickingQuad.quad}
            onExport={handleExportPdf}
            onCancel={handleCancelExport}
            fetchName={getMapQuadName}
            look={exportLook}
            onLook={handleExportLook}
            status={exportStatus}
            error={exportError}
            onClose={() => {
                setExportError(null);
                setPickingQuad(null);
            }}
        />}
        {mapReady && nuclear && falloutOpen && <FalloutPanel
            map={mapRef.current}
            targets={pins.filter(p => p.kind === "target")}
            burst={falloutBurst}
            onSaveBurst={(burst, weapon) => setAddingPin({lat: burst.lat, lon: burst.lon, kind: "target", weapon})}
            onTargetWeapon={handleTargetWeapon}
            onClose={() => {
                setFalloutOpen(false);
                setFalloutBurst(null);
            }}
        />}
        {addingPin && <AddPinDialog
            lat={addingPin.lat}
            lon={addingPin.lon}
            target={addingPin.kind === "target"}
            weapon={addingPin.weapon}
            onSubmit={handleSubmitPin}
            onCancel={() => setAddingPin(null)}
        />}
    </div>;
}
