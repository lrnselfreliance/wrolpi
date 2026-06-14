import React, {useState} from "react";
import {Dropdown, Input, Select} from "semantic-ui-react";
import {Button, Confirm, Header, Icon, Loader, Menu, Modal, Segment} from "../Theme";
import {PageContainer, useTitle} from "../Common";
import {collectLocations, useCatalog, useInventories} from "../../hooks/customHooks";
import {InventoryTable} from "./InventoryTable";
import {InventorySummary} from "./InventorySummary";
import {FieldSchemaEditor} from "./FieldSchemaEditor";
import {CatalogEditor} from "./CatalogEditor";

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

    // Default to the first inventory once loaded.
    React.useEffect(() => {
        if (slug == null && inventories && inventories.length > 0) {
            setSlug(inventories[0].slug);
        }
    }, [inventories, slug]);

    const current = inventories?.find(i => i.slug === slug);
    const fields = current ? current.fields : [];
    const items = current ? current.items : [];
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
        </Segment>

        {current ? <>
            <Menu pointing secondary>
                <Menu.Item name='Items' active={tab === 'items'} onClick={() => setTab('items')}/>
                <Menu.Item name='Summary' active={tab === 'summary'} onClick={() => setTab('summary')}/>
            </Menu>

            {tab === 'items'
                ? <InventoryTable slug={slug} fields={fields} items={items} locations={locations} catalog={catalog}
                                  onChange={newItems => persistInventory(slug, {items: newItems})}/>
                : <InventorySummary fields={fields} items={items}/>}

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
