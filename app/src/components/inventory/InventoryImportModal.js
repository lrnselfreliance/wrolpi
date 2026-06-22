import React, {useContext, useEffect, useState} from "react";
import {toast} from "../../toast";
import {TableBody, TableCell, TableHeader, TableHeaderCell, TableRow} from "semantic-ui-react";
import {Button, Divider, Header, Icon, Loader, Modal, Table} from "../Theme";
import {
    getInventoryBackups, postInventoryRestore, postInventoryRestorePreview, reimportInventories,
} from "../../api";
import {ThemeContext} from "../../contexts/contexts";

const formatDate = (d) => d && d.length === 8 ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : d;

const itemName = (item) => (item && (item.name || `Item ${item.id}`)) || 'Item';

// Compact list of item names from a preview's add/remove arrays.
function ItemNameList({items}) {
    const {t} = useContext(ThemeContext);
    if (!items || items.length === 0) {
        return null;
    }
    return <ul style={{marginTop: '0.25em'}}>
        {items.map((i, idx) => <li key={`${i.id}-${idx}`} {...t}>{itemName(i)}</li>)}
    </ul>;
}

/**
 * Per-inventory import/restore modal (opened from the Inventory toolbar).  Two actions:
 *   - Re-import from disk: reload every inventory's config file (picks up hand-edits and copied-in files).
 *   - Restore from a backup: pick a dated backup and Merge (add items missing by id) or Overwrite (replace).
 * `onChanged` refreshes the page's inventory state after a successful action.
 */
export function InventoryImportModal({open, onClose, slug, name, onChanged}) {
    const {t} = useContext(ThemeContext);
    const [dates, setDates] = useState(null);          // null while loading
    const [reimporting, setReimporting] = useState(false);
    const [selected, setSelected] = useState(null);    // {date, mode, preview} confirmation view
    const [previewing, setPreviewing] = useState(null); // `${date}:${mode}` currently loading a preview
    const [applying, setApplying] = useState(false);

    useEffect(() => {
        if (!open) {
            return;
        }
        let cancelled = false;
        setDates(null);
        setSelected(null);
        setReimporting(false);
        setApplying(false);
        setPreviewing(null);
        getInventoryBackups(slug).then(result => {
            if (!cancelled) {
                setDates(result || []);
            }
        });
        return () => {
            cancelled = true;
        };
    }, [open, slug]);

    const doReimport = async () => {
        setReimporting(true);
        const result = await reimportInventories();
        setReimporting(false);
        if (result) {
            await onChanged();
            toast({type: 'success', title: 'Re-imported', description: 'Inventories reloaded from disk.', time: 4000});
            onClose();
        }
    };

    const selectAction = async (date, mode) => {
        setPreviewing(`${date}:${mode}`);
        const preview = await postInventoryRestorePreview(slug, date, mode);
        setPreviewing(null);
        if (preview) {
            setSelected({date, mode, preview});
        }
    };

    const applyRestore = async () => {
        setApplying(true);
        const inventory = await postInventoryRestore(slug, selected.date, selected.mode);
        setApplying(false);
        if (inventory) {
            await onChanged();
            toast({type: 'success', title: 'Restored', description: `Restored from ${formatDate(selected.date)}.`,
                time: 4000});
            onClose();
        }
    };

    // Confirmation view: show what the chosen restore would change.
    if (selected) {
        const {date, mode, preview} = selected;
        const modeLabel = mode === 'merge' ? 'Merge' : 'Overwrite';
        return <Modal open={open} onClose={onClose} closeIcon size='small'>
            <Modal.Header>{modeLabel} backup from {formatDate(date)}</Modal.Header>
            <Modal.Content>
                {applying
                    ? <Loader active inline='centered'>Restoring…</Loader>
                    : <>
                        {mode === 'overwrite'
                            ? <p {...t}>
                                Replace <strong>{name}</strong> entirely with the {formatDate(date)} backup
                                ({preview.backup_count} item{preview.backup_count === 1 ? '' : 's'}).
                            </p>
                            : <p {...t}>
                                Add items from the {formatDate(date)} backup that aren't already present; your
                                current items and fields are kept.
                            </p>}

                        {preview.add.length > 0 && <>
                            <Header as='h5' color='green'><Icon name='plus'/> {preview.add.length} to add</Header>
                            <ItemNameList items={preview.add}/>
                        </>}
                        {preview.remove.length > 0 && <>
                            <Header as='h5' color='red'><Icon name='minus'/> {preview.remove.length} to remove</Header>
                            <ItemNameList items={preview.remove}/>
                        </>}
                        {preview.fields_change &&
                            <p {...t}><Icon name='columns'/> The field columns will also change.</p>}
                        {preview.add.length === 0 && preview.remove.length === 0 && !preview.fields_change &&
                            <p {...t}>No changes — this backup matches the current inventory.</p>}
                        <p style={{color: 'grey'}}>{preview.unchanged} unchanged
                            item{preview.unchanged === 1 ? '' : 's'}</p>
                    </>}
            </Modal.Content>
            <Modal.Actions>
                {!applying && <>
                    <Button onClick={() => setSelected(null)}>Back</Button>
                    <Button color='green' onClick={applyRestore}><Icon name='check'/> Apply</Button>
                </>}
            </Modal.Actions>
        </Modal>;
    }

    return <Modal open={open} onClose={onClose} closeIcon size='small'>
        <Modal.Header>Import / Restore: {name}</Modal.Header>
        <Modal.Content>
            <Header as='h4'>Re-import from disk</Header>
            <p {...t}>
                Reload every inventory from its config file. Use this after editing a file by hand, or after copying
                an inventory file in from another WROLPi.
            </p>
            <Button primary onClick={doReimport} loading={reimporting} disabled={reimporting}>
                <Icon name='sync'/> Re-import from disk
            </Button>

            <Divider/>

            <Header as='h4'>Restore from a backup</Header>
            <p {...t}>
                <strong>Merge</strong> adds items from the backup that aren't already present.
                {' '}<strong>Overwrite</strong> replaces this inventory entirely with the backup.
            </p>
            {dates === null
                ? <Loader active inline='centered'>Loading backups…</Loader>
                : dates.length === 0
                    ? <p {...t}>No backups yet. A backup is saved automatically whenever this inventory changes.</p>
                    : <div style={{maxHeight: '320px', overflowY: 'auto'}}>
                        <Table compact unstackable>
                            <TableHeader>
                                <TableRow>
                                    <TableHeaderCell>Date</TableHeaderCell>
                                    <TableHeaderCell>Merge</TableHeaderCell>
                                    <TableHeaderCell>Overwrite</TableHeaderCell>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {dates.map(date => <TableRow key={date}>
                                    <TableCell>{formatDate(date)}</TableCell>
                                    <TableCell>
                                        <Button size='mini' color='green' loading={previewing === `${date}:merge`}
                                                onClick={() => selectAction(date, 'merge')}>
                                            <Icon name='plus'/> Merge
                                        </Button>
                                    </TableCell>
                                    <TableCell>
                                        <Button size='mini' color='orange'
                                                loading={previewing === `${date}:overwrite`}
                                                onClick={() => selectAction(date, 'overwrite')}>
                                            <Icon name='refresh'/> Overwrite
                                        </Button>
                                    </TableCell>
                                </TableRow>)}
                            </TableBody>
                        </Table>
                    </div>}
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Close</Button>
        </Modal.Actions>
    </Modal>;
}
