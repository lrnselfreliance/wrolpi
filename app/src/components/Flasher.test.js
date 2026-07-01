import React from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';

// esptool-js ships untranspiled ESM which Jest will not transform; mock it so importing Flasher.js is safe.
// Real classes (not jest.fn mock impls) so `new ESPLoader()` reliably yields an instance with main()/after().
// The ESPLoader mock reports an ESP32-S2 so the connect/detect flow can be exercised.
jest.mock('esptool-js', () => ({
    __esModule: true,
    ESPLoader: class {
        async main() {
            return 'ESP32-S2 (revision v0.0)';
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
    filesSearch: jest.fn().mockResolvedValue([[], 0]),
    flasherSearch: jest.fn().mockResolvedValue([[], 0]),
}));

import {filesSearch, flasherSearch} from '../api';
import {chipFamily, FlasherPage, isValidHexOffset, parseAddress, webSerialSupported} from './Flasher';

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

describe('FlasherPage', () => {
    const original = Object.getOwnPropertyDescriptor(global.navigator, 'serial');

    beforeEach(() => {
        filesSearch.mockClear();
        filesSearch.mockResolvedValue([[], 0]);
        flasherSearch.mockClear();
        flasherSearch.mockResolvedValue([[], 0]);
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
        expect(screen.getAllByText('Add file from computer').length).toBeGreaterThan(0);
        // Flash button is disabled until a device is connected and a file is added.
        expect(screen.getAllByText('Flash Device')[0].closest('button')).toBeDisabled();
    });

    it('fetches media firmware by suffix on load and lists results', async () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        filesSearch.mockResolvedValue([[
            {primary_path: 'software/MALVEKE.ino.bin', name: 'MALVEKE.ino.bin', size: 1024},
        ], 1]);
        render(<FlasherPage/>);
        // Media firmware is fetched on mount filtered to the .bin suffix (the `suffix` positional arg).
        await waitFor(() => expect(filesSearch).toHaveBeenCalled());
        const call = filesSearch.mock.calls[0];
        // filesSearch(offset, limit, searchStr, mimetypes, model, tagNames, headline, months, fromYear, toYear,
        //             anyTag, order, suffix, path)
        expect(call[12]).toBe('.bin');
        // The result is listed for the user to add.
        expect((await screen.findAllByText('MALVEKE.ino.bin')).length).toBeGreaterThan(0);
    });

    it('offers the detect-device filter button', () => {
        Object.defineProperty(global.navigator, 'serial', {value: {}, configurable: true});
        render(<FlasherPage/>);
        expect(screen.getAllByText('Filter files by detecting device').length).toBeGreaterThan(0);
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
        fireEvent.click(screen.getAllByText('Filter files by detecting device')[0].closest('button'));

        // The detected chip (ESP32-S2, parsed from the esptool description) is used to filter firmware.
        await waitFor(() => expect(flasherSearch).toHaveBeenCalledWith('ESP32-S2', null));
        // The active filter is shown, and only the matching firmware is listed.
        expect((await screen.findAllByText('ESP32-S2', {exact: false})).length).toBeGreaterThan(0);
        expect((await screen.findAllByText('s2.bin')).length).toBeGreaterThan(0);
    });
});
