// The map's ATAK tab: how to use this WROLPi's map in ATAK (Android) and iTAK (iPhone), and what the
// tile service (tiles/, wrolpi-tiles) is doing.
import React, {useEffect, useState} from "react";
import {APIButton, ErrorMessage, humanFileSize, InfoMessage} from "./Common";
import {Header, Panel, Table} from "./ui";

// How often the status is asked for while the tab is open.
const STATUS_INTERVAL_MS = 5000;

// The map source over plain HTTP: no certificate is needed, so it works on any phone.
export function httpMapSourceUrl(hostname = window.location.hostname) {
    return `http://${hostname}:8088/tiles/wrolpi.xml`;
}

// The map source over HTTPS: the phone must trust this WROLPi's certificate authority.
export function httpsMapSourceUrl(origin = window.location.origin) {
    return `${origin}/tiles/wrolpi.xml`;
}

// The status of the tile service.  null while the first request is pending, undefined when the
// service did not answer.
export function useTileStatus(interval = STATUS_INTERVAL_MS) {
    const [status, setStatus] = useState(null);

    useEffect(() => {
        let cancelled = false;
        const fetchStatus = async () => {
            try {
                const response = await fetch('/tiles/status');
                const data = response.ok ? await response.json() : undefined;
                if (!cancelled) setStatus(data);
            } catch (e) {
                if (!cancelled) setStatus(undefined);
            }
        };
        fetchStatus();
        const timer = setInterval(fetchStatus, interval);
        return () => {
            cancelled = true;
            clearInterval(timer);
        };
    }, [interval]);

    return status;
}

function MapSourceRow({label, url, note}) {
    return <Table.Row>
        <Table.Cell><b>{label}</b><div style={{fontSize: '0.8125rem', color: 'var(--muted)'}}>{note}</div></Table.Cell>
        <Table.Cell style={{wordBreak: 'break-all'}}><a href={url}>{url}</a></Table.Cell>
        <Table.Cell>
            <APIButton icon='copy' aria-label={`Copy ${label} map source address`}
                       onClick={() => navigator.clipboard.writeText(url)}/>
        </Table.Cell>
    </Table.Row>;
}

function HowTo() {
    return <Panel>
        <Header as='h3'>Use this map in ATAK or iTAK</Header>
        <p>
            ATAK (Android) and iTAK (iPhone) can draw this WROLPi's map while the phone is on this
            WROLPi's network. ATAK can also download an area of the map to use when it is not.
        </p>
        <Table>
            <Table.Body>
                <MapSourceRow label='HTTP' url={httpMapSourceUrl()}
                              note='Works on any phone, nothing to install.'/>
                <MapSourceRow label='HTTPS' url={httpsMapSourceUrl()}
                              note="Only once the phone trusts this WROLPi's certificate."/>
            </Table.Body>
        </Table>
        <ol>
            <li>On the phone, open a map source address above in its browser; it downloads a small
                file.
            </li>
            <li>Open that file with ATAK or iTAK (or import it with the app's import tool).</li>
            <li>Choose <b>WROLPi Map</b> in the app's list of maps.</li>
            <li>ATAK only: to use the map away from this WROLPi, download an area of it with ATAK's
                map download tool while still connected.
            </li>
        </ol>
        <p>
            For HTTPS, the phone must first install and trust{' '}
            <a href='/ca.crt'>this WROLPi's certificate</a>. On an iPhone, after installing it, turn
            it on in Settings, General, About, Certificate Trust Settings.
        </p>
        <p style={{color: 'var(--muted)'}}>
            The map is of the map files on the Manage tab. Map data &copy; OpenStreetMap contributors.
        </p>
    </Panel>;
}

function secondsAgo(timestamp) {
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
    return `${Math.round(seconds / 3600)}h ago`;
}

function TileServiceStatus({status}) {
    if (status === null) {
        return <Panel><Header as='h3'>Tile service</Header><p>Loading...</p></Panel>;
    }
    if (status === undefined) {
        return <Panel>
            <Header as='h3'>Tile service</Header>
            <ErrorMessage>The tile service is not running. Start <b>wrolpi-tiles</b> on the
                Controller page.</ErrorMessage>
        </Panel>;
    }

    const basemaps = status.maps.length;
    const cache = status.cache;
    return <Panel>
        <Header as='h3'>Tile service</Header>
        {!status.renderer && <ErrorMessage>The tile service cannot draw tiles: its renderer (mapli) is not
            installed.</ErrorMessage>}
        {basemaps === 0 && <InfoMessage>There are no map files; download some on the Manage tab.</InfoMessage>}
        <Table>
            <Table.Body>
                <Table.Row>
                    <Table.Cell>Map files</Table.Cell>
                    <Table.Cell>{basemaps}</Table.Cell>
                </Table.Row>
                <Table.Row>
                    <Table.Cell>Tiles sent</Table.Cell>
                    <Table.Cell>{status.tiles_per_second} per second (last minute)</Table.Cell>
                </Table.Row>
                <Table.Row>
                    <Table.Cell>Waiting to be drawn</Table.Cell>
                    <Table.Cell>{status.queued_blocks + status.drawing_blocks} blocks of 16 tiles</Table.Cell>
                </Table.Row>
                <Table.Row>
                    <Table.Cell>Kept tiles</Table.Cell>
                    <Table.Cell>{cache.enabled
                        ? `${humanFileSize(cache.bytes)} of ${humanFileSize(cache.max_bytes)}`
                        : 'Not kept'}</Table.Cell>
                </Table.Row>
            </Table.Body>
        </Table>
        <Header as='h4'>Phones (last day)</Header>
        {status.clients.length === 0
            ? <p>No phone has asked for tiles.</p>
            : <Table>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>Address</Table.HeaderCell>
                        <Table.HeaderCell>Tiles</Table.HeaderCell>
                        <Table.HeaderCell>Last tile</Table.HeaderCell>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {status.clients.map(client => <Table.Row key={client.client}>
                        <Table.Cell>{client.client}</Table.Cell>
                        <Table.Cell>{client.tiles}</Table.Cell>
                        <Table.Cell>{secondsAgo(client.last_seen)}</Table.Cell>
                    </Table.Row>)}
                </Table.Body>
            </Table>}
    </Panel>;
}

export function MapAtak() {
    const status = useTileStatus();
    return <>
        <HowTo/>
        <TileServiceStatus status={status}/>
    </>;
}
