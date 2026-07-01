import React, {useContext, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Route, Routes} from "react-router";
import {Checkbox, Label, Message, Select, Button as SButton, Icon as SIcon} from "semantic-ui-react";
import {ESPLoader, Transport} from "esptool-js";
import _ from "lodash";
import {encodeMediaPath, humanFileSize, PageContainer, useTitle} from "./Common";
import {Button, Divider, Form, Header, Icon, List, Loader, Modal, Progress, Segment, Table, TextArea} from "./Theme";
import {ThemeContext} from "../contexts/contexts";
import {deleteFlasherConfig, filesSearch, flasherSearch, getFlasherConfigs, saveFlasherConfig} from "../api";

// The suffix used to find flashable ESP32 firmware in the media directory.
const FIRMWARE_SUFFIX = '.bin';

// esptool-js reports a chip description like "ESP32-S2 (revision v0.0)"; take the family before " (".
export function chipFamily(description) {
    return (description || '').split(' (')[0].trim() || null;
}

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

// A flash offset must be a 0x-prefixed hex string, e.g. "0x0" or "0x10000".
const HEX_OFFSET_RE = /^0x[0-9a-f]+$/i;

export function isValidHexOffset(value) {
    return HEX_OFFSET_RE.test((value || '').trim());
}

// Parse a validated hex flash offset like "0x10000" or "0x0" into a number.
export function parseAddress(value) {
    const trimmed = (value || '').trim();
    if (trimmed === '') {
        throw new Error('Flash offset is required');
    }
    if (!isValidHexOffset(trimmed)) {
        throw new Error(`Invalid flash offset (expected a hex value like 0x10000): ${value}`);
    }
    return parseInt(trimmed, 16);
}

// Rough estimate of how long flashing will take, in seconds.  Serial is 8N1 (10 bits per byte), so the link
// carries ~baud/10 bytes/sec; esptool-js compresses the image (~0.6x), which roughly offsets SLIP framing and
// flash-write overhead, making raw bytes / (baud/10) a reasonable ballpark.
export function estimateFlashSeconds(totalBytes, baudrate) {
    if (!totalBytes || !baudrate) {
        return 0;
    }
    return totalBytes / (baudrate / 10);
}

// Format a duration in seconds as e.g. "45s" or "2m 5s".
export function humanDuration(seconds) {
    if (!seconds || !isFinite(seconds) || seconds <= 0) {
        return null;
    }
    const total = Math.round(seconds);
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return minutes > 0 ? `${minutes}m ${secs}s` : `${secs}s`;
}

// Reject if `promise` doesn't settle within `ms`.  esptool-js's connect can hang indefinitely when a board is
// not in download mode; this guarantees the caller always gets a result so the UI can recover.
export function withTimeout(promise, ms, message) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), ms);
    });
    // Swallow a late rejection from the raced promise so it doesn't surface as an unhandled rejection.
    promise.catch(() => {
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

// How long to wait for a device to connect before giving up (esptool-js retries can otherwise stall the UI).
const CONNECT_TIMEOUT_MS = 30_000;

// A read-only log TextArea that auto-scrolls to the newest output — but only when the user is already at the
// bottom, so scrolling up to read earlier lines isn't yanked back down.  Starts at the bottom on mount (e.g. when
// a modal opens).
function AutoScrollLog({value, ...props}) {
    const containerRef = useRef(null);
    const atBottomRef = useRef(true);

    const getTextArea = () => containerRef.current && containerRef.current.querySelector('textarea');

    const handleScroll = (e) => {
        const el = e.target;
        // Treat "within a few px of the bottom" as at-bottom so it re-sticks when the user scrolls back down.
        atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 20;
    };

    useLayoutEffect(() => {
        const el = getTextArea();
        if (el && atBottomRef.current) {
            el.scrollTop = el.scrollHeight;
        }
    }, [value]);

    return <div ref={containerRef}>
        <TextArea readOnly value={value} onScroll={handleScroll} {...props}/>
    </div>;
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
    // When set (e.g. "ESP32-S2"), the picker only shows firmware for that chip (detected from the device).
    const [deviceChip, setDeviceChip] = useState(null);
    const deviceChipRef = useRef(null);  // Mirror for the debounced fetch closure.

    const [connected, setConnected] = useState(false);
    const [connecting, setConnecting] = useState(false);
    const [flashing, setFlashing] = useState(false);
    const [chip, setChip] = useState('');
    const [progress, setProgress] = useState(null); // {fileIndex, percent}
    const [error, setError] = useState('');
    // Set when a connection attempt fails, so we can remind the user to put the board into download/boot mode.
    const [bootHint, setBootHint] = useState(false);
    const [log, setLog] = useState('');
    const [logOpen, setLogOpen] = useState(false);
    const [flashOpen, setFlashOpen] = useState(false);

    // Saved firmware configurations (flasher.yaml).
    const [savedConfigs, setSavedConfigs] = useState([]);
    const [saveModalOpen, setSaveModalOpen] = useState(false);
    const [saveName, setSaveName] = useState('');

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

    // Fetch firmware for the picker.  `pathFilter` is a case-insensitive match against the full file path (so
    // "bffb" lists the firmware inside that directory).  When `chip` is set, only ESP images for that chip are
    // returned (server inspects each file's header); otherwise all .bin files are listed.
    const fetchMediaFirmware = React.useCallback(async (pathFilter, chip) => {
        setMediaLoading(true);
        try {
            let fileGroups;
            if (chip) {
                [fileGroups] = await flasherSearch(chip, pathFilter || null);
            } else {
                [fileGroups] = await filesSearch(0, 50, null, null, null, null,
                    false, null, null, null, false, null, FIRMWARE_SUFFIX, pathFilter || null);
            }
            setMediaResults(fileGroups || []);
        } catch (e) {
            // Surface connectivity errors instead of showing the empty "no firmware found" state, which would
            // be indistinguishable from genuinely having no firmware.
            setError(e && e.message ? e.message : String(e));
            setBootHint(false);
            setMediaResults([]);
        } finally {
            setMediaLoading(false);
        }
    }, []);

    // Auto-fetch on page load.
    useEffect(() => {
        fetchMediaFirmware('', null);
    }, [fetchMediaFirmware]);

    // Debounce filter changes so we don't fire a request on every keystroke.  Reads the device chip from a ref
    // so the (once-created) debounced function always uses the current filter.
    const debouncedFetch = useRef(_.debounce((value) => fetchMediaFirmware(value, deviceChipRef.current), 400)).current;
    // Cancel any pending debounced fetch on unmount so it can't setState on a gone component.
    useEffect(() => () => debouncedFetch.cancel(), [debouncedFetch]);
    const handleMediaFilterChange = (value) => {
        setMediaFilter(value);
        debouncedFetch(value);
    };

    const applyDeviceChip = (chip) => {
        deviceChipRef.current = chip;
        setDeviceChip(chip);
        fetchMediaFirmware(mediaFilter, chip);
    };

    // Saved firmware configurations.
    const fetchSavedConfigs = React.useCallback(async () => {
        setSavedConfigs(await getFlasherConfigs());
    }, []);

    useEffect(() => {
        fetchSavedConfigs();
    }, [fetchSavedConfigs]);

    // Media firmware entries that can be persisted (local computer files have no stable path, so are excluded).
    const saveableFiles = files.filter(item => item.mediaPath);

    const handleSaveConfig = async () => {
        const name = saveName.trim();
        if (!name) {
            return;
        }
        const payload = saveableFiles.map(item => ({
            path: item.mediaPath, address: item.address, name: item.name, size: item.size,
        }));
        if (await saveFlasherConfig(name, payload, eraseAll)) {
            setSaveModalOpen(false);
            setSaveName('');
            await fetchSavedConfigs();
        }
    };

    // Load a saved configuration into the firmware list, replacing the current selection.
    const handleLoadConfig = (configuration) => {
        setFiles((configuration.files || []).map(f => ({
            mediaPath: f.path,
            address: f.address || '',
            name: f.name || (f.path || '').split('/').pop(),
            size: f.size,
        })));
        setEraseAll(!!configuration.erase_all);
    };

    const handleDeleteConfig = async (name) => {
        if (await deleteFlasherConfig(name)) {
            await fetchSavedConfigs();
        }
    };

    const handleAddressChange = (index, value) => {
        setFiles(prev => prev.map((item, i) => i === index ? {...item, address: value} : item));
    };

    const handleRemoveFile = (index) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    // Open the serial port and detect the chip.  Returns the chip description string (e.g. "ESP32-S2 (...)").
    const connectAndDetect = async () => {
        const port = await navigator.serial.requestPort();
        const transport = new Transport(port, true);
        // Store the transport before main() so a failure below still reaches disconnect() and releases the
        // serial port (otherwise the port stays locked until the page is refreshed).
        transportRef.current = transport;
        const esploader = new ESPLoader({transport, baudrate, terminal});
        // esptool-js can hang forever if the board is not in download mode; bound it so the UI always recovers.
        const chipDescription = await withTimeout(esploader.main(), CONNECT_TIMEOUT_MS,
            'Timed out waiting for the device to respond.');
        esploaderRef.current = esploader;
        setChip(chipDescription);
        setConnected(true);
        return chipDescription;
    };

    const handleConnectError = async (e) => {
        // A user cancelling the browser's device picker throws; treat that quietly.
        if (e && e.name === 'NotFoundError') {
            appendLog('No device selected.\n');
        } else {
            const detail = e && e.message ? e.message : String(e);
            setError(detail);
            // A connect/sync failure is usually the board not being in download mode; remind the user.
            setBootHint(true);
            // Also record it in the log, which otherwise freezes at "Connecting..." with no indication of failure.
            appendLog(`\nConnection failed: ${detail}\n`);
        }
        await disconnect();
    };

    const handleConnect = async () => {
        setError('');
        setBootHint(false);
        setConnecting(true);
        try {
            await connectAndDetect();
        } catch (e) {
            await handleConnectError(e);
        } finally {
            setConnecting(false);
        }
    };

    // Layman flow: (re)detect the connected device and filter the firmware list to its chip.  Always releases any
    // existing connection and prompts for the port again, so swapping to a different ESP device is detected fresh.
    const handleFilterByDevice = async () => {
        setError('');
        setBootHint(false);
        setConnecting(true);
        try {
            await disconnect();
            const family = chipFamily(await connectAndDetect());
            if (family) {
                applyDeviceChip(family);
            }
        } catch (e) {
            await handleConnectError(e);
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
        setBootHint(false);
        setFlashOpen(true);
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
            setBootHint(false);
        } finally {
            setFlashing(false);
        }
    };

    if (!webSerialSupported()) {
        return <PageContainer>
            <Header as='h1'>Flasher</Header>
            <Message icon warning>
                <SIcon name='warning sign'/>
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
    // Every firmware file must have a valid hex offset before flashing is allowed.
    const offsetsValid = files.length > 0 && files.every(item => isValidHexOffset(item.address));

    // Estimated flash time from the total firmware size and the selected baud rate.
    const totalFlashBytes = files.reduce((sum, item) => sum + (item.size || 0), 0);
    const flashEtaText = humanDuration(estimateFlashSeconds(totalFlashBytes, baudrate));

    return <PageContainer>
        <Header as='h1'>Flasher</Header>
        <p {...t}>
            Flash firmware onto an ESP32/ESP8266 device directly from your browser over USB. Choose one or more
            firmware <code>.bin</code> files &mdash; from your computer or from your WROLPi's media directory &mdash;
            connect your device, then flash. The flash happens entirely in your browser and is written straight to
            the device over USB.
        </p>

        {/* Connection errors render inside the Connect segment (below), where the user just clicked.  Other
            errors show here at the top. */}
        {error && !bootHint && <Message error onDismiss={() => setError('')}>
            <Message.Header>Error</Message.Header>
            <p>{error}</p>
        </Message>}

        <Segment>
            <Header as='h3'>1. Firmware files</Header>
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

            <Divider/>
            <Header as='h4'>Or choose firmware from your WROLPi</Header>
            <p {...t} style={{opacity: 0.8}}>
                Not sure which file you need? Plug in your device and let WROLPi show only the firmware that
                matches it.
            </p>
            {/* Always available so a user who swaps to a different ESP device can re-detect it. */}
            <Button
                icon labelPosition='left'
                loading={connecting}
                disabled={busy}
                onClick={handleFilterByDevice}
            >
                <Icon name='usb'/>
                {deviceChip ? 'Detect a different device' : 'Filter files by detecting device'}
            </Button>
            {deviceChip &&
                <Message info>
                    {/* Plain (non-inverted) icon: Message backgrounds are light, so a themed white icon vanishes. */}
                    <SIcon name='microchip'/>
                    Showing firmware for <b>{deviceChip}</b>.
                    <SButton size='tiny' compact onClick={() => applyDeviceChip(null)}
                             disabled={busy} style={{marginLeft: '1em'}}>
                        Show all firmware
                    </SButton>
                </Message>}
            <Form style={{marginTop: '1em'}}>
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
                            No <code>.bin</code> firmware found
                            {deviceChip ? ` for ${deviceChip}` : ' in your media directory'}
                            {mediaFilter ? ' matching that filter.' : '.'}
                        </p>
                        : <List divided relaxed selection>
                            {mediaResults.map(result => <List.Item
                                key={result.primary_path}
                                onClick={busy ? undefined : () => handleAddMediaFile(result)}
                                style={busy ? {opacity: 0.5} : {cursor: 'pointer'}}
                            >
                                <List.Icon name='plus' verticalAlign='middle'/>
                                <List.Content>
                                    <List.Header>
                                        {result.name || result.primary_path}
                                        {result.esp_kind &&
                                            <Label size='tiny' color={result.esp_kind === 'factory' ? 'green' : 'grey'}
                                                   style={{marginLeft: '0.5em'}}>
                                                {result.esp_kind}
                                            </Label>}
                                    </List.Header>
                                    <List.Description {...t}>
                                        {result.primary_path} &mdash; {humanFileSize(result.size)}
                                        {result.esp_chip && ` — ${result.esp_chip}`}
                                    </List.Description>
                                </List.Content>
                            </List.Item>)}
                        </List>)}
            </div>

            {/* Selected files are shown below the picker so adding one doesn't shove the list down the page. */}
            {files.length > 0 && <>
                <Divider/>
                <Header as='h4'>Selected firmware</Header>
                <Table compact unstackable>
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
                                    error={!isValidHexOffset(item.address)}
                                    onChange={(e, {value}) => handleAddressChange(index, value)}
                                />
                            </Table.Cell>
                            <Table.Cell textAlign='center'>
                                <Button icon='trash' size='mini' color='red' disabled={busy}
                                        onClick={() => handleRemoveFile(index)}/>
                            </Table.Cell>
                        </Table.Row>)}
                    </Table.Body>
                </Table>
            </>}

            <Divider/>
            <Header as='h4'>Saved Firmwares</Header>
            <p {...t} style={{opacity: 0.8}}>
                Configure the firmware files and offsets above, then save them as a named set to re-flash later
                (e.g. a Meshtastic T-Deck: firmware at <code>0x0</code>, littlefs at <code>0xc90000</code>).
            </p>
            {savedConfigs.length > 0
                ? <List divided relaxed selection>
                    {savedConfigs.map(configuration => <List.Item key={configuration.name}>
                        <List.Content floated='right'>
                            <Button icon='trash' size='mini' color='red' disabled={busy}
                                    onClick={() => handleDeleteConfig(configuration.name)}/>
                        </List.Content>
                        <List.Icon name='save' verticalAlign='middle'/>
                        <List.Content onClick={busy ? undefined : () => handleLoadConfig(configuration)}
                                      style={busy ? {} : {cursor: 'pointer'}}>
                            <List.Header>{configuration.name}</List.Header>
                            <List.Description {...t}>
                                {(configuration.files || []).length} file(s)
                                {configuration.erase_all ? ' — erases flash' : ''}
                            </List.Description>
                        </List.Content>
                    </List.Item>)}
                </List>
                : <p {...t} style={{opacity: 0.7}}>No saved configurations yet.</p>}
            <Button icon labelPosition='left' disabled={busy || saveableFiles.length === 0}
                    onClick={() => setSaveModalOpen(true)} style={{marginTop: '0.5em'}}>
                <Icon name='save'/>
                Save current firmware
            </Button>
        </Segment>

        <Modal open={saveModalOpen} onClose={() => setSaveModalOpen(false)} size='tiny'>
            <Modal.Header>Save firmware configuration</Modal.Header>
            <Modal.Content>
                <Form onSubmit={handleSaveConfig}>
                    <Form.Input
                        autoFocus
                        label='Name'
                        placeholder='e.g. T-Deck Meshtastic UI'
                        value={saveName}
                        onChange={(e, {value}) => setSaveName(value)}
                    />
                    <p {...t} style={{opacity: 0.8}}>
                        Saving {saveableFiles.length} firmware file(s) from your WROLPi. An existing configuration
                        with the same name will be replaced.
                    </p>
                </Form>
            </Modal.Content>
            <Modal.Actions>
                <SButton onClick={() => setSaveModalOpen(false)}>Cancel</SButton>
                <Button primary disabled={!saveName.trim()} onClick={handleSaveConfig}>Save</Button>
            </Modal.Actions>
        </Modal>

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
                {connected &&
                    <Message positive>
                        <SIcon name='usb'/> Connected to <b>{chip}</b>
                    </Message>}
                {connected
                    ? <Button color='grey' disabled={busy} onClick={disconnect}>Disconnect</Button>
                    : <Button primary loading={connecting} disabled={busy} onClick={handleConnect}>
                        Connect Device
                    </Button>}
                <Button icon labelPosition='left' disabled={!log} onClick={() => setLogOpen(true)}>
                    <Icon name='terminal'/> Logs
                </Button>
            </Form>
            {/* Rendered outside <Form> so Semantic's ".ui.form .error.message { display:none }" rule doesn't
                hide it, and here (not at the top) so it is visible right where the user clicked Connect. */}
            {error && bootHint && <Message error onDismiss={() => {
                setError('');
                setBootHint(false);
            }} style={{marginTop: '1em'}}>
                <Message.Header>Could not connect to the device</Message.Header>
                <p>{error}</p>
                <p>
                    Many ESP boards must be put into <b>download mode</b> manually before flashing. Hold the
                    {' '}<b>BOOT</b> (or <b>IO0</b>) button, briefly press <b>RESET</b> (<b>EN</b>), then release
                    BOOT and try again. Also check the USB cable is a data cable and no other tab has the port
                    open.
                </p>
            </Message>}
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
                    disabled={!connected || flashing || files.length === 0 || !offsetsValid}
                    onClick={handleFlash}
                >
                    <Icon name='lightning'/> Flash Device
                </Button>
                {offsetsValid && flashEtaText &&
                    <span {...t} style={{marginLeft: '1em', opacity: 0.8}}>
                        Estimated time: ~{flashEtaText} at {baudrate.toLocaleString()} baud
                    </span>}
                {files.length > 0 && !offsetsValid &&
                    <p {...t} style={{marginTop: '0.5em', opacity: 0.8}}>
                        Every firmware file needs a valid hex flash offset (e.g. <code>0x0</code> or{' '}
                        <code>0x10000</code>).
                    </p>}
            </Form>
        </Segment>

        <Modal
            open={flashOpen}
            onClose={() => !flashing && setFlashOpen(false)}
            closeOnDimmerClick={!flashing}
            size='fullscreen'
        >
            <Modal.Header>{flashing ? 'Flashing device…' : 'Flash complete'}</Modal.Header>
            <Modal.Content scrolling>
                {progress !== null &&
                    <Progress percent={progress.percent} progress indicating={flashing} autoSuccess>
                        {flashing ? `Writing file ${progress.fileIndex + 1} of ${files.length}` : 'Done'}
                    </Progress>}
                {flashing && flashEtaText &&
                    <p {...t} style={{opacity: 0.8}}>
                        Estimated total time: ~{flashEtaText} at {baudrate.toLocaleString()} baud. Keep this tab
                        open and do not unplug the device.
                    </p>}
                <AutoScrollLog
                    value={log || 'Starting…'}
                    style={{fontFamily: 'monospace', width: '100%', minHeight: '60vh', whiteSpace: 'pre'}}
                />
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={() => setFlashOpen(false)} disabled={flashing}>Close</Button>
            </Modal.Actions>
        </Modal>

        <Modal open={logOpen} onClose={() => setLogOpen(false)} size='fullscreen'>
            <Modal.Header>Flasher Log</Modal.Header>
            <Modal.Content scrolling>
                <AutoScrollLog
                    value={log || 'No activity yet.'}
                    style={{fontFamily: 'monospace', width: '100%', minHeight: '70vh', whiteSpace: 'pre'}}
                />
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={() => setLogOpen(false)}>Close</Button>
            </Modal.Actions>
        </Modal>
    </PageContainer>;
}

export function FlasherRoute() {
    return <Routes>
        <Route path='/' exact element={<FlasherPage/>}/>
    </Routes>;
}
