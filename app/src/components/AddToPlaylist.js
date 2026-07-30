import React, {useEffect, useState} from "react";
import {Button, IconButton, Loading, Message, Modal, Radio, Stack, TextInput, toast} from "./ui";
import {addPlaylistItem, createPlaylist, fetchPlaylists} from "../api";


/**
 * Modal that adds one or more items to a playlist — an existing one or a newly-created one.
 *
 * `items` is a list of item payloads, each ready to POST to .../items, e.g.
 *   {item_kind: 'file', file_group_id: 123}
 *   {item_kind: 'zim', zim_id: 1, zim_entry: 'A/Fire', title: 'Fire'}
 *   {item_kind: 'url', url: '/map?...', title: '...'}
 */
export function AddToPlaylistModal({open, onClose, items = [], onComplete}) {
    const [playlists, setPlaylists] = useState(null);  // null=loading, []/[...]=ok, undefined=error
    const [selected, setSelected] = useState(null);
    const [newName, setNewName] = useState('');
    const [adding, setAdding] = useState(false);

    useEffect(() => {
        if (!open) return;
        setSelected(null);
        setNewName('');
        setPlaylists(null);
        fetchPlaylists().then(setPlaylists).catch(() => setPlaylists(undefined));
    }, [open]);

    const addAll = async (playlistId, playlistName) => {
        setAdding(true);
        try {
            for (const payload of items) {
                await addPlaylistItem(playlistId, payload);
            }
            const n = items.length;
            toast({
                type: 'success', title: 'Added to playlist',
                description: `${n} item${n === 1 ? '' : 's'} added to "${playlistName}"`, time: 3000,
            });
            if (onComplete) onComplete();
            onClose();
        } catch (e) {
            // Error toast already shown by the API client.
        } finally {
            setAdding(false);
        }
    };

    const handleAddExisting = async () => {
        const playlist = (playlists || []).find(p => p.id === selected);
        if (playlist) await addAll(playlist.id, playlist.name);
    };

    const handleCreateAndAdd = async () => {
        const name = newName.trim();
        if (!name) return;
        try {
            const playlist = await createPlaylist(name);
            if (playlist && playlist.id) await addAll(playlist.id, playlist.name);
        } catch (e) {
        }
    };

    const creating = !!newName.trim();

    return <Modal open={open} onClose={onClose} size='tiny'>
        <Modal.Header>Add to Playlist</Modal.Header>
        <Modal.Content>
            {playlists === undefined && <Message kind='error' title='Could not load playlists'/>}
            {playlists === null && <Loading/>}
            {Array.isArray(playlists) && playlists.length > 0 &&
                <Stack gap={4}>
                    {playlists.map(p => <Radio
                        key={p.id}
                        name='playlist'
                        label={p.name}
                        checked={selected === p.id}
                        onChange={() => setSelected(p.id)}
                    />)}
                </Stack>}
            {Array.isArray(playlists) && playlists.length === 0 &&
                <p>No playlists yet — create one below.</p>}
            <form onSubmit={(e) => {
                e.preventDefault();
                handleCreateAndAdd();
            }} style={{marginTop: '1em'}}>
                <TextInput
                    label='Or create a new playlist'
                    autoFocus
                    placeholder='New playlist name...'
                    value={newName}
                    onChange={(e) => setNewName(e.currentTarget.value)}
                />
            </form>
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={onClose}>Cancel</Button>
            {creating
                ? <Button role='primary' loading={adding} onClick={handleCreateAndAdd}>Create &amp; Add</Button>
                : <Button role='primary' disabled={!selected} loading={adding} onClick={handleAddExisting}>Add</Button>}
        </Modal.Actions>
    </Modal>;
}


/**
 * A button that opens AddToPlaylistModal for one of:
 *   - one FileGroup (fileGroupId) or many (fileGroupIds),
 *   - a Zim article (zim={zimId, entry, title}), or
 *   - a URL (url={url, title}) — link to anything the WROLPi browser can open (e.g. a map location).
 * Extra props are forwarded to the Button (size, disabled, ...).
 */
export function AddToPlaylistButton({
                                        fileGroupId, fileGroupIds, zim, url, content = 'Add to Playlist',
                                        title, onComplete, ...buttonProps
                                    }) {
    const [open, setOpen] = useState(false);

    let items;
    if (url && url.url) {
        items = [{item_kind: 'url', url: url.url, title: url.title || null}];
    } else if (zim && zim.zimId != null && zim.entry) {
        items = [{item_kind: 'zim', zim_id: zim.zimId, zim_entry: zim.entry, title: zim.title || null}];
    } else {
        const ids = fileGroupIds || (fileGroupId != null ? [fileGroupId] : []);
        items = ids.map(id => ({item_kind: 'file', file_group_id: id}));
    }

    // An empty/null `content` makes a compact icon-only button; the accessible name comes
    // from `title` (kept for callers that already pass it) or falls back to the action name.
    const iconOnly = !content;

    return <>
        {iconOnly
            ? <IconButton role='save' icon='list' label={title || 'Add to Playlist'} onClick={() => setOpen(true)}
                          disabled={items.length === 0} {...buttonProps}/>
            : <Button role='save' icon='list' onClick={() => setOpen(true)}
                      disabled={items.length === 0} {...buttonProps}>{content}</Button>}
        <AddToPlaylistModal open={open} onClose={() => setOpen(false)} items={items}
                            onComplete={onComplete}/>
    </>;
}
