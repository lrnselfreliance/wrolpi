import React, {useEffect, useState} from "react";
import {Link, Route, Routes, useNavigate, useParams} from "react-router";
import {Grid, Image, Input, Message} from "semantic-ui-react";
import {toast} from "react-semantic-toasts-2";

import {Button, Form, Header, Icon, Loader, Modal, Segment, Table} from "./Theme";
import {
    APIButton,
    encodeMediaPath,
    ErrorMessage,
    findPosterPath,
    mimetypeColor,
    mimetypeIconName,
    PageContainer,
    PreviewLink,
    SearchInput,
    useTitle,
} from "./Common";
import {useOneQuery, useWROLMode} from "../hooks/customHooks";
import {CollectionTable} from "./collections/CollectionTable";
import {TagsSelector} from "../Tags";
import {
    addPlaylistItem,
    createPlaylist,
    deletePlaylist,
    fetchPlaylists,
    getPlaylist,
    removePlaylistItem,
    reorderPlaylistItems,
    setPlaylistTag,
} from "../api";


const PLAYLIST_COLUMNS = [
    {key: 'name', label: 'Name', sortable: true},
    {key: 'item_count', label: 'Items', sortable: true, width: 2},
    {key: 'tag_name', label: 'Tag', width: 3},
    {key: 'actions', type: 'actions', label: 'Manage', width: 2, align: 'right'},
];
// The "Name" column links to the view-only page; the "Edit" button links to the edit page.
const PLAYLIST_ROUTES = {search: '/playlists/:id', edit: '/playlists/:id/edit', id_field: 'id'};


function usePlaylists() {
    const [playlists, setPlaylists] = useState(null);  // null=loading, []/[...]=ok, undefined=error

    const refetch = async () => {
        try {
            setPlaylists(await fetchPlaylists());
        } catch (e) {
            console.error(e);
            setPlaylists(undefined);
        }
    };

    useEffect(() => {
        refetch();
    }, []);

    return {playlists, refetch};
}


function usePlaylist(playlistId) {
    const [playlist, setPlaylist] = useState(null);

    const refetch = async () => {
        try {
            setPlaylist(await getPlaylist(playlistId));
        } catch (e) {
            console.error(e);
            setPlaylist(undefined);
        }
    };

    useEffect(() => {
        refetch();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playlistId]);

    return {playlist, refetch};
}


export function PlaylistsPage() {
    useTitle('Playlists');
    const {playlists, refetch} = usePlaylists();
    const [searchStr, setSearchStr] = useOneQuery('name');
    const [modalOpen, setModalOpen] = useState(false);
    const [name, setName] = useState('');
    const searchInputRef = React.useRef();
    const navigate = useNavigate();

    const handleCreate = async () => {
        const trimmed = name.trim();
        if (!trimmed) return;
        try {
            const playlist = await createPlaylist(trimmed);
            toast({type: 'success', title: 'Playlist created', description: trimmed, time: 3000});
            setName('');
            setModalOpen(false);
            if (playlist && playlist.id) {
                navigate(`/playlists/${playlist.id}`);
            } else {
                await refetch();
            }
        } catch (e) {
            // Error toast already shown by the API client.
        }
    };

    const header = <div style={{marginBottom: '1em'}}>
        <Grid stackable columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <SearchInput
                        placeholder='Name filter...'
                        size='large'
                        searchStr={searchStr}
                        disabled={!Array.isArray(playlists) || playlists.length === 0}
                        onClear={() => setSearchStr('')}
                        onChange={setSearchStr}
                        onSubmit={null}
                        inputRef={searchInputRef}
                    />
                </Grid.Column>
                <Grid.Column textAlign='right'>
                    <Button secondary onClick={() => setModalOpen(true)}>New Playlist</Button>
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </div>;

    const createModal = <Modal open={modalOpen} onClose={() => setModalOpen(false)} size='tiny'>
        <Modal.Header>New Playlist</Modal.Header>
        <Modal.Content>
            <Form onSubmit={handleCreate}>
                <Form.Field>
                    <label>Name</label>
                    <Input autoFocus placeholder='Playlist name...' value={name}
                           onChange={(e, {value}) => setName(value)}/>
                </Form.Field>
            </Form>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button primary disabled={!name.trim()} onClick={handleCreate}>Create</Button>
        </Modal.Actions>
    </Modal>;

    return <>
        {header}
        {createModal}
        <CollectionTable
            collections={playlists}
            columns={PLAYLIST_COLUMNS}
            routes={PLAYLIST_ROUTES}
            searchStr={searchStr}
            emptyMessage='No playlists yet'
        />
    </>;
}


// Icon (name + color) for a playlist item.  File items use the FileGroup's mimetype/model icon
// and color (video, pdf, ebook, image, ...) so they match the rest of the UI; zim/url are fixed.
function itemIcon(item) {
    if (item.item_kind === 'file' && item.file_group) {
        const fg = item.file_group;
        const lowerPath = (fg.primary_path || '').toLowerCase();
        return {name: mimetypeIconName(fg.mimetype, lowerPath), color: mimetypeColor(fg.mimetype, lowerPath)};
    }
    if (item.item_kind === 'zim') return {name: 'book'};
    if (item.item_kind === 'url') {
        // A map-location URL (e.g. /map?lat=&lon=) gets a map marker; other URLs get the link icon.
        const u = (item.url || '').toLowerCase();
        if (u.startsWith('/map')) return {name: 'map marker alternate'};
        return {name: 'linkify'};
    }
    return {name: 'file'};
}


function itemLabel(item) {
    if (item.item_kind === 'file' && item.file_group) {
        return item.title || item.file_group.title || item.file_group.primary_path || 'File';
    }
    if (item.item_kind === 'zim' && item.zim) {
        return item.title || item.zim.entry;
    }
    if (item.item_kind === 'url') {
        return item.title || item.url;
    }
    return item.title || 'Item';
}


// Only http(s) and relative WROLPi paths are safe for an href; reject javascript:/data:/etc. so a
// shared playlist's url item cannot execute script when opened.  Exported for tests.
export function safeHref(url) {
    if (!url) return null;
    try {
        const u = new URL(url, window.location.origin);
        if (u.protocol === 'http:' || u.protocol === 'https:') {
            return url;  // Keep the original (may be a relative WROLPi path).
        }
    } catch {
        return null;
    }
    return null;
}


function itemLink(item) {
    if (item.item_kind === 'url') {
        return safeHref(item.url);
    }
    if (item.item_kind === 'zim' && item.zim) {
        // Built from a numeric id + encoded entry — no user-supplied scheme.
        return `/api/zim/${item.zim.id}/entry/${encodeURIComponent(item.zim.entry)}`;
    }
    return null;
}


// The in-app model page for a FileGroup, or null when there is none (image, audio, 3D, ...).
function fileModelUrl(fg) {
    if (!fg) return null;
    if (fg.model === 'video') return `/videos/${fg.id}`;
    if (fg.model === 'archive') return `/archives/${fg.id}`;
    if (fg.model === 'doc') return `/docs/${fg.id}`;
    return null;
}


// Render a playlist item's title as the appropriate link:
// - file with a model page (video/archive/doc) -> in-app Link to that page
// - file without a model page (image, etc.)     -> PreviewLink (opens the preview modal)
// - zim/url                                      -> the entry/url in a new tab
function ItemTitle({item, label}) {
    if (item.item_kind === 'file' && item.file_group) {
        const url = fileModelUrl(item.file_group);
        if (url) {
            return <Link to={url}>{label}</Link>;
        }
        return <PreviewLink file={item.file_group}>{label}</PreviewLink>;
    }
    const link = itemLink(item);
    return link
        ? <a href={link} target='_blank' rel='noopener noreferrer'>{label}</a>
        : <span>{label}</span>;
}


// The ordered items table, shared by the view and edit pages.  When `editable`, the reorder/remove
// action buttons (and their column) are shown; otherwise the table is read-only.
function PlaylistItemsTable({items, editable, onMove, onRemove}) {
    return <Table unstackable celled>
        <Table.Header>
            <Table.Row>
                <Table.HeaderCell collapsing>#</Table.HeaderCell>
                <Table.HeaderCell collapsing>Item</Table.HeaderCell>
                <Table.HeaderCell>Title</Table.HeaderCell>
                {editable && <Table.HeaderCell collapsing/>}
            </Table.Row>
        </Table.Header>
        <Table.Body>
            {items.map((item, index) => {
                const label = itemLabel(item);
                const poster = item.item_kind === 'file' && item.file_group
                    ? findPosterPath(item.file_group) : null;
                return <Table.Row key={item.id} verticalAlign='middle'>
                    <Table.Cell collapsing>{String(index + 1).padStart(2, '0')}</Table.Cell>
                    <Table.Cell collapsing textAlign='center' style={{width: '90px'}}>
                        {poster
                            ? <Image src={`/media/${encodeMediaPath(poster)}`} alt=''
                                     centered style={{maxHeight: '45px', maxWidth: '80px', width: 'auto'}}/>
                            : <Icon {...itemIcon(item)} size='large'/>}
                    </Table.Cell>
                    <Table.Cell>
                        <ItemTitle item={item} label={label}/>
                    </Table.Cell>
                    {editable && <Table.Cell collapsing textAlign='right'>
                        <Button icon='arrow up' size='mini' disabled={index === 0}
                                onClick={() => onMove(index, -1)}/>
                        <Button icon='arrow down' size='mini' disabled={index === items.length - 1}
                                onClick={() => onMove(index, 1)}/>
                        <Button icon='trash' color='red' size='mini'
                                onClick={() => onRemove(item.id)}/>
                    </Table.Cell>}
                </Table.Row>;
            })}
        </Table.Body>
    </Table>;
}


// View-only playlist page (opened from the "Name" column).  No reorder/remove/add/delete controls;
// just an "Edit" button to switch to the edit page.
export function PlaylistViewPage() {
    const {playlistId} = useParams();
    const {playlist} = usePlaylist(playlistId);

    useTitle(playlist && playlist.name ? `${playlist.name} Playlist` : 'Playlist');

    if (playlist === undefined) {
        return <ErrorMessage>Could not fetch playlist</ErrorMessage>;
    }
    if (playlist === null) {
        return <Loader active inline='centered'/>;
    }

    const items = playlist.items || [];

    return <>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1em'}}>
            <Header as='h1' style={{marginTop: 0}}>{playlist.name}</Header>
            <Button as={Link} to={`/playlists/${playlistId}/edit`} secondary icon='edit' content='Edit'/>
        </div>
        {playlist.description && <p>{playlist.description}</p>}

        {items.length === 0
            ? <Message><Message.Header>This playlist is empty</Message.Header></Message>
            : <PlaylistItemsTable items={items} editable={false}/>}
    </>;
}


// Edit playlist page (opened from the "Edit" button): reorder, remove, add URL items, delete playlist.
export function PlaylistEditPage() {
    const {playlistId} = useParams();
    const {playlist, refetch} = usePlaylist(playlistId);
    const navigate = useNavigate();
    const wrolMode = useWROLMode();
    const [url, setUrl] = useState('');
    const [urlTitle, setUrlTitle] = useState('');

    useTitle(playlist && playlist.name ? `Edit ${playlist.name} Playlist` : 'Edit Playlist');

    if (playlist === undefined) {
        return <ErrorMessage>Could not fetch playlist</ErrorMessage>;
    }
    if (playlist === null) {
        return <Loader active inline='centered'/>;
    }

    const items = playlist.items || [];
    // Editing is blocked while in WROL Mode (the API enforces this too); fall back to a read-only view.
    const editable = !wrolMode;

    const handleAddTag = async (name) => {
        try {
            await setPlaylistTag(playlistId, name);
            await refetch();
        } catch (e) {
        }
    };

    const handleRemoveTag = async () => {
        try {
            await setPlaylistTag(playlistId, '');
            await refetch();
        } catch (e) {
        }
    };

    const handleAddUrl = async () => {
        const trimmed = url.trim();
        if (!trimmed) return;
        try {
            await addPlaylistItem(playlistId, {
                item_kind: 'url', url: trimmed, title: urlTitle.trim() || null,
            });
            setUrl('');
            setUrlTitle('');
            await refetch();
        } catch (e) {
            // Error toast already shown.
        }
    };

    const handleRemove = async (itemId) => {
        try {
            await removePlaylistItem(playlistId, itemId);
            await refetch();
        } catch (e) {
        }
    };

    const move = async (index, delta) => {
        const ids = items.map(i => i.id);
        const target = index + delta;
        if (target < 0 || target >= ids.length) return;
        [ids[index], ids[target]] = [ids[target], ids[index]];
        try {
            await reorderPlaylistItems(playlistId, ids);
            await refetch();
        } catch (e) {
        }
    };

    const handleDelete = async () => {
        try {
            await deletePlaylist(playlistId);
            navigate('/playlists');
        } catch (e) {
        }
    };

    return <>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1em'}}>
            <Header as='h1' style={{marginTop: 0}}>{playlist.name}</Header>
            <Button as={Link} to={`/playlists/${playlistId}`} secondary icon='eye' content='View'/>
        </div>
        {playlist.description && <p>{playlist.description}</p>}

        {wrolMode && <Message warning>
            <Message.Header>WROL Mode</Message.Header>
            <Message.Content>Editing playlists is disabled while in WROL Mode.</Message.Content>
        </Message>}

        <Segment>
            <TagsSelector
                limit={1}
                disabled={!editable}
                selectedTagNames={playlist.tag_name ? [playlist.tag_name] : []}
                onAdd={handleAddTag}
                onRemove={handleRemoveTag}
            />
        </Segment>

        {items.length === 0
            ? <Message>
                <Message.Header>This playlist is empty</Message.Header>
                {editable && <Message.Content>Add a link below.</Message.Content>}
            </Message>
            : <PlaylistItemsTable items={items} editable={editable} onMove={move} onRemove={handleRemove}/>}

        <Segment>
            <Header as='h4'>Add a link</Header>
            <Form onSubmit={handleAddUrl}>
                <Form.Group>
                    <Form.Field width={8}>
                        <Input placeholder='URL (e.g. /map?lat=40.76&lon=-111.89&z=10)'
                               value={url} disabled={!editable}
                               onChange={(e, {value}) => setUrl(value)}/>
                    </Form.Field>
                    <Form.Field width={6}>
                        <Input placeholder='Title (optional)' value={urlTitle} disabled={!editable}
                               onChange={(e, {value}) => setUrlTitle(value)}/>
                    </Form.Field>
                    <Form.Field>
                        <Button primary type='submit' disabled={!editable || !url.trim()}>Add</Button>
                    </Form.Field>
                </Form.Group>
            </Form>
        </Segment>

        <APIButton
            color='red'
            disabled={!editable}
            confirmContent='Are you sure you want to delete this playlist? Its directory will be removed.'
            confirmButton='Delete'
            onClick={handleDelete}
            obeyWROLMode={true}
        >Delete Playlist</APIButton>
    </>;
}


export function PlaylistsRoute() {
    return <PageContainer>
        <Routes>
            <Route path='/' exact element={<PlaylistsPage/>}/>
            <Route path=':playlistId' exact element={<PlaylistViewPage/>}/>
            <Route path=':playlistId/edit' exact element={<PlaylistEditPage/>}/>
        </Routes>
    </PageContainer>;
}
