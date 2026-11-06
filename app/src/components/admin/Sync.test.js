import React from 'react';
import {fireEvent, screen, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../../test-utils';
import {backupStatusFixture, settingsFixture, statusFixture, syncStatusFixture} from '../../test-fixtures';
import {BackupDriveSection, backupDriveOptions, SecondaryRoleMessage, SyncingOverlay, SyncSection} from './Sync';

jest.mock('../../api/controller', () => ({
    getDisks: jest.fn(),
}));

jest.mock('../../api', () => ({
    cancelBackup: jest.fn(),
    runBackup: jest.fn(),
    cancelSync: jest.fn(),
    runSync: jest.fn(),
    saveSyncSettings: jest.fn(),
    testSync: jest.fn(),
}));

import {cancelBackup, cancelSync, runBackup, runSync, saveSyncSettings, testSync} from '../../api';
import {getDisks} from '../../api/controller';

beforeEach(() => {
    // react-scripts resets mock implementations before each test.
    cancelSync.mockResolvedValue({ok: true});
    runSync.mockResolvedValue({ok: true});
    saveSyncSettings.mockResolvedValue({ok: true});
    testSync.mockResolvedValue({ok: true, info: {version: '0.30.5-beta'}});
    runBackup.mockResolvedValue({ok: true});
    cancelBackup.mockResolvedValue({ok: true});
    getDisks.mockResolvedValue(disks);
});

const disks = [
    {name: 'sda1', size: '9.1T', mountpoint: '/media/wrolpi_backup', label: 'Decay2of2', uuid: 'uuid-backup'},
    {name: 'sdb1', size: '9.1T', mountpoint: '/media/wrolpi', label: 'Decay1of2', uuid: 'uuid-media'},
    {name: 'mmcblk0p2', size: '118.6G', mountpoint: '/', label: 'rootfs', uuid: 'uuid-root'},
    {name: 'sdc1', size: '64G', mountpoint: null, label: 'stick', uuid: 'uuid-stick'},
];

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

describe('backupDriveOptions', () => {
    it('lists mounted drives under /media that are not the media drive', () => {
        expect(backupDriveOptions(disks, '/media/wrolpi')).toEqual([
            {value: '/media/wrolpi_backup', uuid: 'uuid-backup', label: 'Decay2of2 (9.1T) at /media/wrolpi_backup'},
        ]);
    });
});

describe('BackupDriveSection', () => {
    it('saves the chosen drive with its UUID', async () => {
        renderWithProviders(<BackupDriveSection/>);
        await waitFor(() => expect(getDisks).toHaveBeenCalled());
        fireEvent.click(screen.getByDisplayValue('None'));
        fireEvent.click(await screen.findByText('Decay2of2 (9.1T) at /media/wrolpi_backup'));
        fireEvent.click(screen.getByText('Save'));
        await waitFor(() => expect(saveSyncSettings).toHaveBeenCalledWith({
            backup_directory: '/media/wrolpi_backup', backup_device_uuid: 'uuid-backup',
        }));
    });

    it('shows the backup and runs it on request', async () => {
        const settings = {settings: settingsFixture({backup_directory: '/media/wrolpi_backup',
                backup_device_uuid: 'uuid-backup'})};
        const status = {status: statusFixture({backup: backupStatusFixture({last_error: 'rsync failed (12)'})})};
        renderWithProviders(<BackupDriveSection/>, {settings, status});
        expect(await screen.findByDisplayValue('Decay2of2 (9.1T) at /media/wrolpi_backup')).toBeInTheDocument();
        expect(screen.getByText('rsync failed (12)')).toBeInTheDocument();
        fireEvent.click(screen.getByText('Back Up Now'));
        await waitFor(() => expect(runBackup).toHaveBeenCalled());
    });

    it('keeps an unplugged drive selected', async () => {
        getDisks.mockResolvedValue([]);
        const settings = {settings: settingsFixture({backup_directory: '/media/gone', backup_device_uuid: 'x'})};
        renderWithProviders(<BackupDriveSection/>, {settings});
        expect(await screen.findByDisplayValue('/media/gone (not mounted)')).toBeInTheDocument();
    });

    it('offers to stop a running backup', async () => {
        const settings = {settings: settingsFixture({backup_directory: '/media/wrolpi_backup',
                backup_device_uuid: 'uuid-backup'})};
        const status = {status: statusFixture({flags: {backup_running: true},
                backup: backupStatusFixture({state: 'running', phase: 'files', percent: 40})})};
        renderWithProviders(<BackupDriveSection/>, {settings, status});
        fireEvent.click(await screen.findByText('Stop Backup'));
        expect(cancelBackup).toHaveBeenCalled();
    });

    it('is absent in Docker, which cannot reach other drives', () => {
        renderWithProviders(<BackupDriveSection/>, {status: {status: statusFixture({dockerized: true})}});
        expect(screen.queryByText('Backup Drive')).not.toBeInTheDocument();
        expect(getDisks).not.toHaveBeenCalled();
    });
});

