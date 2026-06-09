import React, {useEffect, useState} from "react";
import {Input, Message} from "semantic-ui-react";
import {toast} from "react-semantic-toasts-2";

import {Button, Form, List, Loader, Modal} from "./Theme";
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
            {playlists === undefined && <Message error><Message.Header>Could not load playlists</Message.Header></Message>}
            {playlists === null && <Loader active inline='centered'/>}
            {Array.isArray(playlists) && playlists.length > 0 &&
                <List divided selection>
                    {playlists.map(p => <List.Item key={p.id} active={selected === p.id}
                                                   onClick={() => setSelected(p.id)}>
                        <List.Icon name={selected === p.id ? 'check circle' : 'circle outline'}
                                   verticalAlign='middle'/>
                        <List.Content><List.Header>{p.name}</List.Header></List.Content>
                    </List.Item>)}
                </List>}
            {Array.isArray(playlists) && playlists.length === 0 &&
                <p>No playlists yet — create one below.</p>}
            <Form onSubmit={handleCreateAndAdd} style={{marginTop: '1em'}}>
                <Form.Field>
                    <label>Or create a new playlist</label>
                    <Input placeholder='New playlist name...' value={newName}
                           onChange={(e, {value}) => setNewName(value)}/>
                </Form.Field>
            </Form>
        </Modal.Content>
        <Modal.Actions>
            <Button onClick={onClose}>Cancel</Button>
            {creating
                ? <Button primary loading={adding} onClick={handleCreateAndAdd}>Create &amp; Add</Button>
                : <Button primary disabled={!selected} loading={adding} onClick={handleAddExisting}>Add</Button>}
        </Modal.Actions>
    </Modal>;
}


/**
 * A button that opens AddToPlaylistModal for one of:
 *   - one FileGroup (fileGroupId) or many (fileGroupIds),
 *   - a Zim article (zim={zimId, entry, title}), or
 *   - a URL (url={url, title}) — link to anything the WROLPi browser can open (e.g. a map location).
 * Extra props are forwarded to the Button (color, size, disabled, icon, content, ...).
 */
export function AddToPlaylistButton({fileGroupId, fileGroupIds, zim, url, content = 'Add to Playlist', onComplete, ...buttonProps}) {
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

    // An empty `content` makes a compact icon-only button (omit content entirely so Semantic does
    // not reserve label padding); otherwise render the labeled "Add to Playlist" button.
    const contentProps = content ? {content} : {};

    return <>
        <Button color='green' icon='list' onClick={() => setOpen(true)}
                disabled={items.length === 0} {...contentProps} {...buttonProps}/>
        <AddToPlaylistModal open={open} onClose={() => setOpen(false)} items={items}
                            onComplete={onComplete}/>
    </>;
}
