import React, {useContext, useEffect, useRef, useState} from "react";
import {StatusContext} from "../../contexts/contexts";
import {Button, Grid, Header, Label, Message, Panel, Progress, Sparkline, Statistic, StatisticGroup, Table, Text} from "../ui";
import {
    bytesToMbps,
    describePing,
    fetchInfo,
    formatMbps,
    formatMs,
    isHotspotAddress,
    mbpsToMBps,
    otherActiveTests,
    PHASE_SECONDS,
    PING_SAMPLES,
    runDownload,
    runPing,
    runUpload,
    streamCapacity,
} from "./speedtest";

const PHASES = {
    idle: {label: 'Ready', order: 0},
    ping: {label: 'Measuring latency…', order: 1},
    download: {label: 'Downloading…', order: 2},
    upload: {label: 'Uploading…', order: 3},
    done: {label: 'Complete', order: 4},
    cancelled: {label: 'Cancelled', order: 4},
    error: {label: 'Failed', order: 4},
};

// The rolling trace shows this many buckets (PHASE_SECONDS at 250 ms each).
const TRACE_LENGTH = PHASE_SECONDS * 4;

const emptyResults = () => ({ping: null, download: null, upload: null});

/**
 * Measures the network between this browser and the WROLPi: ping, then a 10 s download, then a
 * 10 s upload, all against the API.  Nothing is stored.
 */
export function SpeedTestCalculator() {
    const {status} = useContext(StatusContext) || {};
    const hotspotConnected = status?.hotspot_status === 'connected';

    const [phase, setPhase] = useState('idle');
    const [results, setResults] = useState(emptyResults);
    const [live, setLive] = useState({mbps: 0, trace: [], progress: 0, rtts: []});
    const [info, setInfo] = useState(null);
    const [activeDuring, setActiveDuring] = useState(0);
    const [error, setError] = useState(null);
    const controllerRef = useRef(null);

    // Abort a running test if the user navigates away.
    useEffect(() => () => controllerRef.current?.abort(), []);

    const onThroughput = buckets => {
        const trace = buckets.samples.slice(-TRACE_LENGTH).map(s => bytesToMbps(s.bytes, s.width));
        setLive({
            mbps: buckets.currentMbps,
            trace,
            progress: Math.min(100, (buckets.elapsedMs / (PHASE_SECONDS * 1000)) * 100),
            rtts: [],
        });
    };

    const sampleActive = async () => {
        try {
            const during = await fetchInfo();
            setActiveDuring(prev => Math.max(prev, during.active_tests));
        } catch (e) {
            // Context only; the test result does not depend on it.
        }
    };

    const start = async () => {
        const controller = new AbortController();
        controllerRef.current = controller;
        const {signal} = controller;
        setResults(emptyResults());
        setError(null);
        setActiveDuring(0);
        setLive({mbps: 0, trace: [], progress: 0, rtts: []});

        try {
            try {
                setInfo(await fetchInfo());
            } catch (e) {
                setInfo(null);
                throw new Error('The WROLPi API could not be reached.');
            }

            setPhase('ping');
            const ping = await runPing({
                signal,
                onSample: rtts => setLive({mbps: 0, trace: [], progress: (rtts.length / PING_SAMPLES) * 100, rtts}),
            });
            if (signal.aborted) return;
            setResults(r => ({...r, ping}));

            setPhase('download');
            setLive({mbps: 0, trace: [], progress: 0, rtts: []});
            // Sample the counter while our own stream is open so concurrent testers show up.
            const midDownload = setTimeout(sampleActive, (PHASE_SECONDS * 1000) / 2);
            let download;
            try {
                download = await runDownload({signal, onProgress: onThroughput});
            } finally {
                clearTimeout(midDownload);
            }
            if (signal.aborted) return;
            setResults(r => ({...r, download}));

            setPhase('upload');
            setLive({mbps: 0, trace: [], progress: 0, rtts: []});
            const midUpload = setTimeout(sampleActive, (PHASE_SECONDS * 1000) / 2);
            let upload;
            try {
                upload = await runUpload({signal, onProgress: onThroughput});
            } finally {
                clearTimeout(midUpload);
            }
            if (signal.aborted) return;
            setResults(r => ({...r, upload}));

            setPhase('done');
        } catch (e) {
            if (signal.aborted) {
                return;
            }
            console.error(e);
            setError(e.message || 'The speed test failed.');
            setPhase('error');
        } finally {
            if (signal.aborted) {
                setPhase('cancelled');
            }
            controllerRef.current = null;
        }
    };

    const cancel = () => controllerRef.current?.abort();

    const running = ['ping', 'download', 'upload'].includes(phase);
    const finished = ['done', 'cancelled', 'error'].includes(phase);
    const others = otherActiveTests(info?.active_tests, activeDuring);

    const liveRtt = live.rtts.length ? live.rtts[live.rtts.length - 1] : null;
    const liveTrace = phase === 'ping' ? live.rtts : live.trace;
    const liveValue = phase === 'ping'
        ? (liveRtt === null ? '—' : formatMs(liveRtt))
        : formatMbps(live.mbps);
    const liveUnit = phase === 'ping' ? 'ms' : 'Mbps';

    return <div className='wrolpi-speedtest'>
        <Panel>
            <Grid>
                <Grid.Col span={{base: 12, sm: 4}}>
                    {running
                        ? <Button color='red' onClick={cancel} icon='stop'>Cancel</Button>
                        : <Button color='blue' onClick={start} icon='tachometer alternate'>
                            {finished ? 'Run again' : 'Start test'}
                        </Button>}
                </Grid.Col>
                <Grid.Col span={{base: 12, sm: 8}}>
                    <Text size='sm' c='dimmed' data-testid='speedtest-phase'>{PHASES[phase].label}</Text>
                    {running && <Progress percent={live.progress} showPercent={false} color='blue'/>}
                </Grid.Col>
            </Grid>

            {running && <div style={{marginTop: '1em'}} data-testid='speedtest-live'>
                <div style={{display: 'flex', alignItems: 'baseline', gap: '0.5em'}}>
                    <span style={{fontSize: '2.5rem', fontWeight: 600, fontVariantNumeric: 'tabular-nums'}}>
                        {liveValue}
                    </span>
                    <span style={{color: 'var(--muted)'}}>{liveUnit}</span>
                </div>
                <Sparkline values={liveTrace} height={56} color='blue'
                           label={phase === 'ping' ? 'Round trip time per ping' : `${PHASES[phase].label} throughput`}/>
            </div>}

            {error && <Message kind='error' title='Speed test failed'>{error}</Message>}
        </Panel>

        {(results.ping || results.download || results.upload) && <>
            <Header as='h3'>Results</Header>
            <StatisticGroup data-testid='speedtest-results'>
                {results.download && <Statistic value={`${formatMbps(results.download.mbps)} Mbps`} label='Download'/>}
                {results.upload && <Statistic value={`${formatMbps(results.upload.mbps)} Mbps`} label='Upload'/>}
                {results.ping && <Statistic value={`${formatMs(results.ping.median)} ms`} label='Ping'/>}
                {results.ping && <Statistic value={`${formatMs(results.ping.jitter)} ms`} label='Jitter'/>}
            </StatisticGroup>

            <Table>
                <Table.Body>
                    {results.download && <Table.Row>
                        <Table.Cell style={{fontWeight: 600}}>Download</Table.Cell>
                        <Table.Cell>{formatMbps(results.download.mbps)} Mbps</Table.Cell>
                        <Table.Cell>{formatMbps(mbpsToMBps(results.download.mbps))} MB/s</Table.Cell>
                        <Table.Cell>peak {formatMbps(results.download.peak)} Mbps</Table.Cell>
                    </Table.Row>}
                    {results.upload && <Table.Row>
                        <Table.Cell style={{fontWeight: 600}}>Upload</Table.Cell>
                        <Table.Cell>{formatMbps(results.upload.mbps)} Mbps</Table.Cell>
                        <Table.Cell>{formatMbps(mbpsToMBps(results.upload.mbps))} MB/s</Table.Cell>
                        <Table.Cell>peak {formatMbps(results.upload.peak)} Mbps</Table.Cell>
                    </Table.Row>}
                    {results.ping && <Table.Row>
                        <Table.Cell style={{fontWeight: 600}}>Ping</Table.Cell>
                        <Table.Cell>{formatMs(results.ping.median)} ms median</Table.Cell>
                        <Table.Cell>{formatMs(results.ping.min)} ms best</Table.Cell>
                        <Table.Cell>
                            <PingVerdict median={results.ping.median}/>
                            {results.ping.lost > 0 && ` ${results.ping.lost} of ${PING_SAMPLES} lost`}
                        </Table.Cell>
                    </Table.Row>}
                </Table.Body>
            </Table>

            <ConnectionContext info={info} hotspotConnected={hotspotConnected} others={others}/>

            {results.download && <StreamCapacity mbps={results.download.mbps}/>}
        </>}

        {phase === 'idle' && <Text size='sm' c='dimmed' style={{marginTop: '1em'}}>
            Runs {PING_SAMPLES} pings, then a {PHASE_SECONDS} second download and a {PHASE_SECONDS} second
            upload between this device and the WROLPi. Nothing is saved.
        </Text>}
    </div>
}

function PingVerdict({median}) {
    const {kind, text} = describePing(median);
    const color = {success: 'green', warning: 'yellow', danger: 'red'}[kind] || 'grey';
    return <Label color={color}>{text}</Label>;
}

export function ConnectionContext({info, hotspotConnected, others}) {
    if (!info) {
        return null;
    }
    const viaHotspot = hotspotConnected && isHotspotAddress(info.client_ip);
    return <Text size='sm' style={{marginTop: '0.5em'}} data-testid='speedtest-context'>
        Tested from <code>{info.client_ip}</code>{' '}
        {viaHotspot
            ? <Label color='blue' icon='wifi'>via WROLPi hotspot</Label>
            : <Label color='grey'>via LAN</Label>}
        {others > 0 && <span> {others === 1 ? '1 other speed test was' : `${others} other speed tests were`} running
            at the same time, so the link was shared.</span>}
    </Text>;
}

export function StreamCapacity({mbps}) {
    const rows = streamCapacity(mbps);
    return <div data-testid='speedtest-capacity'>
        <Header as='h3'>Simultaneous video streams</Header>
        <Table>
            <Table.Header>
                <Table.Row>
                    <Table.HeaderCell>Quality</Table.HeaderCell>
                    <Table.HeaderCell>About</Table.HeaderCell>
                    <Table.HeaderCell>Streams at once</Table.HeaderCell>
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {rows.map(row => <Table.Row key={row.key}>
                    <Table.Cell style={{fontWeight: 600}}>{row.label}</Table.Cell>
                    <Table.Cell>{row.mbps} Mbps</Table.Cell>
                    <Table.Cell>{row.streams}</Table.Cell>
                </Table.Row>)}
            </Table.Body>
        </Table>
        <Text size='sm' c='dimmed'>
            Measures the network between this device and the WROLPi. Videos are served from the drive, which
            can also limit how many play at once. Bitrates are typical for each resolution; individual videos
            vary.
        </Text>
    </div>;
}
