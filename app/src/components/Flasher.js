import React, {useContext, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Route, Routes} from "react-router";
import {Checkbox, Label, Message, Select, Button as SButton, Icon as SIcon} from "semantic-ui-react";
import {ESPLoader, Transport} from "esptool-js";
import {useDropzone} from "react-dropzone";
import _ from "lodash";
import {encodeMediaPath, humanFileSize, PageContainer, useTitle} from "./Common";
import {
    Button,
    darkTheme,
    Divider,
    Form,
    Header,
    Icon,
    List,
    Loader,
    Modal,
    Progress,
    Segment,
    Tab,
    Table,
    TextArea
} from "./Theme";
import {ThemeContext} from "../contexts/contexts";
import {deleteFlasherConfig, flasherSearch, getFlasherConfigs, saveFlasherConfig} from "../api";

// The suffix used to find flashable ESP32 firmware in the media directory.
const FIRMWARE_SUFFIX = '.bin';

// esptool-js reports a chip description like "ESP32-S2 (revision v0.0)"; take the family before " (".
export function chipFamily(description) {
    return (description || '').split(' (')[0].trim() || null;
}

// ESP image chip_id -> family name (matches esptool-js IMAGE_CHIP_ID values).
const ESP_CHIP_ID_NAMES = {
    0: 'ESP32', 2: 'ESP32-S2', 5: 'ESP32-C3', 9: 'ESP32-S3',
    12: 'ESP32-C2', 13: 'ESP32-C6', 16: 'ESP32-H2', 18: 'ESP32-C5',
};

// Known ESP chip names, sorted so each maps to a stable color — colors survive reboots/refreshes and only shift
// if a new name is added here.  A chip not in this list still gets a deterministic color via hashing below.
const KNOWN_ESP_CHIPS = [
    'ESP32', 'ESP32-S2', 'ESP32-S3', 'ESP32-C2', 'ESP32-C3',
    'ESP32-C5', 'ESP32-C6', 'ESP32-C61', 'ESP32-H2', 'ESP32-P4',
].sort();

// Paul Tol's "bright" qualitative palette (colorblind-safe) plus black, then four more distinct colors for
// headroom.  A label's *width* (chip-name length) is itself a discriminator, so two chips only need distinct
// colors when they render at the same width.  The first eight cover today's largest same-width group (the eight
// 8-character ESP32-* names); the extras let a same-width group grow past eight before colors would repeat.
// (Truly colorblind-distinct qualitative colors top out around ten, so beyond that distinctness is best-effort.)
const CHIP_COLORS = [
    '#4477aa', '#ee6677', '#228833', '#ccbb44', '#66ccee', '#aa3377', '#bbbbbb', '#000000',
    '#ee7733', '#332288', '#999933', '#882255',
];

// Assign each known chip a color *index within its own name-length group*.  Same-width chips therefore always get
// different (colorblind-distinguishable) colors, while chips of different widths may share one — the width tells
// them apart.  Built once from the sorted known list.
const CHIP_COLOR_INDEX = (() => {
    const perLength = {};
    const index = {};
    for (const name of KNOWN_ESP_CHIPS) {
        const slot = perLength[name.length] || 0;
        index[name] = slot;
        perLength[name.length] = slot + 1;
    }
    return index;
})();

// Deterministic background color for a chip label (see CHIP_COLORS/CHIP_COLOR_INDEX).  Unknown chips hash to a
// stable slot so they still get a consistent color.
export function chipColor(name) {
    if (!name) {
        return CHIP_COLORS[CHIP_COLORS.length - 1];
    }
    if (name in CHIP_COLOR_INDEX) {
        return CHIP_COLORS[CHIP_COLOR_INDEX[name] % CHIP_COLORS.length];
    }
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    }
    return CHIP_COLORS[hash % CHIP_COLORS.length];
}

// Black or white text for readability on a given hex background (YIQ brightness).
export function chipTextColor(hex) {
    const c = (hex || '').replace('#', '');
    if (c.length < 6) {
        return '#fff';
    }
    const r = parseInt(c.slice(0, 2), 16);
    const g = parseInt(c.slice(2, 4), 16);
    const b = parseInt(c.slice(4, 6), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 140 ? '#000' : '#fff';
}

export function chipIdName(chipId) {
    return ESP_CHIP_ID_NAMES[chipId] || `chip id ${chipId}`;
}

// Read the chip_id from an ESP application/bootloader image header: magic byte 0xE9 at offset 0, chip_id as a
// uint16 LE at offset 0x0C.  Returns null for non-ESP-image files (partition tables start 0xAA, boot_app0 and
// littlefs are raw, etc.) — those carry no chip_id and must never be flagged as a mismatch.
export function espImageChipId(header) {
    if (!header || header.length < 14 || header[0] !== 0xE9) {
        return null;
    }
    return header[12] | (header[13] << 8);
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

// Read just the leading bytes of a firmware entry (enough for the ESP image header) without downloading the
// whole file.  Local files are sliced; media files use an HTTP Range request (the media server supports Range).
async function readEntryHeader(item) {
    if (item.file) {
        return new Uint8Array(await item.file.slice(0, 24).arrayBuffer());
    }
    const resp = await fetch(`/media/${encodeMediaPath(item.mediaPath)}`, {headers: {Range: 'bytes=0-23'}});
    if (!resp.ok) {
        return null;
    }
    return new Uint8Array(await resp.arrayBuffer()).slice(0, 24);
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
    const {t, theme} = useContext(ThemeContext);

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
    // The connected device's ESP image chip_id (0=ESP32, 2=S2, 9=S3, …); used to catch wrong-chip firmware.
    const [deviceChipId, setDeviceChipId] = useState(null);
    // Per-selected-file chip_id read from each ESP image header, aligned to `files` (null = not an ESP image or
    // unreadable).  Compared against deviceChipId to warn on the offending table row.
    const [fileChipIds, setFileChipIds] = useState([]);
    const [progress, setProgress] = useState(null); // {fileIndex, percent}
    const [error, setError] = useState('');
    // Set when a connection attempt fails, so we can remind the user to put the board into download/boot mode.
    const [bootHint, setBootHint] = useState(false);
    const [log, setLog] = useState('');
    const [logOpen, setLogOpen] = useState(false);
    const [flashOpen, setFlashOpen] = useState(false);
    // A flash failure, shown inside the flash modal (the top-of-page error banner is hidden behind the modal).
    const [flashError, setFlashError] = useState('');

    // Which firmware-source tab is active (controlled so a file drop can switch to "Add from computer").
    const [activeTab, setActiveTab] = useState(0);

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

    // Disabled while connecting or flashing (also gates the dropzone below).
    const busy = connecting || flashing;

    // First entry added defaults to offset 0x0 (a single merged image); later parts default to blank so the user
    // must set their offset deliberately.
    const nextDefaultAddress = (prev, idx) => (prev.length === 0 && idx === 0 ? '0x0' : '');

    // Add local File objects to the firmware list.  Shared by the file input and drag-and-drop.
    const addFiles = (selected) => {
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
    };

    // The "Add from computer" tab (index 2 in firmwarePanes) hosts the dropzone; a drop anywhere on the page or a
    // click on the zone lands here.
    const COMPUTER_TAB_INDEX = 2;
    const onDrop = React.useCallback((droppedFiles) => {
        // Only take .bin firmware; anything else dropped is ignored.
        const bins = (droppedFiles || []).filter(file => file.name.toLowerCase().endsWith(FIRMWARE_SUFFIX));
        if (bins.length > 0) {
            addFiles(bins);
            setActiveTab(COMPUTER_TAB_INDEX);
        }
    }, []);  // eslint-disable-line react-hooks/exhaustive-deps
    // The dropzone root wraps the whole page so firmware can be dropped anywhere.  noClick/noKeyboard because the
    // page has its own controls; the file dialog is opened explicitly via open() from the dropzone in the tab.
    const {getRootProps, getInputProps, isDragActive, open} = useDropzone({
        onDrop,
        disabled: busy,
        noClick: true,
        noKeyboard: true,
    });

    // While the user drags a file over the page, jump to the "Add from computer" tab so the drop target is shown.
    useEffect(() => {
        if (isDragActive) {
            setActiveTab(COMPUTER_TAB_INDEX);
        }
    }, [isDragActive]);

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
    // "bffb" lists the firmware inside that directory).  The server inspects each .bin's header and returns its
    // chip/kind; when `chip` is set, only ESP images for that chip are returned (otherwise every .bin is listed,
    // including non-ESP parts like partition tables and littlefs).
    const fetchMediaFirmware = React.useCallback(async (pathFilter, chip) => {
        setMediaLoading(true);
        try {
            const [fileGroups] = await flasherSearch(chip || null, pathFilter || null);
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

    // Once connected, read each selected firmware's image chip_id so a wrong-chip file — e.g. an ESP32-S2
    // bootloader in an ESP32 set — can be flagged on its table row.  Non-ESP-image files (partition tables,
    // boot_app0, littlefs) carry no chip_id and read as null (never flagged).  Only the small header of each file
    // is read (Range request for media files).  Keyed on file identity so editing an offset doesn't re-fetch.
    const fileIdentityKey = files
        .map(item => item.mediaPath || (item.file ? `${item.file.name}:${item.file.size}` : item.name))
        .join('|');
    useEffect(() => {
        if (!connected || files.length === 0) {
            setFileChipIds([]);
            return;
        }
        let cancelled = false;
        (async () => {
            const ids = await Promise.all(files.map(async (item) => {
                try {
                    return espImageChipId(await readEntryHeader(item));
                } catch (e) {
                    return null;  // Unreadable header: just don't flag this file.
                }
            }));
            if (!cancelled) {
                setFileChipIds(ids);
            }
        })();
        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [connected, fileIdentityKey]);

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
        // Capture the device's image chip_id so selected firmware can be checked against it (ESP8266 has none).
        const detected = esploader.chip;
        setDeviceChipId(detected && typeof detected.IMAGE_CHIP_ID === 'number' ? detected.IMAGE_CHIP_ID : null);
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
            await connectAndDetect();
            // Filter by esptool's canonical chip name (e.g. "ESP32", not the "ESP32-D0WD-V3" variant from the
            // description) so it matches the backend's chip_id-derived names — otherwise the search finds nothing.
            const detected = esploaderRef.current && esploaderRef.current.chip;
            const family = detected && detected.CHIP_NAME ? detected.CHIP_NAME : null;
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
        setDeviceChipId(null);
        setFileChipIds([]);
        setProgress(null);
    };

    // Changing the selected firmware set invalidates the chip check performed at connect time.  Drop the
    // connection so the user must reconnect and be re-checked — otherwise loading a different (wrong-chip) saved
    // config while connected would appear valid against the previously-detected device.
    const prevFileKeyRef = useRef(fileIdentityKey);
    useEffect(() => {
        if (prevFileKeyRef.current !== fileIdentityKey) {
            prevFileKeyRef.current = fileIdentityKey;
            if (connected) {
                disconnect();
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fileIdentityKey, connected]);

    const handleFlash = async () => {
        if (!esploaderRef.current || files.length === 0) {
            return;
        }
        setError('');
        setBootHint(false);
        setFlashError('');
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
                // esptool-js 0.6.0 only implements compressed writes (compress:false throws
                // "Yet to handle Non Compressed writes"), so this must stay true.
                compress: true,
                reportProgress: (fileIndex, written, total) => {
                    setProgress({fileIndex, percent: total ? Math.round((written / total) * 100) : 0});
                },
            });
            await esploaderRef.current.after('hard_reset');
            appendLog('\nFlash complete! Unplug the device and power it back on to run the new firmware.\n');
        } catch (e) {
            const detail = e && e.message ? e.message : String(e);
            // Show the failure inside the flash modal (the page-level error banner is hidden behind it) and in
            // the log, so a failed flash can't be mistaken for a frozen one.
            setFlashError(detail);
            appendLog(`\nFlash failed: ${detail}\n`);
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

    // Every firmware file must have a valid hex offset before flashing is allowed.
    const offsetsValid = files.length > 0 && files.every(item => isValidHexOffset(item.address));

    // Estimated flash time from the total firmware size and the selected baud rate.
    const totalFlashBytes = files.reduce((sum, item) => sum + (item.size || 0), 0);
    const flashEtaText = humanDuration(estimateFlashSeconds(totalFlashBytes, baudrate));

    // The nested tab menu isn't inverted automatically; give it the inverted style in dark mode so it matches.
    const tabMenu = theme === darkTheme ? {inverted: true, attached: true} : {attached: true};

    // The firmware source is chosen via three tabs (see the ordered array below).
    const computerPane = {
            menuItem: 'Add from computer',
            render: () => <Tab.Pane>
                {/* Clickable drop target (files may also be dropped anywhere on the page, which routes here). */}
                <Segment
                    placeholder
                    onClick={busy ? undefined : open}
                    style={{
                        cursor: busy ? 'default' : 'pointer',
                        textAlign: 'center',
                        ...(isDragActive ? {outline: '2px dashed #2185d0', outlineOffset: '-2px'} : {}),
                    }}
                >
                    <Header icon {...t}>
                        <Icon name='microchip'/>
                        {isDragActive
                            ? <>Drop <code>.bin</code> firmware to add it</>
                            : <>Click here, or drop <code>.bin</code> firmware here</>}
                    </Header>
                </Segment>
                <p {...t} style={{marginTop: '1em', opacity: 0.8}}>
                    A single merged image is flashed at offset <code>0x0</code>. For multi-part firmware, add each
                    part and set its offset (e.g. bootloader <code>0x1000</code>, partitions <code>0x8000</code>,
                    app <code>0x10000</code>).
                </p>
            </Tab.Pane>,
    };
    const wrolpiPane = {
            menuItem: 'Choose from your WROLPi',
            render: () => <Tab.Pane>
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
                        {/* Plain (non-inverted) icon: Message backgrounds are light, so a themed white icon
                            vanishes. */}
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
                <div style={{marginTop: '1em', overflowX: 'auto'}}>
                    {mediaLoading
                        ? <Loader active inline='centered'/>
                        : (mediaResults.length === 0
                            ? <p {...t} style={{opacity: 0.7}}>
                                No <code>.bin</code> firmware found
                                {deviceChip ? ` for ${deviceChip}` : ' in your media directory'}
                                {mediaFilter ? ' matching that filter.' : '.'}
                            </p>
                            : <Table compact selectable unstackable>
                                <Table.Header>
                                    <Table.Row>
                                        <Table.HeaderCell>File</Table.HeaderCell>
                                        <Table.HeaderCell>Path</Table.HeaderCell>
                                        <Table.HeaderCell>Size</Table.HeaderCell>
                                        <Table.HeaderCell>Chip</Table.HeaderCell>
                                        <Table.HeaderCell>Kind</Table.HeaderCell>
                                        <Table.HeaderCell width={1}/>
                                    </Table.Row>
                                </Table.Header>
                                <Table.Body>
                                    {mediaResults.map(result => {
                                        const name = result.name || (result.primary_path || '').split('/').pop();
                                        // esp_kind is 'not_esp_image' for parts with no chip (partitions, littlefs).
                                        const kind = result.esp_kind && result.esp_kind !== 'not_esp_image'
                                            ? result.esp_kind : null;
                                        return <Table.Row key={result.primary_path}>
                                            <Table.Cell>{name}</Table.Cell>
                                            <Table.Cell {...t} style={{opacity: 0.7, wordBreak: 'break-all'}}>
                                                {result.primary_path}
                                            </Table.Cell>
                                            <Table.Cell>{humanFileSize(result.size)}</Table.Cell>
                                            <Table.Cell>
                                                {result.esp_chip
                                                    ? <Label size='tiny' style={{
                                                        backgroundColor: chipColor(result.esp_chip),
                                                        color: chipTextColor(chipColor(result.esp_chip)),
                                                        borderColor: 'transparent',
                                                    }}>{result.esp_chip}</Label>
                                                    : <span style={{opacity: 0.5}}>—</span>}
                                            </Table.Cell>
                                            <Table.Cell>
                                                {kind || <span style={{opacity: 0.5}}>—</span>}
                                            </Table.Cell>
                                            <Table.Cell textAlign='center'>
                                                <Button icon='plus' size='mini' primary disabled={busy}
                                                        title='Add to selected firmware'
                                                        onClick={() => handleAddMediaFile(result)}/>
                                            </Table.Cell>
                                        </Table.Row>;
                                    })}
                                </Table.Body>
                            </Table>)}
                </div>
            </Tab.Pane>,
    };
    const savedPane = {
            menuItem: 'Saved Firmwares',
            render: () => <Tab.Pane>
                <p {...t} style={{opacity: 0.8}}>
                    Configure the firmware files and offsets, then save them as a named set to re-flash later
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
            </Tab.Pane>,
    };
    // Tab order: saved sets first, then the media picker, then a local file.
    const firmwarePanes = [savedPane, wrolpiPane, computerPane];

    return <div {...getRootProps()}>
        {/* The dropzone root wraps the whole page: firmware .bin files can be dropped anywhere and are routed to
            the "Add from computer" tab.  noClick is set, so this wrapper never opens the file dialog itself. */}
        <input {...getInputProps()}/>
        <PageContainer>
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
            <Tab
                menu={tabMenu}
                panes={firmwarePanes}
                activeIndex={activeTab}
                onTabChange={(e, {activeIndex}) => setActiveTab(activeIndex)}
            />

            {/* The selected firmware is shown below the source tabs so it stays visible regardless of which tab
                (computer / WROLPi / saved) the user is on. */}
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
                        {files.map((item, index) => {
                            // Flag (but never block) a file whose image targets a different chip than the device.
                            const fileChipId = fileChipIds[index];
                            const chipMismatch = deviceChipId !== null && fileChipId != null
                                && fileChipId !== deviceChipId;
                            return <Table.Row key={`${item.name}-${index}`} warning={chipMismatch}>
                            <Table.Cell>
                                <Icon name={item.mediaPath ? 'database' : 'file'}/>
                                {item.name} <span style={{opacity: 0.6}}>({humanFileSize(item.size)})</span>
                                {chipMismatch &&
                                    <Label color='red' size='tiny' style={{marginLeft: '0.5em'}}>
                                        <SIcon name='warning sign'/>
                                        Built for {chipIdName(fileChipId)}, not {chipIdName(deviceChipId)}
                                    </Label>}
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
                        </Table.Row>;
                        })}
                    </Table.Body>
                </Table>
                {/* Save lives here (not in the Saved Firmwares tab) so the current selection can be saved from
                    any source tab. */}
                <Button icon labelPosition='left' disabled={busy || saveableFiles.length === 0}
                        onClick={() => setSaveModalOpen(true)}>
                    <Icon name='save'/>
                    Save current firmware
                </Button>
            </>}
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
            <Modal.Header>{flashing ? 'Flashing device…' : (flashError ? 'Flash failed' : 'Flash complete')}</Modal.Header>
            <Modal.Content scrolling>
                {progress !== null &&
                    <Progress percent={progress.percent} progress indicating={flashing}
                              error={!!flashError} autoSuccess={!flashError}>
                        {flashing ? `Writing file ${progress.fileIndex + 1} of ${files.length}`
                            : (flashError ? 'Failed' : 'Done')}
                    </Progress>}
                {flashing && flashEtaText &&
                    <p {...t} style={{opacity: 0.8}}>
                        Estimated total time: ~{flashEtaText} at {baudrate.toLocaleString()} baud. Keep this tab
                        open and do not unplug the device.
                    </p>}
                {/* Surface a failure right here — otherwise a failed flash looks identical to a frozen one. */}
                {flashError &&
                    <Message error>
                        <SIcon name='warning circle'/>
                        <Message.Content>
                            <Message.Header>Flashing failed</Message.Header>
                            <p>{flashError}</p>
                        </Message.Content>
                    </Message>}
                {!flashing && !flashError && progress !== null &&
                    <Message success>
                        <SIcon name='check circle'/>
                        <Message.Content>
                            <Message.Header>Flashing complete</Message.Header>
                            <p>Unplug the device and power it back on to run the new firmware.</p>
                        </Message.Content>
                    </Message>}
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
        </PageContainer>
    </div>;
}

export function FlasherRoute() {
    return <Routes>
        <Route path='/' exact element={<FlasherPage/>}/>
    </Routes>;
}
