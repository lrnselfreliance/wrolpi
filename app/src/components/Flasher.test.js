import React from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';

// esptool-js ships untranspiled ESM which Jest will not transform; mock it so importing Flasher.js is safe.
// Real classes (not jest.fn mock impls) so `new ESPLoader()` reliably yields an instance with main()/after().
// The `mock`-prefixed holders let individual tests model different chips (esptool-js sets esploader.chip with a
// canonical CHIP_NAME plus IMAGE_CHIP_ID during main()); defaults describe an ESP32-S2.
let mockChipName = 'ESP32-S2';
let mockChipId = 2;
let mockDescription = 'ESP32-S2 (revision v0.0)';
jest.mock('esptool-js', () => ({
    __esModule: true,
    ESPLoader: class {
        async main() {
            this.chip = {CHIP_NAME: mockChipName, IMAGE_CHIP_ID: mockChipId};
            return mockDescription;
        }

        async after() {
        }
    },
    Transport: class {
        async disconnect() {
        }
    },
}));

// Flasher fetches media firmware on mount; mock the API so tests don't hit the network.
jest.mock('../api', () => ({
    flasherSearch: jest.fn().mockResolvedValue([[], 0]),
    getFlasherConfigs: jest.fn().mockResolvedValue([]),
    saveFlasherConfig: jest.fn().mockResolvedValue(true),
    deleteFlasherConfig: jest.fn().mockResolvedValue(true),
}));

import {flasherSearch, getFlasherConfigs} from '../api';
import {
    chipColor,
    chipTextColor,
    chipFamily,
    chipIdName,
    espImageChipId,
    estimateFlashSeconds,
    FlasherPage,
    humanDuration,
    isValidHexOffset,
    parseAddress,
    webSerialSupported,
    withTimeout,
} from './Flasher';

describe('withTimeout', () => {
    it('resolves when the promise settles before the timeout', async () => {
        await expect(withTimeout(Promise.resolve('ok'), 50, 'too slow')).resolves.toBe('ok');
    });

    it('rejects with the message when the promise stalls (e.g. a hung connect)', async () => {
        await expect(withTimeout(new Promise(() => {}), 10, 'too slow')).rejects.toThrow('too slow');
    });
});

describe('estimateFlashSeconds', () => {
    it('estimates from total bytes and baud rate (8N1: baud/10 bytes/sec)', () => {
        // 115200 baud -> 11520 bytes/sec.  115200 bytes -> ~10s.
        expect(estimateFlashSeconds(115200, 115200)).toBeCloseTo(10, 5);
        // Faster baud -> proportionally less time.
        expect(estimateFlashSeconds(115200, 921600)).toBeCloseTo(1.25, 5);
    });

    it('returns 0 for missing size or baud', () => {
        expect(estimateFlashSeconds(0, 115200)).toBe(0);
        expect(estimateFlashSeconds(1000, 0)).toBe(0);
    });
});

describe('humanDuration', () => {
    it('formats seconds and minutes', () => {
        expect(humanDuration(45)).toBe('45s');
        expect(humanDuration(60)).toBe('1m 0s');
        expect(humanDuration(125)).toBe('2m 5s');
    });

    it('returns null for non-positive or invalid input', () => {
        expect(humanDuration(0)).toBeNull();
        expect(humanDuration(-5)).toBeNull();
        expect(humanDuration(Infinity)).toBeNull();
    });
});

describe('chipFamily', () => {
    it('extracts the chip family from an esptool-js description', () => {
        expect(chipFamily('ESP32-S2 (revision v0.0)')).toBe('ESP32-S2');
        expect(chipFamily('ESP32-S3')).toBe('ESP32-S3');
        expect(chipFamily('ESP32 (revision 3)')).toBe('ESP32');
    });

    it('returns null for empty input', () => {
        expect(chipFamily('')).toBeNull();
        expect(chipFamily(null)).toBeNull();
        expect(chipFamily(undefined)).toBeNull();
    });
});

describe('espImageChipId', () => {
    // ESP image header: magic 0xE9 at byte 0, chip_id as uint16 LE at offset 0x0C.
    const header = (magic, chipId) => {
        const h = new Uint8Array(24);
        h[0] = magic;
        h[12] = chipId & 0xFF;
        h[13] = (chipId >> 8) & 0xFF;
        return h;
    };

    it('reads the chip_id from an ESP image header', () => {
        expect(espImageChipId(header(0xE9, 0))).toBe(0);   // ESP32
        expect(espImageChipId(header(0xE9, 2))).toBe(2);   // ESP32-S2
        expect(espImageChipId(header(0xE9, 9))).toBe(9);   // ESP32-S3
    });

    it('returns null for non-ESP-image files (no chip_id to compare)', () => {
        expect(espImageChipId(header(0xAA, 0))).toBeNull(); // partition table magic
        expect(espImageChipId(new Uint8Array([0x00, 0x01]))).toBeNull(); // too short / raw (boot_app0)
        expect(espImageChipId(null)).toBeNull();
    });
});

describe('chipColor', () => {
    it('is deterministic — the same chip always gets the same color', () => {
        expect(chipColor('ESP32')).toBe(chipColor('ESP32'));
        expect(chipColor('ESP32-S3')).toBe(chipColor('ESP32-S3'));
    });

    it('gives every same-width chip a distinct color (the colorblind aid)', () => {
        // All the 8-character ESP32-* names render at the same width, so they must never share a color.
        const sameWidth = ['ESP32-S2', 'ESP32-S3', 'ESP32-C2', 'ESP32-C3',
            'ESP32-C5', 'ESP32-C6', 'ESP32-H2', 'ESP32-P4'];
        const colors = sameWidth.map(chipColor);
        expect(new Set(colors).size).toBe(sameWidth.length);
    });

    it('may reuse a color across different widths (width itself disambiguates)', () => {
        // ESP32 (5 chars) and a same-index 8-char chip can share a color — different widths tell them apart.
        expect(chipColor('ESP32')).toBe(chipColor('ESP32-C2'));
    });

    it('returns a valid palette color for known, unknown, and empty names', () => {
        const hex = /^#[0-9a-f]{6}$/i;
        expect(chipColor('ESP32')).toMatch(hex);
        expect(chipColor('ESP32-FUTURE')).toMatch(hex); // unknown -> stable hash
        expect(chipColor('ESP32-FUTURE')).toBe(chipColor('ESP32-FUTURE'));
        expect(chipColor(null)).toMatch(hex);
    });
});

describe('chipTextColor', () => {
    it('uses white text on dark backgrounds and black on light ones', () => {
        expect(chipTextColor('#000000')).toBe('#fff'); // black bg
        expect(chipTextColor('#4477aa')).toBe('#fff'); // Tol blue (dark)
        expect(chipTextColor('#ccbb44')).toBe('#000'); // Tol yellow (light)
        expect(chipTextColor('#bbbbbb')).toBe('#000'); // grey (light)
    });
});

describe('chipIdName', () => {
    it('maps known chip ids to family names', () => {
        expect(chipIdName(0)).toBe('ESP32');
        expect(chipIdName(2)).toBe('ESP32-S2');
        expect(chipIdName(9)).toBe('ESP32-S3');
        // Must match the backend ESP_CHIP_IDS map: 17 -> C5, 18 -> P4 (not the reverse).
        expect(chipIdName(17)).toBe('ESP32-C5');
        expect(chipIdName(18)).toBe('ESP32-P4');
    });

    it('falls back to a readable string for unknown ids', () => {
        expect(chipIdName(99)).toBe('chip id 99');
    });
});

describe('isValidHexOffset', () => {
    it('accepts 0x-prefixed hex strings', () => {
        expect(isValidHexOffset('0x0')).toBe(true);
        expect(isValidHexOffset('0x10000')).toBe(true);
        expect(isValidHexOffset('0XABCDEF')).toBe(true);
        expect(isValidHexOffset('  0x8000  ')).toBe(true);
    });

    it('rejects non-hex, un-prefixed, and empty values', () => {
        expect(isValidHexOffset('')).toBe(false);
        expect(isValidHexOffset('   ')).toBe(false);
        expect(isValidHexOffset('10000')).toBe(false); // missing 0x prefix
        expect(isValidHexOffset('0x')).toBe(false); // no digits
        expect(isValidHexOffset('0xZZ')).toBe(false); // not hex
        expect(isValidHexOffset('nope')).toBe(false);
        expect(isValidHexOffset('0x1000 extra')).toBe(false);
    });
});

describe('parseAddress', () => {
    it('parses valid hex offsets', () => {
        expect(parseAddress('0x0')).toBe(0);
        expect(parseAddress('0x1000')).toBe(0x1000);
        expect(parseAddress('0X10000')).toBe(0x10000);
        expect(parseAddress('  0x8000  ')).toBe(0x8000);
    });

    it('rejects empty offsets', () => {
        expect(() => parseAddress('')).toThrow(/required/);
        expect(() => parseAddress('   ')).toThrow(/required/);
    });

    it('rejects non-hex offsets', () => {
        expect(() => parseAddress('nope')).toThrow(/Invalid/);
        expect(() => parseAddress('0xZZ')).toThrow(/Invalid/);
        expect(() => parseAddress('65536')).toThrow(/Invalid/); // decimal is no longer accepted
    });
});

describe('webSerialSupported', () => {
    const original = Object.getOwnPropertyDescriptor(global.navigator, 'serial');

    afterEach(() => {
        if (original) {
            Object.defineProperty(global.navigator, 'serial', original);
        } else {
            delete global.navigator.serial;
        }
    });

    it('is false when navigator.serial is missing', () => {
        delete global.navigator.serial;
        expect(webSerialSupported()).toBe(false);
    });

    it('is true when navigator.serial is present', () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        expect(webSerialSupported()).toBe(true);
    });
});

// The firmware sources live behind three tabs; click a tab's menu item to reveal its pane.  PageContainer renders
// both breakpoints (fresnel Media), so the menu item appears twice — clicking the first is enough.
function switchTab(name) {
    fireEvent.click(screen.getAllByText(name)[0]);
}

describe('FlasherPage', () => {
    const original = Object.getOwnPropertyDescriptor(global.navigator, 'serial');

    beforeEach(() => {
        flasherSearch.mockClear();
        flasherSearch.mockResolvedValue([[], 0]);
        getFlasherConfigs.mockClear();
        getFlasherConfigs.mockResolvedValue([]);
        // Default the mocked chip back to ESP32-S2 for each test.
        mockChipName = 'ESP32-S2';
        mockChipId = 2;
        mockDescription = 'ESP32-S2 (revision v0.0)';
    });

    afterEach(() => {
        if (original) {
            Object.defineProperty(global.navigator, 'serial', original);
        } else {
            delete global.navigator.serial;
        }
    });

    // PageContainer renders both the mobile and desktop breakpoints (fresnel Media), so each label appears twice.
    it('warns when Web Serial is unavailable', () => {
        delete global.navigator.serial;
        render(<FlasherPage/>);
        expect(screen.getAllByText('Web Serial is not available').length).toBeGreaterThan(0);
        // The flashing controls must not render on an unsupported browser.
        expect(screen.queryByText('Connect Device')).not.toBeInTheDocument();
    });

    it('renders the flasher controls when Web Serial is available', () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        render(<FlasherPage/>);
        expect(screen.getAllByText('Connect Device').length).toBeGreaterThan(0);
        // "Add from computer" is now a non-default tab; switch to it to reveal the dropzone.
        switchTab('Add from computer');
        expect(screen.getAllByText(/Click here/).length).toBeGreaterThan(0);
        // Flash button is disabled until a device is connected and a file is added.
        expect(screen.getAllByText('Flash Device')[0].closest('button')).toBeDisabled();
    });

    it('fetches media firmware on load and lists it with chip/kind in a table', async () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        flasherSearch.mockResolvedValue([[
            {primary_path: 'software/MALVEKE.ino.bin', name: 'MALVEKE.ino.bin', size: 1024,
                esp_chip: 'ESP32', esp_kind: 'app'},
        ], 1]);
        render(<FlasherPage/>);
        // Media firmware is fetched on mount via the flasher search (no chip filter, no path).
        await waitFor(() => expect(flasherSearch).toHaveBeenCalledWith(null, null));
        // The result is listed for the user to add, under the "Choose from your WROLPi" tab.
        switchTab('Choose from your WROLPi');
        expect((await screen.findAllByText('MALVEKE.ino.bin')).length).toBeGreaterThan(0);
        // The table surfaces the detected chip and kind.
        expect(screen.getAllByText('ESP32').length).toBeGreaterThan(0);
        expect(screen.getAllByText('app').length).toBeGreaterThan(0);
    });

    it('offers the detect-device filter button', () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        render(<FlasherPage/>);
        switchTab('Choose from your WROLPi');
        expect(screen.getAllByText('Filter files by detecting device').length).toBeGreaterThan(0);
    });

    it('lists saved firmware configurations fetched on load', async () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        getFlasherConfigs.mockResolvedValue([
            {name: 'T-Deck MUI', erase_all: true, files: [{path: 'a.bin', address: '0x0'}]},
        ]);
        render(<FlasherPage/>);
        await waitFor(() => expect(getFlasherConfigs).toHaveBeenCalled());
        // "Saved Firmwares" is always visible as a tab label; its contents appear once the tab is active.
        expect((await screen.findAllByText('Saved Firmwares')).length).toBeGreaterThan(0);
        switchTab('Saved Firmwares');
        expect((await screen.findAllByText('T-Deck MUI')).length).toBeGreaterThan(0);
    });

    it('reminds the user about boot/download mode when connecting fails', async () => {
        // A non-cancel connect failure (e.g. board not in download mode) should surface the reminder.
        Object.defineProperty(global.navigator, 'serial',
            {value: {requestPort: jest.fn().mockRejectedValue(new Error('Failed to connect'))}, configurable: true});
        render(<FlasherPage/>);
        fireEvent.click(screen.getAllByText('Connect Device')[0].closest('button'));
        expect((await screen.findAllByText(/download mode/i)).length).toBeGreaterThan(0);
        expect((await screen.findAllByText(/Could not connect to the device/i)).length).toBeGreaterThan(0);
    });

    it('does not show the boot-mode reminder when the user cancels the port picker', async () => {
        // Cancelling the browser picker throws NotFoundError, which is not a real failure.
        const notFound = Object.assign(new Error('No port selected'), {name: 'NotFoundError'});
        Object.defineProperty(global.navigator, 'serial',
            {value: {requestPort: jest.fn().mockRejectedValue(notFound)}, configurable: true});
        render(<FlasherPage/>);
        fireEvent.click(screen.getAllByText('Connect Device')[0].closest('button'));
        await waitFor(() => expect(navigator.serial.requestPort).toHaveBeenCalled());
        expect(screen.queryByText(/download mode/i)).not.toBeInTheDocument();
    });

    it('detects the device and filters firmware by its chip', async () => {
        Object.defineProperty(global.navigator, 'serial',
            {value: {requestPort: jest.fn().mockResolvedValue({})}, configurable: true});
        flasherSearch.mockResolvedValue([[
            {primary_path: 'software/s2.bin', name: 's2.bin', size: 1024, esp_chip: 'ESP32-S2', esp_kind: 'app'},
        ], 1]);

        render(<FlasherPage/>);
        switchTab('Choose from your WROLPi');
        fireEvent.click(screen.getAllByText('Filter files by detecting device')[0].closest('button'));

        // The detected chip (ESP32-S2, parsed from the esptool description) is used to filter firmware.
        await waitFor(() => expect(flasherSearch).toHaveBeenCalledWith('ESP32-S2', null));
        // The active filter is shown, and only the matching firmware is listed.
        expect((await screen.findAllByText('ESP32-S2', {exact: false})).length).toBeGreaterThan(0);
        expect((await screen.findAllByText('s2.bin')).length).toBeGreaterThan(0);
    });

    it('filters by the canonical chip name, not the variant from the chip description', async () => {
        // An ESP32-classic reports description "ESP32-D0WD-V3 (revision 3)" but CHIP_NAME "ESP32".  The backend
        // stores firmware chips as the canonical name ("ESP32"), so the search must use CHIP_NAME — searching the
        // variant "ESP32-D0WD-V3" would match nothing even when valid firmware exists.
        mockChipName = 'ESP32';
        mockChipId = 0;
        mockDescription = 'ESP32-D0WD-V3 (revision 3)';
        Object.defineProperty(global.navigator, 'serial',
            {value: {requestPort: jest.fn().mockResolvedValue({})}, configurable: true});

        render(<FlasherPage/>);
        switchTab('Choose from your WROLPi');
        fireEvent.click(screen.getAllByText('Filter files by detecting device')[0].closest('button'));

        // (flasherSearch also runs on mount with no chip; wait for the detect-driven call specifically.)
        await waitFor(() => expect(flasherSearch).toHaveBeenCalledWith('ESP32', null));
    });

    it('adds dropped .bin files and switches to the Add-from-computer tab', async () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        render(<FlasherPage/>);

        // Default tab is "Saved Firmwares"; the computer dropzone is not shown yet.
        expect(screen.queryByText(/Click here/)).not.toBeInTheDocument();

        const binFile = new File([new Uint8Array([0xe9, 0, 0])], 'dropped.bin');
        const txtFile = new File(['nope'], 'notes.txt');
        // The dropzone root wraps the whole page; a drop on any descendant bubbles up to it.  react-dropzone
        // requires dataTransfer.types to include 'Files' before it reads the dropped files.
        const target = screen.getAllByText('1. Firmware files')[0];
        fireEvent.drop(target, {dataTransfer: {files: [binFile, txtFile], types: ['Files']}});

        // The .bin is added (shown in the selected-firmware table) and the .txt is ignored.
        expect((await screen.findAllByText('dropped.bin')).length).toBeGreaterThan(0);
        expect(screen.queryByText('notes.txt')).not.toBeInTheDocument();
        // The drop switches to the "Add from computer" tab, revealing its dropzone.
        expect(screen.getAllByText(/Click here/).length).toBeGreaterThan(0);
    });

    it('disconnects when the selected firmware set changes, forcing a fresh chip check', async () => {
        Object.defineProperty(global.navigator, 'serial',
            {value: {requestPort: jest.fn().mockResolvedValue({})}, configurable: true});
        render(<FlasherPage/>);

        // Connect to the device.
        fireEvent.click(screen.getAllByText('Connect Device')[0].closest('button'));
        await waitFor(() => expect(screen.getAllByText('Disconnect').length).toBeGreaterThan(0));

        // Changing the firmware selection (drop a new file) must drop the connection so it is re-checked.
        const bin = new File([new Uint8Array([0xe9, 0, 0])], 'swapped.bin');
        fireEvent.drop(screen.getAllByText('1. Firmware files')[0],
            {dataTransfer: {files: [bin], types: ['Files']}});

        await waitFor(() => expect(screen.getAllByText('Connect Device').length).toBeGreaterThan(0));
        expect(screen.queryByText('Disconnect')).not.toBeInTheDocument();
    });
});
