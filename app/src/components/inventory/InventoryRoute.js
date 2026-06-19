import React, {useMemo, useState} from "react";
import {Dropdown, Input, Select} from "semantic-ui-react";
import {Button, Confirm, Header, Icon, Loader, Menu, Modal, Segment} from "../Theme";
import {PageContainer, useTitle} from "../Common";
import {collectLocations, useCatalog, useInventories} from "../../hooks/customHooks";
import {filterItems, InventoryTable} from "./InventoryTable";
import {InventoryItemsMobile} from "./InventoryItemsMobile";
import {InventorySummary} from "./InventorySummary";
import {InventoryExportPanel} from "./InventoryExportPanel";
import {InventoryPrint} from "./InventoryPrint";
import {defaultGroupKey, defaultSumKey} from "./summarize";
import {FieldSchemaEditor} from "./FieldSchemaEditor";
import {CatalogEditor} from "./CatalogEditor";
import {Media} from "../../contexts/contexts";

const INVENTORY_TYPES = [
    {key: 'food', value: 'food', text: 'Food Storage'},
    {key: 'fuel', value: 'fuel', text: 'Fuel'},
    {key: 'tool', value: 'tool', text: 'Tools'},
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

    return <Modal open={open} onClose={onClose} closeIcon>
        <Modal.Header>New Inventory</Modal.Header>
        <Modal.Content>
            <Input fluid label='Name' value={name} onChange={e => setName(e.target.value)}
                   placeholder='Food Storage' style={{marginBottom: '1em'}}/>
            <div>
                Type:{' '}
                <Select options={INVENTORY_TYPES} value={type} onChange={(e, data) => setType(data.value)}/>
                <p style={{fontSize: '0.85em', opacity: 0.7, marginTop: '0.5em'}}>
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
    const {inventories, persistInventory, addInventory, removeInventory} = useInventories();
    const {catalog, persistCatalog} = useCatalog();
    const [slug, setSlug] = useState(null);

    const [tab, setTab] = useState('items');
    const [newOpen, setNewOpen] = useState(false);
    const [catalogOpen, setCatalogOpen] = useState(false);
    const [editFieldsOpen, setEditFieldsOpen] = useState(false);
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

    // Re-seed the export grouping when the selected inventory (or its schema) changes.
    React.useEffect(() => {
        setExportGroupKey(defaultGroupKey(fields));
        setExportSumKey(defaultSumKey(fields));
    }, [fields]);
    // Clear the search when switching inventories.
    React.useEffect(() => setSearch(''), [slug]);

    // The search narrows the whole inventory view (Items display, Summary, Export); edits/adds in InventoryTable
    // still operate on the full `items`, so filtering never drops data.
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
                <Button primary icon onClick={() => setNewOpen(true)} aria-label='New inventory'>
                    <Icon name='plus'/>
                </Button>
                <Button icon onClick={() => setCatalogOpen(true)} aria-label='Food catalog'>
                    <Icon name='book'/> Catalog
                </Button>
                {current && <>
                    <Button icon onClick={() => {
                        setRenameValue(current.name);
                        setRenaming(true);
                    }} aria-label='Rename inventory'><Icon name='edit'/></Button>
                    <Button icon onClick={() => setEditFieldsOpen(true)} aria-label='Customize fields'>
                        <Icon name='columns'/> Fields
                    </Button>
                    <Button color='red' icon onClick={() => setConfirmDelete(true)} aria-label='Delete inventory'>
                        <Icon name='trash'/>
                    </Button>
                </>}
            </div>
            {current &&
                <Input fluid icon='search' iconPosition='left' placeholder='Search items…' value={search}
                       aria-label='Search items' clearable style={{marginTop: '0.75em'}}
                       onChange={(e, data) => setSearch(data.value)}/>}
        </Segment>

        {current ? <>
            <Menu pointing secondary>
                <Menu.Item name='Items' active={tab === 'items'} onClick={() => setTab('items')}/>
                <Menu.Item name='Summary' active={tab === 'summary'} onClick={() => setTab('summary')}/>
                <Menu.Item name='Export' active={tab === 'export'} onClick={() => setTab('export')}/>
            </Menu>

            {tab === 'items' && <>
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
            {tab === 'summary' && <InventorySummary fields={fields} items={filteredItems}/>}
            {tab === 'export' &&
                <InventoryExportPanel name={current.name} fields={fields} items={filteredItems}
                                      groupKey={exportGroupKey} sumKey={exportSumKey}
                                      onGroupKey={setExportGroupKey} onSumKey={setExportSumKey}/>}

            {/* Always mounted (hidden on screen) so the browser print dialog has the full table + summary to render. */}
            <InventoryPrint name={current.name} fields={fields} items={filteredItems}
                            groupKey={exportGroupKey} sumKey={exportSumKey}/>

            <FieldSchemaEditor fields={fields} open={editFieldsOpen}
                               onClose={() => setEditFieldsOpen(false)}
                               onSave={newFields => persistInventory(slug, {fields: newFields})}/>
        </> : <p>Create an inventory to get started.</p>}

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
