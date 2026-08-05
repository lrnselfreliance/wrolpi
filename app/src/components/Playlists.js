import React, {useEffect, useState} from "react";
import {Link, Route, Routes, useNavigate, useParams} from "react-router";
import {IconMapPin} from "@tabler/icons-react";
import {
    Button,
    Group,
    Header,
    Icon,
    Loading,
    Message,
    Modal,
    Panel,
    Table,
    TextInput,
    toast,
} from "./ui";
import {
    APIButton,
    BackButton,
    DirectorySearch,
    encodeMediaPath,
    ErrorMessage,
    findPosterPath,
    InfoPopup,
    mimetypeColor,
    mimetypeIconName,
    PageContainer,
    PreviewLink,
    SearchInput,
    useTitle,
} from "./Common";
import {useOneQuery, useWROLMode} from "../hooks/customHooks";
import {CollectionTable} from "./collections/CollectionTable";
import {CollectionEditForm} from "./collections/CollectionEditForm";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {
    addPlaylistItem,
    createPlaylist,
    deletePlaylist,
    fetchPlaylists,
    getCollectionTagInfo,
    getPlaylist,
    removePlaylistItem,
    reorderPlaylistItems,
    setPlaylistTag,
    updatePlaylist,
} from "../api";
import {TagsSelector} from "../Tags";


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
    const [tagName, setTagName] = useState(null);
    const searchInputRef = React.useRef();
    const navigate = useNavigate();

    const handleCreate = async () => {
        const trimmed = name.trim();
        if (!trimmed) return;
        try {
            const playlist = await createPlaylist(trimmed, undefined, tagName);
            toast({type: 'success', title: 'Playlist created', description: trimmed, time: 3000});
            setName('');
            setTagName(null);
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

    // No `mb`: this is a top-level block of the page, and the page's stack spaces it.  Its own
    // margin was added to that gap -- the same fix as the twin filter rows on Channels/Domains.
    const header = <Group justify='space-between' align='flex-end' wrap='wrap'>
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
        <Button role='primary' onClick={() => setModalOpen(true)}>New Playlist</Button>
    </Group>;

    const createModal = <Modal open={modalOpen} onClose={() => setModalOpen(false)} size='tiny'>
        <Modal.Header>New Playlist</Modal.Header>
        <Modal.Content>
            <form onSubmit={e => {
                e.preventDefault();
                handleCreate();
            }}>
                <TextInput
                    autoFocus
                    label='Name'
                    placeholder='Playlist name...'
                    value={name}
                    onChange={(e) => setName(e.currentTarget.value)}
                />
                <div style={{marginTop: '1em'}}>
                    <label style={{display: 'flex', alignItems: 'center', gap: '0.3em', marginBottom: '0.3em'}}>
                        Tag
                        <InfoPopup content='Optional. A tagged playlist lives under its tag in the
                            Playlists Directory.'/>
                    </label>
                    <TagsSelector
                        limit={1}
                        selectedTagNames={tagName ? [tagName] : []}
                        onAdd={setTagName}
                        onRemove={() => setTagName(null)}
                    />
                </div>
            </form>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button role='save' disabled={!name.trim()} onClick={handleCreate}>Create</Button>
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


// Icon for a playlist item.  File items use FileGroup's mimetype/model icon and color (video,
// pdf, ebook, image, ...) so they match the rest of the UI; zim/url are fixed.
function ItemIcon({item}) {
    if (item.item_kind === 'file' && item.file_group) {
        const fg = item.file_group;
        const lowerPath = (fg.primary_path || '').toLowerCase();
        const name = mimetypeIconName(fg.mimetype, lowerPath);
        const color = mimetypeColor(fg.mimetype, lowerPath);
        return <Icon name={name} size='large' style={{color: `var(--${color})`}}/>;
    }
    if (item.item_kind === 'zim') return <Icon name='book' size='large'/>;
    if (item.item_kind === 'url') {
        // A map-location URL (e.g. /map?lat=&lon=) gets a map marker; other URLs get the link icon.
        const u = (item.url || '').toLowerCase();
        if (u.startsWith('/map')) return <Icon component={IconMapPin} size='large'/>;
        return <Icon name='linkify' size='large'/>;
    }
    return <Icon name='file' size='large'/>;
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
    return <Table>
        <Table.Header>
            <Table.Row>
                <Table.HeaderCell>#</Table.HeaderCell>
                <Table.HeaderCell>Item</Table.HeaderCell>
                <Table.HeaderCell>Title</Table.HeaderCell>
                {editable && <Table.HeaderCell/>}
            </Table.Row>
        </Table.Header>
        <Table.Body>
            {items.map((item, index) => {
                const label = itemLabel(item);
                const poster = item.item_kind === 'file' && item.file_group
                    ? findPosterPath(item.file_group) : null;
                return <Table.Row key={item.id}>
                    <Table.Cell>{String(index + 1).padStart(2, '0')}</Table.Cell>
                    <Table.Cell style={{width: '90px', textAlign: 'center'}}>
                        {poster
                            ? <img alt='' src={`/media/${encodeMediaPath(poster)}`}
                                   style={{maxHeight: '45px', maxWidth: '80px', width: 'auto', display: 'block', margin: '0 auto'}}/>
                            : <ItemIcon item={item}/>}
                    </Table.Cell>
                    <Table.Cell>
                        <ItemTitle item={item} label={label}/>
                    </Table.Cell>
                    {editable && <Table.Cell style={{textAlign: 'right', whiteSpace: 'nowrap'}}>
                        <Button icon='arrow up' size='xs' disabled={index === 0}
                                onClick={() => onMove(index, -1)}/>
                        <Button icon='arrow down' size='xs' disabled={index === items.length - 1}
                                onClick={() => onMove(index, 1)}/>
                        <Button role='danger' icon='trash' size='xs'
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
        return <Loading/>;
    }

    const items = playlist.items || [];

    return <>
        <BackButton/>

        <Header as='h1'>
            {playlist.name}
            <Link to={`/playlists/${playlistId}/edit`}>
                <Icon name='edit' style={{marginLeft: '0.5em'}}/>
            </Link>
        </Header>
        {playlist.description && <p>{playlist.description}</p>}

        {items.length === 0
            ? <Message title='This playlist is empty'/>
            : <PlaylistItemsTable items={items} editable={false}/>}
    </>;
}


// Edit playlist page (opened from the edit icon), mirroring ChannelEditPage: Back/View buttons at
// the top, a form segment for name/description/tag, then a segment with the ordered items.
export function PlaylistEditPage() {
    const {playlistId} = useParams();
    const {playlist, refetch} = usePlaylist(playlistId);
    const navigate = useNavigate();
    const wrolMode = useWROLMode();
    const [url, setUrl] = useState('');
    const [urlTitle, setUrlTitle] = useState('');
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [directory, setDirectory] = useState('');
    const [tagModalOpen, setTagModalOpen] = useState(false);

    useTitle(playlist && playlist.name ? `Edit ${playlist.name} Playlist` : 'Edit Playlist');

    // Seed the form fields once the playlist loads (keyed on id so a refetch doesn't clobber edits).
    const playlistDbId = playlist && playlist.id;
    useEffect(() => {
        if (playlistDbId) {
            setName(playlist.name || '');
            setDescription(playlist.description || '');
            setDirectory(playlist.directory || '');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playlistDbId]);

    if (playlist === undefined) {
        return <ErrorMessage>Could not fetch playlist</ErrorMessage>;
    }
    if (playlist === null) {
        return <Loading/>;
    }

    const items = playlist.items || [];
    // Editing is blocked while in WROL Mode (the API enforces this too); fall back to a read-only view.
    const editable = !wrolMode;

    const handleSave = async () => {
        try {
            await updatePlaylist(playlistId, {
                name: name.trim(),
                description: description.trim(),
                directory: directory.trim(),
            });
            toast({
                type: 'success', title: 'Playlist Updated',
                description: 'Playlist was successfully updated', time: 3000,
            });
            await refetch();
        } catch (e) {
            // Error toast already shown by the API client.
        }
    };

    // Set or clear (tagName=null) the playlist's tag from the tag modal.  `directory` is the
    // modal's move-to suggestion (null when the move toggle is off).
    const handleTagSave = async (tagName, directory) => {
        try {
            await setPlaylistTag(playlistId, tagName || '', directory);
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

    const deleteButton = <APIButton
        role='danger'
        size='small'
        confirmContent='Are you sure you want to delete this playlist? Its directory will be removed.'
        confirmButton='Delete'
        confirmHeader='Delete Playlist?'
        onClick={handleDelete}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Delete</APIButton>;

    const tagButton = <Button
        type="button"
        size='small'
        onClick={() => setTagModalOpen(true)}
        role='primary'
        disabled={!editable}
        style={{marginTop: '1em'}}
    >Tag</Button>;

    const actionButtons = <>
        {deleteButton}
        {tagButton}
    </>;

    // Minimal form object for CollectionEditForm (mirrors the useForm interface it consumes).
    const form = {error: null, loading: false, disabled: !editable || !name.trim(), ready: true};

    return <>
        <BackButton/>
        <Link to={`/playlists/${playlistId}`}>
            <Button>View</Button>
        </Link>

        <CollectionEditForm
            form={form}
            title='Edit Playlist'
            wrolModeContent='Playlist editing is disabled while in WROL Mode.'
            actionButtons={actionButtons}
            appliedTagName={playlist.tag_name}
            onSubmit={handleSave}
        >
            <TextInput
                label='Playlist Name'
                placeholder='Playlist name...'
                value={name}
                disabled={!editable}
                onChange={(e) => setName(e.currentTarget.value)}
            />
            <div style={{marginTop: '1em'}}>
                <label style={{display: 'flex', alignItems: 'center', gap: '0.3em', marginBottom: '0.3em'}}>
                    Directory
                    <InfoPopup content='Where the playlist lives on disk. By default it is
                        managed automatically in the Playlists Directory (under its tag, if
                        tagged); choose a different directory to manage it manually.'/>
                </label>
                <DirectorySearch
                    value={directory}
                    disabled={!editable}
                    onSelect={value => setDirectory(value || '')}
                />
            </div>
            <div style={{marginTop: '1em'}}>
                <TextInput
                    label='Description'
                    placeholder='Optional description...'
                    value={description}
                    disabled={!editable}
                    onChange={(e) => setDescription(e.currentTarget.value)}
                />
            </div>
        </CollectionEditForm>

        {/* Tag Modal */}
        <CollectionTagModal
            open={tagModalOpen}
            onClose={() => setTagModalOpen(false)}
            currentTagName={playlist.tag_name}
            originalDirectory={playlist.directory || ''}
            getTagInfo={(tagName) => getCollectionTagInfo(playlistId, tagName)}
            onSave={handleTagSave}
            collectionName="Playlist"
        />

        {/* Items Segment */}
        <Panel>
            <Header as='h1'>Items</Header>

            {items.length === 0
                ? <Message title='This playlist is empty'>
                    {editable && 'Add a link below.'}
                </Message>
                : <PlaylistItemsTable items={items} editable={editable} onMove={move} onRemove={handleRemove}/>}

            <Header as='h4'>Add a link</Header>
            <form onSubmit={e => {
                e.preventDefault();
                handleAddUrl();
            }}>
                <Group align='flex-end' wrap='wrap'>
                    <TextInput
                        style={{flex: '2 1 300px'}}
                        placeholder='URL (e.g. /map?lat=40.76&lon=-111.89&z=10)'
                        value={url} disabled={!editable}
                        onChange={(e) => setUrl(e.currentTarget.value)}/>
                    <TextInput
                        style={{flex: '1 1 200px'}}
                        placeholder='Title (optional)' value={urlTitle} disabled={!editable}
                        onChange={(e) => setUrlTitle(e.currentTarget.value)}/>
                    <Button role='primary' type='submit' disabled={!editable || !url.trim()}>Add</Button>
                </Group>
            </form>
        </Panel>
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
