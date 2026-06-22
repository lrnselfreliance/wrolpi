import React, {useMemo, useState} from "react";
import {Dropdown, Input, Message, Select} from "semantic-ui-react";
import {Button, Confirm, Header, Icon, Loader, Menu, Modal, Segment} from "../Theme";
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
import {Media, ThemeContext} from "../../contexts/contexts";
import {usePwa} from "../../contexts/PwaContext";

const INVENTORY_TYPES = [
    {key: 'food', value: 'food', text: 'Food Storage'},
    {key: 'fuel', value: 'fuel', text: 'Fuel'},
    {key: 'tool', value: 'tool', text: 'Tools'},
];

function NewInventoryModal({open, onClose, onCreate}) {
    const [name, setName] = useState('');
    const [type, setType] = useState('food');
    const {t} = React.useContext(ThemeContext);

    const create = async () => {
        const inventory = await onCreate(name, type);
        if (inventory) {
            setName('');
            setType('food');
            onClose();
        }
    };

    return <Modal open={open} onClose={onClose} closeIcon>
        <Modal.Header>New Inventory</Modal.Header>
        <Modal.Content>
            <Input fluid label='Name' value={name} onChange={e => setName(e.target.value)}
                   placeholder='Food Storage' style={{marginBottom: '1em'}}/>
            <div>
                Type:{' '}
                <Select options={INVENTORY_TYPES} value={type} onChange={(e, data) => setType(data.value)}/>
                <p {...t} style={{...t.style, fontSize: '0.85em', opacity: 0.7, marginTop: '0.5em'}}>
                    The type seeds a starting set of fields — you can customize them afterward.
                </p>
            </div>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Cancel</Button>
            <Button primary onClick={create} disabled={!name.trim()}>Create</Button>
        </Modal.Actions>
    </Modal>;
}

export function InventoryRoute() {
    useTitle('Inventory');
    const {inventories, fetchInventories, persistInventory, addInventory, removeInventory} = useInventories();
    const {catalog, persistCatalog} = useCatalog();
    const [slug, setSlug] = useState(null);

    // When offline, inventory reads come from the service-worker cache, but writes can't reach the config-only
    // backend, so the editing UI is disabled and a read-only banner is shown.
    const {offline} = usePwa();

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

    const {t} = React.useContext(ThemeContext);

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
        return <PageContainer><Loader active inline='centered'/></PageContainer>;
    }

    const inventoryOptions = inventories.map(i => ({key: i.slug, value: i.slug, text: i.name}));

    return <PageContainer>
        <Header as='h1'>Inventory</Header>

        {offline &&
            <Message icon warning>
                <Icon name='wifi'/>
                <Message.Content>
                    <Message.Header>Offline — read only</Message.Header>
                    You're viewing the last synced copy of your inventory. Changes can't be saved until you reconnect.
                </Message.Content>
            </Message>}

        <Segment>
            <div style={{display: 'flex', gap: '0.5em', alignItems: 'center', flexWrap: 'wrap'}}>
                <Dropdown
                    selection
                    placeholder='Select an inventory'
                    options={inventoryOptions}
                    value={slug || ''}
                    onChange={(e, data) => setSlug(data.value)}
                    style={{minWidth: '14em'}}
                />
                <Button primary icon disabled={offline} onClick={() => setNewOpen(true)} aria-label='New inventory'>
                    <Icon name='plus'/>
                </Button>
                <Button icon disabled={offline} onClick={() => setCatalogOpen(true)} aria-label='Food catalog'>
                    <Icon name='book'/> Catalog
                </Button>
                {current && <>
                    <Button icon disabled={offline} onClick={() => {
                        setRenameValue(current.name);
                        setRenaming(true);
                    }} aria-label='Rename inventory'><Icon name='edit'/></Button>
                    <Button icon disabled={offline} onClick={() => setEditFieldsOpen(true)} aria-label='Customize fields'>
                        <Icon name='columns'/> Fields
                    </Button>
                    <Button icon disabled={offline} onClick={() => setImportOpen(true)} aria-label='Import or restore inventory'>
                        <Icon name='history'/> Restore
                    </Button>
                    <Button color='red' icon disabled={offline} onClick={() => setConfirmDelete(true)} aria-label='Delete inventory'>
                        <Icon name='trash'/>
                    </Button>
                </>}
            </div>
        </Segment>

        {current ? <>
            <Menu pointing secondary>
                <Menu.Item name='Items' active={tab === 'items'} onClick={() => setTab('items')}/>
                <Menu.Item name='Summary' active={tab === 'summary'} onClick={() => setTab('summary')}/>
                {caloriesKey &&
                    <Menu.Item name='Ration' active={tab === 'ration'} onClick={() => setTab('ration')}/>}
                <Menu.Item name='Export' active={tab === 'export'} onClick={() => setTab('export')}/>
            </Menu>

            {tab === 'items' && <>
                {/* The search filter lives here so it clearly applies to the Items tab only, not Summary/Ration/Export. */}
                <Input fluid icon='search' iconPosition='left' placeholder='Search items…' value={search}
                       aria-label='Search items' clearable style={{marginBottom: '0.75em'}}
                       onChange={(e, data) => setSearch(data.value)}/>
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
        </> : <p {...t}>Create an inventory to get started.</p>}

        <NewInventoryModal open={newOpen} onClose={() => setNewOpen(false)} onCreate={onCreate}/>

        <CatalogEditor catalog={catalog || []} open={catalogOpen} onClose={() => setCatalogOpen(false)}
                       onSave={persistCatalog}/>

        <Modal open={renaming} onClose={() => setRenaming(false)} closeIcon size='tiny'>
            <Modal.Header>Rename Inventory</Modal.Header>
            <Modal.Content>
                <Input fluid value={renameValue} onChange={e => setRenameValue(e.target.value)}/>
            </Modal.Content>
            <Modal.Actions>
                <Button onClick={() => setRenaming(false)}>Cancel</Button>
                <Button primary onClick={doRename} disabled={!renameValue.trim()}>Save</Button>
            </Modal.Actions>
        </Modal>

        <Confirm
            open={confirmDelete}
            header='Delete Inventory'
            content={`Delete "${current?.name}" and all its items?  This cannot be undone.`}
            confirmButton='Delete'
            onCancel={() => setConfirmDelete(false)}
            onConfirm={doDelete}
        />
    </PageContainer>;
}
