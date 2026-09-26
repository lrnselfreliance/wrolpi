import React, {useState} from 'react';
import {Link} from 'react-router';
import {IconBookmark} from '@tabler/icons-react';
import {Button, Group, Header, Icon, Menu, Message, Modal, Panel, Select, Table, Text, TextInput, Toggle} from './ui';
import {APIButton, PageContainer, useTitle} from './Common';
import {isBookmarkDirectory, resolveBookmarkUrl, useBookmarks} from '../contexts/BookmarksContext';
import {addBookmark, addBookmarkDirectory, deleteBookmark, moveBookmark, updateBookmark} from '../api';

export const EDIT_BOOKMARKS_PATH = '/more/bookmarks';

/**
 * The props that make a Menu.Item open a bookmark: an in-app Link for a path, a plain
 * anchor for everything else, and a new tab when the bookmark asks for one.
 */
function bookmarkItemProps(node) {
    const {internal, href} = resolveBookmarkUrl(node.url);
    const target = node.new_tab ? {target: '_blank', rel: 'noopener noreferrer'} : {};
    if (internal) {
        return {component: Link, to: href, ...target};
    }
    return {component: 'a', href, ...target};
}

/**
 * The items of a bookmarks menu.
 *
 * `nested` draws a directory as a flyout (Menu.Sub), which opens beside the menu on hover.
 * Without it a directory is a labelled, indented run of items instead: the mobile
 * hamburger is the one place bookmarks are shown where a flyout cannot be hovered.
 */
export function BookmarkMenuItems({nodes, nested = true, depth = 0}) {
    if (!nodes || nodes.length === 0) {
        return null;
    }
    return nodes.map(node => {
        if (isBookmarkDirectory(node)) {
            if (nested) {
                return <Menu.Sub key={node.id}>
                    <Menu.Sub.Target>
                        <Menu.Sub.Item leftSection={<Icon name='folder' size='small'/>}>{node.name}</Menu.Sub.Item>
                    </Menu.Sub.Target>
                    <Menu.Sub.Dropdown>
                        {node.children.length > 0
                            ? <BookmarkMenuItems nodes={node.children} nested={nested}/>
                            : <Menu.Item disabled>Empty</Menu.Item>}
                    </Menu.Sub.Dropdown>
                </Menu.Sub>;
            }
            return <React.Fragment key={node.id}>
                <Menu.Label style={{paddingLeft: `${0.75 + depth}em`}}>{node.name}</Menu.Label>
                <BookmarkMenuItems nodes={node.children} nested={false} depth={depth + 1}/>
            </React.Fragment>;
        }
        return <Menu.Item
            key={node.id}
            {...bookmarkItemProps(node)}
            style={nested ? undefined : {paddingLeft: `${0.75 + depth}em`}}
            rightSection={node.new_tab ? <Icon name='external' size='small'/> : undefined}
        >
            {node.name}
        </Menu.Item>;
    });
}

/**
 * Everything inside a bookmarks dropdown: the bookmarks, then the link to edit them.  The
 * edit link is always there, so a user with no bookmarks yet can find where to add one.
 */
export function BookmarksMenuContents({nested = true}) {
    const {bookmarks} = useBookmarks();
    const nodes = bookmarks || [];
    return <>
        <BookmarkMenuItems nodes={nodes} nested={nested}/>
        {nodes.length > 0 && <Menu.Divider/>}
        <Menu.Item component={Link} to={EDIT_BOOKMARKS_PATH} leftSection={<Icon name='edit' size='small'/>}>
            Edit bookmarks
        </Menu.Item>
    </>;
}

/** Every directory in the tree with its full path, for the "Location" picker. */
export function directoryOptions(nodes, prefix = '') {
    const options = [];
    for (const node of nodes || []) {
        if (isBookmarkDirectory(node)) {
            const label = `${prefix}${node.name}`;
            options.push({value: String(node.id), label, id: node.id});
            options.push(...directoryOptions(node.children, `${label} / `));
        }
    }
    return options;
}

/** The ids of `node` and everything beneath it. */
const subtreeIds = (node) => {
    const ids = [node.id];
    if (isBookmarkDirectory(node)) {
        node.children.forEach(child => ids.push(...subtreeIds(child)));
    }
    return ids;
};

const ROOT = 'root';

/** The places a node may live: the top level, and every directory not inside `node`. */
export function locationOptions(nodes, node = null) {
    // A directory cannot be moved into itself or its own children.
    const excluded = node ? new Set(subtreeIds(node)) : new Set();
    return [
        {value: ROOT, label: 'Top level'},
        ...directoryOptions(nodes).filter(i => !excluded.has(i.id)).map(({value, label}) => ({value, label})),
    ];
}

/**
 * The form for one node.  `node` is null when adding; `directory` says which kind.
 * `parentId` is where a new node goes, or where an edited one currently lives.
 */
export function BookmarkNodeModal({open, node, directory, parentId, nodes, onSave, onClose}) {
    const [name, setName] = useState(node?.name || '');
    const [url, setUrl] = useState(node?.url || '');
    const [newTab, setNewTab] = useState(Boolean(node?.new_tab));
    const [location, setLocation] = useState(parentId === null || parentId === undefined ? ROOT : String(parentId));
    const [saving, setSaving] = useState(false);

    const locations = locationOptions(nodes, node);

    const valid = name.trim() && (directory || url.trim());
    const title = node ? (directory ? 'Edit directory' : 'Edit bookmark') : (directory ? 'New directory' : 'New bookmark');

    const handleSave = async () => {
        if (!valid) return;
        setSaving(true);
        try {
            await onSave({
                name: name.trim(),
                url: url.trim(),
                new_tab: newTab,
                parent_id: location === ROOT ? null : Number(location),
            });
        } finally {
            setSaving(false);
        }
    };

    return <Modal open={open} onClose={onClose} size='tiny'>
        <Modal.Header>{title}</Modal.Header>
        <Modal.Content>
            <form onSubmit={e => {
                e.preventDefault();
                handleSave();
            }}>
                <TextInput
                    autoFocus
                    label='Name'
                    value={name}
                    onChange={e => setName(e.currentTarget.value)}
                />
                {!directory && <TextInput
                    label='URL'
                    style={{marginTop: '1em'}}
                    value={url}
                    onChange={e => setUrl(e.currentTarget.value)}
                    placeholder='/videos, :8096/, or https://example.com'
                    description='A path on this WROLPi (/videos), a port on this host (:8096/ or http://:8096/), or a full URL.'
                />}
                <Select
                    label='Location'
                    style={{marginTop: '1em'}}
                    data={locations}
                    value={location}
                    onChange={value => setLocation(value || ROOT)}
                    allowDeselect={false}
                />
                {!directory && <Toggle
                    style={{marginTop: '1em'}}
                    label='Open in a new tab'
                    checked={newTab}
                    onChange={e => setNewTab(e.currentTarget.checked)}
                />}
            </form>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            <Button role='save' disabled={!valid || saving} onClick={handleSave}>Save</Button>
        </Modal.Actions>
    </Modal>;
}

/** The rows of the editor, one per node, children beneath their directory and indented. */
function BookmarkTableRows({nodes, parentId, depth, editable, actions}) {
    return nodes.map((node, index) => {
        const directory = isBookmarkDirectory(node);
        const {href} = directory ? {} : resolveBookmarkUrl(node.url);
        return <React.Fragment key={node.id}>
            <Table.Row>
                <Table.Cell>{String(index + 1).padStart(2, '0')}</Table.Cell>
                <Table.Cell style={{width: '90px', textAlign: 'center'}}>
                    {directory
                        ? <Icon name='folder' size='large'/>
                        : <Icon name={node.new_tab ? 'external' : 'linkify'} size='large'/>}
                </Table.Cell>
                <Table.Cell style={{paddingLeft: depth ? `calc(0.75em + ${depth * 1.5}em)` : undefined}}>
                    {directory
                        ? <b>{node.name}</b>
                        : <a href={href} target={node.new_tab ? '_blank' : undefined} rel='noopener noreferrer'>
                            {node.name}
                        </a>}
                    {!directory && <Text size='xs' c='dimmed' truncate='end'>{node.url}</Text>}
                </Table.Cell>
                {editable && <Table.Cell>
                    <div className='wrolpi-button-row' style={{justifyContent: 'flex-end'}}>
                        <Button icon='arrow up' size='xs' aria-label={`Move ${node.name} up`} disabled={index === 0}
                                onClick={() => actions.move(node, parentId, index - 1)}/>
                        <Button icon='arrow down' size='xs' aria-label={`Move ${node.name} down`}
                                disabled={index === nodes.length - 1}
                                onClick={() => actions.move(node, parentId, index + 1)}/>
                        <Button icon='edit' size='xs' aria-label={`Edit ${node.name}`}
                                onClick={() => actions.edit(node, parentId)}/>
                        {directory
                            ? <APIButton
                                role='danger' icon='trash' size='xs' aria-label={`Delete ${node.name}`}
                                confirmContent={`Delete the directory "${node.name}" and everything in it?`}
                                confirmButton='Delete'
                                onClick={() => actions.remove(node)}/>
                            : <Button role='danger' icon='trash' size='xs' aria-label={`Delete ${node.name}`}
                                      onClick={() => actions.remove(node)}/>}
                    </div>
                </Table.Cell>}
            </Table.Row>
            {directory && <BookmarkTableRows nodes={node.children} parentId={node.id} depth={depth + 1}
                                             editable={editable} actions={actions}/>}
        </React.Fragment>;
    });
}

/**
 * The bookmarks table, in the shape of the playlist items table.  `actions` carries
 * edit/move/remove so the gallery can render it with none of them wired.
 */
export function BookmarkTable({nodes, editable = true, actions}) {
    return <Table>
        <Table.Header>
            <Table.Row>
                <Table.HeaderCell>#</Table.HeaderCell>
                <Table.HeaderCell>Kind</Table.HeaderCell>
                <Table.HeaderCell>Bookmark</Table.HeaderCell>
                {editable && <Table.HeaderCell/>}
            </Table.Row>
        </Table.Header>
        <Table.Body>
            <BookmarkTableRows nodes={nodes} parentId={null} depth={0} editable={editable} actions={actions}/>
        </Table.Body>
    </Table>;
}

/** The "Add a bookmark" and "Add a directory" forms beneath the table. */
export function BookmarkAddForms({nodes, onAddBookmark, onAddDirectory}) {
    const [url, setUrl] = useState('');
    const [name, setName] = useState('');
    const [newTab, setNewTab] = useState(false);
    const [location, setLocation] = useState(ROOT);
    const [directoryName, setDirectoryName] = useState('');
    const [directoryLocation, setDirectoryLocation] = useState(ROOT);
    const locations = locationOptions(nodes);
    const parentOf = (value) => value === ROOT ? null : Number(value);

    const handleAddBookmark = async () => {
        if (!url.trim() || !name.trim()) return;
        await onAddBookmark({name: name.trim(), url: url.trim(), new_tab: newTab, parent_id: parentOf(location)});
        setUrl('');
        setName('');
    };

    const handleAddDirectory = async () => {
        if (!directoryName.trim()) return;
        await onAddDirectory({name: directoryName.trim(), parent_id: parentOf(directoryLocation)});
        setDirectoryName('');
    };

    return <>
        <Header as='h4'>Add a bookmark</Header>
        <form onSubmit={e => {
            e.preventDefault();
            handleAddBookmark();
        }}>
            <Group align='flex-end' wrap='wrap'>
                <TextInput
                    style={{flex: '2 1 300px'}}
                    aria-label='Bookmark URL'
                    placeholder='URL (e.g. /videos, :8096/, or https://example.com)'
                    value={url}
                    onChange={e => setUrl(e.currentTarget.value)}/>
                <TextInput
                    style={{flex: '1 1 200px'}}
                    aria-label='Bookmark name'
                    placeholder='Name'
                    value={name}
                    onChange={e => setName(e.currentTarget.value)}/>
                <Select
                    style={{flex: '1 1 160px'}}
                    aria-label='Bookmark location'
                    data={locations}
                    value={location}
                    onChange={value => setLocation(value || ROOT)}
                    allowDeselect={false}/>
                <Toggle
                    label='New tab'
                    checked={newTab}
                    onChange={e => setNewTab(e.currentTarget.checked)}/>
                <Button role='primary' type='submit' disabled={!url.trim() || !name.trim()}>Add</Button>
            </Group>
        </form>
        <p style={{marginTop: '0.5em'}}>
            <Text size='xs' c='dimmed' component='span'>
                A URL is a path on this WROLPi (/videos), a port on this host (:8096/ or http://:8096/) that
                works whichever address you reach it by, or a full URL.
            </Text>
        </p>

        <Header as='h4'>Add a directory</Header>
        <form onSubmit={e => {
            e.preventDefault();
            handleAddDirectory();
        }}>
            <Group align='flex-end' wrap='wrap'>
                <TextInput
                    style={{flex: '2 1 300px'}}
                    aria-label='Directory name'
                    placeholder='Directory name'
                    value={directoryName}
                    onChange={e => setDirectoryName(e.currentTarget.value)}/>
                <Select
                    style={{flex: '1 1 160px'}}
                    aria-label='Directory location'
                    data={locations}
                    value={directoryLocation}
                    onChange={value => setDirectoryLocation(value || ROOT)}
                    allowDeselect={false}/>
                <Button role='primary' type='submit' disabled={!directoryName.trim()}>Add</Button>
            </Group>
        </form>
    </>;
}

export function BookmarksPage() {
    useTitle('Bookmarks');
    const {bookmarks, refresh} = useBookmarks();
    // {node, directory, parentId} while the edit modal is open; a `key` remounts the form fresh.
    const [modal, setModal] = useState(null);
    const [modalKey, setModalKey] = useState(0);
    const nodes = bookmarks || [];

    const actions = {
        edit: (node, parentId) => {
            setModalKey(k => k + 1);
            setModal({node, directory: isBookmarkDirectory(node), parentId});
        },
        move: async (node, parentId, position) => {
            try {
                await moveBookmark(node.id, parentId, position);
                await refresh();
            } catch (e) {
                // Error toast already shown by the API client.
            }
        },
        remove: async (node) => {
            try {
                await deleteBookmark(node.id);
                await refresh();
            } catch (e) {
            }
        },
    };

    const handleAddBookmark = async (bookmark) => {
        try {
            await addBookmark(bookmark);
            await refresh();
        } catch (e) {
        }
    };

    const handleAddDirectory = async (directory) => {
        try {
            await addBookmarkDirectory(directory);
            await refresh();
        } catch (e) {
        }
    };

    const handleEditSave = async ({name, url, new_tab, parent_id}) => {
        const {node, directory, parentId} = modal;
        try {
            await updateBookmark(node.id, directory ? {name} : {name, url, new_tab});
            if (parent_id !== parentId) {
                await moveBookmark(node.id, parent_id);
            }
            await refresh();
            setModal(null);
        } catch (e) {
        }
    };

    return <PageContainer>
        <Panel>
            <Header as='h1' icon={IconBookmark}>Bookmarks</Header>
            <p>
                Bookmarks appear in the Bookmarks menu of the navigation bar. They can point at pages on this
                WROLPi, at other services running beside it, or anywhere on the web.
            </p>

            {nodes.length === 0
                ? <Message title='There are no bookmarks yet'>Add a bookmark below.</Message>
                : <BookmarkTable nodes={nodes} actions={actions}/>}

            <BookmarkAddForms nodes={nodes} onAddBookmark={handleAddBookmark} onAddDirectory={handleAddDirectory}/>
        </Panel>
        {modal && <BookmarkNodeModal
            key={modalKey}
            open
            node={modal.node}
            directory={modal.directory}
            parentId={modal.parentId}
            nodes={nodes}
            onSave={handleEditSave}
            onClose={() => setModal(null)}
        />}
    </PageContainer>;
}
