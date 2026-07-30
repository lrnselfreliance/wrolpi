import React from 'react';
import {act, renderHook, waitFor} from '@testing-library/react';
import {useBluetooth, useDesktop, useHotspot, useThrottle, useVnc} from './customHooks';
import {StatusContext} from '../contexts/contexts';

jest.mock('../api/controller', () => ({
    unblockBluetooth: jest.fn().mockResolvedValue({}),
    blockBluetooth: jest.fn().mockResolvedValue({}),
    startHotspot: jest.fn().mockResolvedValue({}),
    stopHotspot: jest.fn().mockResolvedValue({}),
    startDesktop: jest.fn().mockResolvedValue({}),
    stopDesktop: jest.fn().mockResolvedValue({}),
    startVnc: jest.fn().mockResolvedValue({}),
    stopVnc: jest.fn().mockResolvedValue({}),
    enableThrottle: jest.fn().mockResolvedValue({}),
    disableThrottle: jest.fn().mockResolvedValue({}),
    getControllerStats: jest.fn().mockResolvedValue({}),
}));


const controllerApi = require('../api/controller');

const fetchStatus = jest.fn();

const makeWrapper = (status) => ({children}) => (
    <StatusContext.Provider value={{status, fetchStatus}}>{children}</StatusContext.Provider>
);

beforeEach(() => {
    jest.clearAllMocks();
    Object.values(controllerApi).forEach(fn => fn.mockResolvedValue && fn.mockResolvedValue({}));
});

describe('subsystem toggle hooks', () => {
    // Each hook reads a different status field with different values for on/off.
    const cases = [
        {
            name: 'bluetooth', hook: useBluetooth, setter: 'setBluetooth',
            status: {bluetooth_status: 'on'}, offStatus: {bluetooth_status: 'off'},
            start: 'unblockBluetooth', stop: 'blockBluetooth',
        },
        {
            name: 'desktop', hook: useDesktop, setter: 'setDesktop',
            status: {desktop_status: 'on'}, offStatus: {desktop_status: 'off'},
            start: 'startDesktop', stop: 'stopDesktop',
        },
        {
            name: 'vnc', hook: useVnc, setter: 'setVnc',
            status: {vnc_status: 'on'}, offStatus: {vnc_status: 'off'},
            start: 'startVnc', stop: 'stopVnc',
        },
        {
            name: 'throttle', hook: useThrottle, setter: 'setThrottle',
            status: {throttle_status: 'powersave'}, offStatus: {throttle_status: 'ondemand'},
            start: 'enableThrottle', stop: 'disableThrottle',
        },
        {
            name: 'hotspot', hook: useHotspot, setter: 'setHotspot',
            status: {hotspot_status: 'connected'}, offStatus: {hotspot_status: 'disconnected'},
            start: 'startHotspot', stop: 'stopHotspot',
        },
    ];

    cases.forEach(({name, hook, setter, status, offStatus, start, stop}) => {
        describe(name, () => {
            it('reports on and off from the status field', async () => {
                const {result} = renderHook(hook, {wrapper: makeWrapper(status)});
                await waitFor(() => expect(result.current.on).toBe(true));

                const {result: offResult} = renderHook(hook, {wrapper: makeWrapper(offStatus)});
                await waitFor(() => expect(offResult.current.on).toBe(false));
            });

            it('reports unknown status as null so the UI can disable the toggle', async () => {
                const {result} = renderHook(hook, {wrapper: makeWrapper({})});
                await waitFor(() => expect(result.current.on).toBe(null));
            });

            it('starts and stops through the Controller', async () => {
                const {result} = renderHook(hook, {wrapper: makeWrapper(offStatus)});
                await waitFor(() => expect(result.current.on).toBe(false));

                await act(async () => await result.current[setter](true));
                expect(controllerApi[start]).toHaveBeenCalled();

                await act(async () => await result.current[setter](false));
                expect(controllerApi[stop]).toHaveBeenCalled();
            });

            it('restores the previous state when the request fails', async () => {
                // Otherwise `on` stays null, and because the status poll sees no change
                // the toggle is left disabled and reading as unsupported until remount.
                controllerApi[stop].mockRejectedValue(new Error('boom'));
                const {result} = renderHook(hook, {wrapper: makeWrapper(status)});
                await waitFor(() => expect(result.current.on).toBe(true));

                await act(async () => await result.current[setter](false));

                expect(result.current.on).toBe(true);
            });
        });
    });

    it('throttle refetches status because the governor is read from sysfs', async () => {
        const {result} = renderHook(useThrottle, {wrapper: makeWrapper({throttle_status: 'ondemand'})});
        await waitFor(() => expect(result.current.on).toBe(false));

        await act(async () => await result.current.setThrottle(true));

        expect(fetchStatus).toHaveBeenCalled();
    });

    it('hotspot reports a WiFi device that is in use for a network', async () => {
        const {result} = renderHook(useHotspot, {wrapper: makeWrapper({hotspot_status: 'in_use'})});

        await waitFor(() => expect(result.current.inUse).toBe(true));
        // In use means the hotspot is not running, but starting it leaves that network.
        expect(result.current.on).toBe(false);
    });

    it('vnc exposes whether the desktop it serves is running', async () => {
        const {result} = renderHook(useVnc, {wrapper: makeWrapper({vnc_status: 'off', desktop_status: 'on'})});
        await waitFor(() => expect(result.current.desktopRunning).toBe(true));

        const {result: stopped} = renderHook(useVnc, {wrapper: makeWrapper({vnc_status: 'off', desktop_status: 'off'})});
        await waitFor(() => expect(stopped.current.desktopRunning).toBe(false));
    });
});
