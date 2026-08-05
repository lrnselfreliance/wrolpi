import React, {useEffect, useState} from "react";
import {
    APIButton,
    ErrorMessage,
    HandPointMessage,
    humanFileSize,
    InfoMessage,
    PageContainer,
    TabLinks,
    useTitle,
    WROLModeMessage
} from "./Common";
import {Route, Routes, useNavigate} from "react-router";
import {
    deleteMapFile, deleteMapPin, fetchMapSubscriptions, getMapFiles, getMapPins,
    mapSubscribe, mapUnsubscribe, rebuildMapSearchIndex, updateMapPin
} from "../api";
import {Button, Divider, Group, Header, Icon, Modal, Table, TextInput} from "./ui";
import {SortableTable} from "./SortableTable";
import {Media, StatusContext} from "../contexts/contexts";
import {MAP_VIEWER_URI} from "./Vars";
import MapViewer from "./MapViewer";
import {AddToPlaylistButton} from "./AddToPlaylist";
import maplibregl from "maplibre-gl";
import {Protocol} from "pmtiles";
import layers from "protomaps-themes-base";

// Ensure PMTiles protocol is registered (may already be registered by MapViewer).
try { maplibregl.addProtocol("pmtiles", new Protocol().tile); } catch (e) { /* already registered */ }

const MAP_OVERVIEW_URL = "/blobs/map-overview.pmtiles";

// Detect full planet files: "planet-20260329.pmtiles" or bare date like "20260329.pmtiles".
function isPlanetFile(name) {
    if (name.startsWith("planet-")) return true;
    return /^\d{8}\.pmtiles$/.test(name);
}

// Resolve the best available base map source for preview maps.
// Checks for a user's planet file first, falls back to the overview blob.
async function getPreviewMapSource() {
    try {
        const data = await getMapFiles();
        if (data?.files) {
            for (const f of data.files) {
                if (isPlanetFile(f.name)) {
                    return {type: 'vector', url: `pmtiles:///media/map/${f.name}`};
                }
            }
        }
    } catch (e) { /* ignore */ }
    return {type: 'vector', url: `pmtiles://${MAP_OVERVIEW_URL}`};
}

function RegionPreviewModal({bbox, name, open, onClose}) {
    const mapContainer = React.useRef(null);

    React.useEffect(() => {
        if (!open || !mapContainer.current || !bbox) return;

        const [minLon, minLat, maxLon, maxLat] = bbox.split(',').map(Number);
        const centerLon = (minLon + maxLon) / 2;
        const centerLat = (minLat + maxLat) / 2;

        let map;
        getPreviewMapSource().then(source => {
            if (!mapContainer.current) return;
            map = new maplibregl.Map({
                container: mapContainer.current,
                style: {
                    version: 8,
                    sources: {'basemap': source},
                    layers: layers('basemap', 'light'),
                    glyphs: '/map-assets/fonts/{fontstack}/{range}.pbf',
                    sprite: `${window.location.origin}/map-assets/sprites/light`,
                },
                center: [centerLon, centerLat],
                zoom: 1,
                attributionControl: false,
            });

            map.on('load', () => {
                map.addSource('bbox', {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        geometry: {
                            type: 'Polygon',
                            coordinates: [[
                                [minLon, minLat],
                                [maxLon, minLat],
                                [maxLon, maxLat],
                                [minLon, maxLat],
                                [minLon, minLat],
                            ]],
                        },
                    },
                });
                map.addLayer({
                    id: 'bbox-fill',
                    type: 'fill',
                    source: 'bbox',
                    paint: {'fill-color': '#6435c9', 'fill-opacity': 0.2},
                });
                map.addLayer({
                    id: 'bbox-outline',
                    type: 'line',
                    source: 'bbox',
                    paint: {'line-color': '#6435c9', 'line-width': 2},
                });
                map.fitBounds([[minLon, minLat], [maxLon, maxLat]], {padding: 40});
            });
        });

        return () => { if (map) map.remove(); };
    }, [open, bbox]);

    return <Modal open={open} onClose={onClose} size='fullscreen' closeIcon title={name}>
        {/* No `.media` here: the bbox highlight is drawn as a map layer on the canvas itself
            (see the `bbox` source/layers above), so the automatic `canvas` element-type filter
            already covers it. There is no separate DOM overlay to wrap. */}
        <div ref={mapContainer} style={{width: '100%', height: '50vh'}}/>
    </Modal>;
}

// Random-ish distinct colors for region boxes. These are map-data paint colors (drawn
// on the WebGL canvas itself), not UI chrome, so they are not theme tokens.
const REGION_COLORS = [
    '#6435c9', '#e03997', '#00b5ad', '#2185d0', '#f2711c', '#b5cc18',
    '#a333c8', '#21ba45', '#db2828', '#fbbd08', '#a5673f', '#767676',
];

function AllRegionsPreviewModal({catalog, open, onClose}) {
    const mapContainer = React.useRef(null);

    React.useEffect(() => {
        if (!open || !mapContainer.current) return;

        let map;
        getPreviewMapSource().then(source => {
            if (!mapContainer.current) return;
            map = new maplibregl.Map({
                container: mapContainer.current,
                style: {
                    version: 8,
                    sources: {'basemap': source},
                    layers: layers('basemap', 'light'),
                    glyphs: '/map-assets/fonts/{fontstack}/{range}.pbf',
                    sprite: `${window.location.origin}/map-assets/sprites/light`,
                },
                center: [0, 20],
                zoom: 1,
                attributionControl: false,
            });

            map.on('load', () => {
                const regions = catalog.filter(r => r.bbox);
                regions.forEach((region, i) => {
                    const [minLon, minLat, maxLon, maxLat] = region.bbox.split(',').map(Number);
                    const color = REGION_COLORS[i % REGION_COLORS.length];
                    const id = `region-${i}`;

                    map.addSource(id, {
                        type: 'geojson',
                        data: {
                            type: 'Feature',
                            geometry: {
                                type: 'Polygon',
                                coordinates: [[
                                    [minLon, minLat], [maxLon, minLat],
                                    [maxLon, maxLat], [minLon, maxLat],
                                    [minLon, minLat],
                                ]],
                            },
                            properties: {name: region.name},
                        },
                    });
                    map.addLayer({
                        id: `${id}-fill`, type: 'fill', source: id,
                        paint: {'fill-color': color, 'fill-opacity': 0.15},
                    });
                    map.addLayer({
                        id: `${id}-outline`, type: 'line', source: id,
                        paint: {'line-color': color, 'line-width': 1.5},
                    });
                    map.addLayer({
                        id: `${id}-label`, type: 'symbol', source: id,
                        layout: {
                            'text-field': ['get', 'name'],
                            'text-size': 11,
                            'text-allow-overlap': true,
                        },
                        paint: {
                            'text-color': color,
                            'text-halo-color': 'white',
                            'text-halo-width': 1,
                        },
                    });
                });
            });
        });

        return () => { if (map) map.remove(); };
    }, [open, catalog]);

    return <Modal open={open} onClose={onClose} size='fullscreen' closeIcon title='All Map Regions'>
        {/* No `.media` here either — same reasoning as RegionPreviewModal. */}
        <div ref={mapContainer} style={{width: '100%', height: '75vh'}}/>
    </Modal>;
}

function MapCatalogRow({item, subscribedRegions, fetchData}) {
    const {name, region, size_estimate, bbox} = item;
    const isSubscribed = subscribedRegions.has(region);
    const [previewOpen, setPreviewOpen] = useState(false);

    const handleButton = async () => {
        if (isSubscribed) {
            await mapUnsubscribe(region);
        } else {
            await mapSubscribe(name, region);
        }
        if (fetchData) {
            await fetchData();
        }
    };

    return <Table.Row>
        <Table.Cell>{name}</Table.Cell>
        <Table.Cell>{humanFileSize(size_estimate)}</Table.Cell>
        <Table.Cell>
            {/* See PinEditRow: a Group so the preview and subscribe controls line up and are
                spaced, rather than sitting on baselines they do not share. */}
            <Group gap='xs' wrap='nowrap'>
                {bbox && <Button
                    size='xs'
                    icon='eye'
                    aria-label={`Preview ${name}`}
                    onClick={() => setPreviewOpen(true)}
                />}
                <Button
                    role={isSubscribed ? 'danger' : undefined}
                    color={isSubscribed ? undefined : 'violet'}
                    size='xs'
                    onClick={handleButton}
                >
                    {isSubscribed ? 'Unsubscribe' : 'Subscribe'}
                </Button>
            </Group>
        </Table.Cell>
        {previewOpen && <RegionPreviewModal
            bbox={bbox}
            name={name}
            open={previewOpen}
            onClose={() => setPreviewOpen(false)}
        />}
    </Table.Row>;
}

function ManageMap() {
    const [files, setFiles] = useState(null);
    const [catalog, setCatalog] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [allRegionsOpen, setAllRegionsOpen] = useState(false);
    const {status} = React.useContext(StatusContext);
    const searchBuilding = status?.flags?.map_search_building;

    const fetchFiles = async () => {
        try {
            const data = await getMapFiles();
            if (data) {
                setFiles(data.files || []);
            }
        } catch (e) {
            console.error(e);
            setFiles(undefined);
        }
    };

    const fetchSubscriptionData = async () => {
        try {
            const data = await fetchMapSubscriptions();
            if (data) {
                setCatalog(data.catalog || []);
                setSubscriptions(data.subscriptions || []);
            }
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchFiles();
        fetchSubscriptionData();
        const interval = setInterval(fetchFiles, 30000);
        return () => clearInterval(interval);
    }, []);

    const handleDelete = async (filename) => {
        await deleteMapFile(filename);
        await fetchFiles();
    };

    // --- Files table ---
    const fileHeaders = [
        {key: 'name', text: 'File', sortBy: i => i.name.toLowerCase()},
        {key: 'size', text: 'Size', sortBy: i => i.size || 0},
        {key: 'search', text: 'Search', sortBy: null},
        {key: 'actions', text: '', sortBy: null},
    ];

    const handleBuildSearch = async (filename) => {
        await rebuildMapSearchIndex(filename);
        await fetchFiles();
    };

    const fileRowFunc = (file) => {
        return <Table.Row key={file.name}>
            <Table.Cell>{file.name}</Table.Cell>
            <Table.Cell>{humanFileSize(file.size)}</Table.Cell>
            <Table.Cell>
                {file.name.startsWith('terrain')
                    ? null
                    : file.has_search_index
                        ? <Button size='xs' icon='check' disabled role='save'>Built</Button>
                        : <APIButton size='xs' icon='search'
                                     disabled={searchBuilding}
                                     loading={searchBuilding}
                                     onClick={() => handleBuildSearch(file.name)}>
                            {searchBuilding ? 'Building...' : 'Build'}
                        </APIButton>
                }
            </Table.Cell>
            <Table.Cell>
                <APIButton
                    role='danger'
                    size='xs'
                    confirmContent='Delete this map file?'
                    confirmButton='Delete'
                    onClick={() => handleDelete(file.name)}
                >
                    Delete
                </APIButton>
            </Table.Cell>
        </Table.Row>;
    };

    const emptyRow = <Table.Row>
        <Table.Cell colSpan={4}>No PMTiles map files were found in <b>map/</b></Table.Cell>
    </Table.Row>;

    // --- Catalog table ---
    const catalogHeaders = [
        {key: 'name', text: 'Region', sortBy: i => i.name.toLowerCase()},
        {key: 'size', text: 'Estimated Size', sortBy: i => i.size_estimate || 0},
        {key: 'actions', text: '', sortBy: null},
    ];

    const catalogRowFunc = (item) => {
        return <MapCatalogRow
            key={item.region}
            item={item}
            subscribedRegions={new Set(subscriptions.map(s => s.region))}
            fetchData={fetchSubscriptionData}
        />;
    };

    if (files === undefined) {
        return <PageContainer>
            <WROLModeMessage content='Cannot modify Map'/>
            <ErrorMessage>Could not fetch map files</ErrorMessage>
        </PageContainer>;
    }

    return <PageContainer>
        <WROLModeMessage content='Cannot modify Map'/>

        <Header as='h3'>Map Files</Header>
        <SortableTable
            tableHeaders={fileHeaders}
            data={files}
            rowFunc={fileRowFunc}
            rowKey='name'
            defaultSortColumn='name'
            emptyRow={emptyRow}
        />

        <Divider/>

        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5em'}}>
            <Header as='h3'>Map Subscriptions</Header>
            <Button size='xs' icon='globe' onClick={() => setAllRegionsOpen(true)}>View All Regions</Button>
        </div>

        <AllRegionsPreviewModal catalog={catalog} open={allRegionsOpen} onClose={() => setAllRegionsOpen(false)}/>

        <SortableTable
            tableHeaders={catalogHeaders}
            data={catalog}
            rowFunc={catalogRowFunc}
            rowKey='region'
            defaultSortColumn='name'
        />

        <InfoMessage storageName='hint_map_subscribe'>
            <div style={{fontWeight: 600, marginBottom: 4}}>How to get map files</div>
            <p>Subscribe to a map region to automatically download it. Subscriptions will
                periodically check for updated maps. Downloads may take a long time depending on
                the region size and your internet speed. You can monitor progress on
                the <b>Downloads</b> page.</p>
            <p>You can also manually extract a region using the <b>pmtiles</b> command-line tool
                and place the resulting file into the <b>map/</b> directory:</p>
            <pre>  pmtiles extract https://build.protomaps.com/YYYYMMDD.pmtiles region.pmtiles \{'\n'}    --bbox="-125.0,24.4,-66.9,49.4"</pre>
            <p>Find the latest build date at&nbsp;
                <a href='https://maps.protomaps.com/builds/' rel='noopener noreferrer'
                   target='_blank'>maps.protomaps.com/builds</a>
            </p>
        </InfoMessage>

        <HandPointMessage>
            <p>You can also view the map at <a href={MAP_VIEWER_URI}>{MAP_VIEWER_URI}</a></p>
        </HandPointMessage>
    </PageContainer>
}

const PIN_COLORS = ["red", "blue", "green", "yellow", "orange", "purple"];

function PinEditRow({pin, onSave, onCancel}) {
    const [label, setLabel] = useState(pin.label);
    const [color, setColor] = useState(pin.color);

    return <Table.Row>
        <Table.Cell>
            <div style={{display: "flex", gap: 4}}>
                {PIN_COLORS.map(c =>
                    <div
                        key={c}
                        onClick={() => setColor(c)}
                        style={{
                            width: 20, height: 20, borderRadius: "50%", background: c, cursor: "pointer",
                            border: color === c ? "3px solid var(--text)" : "2px solid var(--border)",
                        }}
                    />
                )}
            </div>
        </Table.Cell>
        <Table.Cell>
            <TextInput
                size='sm'
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && label.trim() && onSave(pin.id, label.trim(), color)}
            />
        </Table.Cell>
        <Table.Cell>{pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}</Table.Cell>
        <Media greaterThan='mobile'><Table.Cell>{pin.created}</Table.Cell></Media>
        <Table.Cell>
            {/* A Group, not bare siblings: inline-block controls align on text baselines they
                do not share, and JSX leaves no whitespace between them to space them out. */}
            <Group gap='xs' wrap='nowrap'>
                <Button size='xs' role='save'
                        onClick={() => label.trim() && onSave(pin.id, label.trim(), color)}>Save</Button>
                <Button size='xs' role='cancel' onClick={onCancel}>Cancel</Button>
            </Group>
        </Table.Cell>
    </Table.Row>;
}

function MapPins() {
    const [pins, setPins] = useState([]);
    const [filter, setFilter] = useState('');
    const [editingId, setEditingId] = useState(null);
    const navigate = useNavigate();

    const fetchPins = async () => {
        try {
            const data = await getMapPins();
            if (data) setPins(data.pins || []);
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchPins();
    }, []);

    const handleDelete = async (pinId) => {
        await deleteMapPin(pinId);
        setEditingId(null);
        await fetchPins();
    };

    const handleSave = async (pinId, label, color) => {
        await updateMapPin(pinId, label, color);
        setEditingId(null);
        await fetchPins();
    };

    const handleNavigate = (pin) => {
        navigate(`/map?lat=${pin.lat}&lon=${pin.lon}&z=14`);
    };

    // --- Desktop headers and row ---
    const fullHeaders = [
        {key: 'color', text: '', sortBy: i => i.color},
        {key: 'label', text: 'Label', sortBy: i => i.label.toLowerCase()},
        {key: 'coords', text: 'Coordinates', sortBy: i => i.lat},
        {key: 'created', text: 'Created', sortBy: i => i.created},
        {key: 'actions', text: '', sortBy: null},
    ];

    const fullRowFunc = (pin) => {
        if (editingId === pin.id) {
            return <PinEditRow
                key={pin.id}
                pin={pin}
                onSave={handleSave}
                onCancel={() => setEditingId(null)}
            />;
        }
        return <Table.Row key={pin.id}>
            <Table.Cell>
                <div style={{
                    width: 16, height: 16, borderRadius: "50%",
                    background: pin.color || "red", border: "1px solid var(--border)",
                }}/>
            </Table.Cell>
            <Table.Cell>{pin.label}</Table.Cell>
            <Table.Cell>
                <a href="#" onClick={(e) => {e.preventDefault(); handleNavigate(pin);}}>
                    {pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}
                </a>
            </Table.Cell>
            <Table.Cell>{pin.created}</Table.Cell>
            <Table.Cell>
                {/* See PinEditRow: a Group so the three controls line up and are spaced. */}
                <Group gap='xs' wrap='nowrap'>
                    <Button size='xs' icon='edit' aria-label={`Edit ${pin.label}`}
                            onClick={() => setEditingId(pin.id)}/>
                    <AddToPlaylistButton
                        size='xs'
                        icon='list'
                        content=''
                        url={{url: `/map?lat=${pin.lat}&lon=${pin.lon}&z=14`, title: pin.label}}
                    />
                    <APIButton
                        size='xs'
                        role='danger'
                        icon='trash'
                        aria-label={`Delete ${pin.label}`}
                        confirmContent='Delete this pin?'
                        confirmButton='Delete'
                        onClick={() => handleDelete(pin.id)}
                    />
                </Group>
            </Table.Cell>
        </Table.Row>;
    };

    // --- Mobile headers and row ---
    const mobileHeaders = [
        {key: 'color', text: '', sortBy: i => i.color},
        {key: 'label', text: 'Label', sortBy: i => i.label.toLowerCase()},
        {key: 'actions', text: '', sortBy: null},
    ];

    const mobileRowFunc = (pin) => {
        return <Table.Row key={pin.id}>
            <Table.Cell>
                <div style={{
                    width: 16, height: 16, borderRadius: "50%",
                    background: pin.color || "red", border: "1px solid var(--border)",
                }}/>
            </Table.Cell>
            <Table.Cell>
                <a href="#" onClick={(e) => {e.preventDefault(); handleNavigate(pin);}}>
                    {pin.label}
                </a>
                <div style={{fontSize: '0.6875rem', color: 'var(--muted)'}}>{pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}</div>
            </Table.Cell>
            <Table.Cell>
                <APIButton
                    size='xs'
                    role='danger'
                    icon='trash'
                    aria-label={`Delete ${pin.label}`}
                    confirmContent='Delete this pin?'
                    confirmButton='Delete'
                    onClick={() => handleDelete(pin.id)}
                />
            </Table.Cell>
        </Table.Row>;
    };

    const emptyRow = <Table.Row>
        <Table.Cell colSpan={5}>No pins. Right-click on the map to add one.</Table.Cell>
    </Table.Row>;

    const lowerFilter = filter.toLowerCase();
    const filteredPins = lowerFilter
        ? pins.filter(p =>
            (p.label || '').toLowerCase().includes(lowerFilter) ||
            `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`.includes(lowerFilter)
        )
        : pins;

    return <PageContainer>
        <TextInput
            leftSection={<Icon name='search'/>}
            placeholder='Filter by label or coordinates...'
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{marginBottom: '1em', width: '100%'}}
        />
        <Media at='mobile'>
            <SortableTable
                tableHeaders={mobileHeaders}
                data={filteredPins}
                rowFunc={mobileRowFunc}
                rowKey='label'
                defaultSortColumn='label'
                emptyRow={emptyRow}
            />
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <SortableTable
                tableHeaders={fullHeaders}
                data={filteredPins}
                rowFunc={fullRowFunc}
                rowKey='label'
                defaultSortColumn='label'
                emptyRow={emptyRow}
            />
        </Media>
    </PageContainer>;
}

function MapPage() {
    return <MapViewer/>;
}

export function MapRoute() {
    useTitle('Map');

    const links = [
        {text: 'Map', to: '/map', key: 'map', end: true},
        {text: 'Pins', to: '/map/pins', key: 'pins'},
        {text: 'Manage', to: '/map/manage', key: 'manage'},
    ];

    // `wrolpi-stack`: as in ZimRoute, this route wraps its own content instead of using
    // PageContainer, so the spacing below the tab bar is this element's to provide.
    return <div className='wrolpi-stack' style={{marginTop: '2em'}}>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' exact element={<MapPage/>}/>
            <Route path='pins' exact element={<MapPins/>}/>
            <Route path='manage' exact element={<ManageMap/>}/>
        </Routes>
    </div>
}
