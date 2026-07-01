import React, {useContext, useEffect, useRef, useState} from 'react';
import {Route, Routes} from "react-router";
import {Checkbox, Message, Select} from "semantic-ui-react";
import {ESPLoader, Transport} from "esptool-js";
import _ from "lodash";
import {encodeMediaPath, humanFileSize, PageContainer, useTitle} from "./Common";
import {Button, Form, Header, Icon, List, Loader, Progress, Segment, Table, TextArea} from "./Theme";
import {ThemeContext} from "../contexts/contexts";
import {filesSearch} from "../api";

// The suffix used to find flashable ESP32 firmware in the media directory.
const FIRMWARE_SUFFIX = '.bin';

// Flashing happens entirely in the browser using the Web Serial API; nothing is uploaded to WROLPi.  esptool-js is
// bundled into the frontend build, so this works fully offline once the page has loaded.

const BAUD_OPTIONS = [
    {key: '115200', value: 115200, text: '115200 (safe)'},
    {key: '230400', value: 230400, text: '230400'},
    {key: '460800', value: 460800, text: '460800'},
    {key: '921600', value: 921600, text: '921600 (fast)'},
];

// Web Serial is only available in a secure context (HTTPS or localhost) on Chromium-based browsers.
export function webSerialSupported() {
    return typeof navigator !== 'undefined' && 'serial' in navigator;
}

function readFileAsUint8Array(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(new Uint8Array(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsArrayBuffer(file);
    });
}

// Load a firmware entry's bytes.  Local files are read from disk; media entries are fetched from the WROLPi
// media directory over HTTP.  Both return a Uint8Array as esptool-js expects.
async function readEntryBytes(item) {
    if (item.file) {
        return readFileAsUint8Array(item.file);
    }
    const resp = await fetch(`/media/${encodeMediaPath(item.mediaPath)}`);
    if (!resp.ok) {
        throw new Error(`Failed to fetch ${item.name} from the media directory (${resp.status})`);
    }
    const buffer = await resp.arrayBuffer();
    return new Uint8Array(buffer);
}

// Parse a user-entered flash offset like "0x10000", "0x0", or "65536".
export function parseAddress(value) {
    const trimmed = (value || '').trim();
    if (trimmed === '') {
        throw new Error('Flash offset is required');
    }
    const address = /^0x/i.test(trimmed) ? parseInt(trimmed, 16) : parseInt(trimmed, 10);
    if (!Number.isInteger(address) || address < 0) {
        throw new Error(`Invalid flash offset: ${value}`);
    }
    return address;
}

export function FlasherPage() {
    useTitle('Flasher');
    const {t} = useContext(ThemeContext);

    // Each entry is {name, size, address, file?: File, mediaPath?: string}.  A local file has `file`; a media
    // firmware has `mediaPath`.  Default offset 0x0 suits a single merged firmware image.
    const [files, setFiles] = useState([]);
    const [baudrate, setBaudrate] = useState(115200);
    const [eraseAll, setEraseAll] = useState(false);

    // Media-directory firmware picker.
    const [mediaFilter, setMediaFilter] = useState('');
    const [mediaResults, setMediaResults] = useState([]);
    const [mediaLoading, setMediaLoading] = useState(false);

    const [connected, setConnected] = useState(false);
    const [connecting, setConnecting] = useState(false);
    const [flashing, setFlashing] = useState(false);
    const [chip, setChip] = useState('');
    const [progress, setProgress] = useState(null); // {fileIndex, percent}
    const [error, setError] = useState('');
    const [log, setLog] = useState('');

    const transportRef = useRef(null);
    const esploaderRef = useRef(null);
    const logRef = useRef('');

    const appendLog = (data) => {
        logRef.current += data;
        setLog(logRef.current);
    };

    // esptool-js writes progress/status through this terminal interface.
    const terminal = {
        clean: () => {
            logRef.current = '';
            setLog('');
        },
        writeLine: (data) => appendLog(data + '\n'),
        write: (data) => appendLog(data),
    };

    // First entry added defaults to offset 0x0 (a single merged image); later parts default to blank so the user
    // must set their offset deliberately.
    const nextDefaultAddress = (prev, idx) => (prev.length === 0 && idx === 0 ? '0x0' : '');

    const handleAddFiles = (event) => {
        const selected = Array.from(event.target.files || []);
        if (selected.length > 0) {
            setFiles(prev => [
                ...prev,
                ...selected.map((file, idx) => ({
                    file,
                    name: file.name,
                    size: file.size,
                    address: nextDefaultAddress(prev, idx),
                })),
            ]);
        }
        // Reset the input so selecting the same file again re-triggers onChange.
        event.target.value = '';
    };

    const handleAddMediaFile = (result) => {
        setFiles(prev => [
            ...prev,
            {
                mediaPath: result.primary_path,
                name: result.name || result.primary_path,
                size: result.size,
                address: nextDefaultAddress(prev, 0),
            },
        ]);
    };

    // Fetch .bin firmware from the media directory, optionally filtered by a case-insensitive match against the
    // full file path (so a filter of "bffb" lists the firmware inside that directory).
    const fetchMediaFirmware = React.useCallback(async (pathFilter) => {
        setMediaLoading(true);
        try {
            const [fileGroups] = await filesSearch(0, 50, null, null, null, null,
                false, null, null, null, false, null, FIRMWARE_SUFFIX, pathFilter || null);
            setMediaResults(fileGroups || []);
        } finally {
            setMediaLoading(false);
        }
    }, []);

    // Auto-fetch on page load.
    useEffect(() => {
        fetchMediaFirmware('');
    }, [fetchMediaFirmware]);

    // Debounce filter changes so we don't fire a request on every keystroke.
    const debouncedFetch = useRef(_.debounce((value) => fetchMediaFirmware(value), 400)).current;
    const handleMediaFilterChange = (value) => {
        setMediaFilter(value);
        debouncedFetch(value);
    };

    const handleAddressChange = (index, value) => {
        setFiles(prev => prev.map((item, i) => i === index ? {...item, address: value} : item));
    };

    const handleRemoveFile = (index) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleConnect = async () => {
        setError('');
        setConnecting(true);
        try {
            const port = await navigator.serial.requestPort();
            const transport = new Transport(port, true);
            const esploader = new ESPLoader({transport, baudrate, terminal});
            const chipDescription = await esploader.main();
            transportRef.current = transport;
            esploaderRef.current = esploader;
            setChip(chipDescription);
            setConnected(true);
        } catch (e) {
            // A user cancelling the browser's device picker throws; treat that quietly.
            if (e && e.name === 'NotFoundError') {
                appendLog('No device selected.\n');
            } else {
                setError(e && e.message ? e.message : String(e));
            }
            await disconnect();
        } finally {
            setConnecting(false);
        }
    };

    const disconnect = async () => {
        try {
            if (transportRef.current) {
                await transportRef.current.disconnect();
            }
        } catch (e) {
            // Ignore disconnect errors; the device may already be gone.
        }
        transportRef.current = null;
        esploaderRef.current = null;
        setConnected(false);
        setChip('');
        setProgress(null);
    };

    const handleFlash = async () => {
        if (!esploaderRef.current || files.length === 0) {
            return;
        }
        setError('');
        setFlashing(true);
        setProgress({fileIndex: 0, percent: 0});
        try {
            const fileArray = [];
            for (const item of files) {
                const address = parseAddress(item.address);
                const data = await readEntryBytes(item);
                fileArray.push({data, address});
            }
            await esploaderRef.current.writeFlash({
                fileArray,
                // 'keep' preserves the flash parameters baked into the firmware image, which is correct for
                // bring-your-own merged binaries.
                flashSize: 'keep',
                flashMode: 'keep',
                flashFreq: 'keep',
                eraseAll,
                compress: true,
                reportProgress: (fileIndex, written, total) => {
                    setProgress({fileIndex, percent: total ? Math.round((written / total) * 100) : 0});
                },
            });
            appendLog('\nFlash complete! Resetting device...\n');
            await esploaderRef.current.after('hard_reset');
        } catch (e) {
            setError(e && e.message ? e.message : String(e));
        } finally {
            setFlashing(false);
        }
    };

    if (!webSerialSupported()) {
        return <PageContainer>
            <Header as='h1'>Flasher</Header>
            <Message icon warning>
                <Icon name='warning sign'/>
                <Message.Content>
                    <Message.Header>Web Serial is not available</Message.Header>
                    <p>Flashing requires the Web Serial API, which is only available in Chromium-based browsers
                        (Chrome, Edge, Brave) served over a secure connection (HTTPS or <code>localhost</code>).</p>
                    <p>Open this page in Chrome or Edge over <code>https://</code> to flash your device. Firefox
                        and iOS are not supported.</p>
                </Message.Content>
            </Message>
        </PageContainer>;
    }

    const busy = connecting || flashing;

    return <PageContainer>
        <Header as='h1'>Flasher</Header>
        <p {...t}>
            Flash firmware onto an ESP32/ESP8266 device directly from your browser over USB. Choose one or more
            firmware <code>.bin</code> files &mdash; from your computer or from your WROLPi's media directory &mdash;
            connect your device, then flash. The flash happens entirely in your browser and is written straight to
            the device over USB.
        </p>

        {error && <Message error onDismiss={() => setError('')}>
            <Message.Header>Error</Message.Header>
            <p>{error}</p>
        </Message>}

        <Segment>
            <Header as='h3'>1. Firmware files</Header>
            {files.length > 0 && <Table compact unstackable>
                <Table.Header>
                    <Table.Row>
                        <Table.HeaderCell>File</Table.HeaderCell>
                        <Table.HeaderCell width={4}>Flash offset</Table.HeaderCell>
                        <Table.HeaderCell width={1}/>
                    </Table.Row>
                </Table.Header>
                <Table.Body>
                    {files.map((item, index) => <Table.Row key={`${item.name}-${index}`}>
                        <Table.Cell>
                            <Icon name={item.mediaPath ? 'database' : 'file'}/>
                            {item.name} <span style={{opacity: 0.6}}>({humanFileSize(item.size)})</span>
                        </Table.Cell>
                        <Table.Cell>
                            <Form.Input
                                fluid
                                size='small'
                                placeholder='0x10000'
                                value={item.address}
                                disabled={busy}
                                onChange={(e, {value}) => handleAddressChange(index, value)}
                            />
                        </Table.Cell>
                        <Table.Cell textAlign='center'>
                            <Button icon='trash' size='mini' color='red' disabled={busy}
                                    onClick={() => handleRemoveFile(index)}/>
                        </Table.Cell>
                    </Table.Row>)}
                </Table.Body>
            </Table>}

            <Button as='label' htmlFor='flasher-file-input' primary disabled={busy} icon labelPosition='left'>
                <Icon name='file'/>
                Add file from computer
            </Button>
            <input
                id='flasher-file-input'
                type='file'
                accept='.bin'
                multiple
                hidden
                onChange={handleAddFiles}
            />
            <p {...t} style={{marginTop: '1em', opacity: 0.8}}>
                A single merged image is flashed at offset <code>0x0</code>. For multi-part firmware, add each part
                and set its offset (e.g. bootloader <code>0x1000</code>, partitions <code>0x8000</code>,
                app <code>0x10000</code>).
            </p>

            <Header as='h4' dividing>Or choose firmware from your WROLPi</Header>
            <Form>
                <Form.Input
                    fluid
                    icon='search'
                    placeholder='Filter firmware by path (e.g. a folder name)...'
                    value={mediaFilter}
                    disabled={busy}
                    onChange={(e, {value}) => handleMediaFilterChange(value)}
                />
            </Form>
            <div style={{marginTop: '1em'}}>
                {mediaLoading
                    ? <Loader active inline='centered'/>
                    : (mediaResults.length === 0
                        ? <p {...t} style={{opacity: 0.7}}>
                            No <code>.bin</code> firmware found in your media directory
                            {mediaFilter ? ' matching that filter.' : '. Add .bin files to the media directory to see them here.'}
                        </p>
                        : <List divided relaxed selection>
                            {mediaResults.map(result => <List.Item
                                key={result.primary_path}
                                onClick={busy ? undefined : () => handleAddMediaFile(result)}
                                style={busy ? {opacity: 0.5} : {cursor: 'pointer'}}
                            >
                                <List.Icon name='plus' verticalAlign='middle'/>
                                <List.Content>
                                    <List.Header>{result.name || result.primary_path}</List.Header>
                                    <List.Description {...t}>
                                        {result.primary_path} &mdash; {humanFileSize(result.size)}
                                    </List.Description>
                                </List.Content>
                            </List.Item>)}
                        </List>)}
            </div>
        </Segment>

        <Segment>
            <Header as='h3'>2. Connect</Header>
            <Form>
                <Form.Field>
                    <label>Baud rate</label>
                    <Select
                        options={BAUD_OPTIONS}
                        value={baudrate}
                        disabled={connected || busy}
                        onChange={(e, {value}) => setBaudrate(value)}
                    />
                </Form.Field>
                {connected
                    ? <>
                        <Message positive>
                            <Icon name='usb'/> Connected to <b>{chip}</b>
                        </Message>
                        <Button color='grey' disabled={busy} onClick={disconnect}>Disconnect</Button>
                    </>
                    : <Button primary loading={connecting} disabled={busy} onClick={handleConnect}>
                        Connect Device
                    </Button>}
            </Form>
        </Segment>

        <Segment>
            <Header as='h3'>3. Flash</Header>
            <Form>
                <Form.Field>
                    <Checkbox
                        label='Erase all flash before writing'
                        checked={eraseAll}
                        disabled={busy}
                        onChange={(e, {checked}) => setEraseAll(checked)}
                    />
                </Form.Field>
                <Button
                    color='red'
                    loading={flashing}
                    disabled={!connected || flashing || files.length === 0}
                    onClick={handleFlash}
                >
                    <Icon name='lightning'/> Flash Device
                </Button>
            </Form>
            {progress !== null && <div style={{marginTop: '1em'}}>
                <Progress percent={progress.percent} progress indicating={flashing} autoSuccess>
                    {flashing ? `Writing file ${progress.fileIndex + 1} of ${files.length}` : 'Done'}
                </Progress>
            </div>}
        </Segment>

        {log && <Segment>
            <Header as='h3'>Log</Header>
            <TextArea
                readOnly
                value={log}
                style={{fontFamily: 'monospace', width: '100%', minHeight: '12em', whiteSpace: 'pre'}}
            />
        </Segment>}
    </PageContainer>;
}

export function FlasherRoute() {
    return <Routes>
        <Route path='/' exact element={<FlasherPage/>}/>
    </Routes>;
}
