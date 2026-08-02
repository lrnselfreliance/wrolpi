import React, {useMemo, useState} from "react";
import {
    Button, Confirm, Header, IconButton, Loading, Modal, Panel, SearchBox, Select, TabBar, tabClassName, Text,
    TextInput,
} from "../ui";
import {PageContainer, useTitle} from "../Common";
import {collectLocations, useCatalog, useInventories} from "../../hooks/customHooks";
import {filterItems, InventoryTable} from "./InventoryTable";
import {InventoryItemsMobile} from "./InventoryItemsMobile";
import {InventorySummary} from "./InventorySummary";
import {InventoryExportPanel} from "./InventoryExportPanel";
import {InventoryPrint} from "./InventoryPrint";
import {RationEstimatePanel} from "../calculators/RationCalculator";
import {defaultGroupKey, defaultSumKey, findCaloriesKey, findCountKey} from "./summarize";
import {FieldSchemaEditor} from "./FieldSchemaEditor";
import {CatalogEditor} from "./CatalogEditor";
import {InventoryImportModal} from "./InventoryImportModal";
import {Media} from "../../contexts/contexts";

const INVENTORY_TYPES = [
    {value: 'food', label: 'Food Storage'},
    {value: 'fuel', label: 'Fuel'},
    {value: 'tool', label: 'Tools'},
];

function NewInventoryModal({open, onClose, onCreate}) {
    const [name, setName] = useState('');
    const [type, setType] = useState('food');

    const create = async () => {
        const inventory = await onCreate(name, type);
        if (inventory) {
            setName('');
            setType('food');
            onClose();
        }
    };

    return <Modal size='small' open={open} onClose={onClose} closeIcon>
        <Modal.Header>New Inventory</Modal.Header>
        <Modal.Content>
            <TextInput autoFocus label='Name' value={name} onChange={e => setName(e.currentTarget.value)}
                       placeholder='Food Storage' mb='1em'/>
            <div>
                Type:{' '}
                <Select data={INVENTORY_TYPES} value={type} onChange={setType}/>
                <Text size='sm' c='dimmed' mt='0.5em'>
                    The type seeds a starting set of fields — you can customize them afterward.
                </Text>
            </div>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button role='primary' onClick={create} disabled={!name.trim()}>Create</Button>
        </Modal.Actions>
    </Modal>;
}

export function InventoryRoute() {
    useTitle('Inventory');
    const {inventories, fetchInventories, persistInventory, addInventory, removeInventory} = useInventories();
    const {catalog, persistCatalog} = useCatalog();
    const [slug, setSlug] = useState(null);

    const [tab, setTab] = useState('items');
    const [newOpen, setNewOpen] = useState(false);
    const [catalogOpen, setCatalogOpen] = useState(false);
    const [editFieldsOpen, setEditFieldsOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [renaming, setRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [confirmDelete, setConfirmDelete] = useState(false);
    // Grouping for the PDF export's summary table (chosen in the Export tab, rendered by the always-mounted print
    // view).  null until seeded from the current inventory's schema.
    const [exportGroupKey, setExportGroupKey] = useState(null);
    const [exportSumKey, setExportSumKey] = useState(null);
    // Free-text filter applied to the active inventory's items across every column.
    const [search, setSearch] = useState('');

    // Default to the first inventory once loaded.
    React.useEffect(() => {
        if (slug == null && inventories && inventories.length > 0) {
            setSlug(inventories[0].slug);
        }
    }, [inventories, slug]);

    const current = inventories?.find(i => i.slug === slug);
    const fields = useMemo(() => (current ? current.fields : []), [current]);
    const items = useMemo(() => (current ? current.items : []), [current]);
    // The Ration tab (estimate + supply plan) only applies to inventories with a calories field.
    const caloriesKey = useMemo(() => findCaloriesKey(fields), [fields]);
    const countKey = useMemo(() => findCountKey(fields), [fields]);

    // Re-seed the export grouping when the selected inventory (or its schema) changes.
    React.useEffect(() => {
        setExportGroupKey(defaultGroupKey(fields));
        setExportSumKey(defaultSumKey(fields));
    }, [fields]);
    // Clear the search when switching inventories.
    React.useEffect(() => setSearch(''), [slug]);
    // The Ration tab disappears for inventories without a calories field; fall back to Items if it was active.
    React.useEffect(() => {
        if (tab === 'ration' && !caloriesKey) {
            setTab('items');
        }
    }, [tab, caloriesKey]);

    // The search lives in (and only narrows) the Items tab.  It feeds the read-only mobile list here; the desktop
    // table filters its own display from the full `items` it receives.  Summary/Ration/Export always use the full
    // inventory, so the filter never silently hides data on those tabs.
    const filteredItems = useMemo(() => filterItems(items, fields, search), [items, fields, search]);

    // Location suggestions are pooled across every inventory.
    const locations = collectLocations(inventories);

    const onCreate = async (name, type) => {
        const inventory = await addInventory(name, type);
        if (inventory) {
            setSlug(inventory.slug);
        }
        return inventory;
    };

    const doRename = async () => {
        await persistInventory(slug, {name: renameValue});
        setRenaming(false);
    };

    const doDelete = async () => {
        await removeInventory(slug);
        setConfirmDelete(false);
        setSlug(null);
    };

    if (inventories === null) {
        return <PageContainer><Loading/></PageContainer>;
    }

    const inventoryOptions = inventories.map(i => ({value: i.slug, label: i.name}));

    const tabs = [
        {key: 'items', label: 'Items'},
        {key: 'summary', label: 'Summary'},
        ...(caloriesKey ? [{key: 'ration', label: 'Ration'}] : []),
        {key: 'export', label: 'Export'},
    ];

    return <PageContainer>
        <Header as='h1'>Inventory</Header>

        <Panel>
            <div style={{display: 'flex', gap: '0.5em', alignItems: 'center', flexWrap: 'wrap'}}>
                <Select
                    placeholder='Select an inventory'
                    data={inventoryOptions}
                    value={slug || ''}
                    onChange={value => setSlug(value)}
                    style={{minWidth: '14em'}}
                />
                <IconButton role='primary' icon='plus' onClick={() => setNewOpen(true)} label='New inventory'/>
                <Button icon='book' onClick={() => setCatalogOpen(true)}>Catalog</Button>
                {current && <>
                    <IconButton icon='edit' onClick={() => {
                        setRenameValue(current.name);
                        setRenaming(true);
                    }} label='Rename inventory'/>
                    <Button icon='columns' onClick={() => setEditFieldsOpen(true)}>Fields</Button>
                    <Button icon='history' onClick={() => setImportOpen(true)}>Restore</Button>
                    <IconButton role='danger' icon='trash' onClick={() => setConfirmDelete(true)}
                                label='Delete inventory'/>
                </>}
            </div>
        </Panel>

        {current ? <>
            <TabBar>
                {tabs.map(({key, label}) => <button
                    key={key}
                    type='button'
                    className={tabClassName(tab === key)}
                    onClick={() => setTab(key)}
                >{label}</button>)}
            </TabBar>

            {tab === 'items' && <>
                {/* The search filter lives here so it clearly applies to the Items tab only, not Summary/Ration/Export. */}
                <div style={{marginBottom: '0.75em'}}>
                    <SearchBox value={search} onChange={setSearch} clearable placeholder='Search items…'
                               label='Search items'/>
                </div>
                {/* Portrait mobile: condensed, read-only.  Rotate to landscape (tablet+) for the full editor. */}
                <Media at='mobile'>
                    <InventoryItemsMobile fields={fields} items={filteredItems}/>
                </Media>
                <Media greaterThanOrEqual='tablet'>
                    {/* The table gets the FULL items (so edits/adds don't drop filtered-out rows) plus the search,
                        which it applies to its displayed rows only. */}
                    <InventoryTable slug={slug} fields={fields} items={items} locations={locations}
                                    catalog={catalog} search={search}
                                    onChange={newItems => persistInventory(slug, {items: newItems})}/>
                </Media>
            </>}
            {tab === 'summary' && <InventorySummary fields={fields} items={items}/>}
            {tab === 'ration' && caloriesKey &&
                <RationEstimatePanel name={current.name} fields={fields} items={items}
                                     caloriesKey={caloriesKey} countKey={countKey}/>}
            {tab === 'export' &&
                <InventoryExportPanel name={current.name} fields={fields} items={items}
                                      groupKey={exportGroupKey} sumKey={exportSumKey}
                                      onGroupKey={setExportGroupKey} onSumKey={setExportSumKey}/>}

            {/* Always mounted (hidden on screen) so the browser print dialog has the full table + summary to render. */}
            <InventoryPrint name={current.name} fields={fields} items={items}
                            groupKey={exportGroupKey} sumKey={exportSumKey}/>

            <FieldSchemaEditor fields={fields} open={editFieldsOpen}
                               onClose={() => setEditFieldsOpen(false)}
                               onSave={newFields => persistInventory(slug, {fields: newFields})}/>

            <InventoryImportModal open={importOpen} onClose={() => setImportOpen(false)}
                                  slug={slug} name={current.name} onChanged={fetchInventories}/>
        </> : <Text>Create an inventory to get started.</Text>}

        <NewInventoryModal open={newOpen} onClose={() => setNewOpen(false)} onCreate={onCreate}/>

        <CatalogEditor catalog={catalog || []} open={catalogOpen} onClose={() => setCatalogOpen(false)}
                       onSave={persistCatalog}/>

        <Modal open={renaming} onClose={() => setRenaming(false)} closeIcon size='tiny'>
            <Modal.Header>Rename Inventory</Modal.Header>
            <Modal.Content>
                <TextInput autoFocus value={renameValue} onChange={e => setRenameValue(e.currentTarget.value)}/>
            </Modal.Content>
            <Modal.Actions>
                <Button role='cancel' onClick={() => setRenaming(false)}>Cancel</Button>
                <Button role='save' onClick={doRename} disabled={!renameValue.trim()}>Save</Button>
            </Modal.Actions>
        </Modal>

        <Confirm
            open={confirmDelete}
            title='Delete Inventory'
            destructive
            confirmLabel='Delete'
            onCancel={() => setConfirmDelete(false)}
            onConfirm={doDelete}
        >
            {`Delete "${current?.name}" and all its items?  This cannot be undone.`}
        </Confirm>
    </PageContainer>;
}
