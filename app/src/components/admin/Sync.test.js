import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../../test-utils';
import {settingsFixture, statusFixture, syncStatusFixture} from '../../test-fixtures';
import {SecondaryRoleMessage, SyncingOverlay, SyncSection} from './Sync';

jest.mock('../../api', () => ({
    cancelSync: jest.fn(),
    runSync: jest.fn(),
    saveSyncSettings: jest.fn(),
    testSync: jest.fn(),
}));

import {cancelSync, runSync, saveSyncSettings, testSync} from '../../api';

beforeEach(() => {
    // react-scripts resets mock implementations before each test.
    cancelSync.mockResolvedValue({ok: true});
    runSync.mockResolvedValue({ok: true});
    saveSyncSettings.mockResolvedValue({ok: true});
    testSync.mockResolvedValue({ok: true, info: {version: '0.30.5-beta'}});
});

const secondary = (overrides = {}) => ({
    settings: settingsFixture({role: 'secondary', sync_primary_url: 'https://192.168.0.10', ...overrides}),
});

describe('SecondaryRoleMessage', () => {
    it('warns on a secondary', () => {
        renderWithProviders(<SecondaryRoleMessage/>, {settings: secondary()});
        expect(screen.getByText('Secondary WROLPi')).toBeInTheDocument();
        expect(screen.getByText('https://192.168.0.10')).toBeInTheDocument();
    });

    it('is absent on a primary', () => {
        renderWithProviders(<SecondaryRoleMessage/>);
        expect(screen.queryByText('Secondary WROLPi')).not.toBeInTheDocument();
    });

    it('goes away in WROL Mode, which stops syncing', () => {
        renderWithProviders(<SecondaryRoleMessage/>, {settings: secondary({wrol_mode: true})});
        expect(screen.queryByText('Secondary WROLPi')).not.toBeInTheDocument();
    });
});

describe('SyncingOverlay', () => {
    const syncing = (sync = {}) => ({
        status: statusFixture({
            flags: {sync_running: true},
            sync: syncStatusFixture({state: 'running', phase: 'files', groups_seen: 50, max_id: 100, ...sync}),
        }),
    });

    it('covers the app while a secondary syncs', () => {
        renderWithProviders(<SyncingOverlay/>, {settings: secondary(), status: syncing()});
        expect(screen.getByRole('alertdialog', {name: 'Syncing'})).toBeInTheDocument();
        expect(screen.getByText('Syncing from the primary')).toBeInTheDocument();

        fireEvent.click(screen.getByText('Stop Sync'));
        expect(cancelSync).toHaveBeenCalled();
    });

    it('is absent when not syncing', () => {
        renderWithProviders(<SyncingOverlay/>, {settings: secondary()});
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    it('is absent on a primary', () => {
        renderWithProviders(<SyncingOverlay/>, {status: syncing()});
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
});

describe('SyncSection', () => {
    it('a primary shows only its role', () => {
        renderWithProviders(<SyncSection/>);
        expect(screen.getByText('This WROLPi is')).toBeInTheDocument();
        expect(screen.queryByText('Primary address')).not.toBeInTheDocument();
        expect(screen.queryByText('Sync Now')).not.toBeInTheDocument();
    });

    it('a secondary shows its primary, window, and sync controls', async () => {
        const status = {status: statusFixture({sync: syncStatusFixture({last_error: 'The primary did not answer'})})};
        renderWithProviders(<SyncSection/>, {settings: secondary({sync_window_start: '01:00'}), status});
        expect(screen.getByDisplayValue('https://192.168.0.10')).toBeInTheDocument();
        expect(screen.getByDisplayValue('01:00')).toBeInTheDocument();
        expect(screen.getByText('The primary did not answer')).toBeInTheDocument();

        fireEvent.click(screen.getByText('Sync Now'));
        await waitFor(() => expect(runSync).toHaveBeenCalled());

        fireEvent.click(screen.getByText('Save'));
        await waitFor(() => expect(saveSyncSettings).toHaveBeenCalledWith({
            role: 'secondary', sync_primary_url: 'https://192.168.0.10', sync_window_start: '01:00',
            sync_window_end: '',
        }));
    });

    it('WROL Mode stops syncing', () => {
        renderWithProviders(<SyncSection/>, {settings: secondary({wrol_mode: true})});
        expect(screen.getByText('Syncing is stopped')).toBeInTheDocument();
        expect(screen.getByText('Sync Now').closest('button')).toBeDisabled();
    });
});
