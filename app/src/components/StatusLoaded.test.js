import React from 'react';
import {render, screen} from '../test-utils';
import {DisableDownloadsToggle, HotspotToggle} from './Common';
import {SettingsPage, UpgradeSegment} from './admin/Settings';

// The status and settings contexts start empty and are filled by the first poll.  Until then a
// consumer must not claim a negative ("Downloading Disabled", "not supported", "up to date") or
// render a form over blank values; `loaded` on each context says whether the first poll landed.

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    getConfigs: jest.fn(() => new Promise(() => {
    })),
}));

const unloadedStatus = {status: {}, loaded: false};

describe('DisableDownloadsToggle before status has loaded', () => {
    test('is disabled and does not claim downloading is disabled', () => {
        render(<DisableDownloadsToggle/>, {status: unloadedStatus});
        expect(screen.getByTestId('toggle')).toBeDisabled();
        expect(screen.queryByText('Downloading Disabled')).not.toBeInTheDocument();
    });

    test('once loaded, reads the downloads state', () => {
        render(<DisableDownloadsToggle/>, {status: {status: {downloads: {disabled: true, stopped: false}}, loaded: true}});
        expect(screen.getByText('Downloading Disabled')).toBeInTheDocument();
        expect(screen.getByTestId('toggle')).toBeEnabled();
    });
});

describe('HotspotToggle before status has loaded', () => {
    test('is disabled without claiming the hotspot is unsupported', () => {
        render(<HotspotToggle/>, {status: unloadedStatus});
        expect(screen.getByTestId('toggle')).toBeDisabled();
        expect(screen.queryByTestId('subsystem-popup')).not.toBeInTheDocument();
    });

    test('once loaded without a hotspot field, is unsupported', () => {
        render(<HotspotToggle/>, {status: {status: {}, loaded: true}});
        expect(screen.getByTestId('toggle')).toBeDisabled();
        expect(screen.getByTestId('subsystem-popup')).toBeInTheDocument();
    });
});

describe('UpgradeSegment before status has loaded', () => {
    test('does not claim the WROLPi is up to date', () => {
        render(<UpgradeSegment/>, {status: unloadedStatus});
        expect(screen.queryByText(/up to date/)).not.toBeInTheDocument();
    });

    test('once loaded with no update, says so', () => {
        render(<UpgradeSegment/>, {status: {status: {update_available: false, version: '1.0'}, loaded: true}});
        expect(screen.getByText(/up to date/)).toBeInTheDocument();
    });
});

describe('SettingsPage before settings have loaded', () => {
    test('shows a loader, not a form over blank values', () => {
        const {container} = render(<SettingsPage/>, {settings: {settings: {}, loaded: false, failed: false}});
        expect(container.querySelector('.wrolpi-loading')).toBeInTheDocument();
        expect(screen.queryByText(/Any changes will be written/)).not.toBeInTheDocument();
    });

    test('shows an error when the settings could not be fetched', () => {
        render(<SettingsPage/>, {settings: {settings: {}, loaded: false, failed: true}});
        expect(screen.getByText('Unable to fetch settings')).toBeInTheDocument();
    });
});
