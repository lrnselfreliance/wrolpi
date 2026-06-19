import React from "react";
import {fireEvent, render, screen, waitFor, within} from "@testing-library/react";

jest.mock("react-semantic-toasts-2", () => ({toast: jest.fn()}));
jest.mock("../../api", () => ({
    getInventoryBackups: jest.fn(),
    postInventoryRestorePreview: jest.fn(),
    postInventoryRestore: jest.fn(),
    reimportInventories: jest.fn(),
}));

import {InventoryImportModal} from "./InventoryImportModal";
import {getInventoryBackups, postInventoryRestore, postInventoryRestorePreview, reimportInventories} from "../../api";

const renderModal = (props = {}) => {
    const onChanged = jest.fn(() => Promise.resolve());
    const onClose = jest.fn();
    render(<InventoryImportModal open slug='food-storage' name='Food Storage'
                                 onChanged={onChanged} onClose={onClose} {...props}/>);
    return {onChanged, onClose};
};

describe('InventoryImportModal', () => {
    // CRA's jest config resets mock implementations before each test, so (re)set them here.
    beforeEach(() => {
        getInventoryBackups.mockResolvedValue(['20260115', '20260101']);
        postInventoryRestorePreview.mockResolvedValue({
            mode: 'merge', add: [{id: 2, name: 'Beans'}], remove: [], unchanged: 1,
            fields_change: false, current_count: 1, backup_count: 2, backup_name: 'Food Storage',
        });
        postInventoryRestore.mockResolvedValue({slug: 'food-storage', items: []});
        reimportInventories.mockResolvedValue([{slug: 'food-storage'}]);
    });

    test('lists backups and applies a merge restore', async () => {
        const {onChanged, onClose} = renderModal();

        // Backup dates load (newest first).
        const row = (await screen.findByText('2026-01-15')).closest('tr');
        fireEvent.click(within(row).getByRole('button', {name: /merge/i}));

        // Preview is requested for that date/mode, then the confirmation view appears.
        await waitFor(() => expect(postInventoryRestorePreview)
            .toHaveBeenCalledWith('food-storage', '20260115', 'merge'));
        await screen.findByText(/Merge backup from 2026-01-15/);
        expect(screen.getByText(/1 to add/)).toBeInTheDocument();
        expect(screen.getByText('Beans')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: /apply/i}));
        await waitFor(() => expect(postInventoryRestore)
            .toHaveBeenCalledWith('food-storage', '20260115', 'merge'));
        await waitFor(() => expect(onChanged).toHaveBeenCalled());
        await waitFor(() => expect(onClose).toHaveBeenCalled());
    });

    test('re-import from disk reloads inventories', async () => {
        const {onChanged} = renderModal();
        await screen.findByText('2026-01-15');   // wait for initial load to settle

        fireEvent.click(screen.getByRole('button', {name: /re-import from disk/i}));
        await waitFor(() => expect(reimportInventories).toHaveBeenCalled());
        await waitFor(() => expect(onChanged).toHaveBeenCalled());
    });

    test('fetches backups for the inventory on open', async () => {
        renderModal();
        await waitFor(() => expect(getInventoryBackups).toHaveBeenCalledWith('food-storage'));
    });
});
