import React from 'react';
import {render, screen} from '../../test-utils';
import {BackupsModal} from './Configs';
import {getConfigBackups} from '../../api';

// The config backups modal says "No backups available" only once the server confirmed there are
// none; a failed fetch is an error, and a thrown one must not leave the loader up forever.

jest.mock('../../api', () => ({
    ...jest.requireActual('../../api'),
    getConfigBackups: jest.fn(),
    postConfigBackupPreview: jest.fn(() => new Promise(() => {
    })),
}));

const NONE = /No backups available/;
const FAILED = /Could not fetch backups/;

const renderModal = () => render(
    <BackupsModal open fileName='wrolpi.yaml' onClose={jest.fn()} fetchConfigs={jest.fn()}/>,
);

beforeEach(() => getConfigBackups.mockReset());

test('empty: says there are no backups', async () => {
    getConfigBackups.mockResolvedValue({dates: []});
    renderModal();
    expect(await screen.findByText(NONE)).toBeInTheDocument();
});

test('failed: shows an error, not "No backups available"', async () => {
    getConfigBackups.mockResolvedValue(undefined);
    renderModal();
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    expect(screen.queryByText(NONE)).not.toBeInTheDocument();
});

test('thrown: shows an error, not a loader forever', async () => {
    getConfigBackups.mockRejectedValue(new Error('down'));
    renderModal();
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    expect(screen.queryByText(/Loading backups/)).not.toBeInTheDocument();
});
