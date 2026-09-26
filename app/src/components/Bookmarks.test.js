import React from 'react';
import {screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {render} from '../test-utils';
import {BookmarkAddForms, BookmarkNodeModal, BookmarkTable, directoryOptions, locationOptions} from './Bookmarks';
import {resolveBookmarkUrl} from '../contexts/BookmarksContext';

const tree = [
    {id: 1, name: 'Channels', url: '/videos/channel', new_tab: false},
    {
        id: 2, name: 'Services', children: [
            {id: 3, name: 'Jellyfin', url: ':8096/', new_tab: true},
            {id: 4, name: 'Radio', children: []},
        ]
    },
];

describe('resolveBookmarkUrl', () => {
    const location = {protocol: 'https:', hostname: '10.0.0.2', host: '10.0.0.2'};

    it.each([
        ['/videos', {internal: true, href: '/videos'}],
        [' /videos/channel/3 ', {internal: true, href: '/videos/channel/3'}],
        // A port on this host takes the page's scheme, or its own when it names one.
        [':8096/web', {internal: false, href: 'https://10.0.0.2:8096/web'}],
        [':8096', {internal: false, href: 'https://10.0.0.2:8096'}],
        ['http://:8096/web', {internal: false, href: 'http://10.0.0.2:8096/web'}],
        ['HTTPS://:8085', {internal: false, href: 'https://10.0.0.2:8085'}],
        ['https://example.com/a?b=c', {internal: false, href: 'https://example.com/a?b=c'}],
    ])('resolves %s', (url, expected) => {
        expect(resolveBookmarkUrl(url, location)).toEqual(expected);
    });

    it.each([
        // Paths a browser takes off this host: network paths, backslashes, and control
        // characters a URL parser strips before deciding.
        '//evil.com', '///evil.com', '/\\evil.com', '/\\@evil.com', '/\t/evil.com', '/\n/evil.com',
        // Port forms where the host would become credentials.
        ':8096@evil.com', 'http://:8096@evil.com', ':8096\t@evil.com', ':8096/x@evil.com', ':8096\\evil.com',
        // Not http(s).
        'javascript:alert(1)', 'data:text/html,hi', 'ftp://example.com', 'videos', '',
    ])('refuses %j rather than guessing', (url) => {
        expect(resolveBookmarkUrl(url, location)).toEqual({internal: false, href: null});
    });

    it('brackets an IPv6 host for a port bookmark', () => {
        // The browser reports an IPv6 hostname bracketed already.
        const v6 = {protocol: 'https:', hostname: '[::1]', host: '[::1]'};
        expect(resolveBookmarkUrl(':8096/web', v6)).toEqual({internal: false, href: 'https://[::1]:8096/web'});
        expect(resolveBookmarkUrl(':8096', {protocol: 'http:', hostname: '::1', host: '[::1]'}))
            .toEqual({internal: false, href: 'http://[::1]:8096'});
    });
});

describe('directoryOptions', () => {
    it('lists every directory with its path, and no bookmarks', () => {
        expect(directoryOptions(tree)).toEqual([
            {value: '2', label: 'Services', id: 2},
            {value: '4', label: 'Services / Radio', id: 4},
        ]);
    });
});

describe('BookmarkTable', () => {
    const actions = () => ({edit: jest.fn(), move: jest.fn(), remove: jest.fn()});

    it('renders the tree with resolved links, numbered within each directory', () => {
        render(<BookmarkTable nodes={tree} actions={actions()}/>);
        const channels = screen.getByRole('link', {name: 'Channels'});
        expect(channels).toHaveAttribute('href', '/videos/channel');
        expect(channels).not.toHaveAttribute('target');
        const jellyfin = screen.getByRole('link', {name: 'Jellyfin'});
        expect(jellyfin).toHaveAttribute('href', `${window.location.protocol}//${window.location.hostname}:8096/`);
        expect(jellyfin).toHaveAttribute('target', '_blank');
        expect(screen.getByText('Radio')).toBeInTheDocument();
        // Channels, Services, then Services' two children.
        const numbers = screen.getAllByRole('row').slice(1).map(row => row.firstChild.textContent);
        expect(numbers).toEqual(['01', '02', '01', '02']);
    });

    it('moves a node among its siblings and only within bounds', async () => {
        const a = actions();
        render(<BookmarkTable nodes={tree} actions={a}/>);
        // The first top-level node cannot move up; the last cannot move down.
        expect(screen.getByRole('button', {name: 'Move Channels up'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Move Services down'})).toBeDisabled();

        await userEvent.click(screen.getByRole('button', {name: 'Move Channels down'}));
        expect(a.move).toHaveBeenCalledWith(tree[0], null, 1);
        // A child moves within its directory: parent 2, from index 1 to 0.
        await userEvent.click(screen.getByRole('button', {name: 'Move Radio up'}));
        expect(a.move).toHaveBeenCalledWith(tree[1].children[1], 2, 0);
    });

    it('shows a bookmark whose URL does not resolve as text, not a link', () => {
        const nodes = [{id: 1, name: 'Bad', url: '//evil.com', new_tab: false}];
        render(<BookmarkTable nodes={nodes} actions={actions()}/>);
        expect(screen.queryByRole('link', {name: 'Bad'})).not.toBeInTheDocument();
        expect(screen.getByText('Bad')).toBeInTheDocument();
    });

    it('edits with the parent the node lives in, and deletes a bookmark without asking', async () => {
        const a = actions();
        render(<BookmarkTable nodes={tree} actions={a}/>);
        await userEvent.click(screen.getByRole('button', {name: 'Edit Jellyfin'}));
        expect(a.edit).toHaveBeenCalledWith(tree[1].children[0], 2);
        await userEvent.click(screen.getByRole('button', {name: 'Delete Channels'}));
        expect(a.remove).toHaveBeenCalledWith(tree[0]);
    });

    it('asks before deleting a directory, since its contents go with it', async () => {
        const a = actions();
        render(<BookmarkTable nodes={tree} actions={a}/>);
        await userEvent.click(screen.getByRole('button', {name: 'Delete Services'}));
        expect(a.remove).not.toHaveBeenCalled();
        await userEvent.click(await screen.findByRole('button', {name: 'Delete'}));
        expect(a.remove).toHaveBeenCalledWith(tree[1]);
    });
});

describe('BookmarkAddForms', () => {
    it('adds a bookmark at the top level and clears the form', async () => {
        const onAddBookmark = jest.fn();
        render(<BookmarkAddForms nodes={tree} onAddBookmark={onAddBookmark} onAddDirectory={jest.fn()}/>);
        const adds = screen.getAllByRole('button', {name: 'Add'});
        expect(adds[0]).toBeDisabled();

        await userEvent.type(screen.getByLabelText('Bookmark URL'), ':8123/');
        expect(adds[0]).toBeDisabled();
        await userEvent.type(screen.getByLabelText('Bookmark name'), 'Home Assistant');
        await userEvent.click(screen.getByLabelText('New tab'));
        await userEvent.click(adds[0]);

        expect(onAddBookmark).toHaveBeenCalledWith({name: 'Home Assistant', url: ':8123/', new_tab: true, parent_id: null});
        expect(screen.getByLabelText('Bookmark URL')).toHaveValue('');
    });

    it('keeps what was typed when the server refuses the bookmark', async () => {
        const onAddBookmark = jest.fn().mockRejectedValue(new Error('refused'));
        render(<BookmarkAddForms nodes={tree} onAddBookmark={onAddBookmark} onAddDirectory={jest.fn()}/>);
        await userEvent.type(screen.getByLabelText('Bookmark URL'), '//evil.com');
        await userEvent.type(screen.getByLabelText('Bookmark name'), 'Oops');
        await userEvent.click(screen.getAllByRole('button', {name: 'Add'})[0]);

        expect(onAddBookmark).toHaveBeenCalled();
        expect(screen.getByLabelText('Bookmark URL')).toHaveValue('//evil.com');
        expect(screen.getByLabelText('Bookmark name')).toHaveValue('Oops');
    });

    it('adds a directory', async () => {
        const onAddDirectory = jest.fn();
        render(<BookmarkAddForms nodes={tree} onAddBookmark={jest.fn()} onAddDirectory={onAddDirectory}/>);
        await userEvent.type(screen.getByLabelText('Directory name'), 'Tools');
        await userEvent.click(screen.getAllByRole('button', {name: 'Add'})[1]);
        expect(onAddDirectory).toHaveBeenCalledWith({name: 'Tools', parent_id: null});
    });
});

describe('BookmarkNodeModal', () => {
    // Mantine's Select scrolls the highlighted option into view; jsdom has no layout.
    beforeAll(() => {
        Element.prototype.scrollIntoView = jest.fn();
    });

    it('saves a new bookmark with its location and new-tab choice', async () => {
        const onSave = jest.fn();
        render(<BookmarkNodeModal open node={null} directory={false} parentId={2} nodes={tree}
                                  onSave={onSave} onClose={jest.fn()}/>);
        const save = screen.getByRole('button', {name: 'Save'});
        expect(save).toBeDisabled();

        await userEvent.type(screen.getByLabelText('Name'), 'Home Assistant');
        expect(save).toBeDisabled();
        await userEvent.type(screen.getByLabelText('URL'), ':8123/');
        await userEvent.click(screen.getByLabelText('Open in a new tab'));
        await userEvent.click(save);

        expect(onSave).toHaveBeenCalledWith({name: 'Home Assistant', url: ':8123/', new_tab: true, parent_id: 2});
    });

    it('a directory has no URL or new-tab choice', () => {
        render(<BookmarkNodeModal open node={tree[1]} directory parentId={null} nodes={tree}
                                  onSave={jest.fn()} onClose={jest.fn()}/>);
        expect(screen.getByLabelText('Name')).toHaveValue('Services');
        expect(screen.queryByLabelText('URL')).not.toBeInTheDocument();
        expect(screen.queryByLabelText('Open in a new tab')).not.toBeInTheDocument();
    });
});

describe('locationOptions', () => {
    it('offers the top level and every directory to a new node', () => {
        expect(locationOptions(tree).map(o => o.label)).toEqual(['Top level', 'Services', 'Services / Radio']);
    });

    it('never offers a directory itself, or its children', () => {
        expect(locationOptions(tree, tree[1]).map(o => o.label)).toEqual(['Top level']);
        expect(locationOptions(tree, tree[1].children[1]).map(o => o.label)).toEqual(['Top level', 'Services']);
    });
});
