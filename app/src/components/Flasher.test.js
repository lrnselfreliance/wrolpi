import React from 'react';
import {render, screen, waitFor} from '@testing-library/react';

// esptool-js ships untranspiled ESM which Jest will not transform; mock it so importing Flasher.js is safe.
jest.mock('esptool-js', () => ({
    ESPLoader: jest.fn(),
    Transport: jest.fn(),
}));

// Flasher fetches media firmware on mount; mock the API so tests don't hit the network.
jest.mock('../api', () => ({
    filesSearch: jest.fn().mockResolvedValue([[], 0]),
}));

import {filesSearch} from '../api';
import {FlasherPage, parseAddress, webSerialSupported} from './Flasher';

describe('parseAddress', () => {
    it('parses hex offsets', () => {
        expect(parseAddress('0x0')).toBe(0);
        expect(parseAddress('0x1000')).toBe(0x1000);
        expect(parseAddress('0X10000')).toBe(0x10000);
        expect(parseAddress('  0x8000  ')).toBe(0x8000);
    });

    it('parses decimal offsets', () => {
        expect(parseAddress('0')).toBe(0);
        expect(parseAddress('65536')).toBe(65536);
    });

    it('rejects empty offsets', () => {
        expect(() => parseAddress('')).toThrow(/required/);
        expect(() => parseAddress('   ')).toThrow(/required/);
    });

    it('rejects invalid offsets', () => {
        expect(() => parseAddress('nope')).toThrow(/Invalid/);
        expect(() => parseAddress('0xZZ')).toThrow(/Invalid/);
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
        // Media firmware is fetched on mount filtered to the .bin suffix (last positional arg).
        await waitFor(() => expect(filesSearch).toHaveBeenCalled());
        const lastArg = filesSearch.mock.calls[0][filesSearch.mock.calls[0].length - 1];
        expect(lastArg).toBe('.bin');
        // The result is listed for the user to add.
        expect((await screen.findAllByText('MALVEKE.ino.bin')).length).toBeGreaterThan(0);
    });
});
