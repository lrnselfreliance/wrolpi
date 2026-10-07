import React from 'react';
import {Route, Routes} from 'react-router';
import {act, fireEvent, render, screen, waitFor, within} from '../test-utils';
import {
    RepoEditPage,
    RepoImportPage,
    repoNameFromURL,
    RepoNewPage,
    ReposPage,
    RepoViewPage,
    safeRepoHref,
} from './Repos';
import {
    createRepo, deleteRepo, fetchRepos, getFile, getRepo, getRepoLog, getRepoTree, importRepo, inspectRepoImport,
    updateRepo,
} from '../api';
import {FilePreviewContext} from './FilePreview';

jest.mock('../api', () => ({
    ...jest.requireActual('../api'),
    createRepo: jest.fn(),
    deleteRepo: jest.fn(),
    fetchRepos: jest.fn(),
    getFile: jest.fn(),
    getRepo: jest.fn(),
    getRepoLog: jest.fn(),
    getRepoTree: jest.fn(),
    importRepo: jest.fn(),
    inspectRepoImport: jest.fn(),
    updateRepo: jest.fn(),
}));

// The directory picker searches the server; picking a directory is all these specs need.
jest.mock('./Common', () => ({
    ...jest.requireActual('./Common'),
    DirectorySearch: ({onSelect}) => <button type='button' onClick={() => onSelect('code/kiwix-tools')}>
        Pick directory
    </button>,
}));

// The README is fetched from the media server; its rendering is MarkdownPreview's own spec.
jest.mock('./MarkdownPreview', () => ({
    ...jest.requireActual('./MarkdownPreview'),
    MarkdownPreview: ({url}) => <div data-testid='markdown-preview'>{url}</div>,
}));

const repoFixture = (overrides = {}) => ({
    id: 1, collection_id: 10, name: 'kiwix-tools', tag_name: null, description: null,
    url: 'https://github.com/kiwix/kiwix-tools', mode: 'full', branch: null, default_branch: 'main',
    head_sha: '3f9c2a1e7b', head_message: 'Fix the mimetype', head_date: '2026-09-30T14:02:00Z',
    size: 1000, directory: 'repos/kiwix-tools', frequency: 604800, download_error: null,
    ...overrides,
});

const treeFixture = {
    path: '',
    readme_path: 'README.md',
    entries: [
        {name: 'src', path: 'src', is_dir: true, size: null},
        {name: 'README.md', path: 'README.md', is_dir: false, size: 120},
    ],
};

const flush = () => act(async () => {
});

beforeEach(() => jest.clearAllMocks());

describe('safeRepoHref', () => {
    it('only links https URLs', () => {
        expect(safeRepoHref('https://github.com/a/b')).toBe('https://github.com/a/b');
        expect(safeRepoHref('javascript:alert(1)')).toBeNull();
        expect(safeRepoHref('http://github.com/a/b')).toBeNull();
        expect(safeRepoHref('file:///etc/passwd')).toBeNull();
        expect(safeRepoHref('not a url')).toBeNull();
    });
});

describe('repoNameFromURL', () => {
    it('is the last path segment, without .git or a branch', () => {
        expect(repoNameFromURL('https://github.com/kiwix/kiwix-tools.git')).toBe('kiwix-tools');
        expect(repoNameFromURL('https://github.com/kiwix/kiwix-tools/tree/dev')).toBe('kiwix-tools');
        expect(repoNameFromURL('https://gitlab.com/group/sub/project/')).toBe('project');
        expect(repoNameFromURL('nope')).toBe('');
    });
});

describe('ReposPage', () => {
    it('lists repos, linking each to its page', async () => {
        fetchRepos.mockResolvedValue([
            repoFixture(),
            repoFixture({id: 2, name: 'gone', download_error: 'git ls-remote failed', head_sha: null}),
        ]);
        render(<ReposPage/>, {route: '/repos'});
        await flush();
        expect(screen.getAllByText('kiwix-tools')[0].closest('a')).toHaveAttribute('href', '/repos/1');
        expect(screen.getAllByText('gone')[0].closest('a')).toHaveAttribute('href', '/repos/2');
        expect(screen.getByText('New Repo').closest('a')).toHaveAttribute('href', '/repos/new');
    });

    it('shows a repo which is never updated', async () => {
        fetchRepos.mockResolvedValue([repoFixture({frequency: 0})]);
        render(<ReposPage/>, {route: '/repos'});
        await flush();
        expect(screen.getAllByText('Never').length).toBeGreaterThan(0);
    });

    it('explains an empty list', async () => {
        fetchRepos.mockResolvedValue([]);
        render(<ReposPage/>, {route: '/repos'});
        await flush();
        expect(screen.getByText(/No repos yet/)).toBeInTheDocument();
    });
});

function renderViewPage({repo, tree = treeFixture, query = {}, setPreviewFile = jest.fn()} = {}) {
    getRepo.mockResolvedValue(repo);
    getRepoTree.mockResolvedValue(tree);
    return render(<Routes><Route path='/repos/:repoId' element={<RepoViewPage/>}/></Routes>, {
        route: '/repos/1',
        query,
        contexts: [[FilePreviewContext, {setPreviewFile}]],
    });
}

describe('RepoViewPage', () => {
    it('shows the latest commit, the files, and the README', async () => {
        renderViewPage({repo: repoFixture()});
        await flush();
        expect(getRepoTree).toHaveBeenCalledWith('1', '');
        expect(screen.getByText('3f9c2a1')).toBeInTheDocument();
        expect(screen.getByText('Fix the mimetype')).toBeInTheDocument();
        expect(screen.getByText('main')).toBeInTheDocument();
        expect(screen.getByText('(default)')).toBeInTheDocument();
        expect(screen.getByText('https://github.com/kiwix/kiwix-tools').closest('a'))
            .toHaveAttribute('href', 'https://github.com/kiwix/kiwix-tools');
        expect(screen.getByText('src')).toBeInTheDocument();
        expect(screen.getByTestId('markdown-preview')).toHaveTextContent('/media/repos/kiwix-tools/README.md');
    });

    it('opens a directory through the URL, and a file in the preview', async () => {
        const updateQuery = jest.fn();
        const setPreviewFile = jest.fn();
        const file = {path: 'repos/kiwix-tools/README.md', mimetype: 'text/markdown', size: 120};
        getFile.mockResolvedValue(file);
        renderViewPage({repo: repoFixture(), query: {updateQuery}, setPreviewFile});
        await flush();

        fireEvent.click(screen.getByText('src'));
        expect(updateQuery).toHaveBeenCalledWith({path: 'src'}, false);

        fireEvent.click(screen.getAllByText('README.md')[0]);
        await flush();
        expect(getFile).toHaveBeenCalledWith('repos/kiwix-tools/README.md', true);
        expect(setPreviewFile).toHaveBeenCalledWith(file);
    });

    it('lists the directory in the URL, with a way back up', async () => {
        const tree = {path: 'src/lib', readme_path: null, entries: [{name: 'a.c', path: 'src/lib/a.c', is_dir: false}]};
        const updateQuery = jest.fn();
        renderViewPage({repo: repoFixture(), tree, query: {searchParams: new URLSearchParams('path=src/lib'), updateQuery}});
        await flush();
        expect(getRepoTree).toHaveBeenCalledWith('1', 'src/lib');
        expect(screen.queryByTestId('markdown-preview')).not.toBeInTheDocument();

        fireEvent.click(screen.getByText('..'));
        expect(updateQuery).toHaveBeenCalledWith({path: 'src'}, false);
        // The breadcrumb's root.
        fireEvent.click(screen.getAllByText('kiwix-tools').find(i => i.tagName === 'BUTTON'));
        expect(updateQuery).toHaveBeenCalledWith({path: ''}, false);
    });

    it('offers a ZIP of the files', async () => {
        renderViewPage({repo: repoFixture()});
        await flush();
        const link = screen.getByText('Download ZIP').closest('a');
        expect(link).toHaveAttribute('href', expect.stringMatching(/\/api\/repos\/1\/archive\.zip$/));
        expect(link).toHaveAttribute('download');
    });

    it('shows the history instead of the files', async () => {
        getRepoLog.mockResolvedValue({
            total: 51,
            commits: [{sha: 'abcdef1234', author: 'Ada', date: '2026-09-30T14:02:00Z', message: 'Fix the mimetype'}],
        });
        const updateQuery = jest.fn();
        renderViewPage({repo: repoFixture(), query: {searchParams: new URLSearchParams('view=history'), updateQuery}});
        await flush();

        expect(getRepoLog).toHaveBeenCalledWith(1, 0, 50);
        expect(getRepoTree).not.toHaveBeenCalled();
        expect(screen.getByText('51 commits')).toBeInTheDocument();
        expect(screen.getByText('abcdef1')).toBeInTheDocument();
        expect(screen.getByText('Ada')).toBeInTheDocument();

        // The next page is appended.
        getRepoLog.mockResolvedValue({
            total: 51,
            commits: [{sha: '0123456789', author: 'Ben', date: '2026-09-01T00:00:00Z', message: 'Older'}],
        });
        fireEvent.click(screen.getByText('Load more'));
        await flush();
        expect(getRepoLog).toHaveBeenLastCalledWith(1, 1, 50);
        expect(screen.getByText('abcdef1')).toBeInTheDocument();
        expect(screen.getByText('0123456')).toBeInTheDocument();

        fireEvent.click(screen.getByText('Files'));
        expect(updateQuery).toHaveBeenCalledWith({view: null}, false);
    });

    it('explains a repo that is not downloaded yet', async () => {
        renderViewPage({repo: repoFixture({head_sha: null, head_message: null, head_date: null})});
        await flush();
        expect(screen.getByText('Not downloaded yet')).toBeInTheDocument();
        expect(getRepoTree).not.toHaveBeenCalled();
        expect(screen.queryByText('Download ZIP')).not.toBeInTheDocument();
        expect(screen.queryByText('History')).not.toBeInTheDocument();
    });

    it('keeps showing the files when the last update failed', async () => {
        renderViewPage({repo: repoFixture({download_error: 'Traceback...\nDownloadError: git ls-remote failed (128)'})});
        await flush();
        expect(screen.getByText('The last update failed')).toBeInTheDocument();
        expect(screen.getByText(/git ls-remote failed/)).toBeInTheDocument();
        expect(screen.getByText('src')).toBeInTheDocument();
    });

    it('says a repo which is never updated is only updated on request', async () => {
        renderViewPage({repo: repoFixture({frequency: 0, download_error: 'git ls-remote failed (128)'})});
        await flush();
        expect(screen.getByText('The last update failed')).toBeInTheDocument();
        expect(screen.getByText(/never updated automatically/)).toBeInTheDocument();
        expect(screen.queryByText(/will be tried again/)).not.toBeInTheDocument();
    });

    it('never links an upstream that is not https', async () => {
        renderViewPage({repo: repoFixture({url: 'javascript:alert(1)'})});
        await flush();
        expect(screen.queryByText('javascript:alert(1)')).not.toBeInTheDocument();
    });
});

describe('RepoNewPage', () => {
    it('adds a repo, then opens it', async () => {
        createRepo.mockResolvedValue(repoFixture({id: 5}));
        render(<Routes>
            <Route path='/repos/new' element={<RepoNewPage/>}/>
            <Route path='/repos/:repoId' element={<div>repo page</div>}/>
        </Routes>, {route: '/repos/new'});

        const add = screen.getByText('Add Repo').closest('button');
        expect(add).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/URL/), {target: {value: 'git@github.com:a/b'}});
        expect(add).toBeDisabled();
        expect(screen.getByText('Must be an https:// URL')).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText(/URL/), {target: {value: 'https://github.com/kiwix/kiwix-tools'}});
        expect(screen.getByPlaceholderText('kiwix-tools')).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('Branch'), {target: {value: ' dev '}});
        fireEvent.click(screen.getByText('Pick directory'));
        fireEvent.click(add);
        await flush();

        expect(createRepo).toHaveBeenCalledWith({
            url: 'https://github.com/kiwix/kiwix-tools', name: null, tag_name: null, frequency: 604800,
            mode: 'full', branch: 'dev', submodules: false, description: null, directory: 'code/kiwix-tools',
        });
        expect(screen.getByText('repo page')).toBeInTheDocument();
    });
});

describe('RepoEditPage', () => {
    function renderEditPage(repo) {
        getRepo.mockResolvedValue(repo);
        return render(<Routes>
            <Route path='/repos/:repoId/edit' element={<RepoEditPage/>}/>
            <Route path='/repos' element={<div>repos page</div>}/>
        </Routes>, {route: '/repos/1/edit'});
    }

    it('saves the settings', async () => {
        updateRepo.mockResolvedValue(repoFixture());
        renderEditPage(repoFixture({branch: 'dev', description: 'Tools'}));
        await flush();
        expect(screen.getByLabelText('Branch')).toHaveValue('dev');

        expect(screen.getByLabelText('Include submodules')).not.toBeChecked();

        fireEvent.change(screen.getByLabelText('Branch'), {target: {value: ''}});
        fireEvent.click(screen.getByLabelText('Include submodules'));
        fireEvent.click(screen.getByText('Save'));
        await flush();
        expect(updateRepo).toHaveBeenCalledWith('1', {
            description: 'Tools', frequency: 604800, mode: 'full', branch: '', submodules: true,
        });
    });

    it('keeps a repo which is never updated', async () => {
        updateRepo.mockResolvedValue(repoFixture({frequency: 0}));
        renderEditPage(repoFixture({frequency: 0}));
        await flush();
        expect(screen.getByDisplayValue('Never')).toBeInTheDocument();
        fireEvent.click(screen.getByText('Save'));
        await flush();
        expect(updateRepo).toHaveBeenCalledWith('1', expect.objectContaining({frequency: 0}));
    });

    it('deletes the repo, and its files only when asked', async () => {
        deleteRepo.mockResolvedValue(undefined);
        renderEditPage(repoFixture());
        await flush();

        fireEvent.click(screen.getByText('Delete'));
        const dialog = await screen.findByRole('dialog');
        fireEvent.click(within(dialog).getByLabelText(/Also delete its files/));
        fireEvent.click(within(dialog).getByText('Delete'));
        await flush();
        expect(deleteRepo).toHaveBeenCalledWith('1', true);
        expect(screen.getByText('repos page')).toBeInTheDocument();
    });
});

describe('RepoImportPage', () => {
    const inspection = (overrides = {}) => ({
        directory: 'code/kiwix-tools', origin: 'git@github.com:kiwix/kiwix-tools.git',
        url: 'https://github.com/kiwix/kiwix-tools', name: 'kiwix-tools', branch: 'main',
        head_sha: 'abcdef1234', head_message: 'Local work', head_date: '2026-09-30T14:02:00Z', local_commits: 2,
        shallow: false, ignored: false,
        ...overrides,
    });

    function renderImportPage() {
        return render(<Routes>
            <Route path='/repos/import' element={<RepoImportPage/>}/>
            <Route path='/repos/:repoId' element={<div>repo page</div>}/>
        </Routes>, {route: '/repos/import'});
    }

    it('inspects the directory, warns about local commits, and imports once confirmed', async () => {
        inspectRepoImport.mockResolvedValue({inspection: inspection()});
        importRepo.mockResolvedValue(repoFixture({id: 9}));
        renderImportPage();

        fireEvent.click(screen.getByText('Pick directory'));
        expect(await screen.findByText('2 commits are not on the remote')).toBeInTheDocument();
        expect(inspectRepoImport).toHaveBeenCalledWith('code/kiwix-tools', '', null, '');
        // Inspected again with the URL the import will use.
        await waitFor(() => expect(inspectRepoImport).toHaveBeenCalledWith('code/kiwix-tools', '', null,
            'https://github.com/kiwix/kiwix-tools'));
        expect(screen.getByText('git@github.com:kiwix/kiwix-tools.git')).toBeInTheDocument();
        expect(screen.getByText(/Its files are indexed/)).toBeInTheDocument();
        // The URL comes from the origin.
        expect(screen.getByLabelText(/^URL/)).toHaveValue('https://github.com/kiwix/kiwix-tools');

        const button = screen.getByText('Import').closest('button');
        expect(button).toBeDisabled();
        fireEvent.click(screen.getByLabelText(/I understand/));
        expect(button).toBeEnabled();
        fireEvent.click(button);
        await flush();

        expect(importRepo).toHaveBeenCalledWith({
            directory: 'code/kiwix-tools', confirm: true, url: 'https://github.com/kiwix/kiwix-tools', name: null,
            tag_name: null, frequency: 604800, mode: 'full', branch: null, submodules: false,
        });
        expect(screen.getByText('repo page')).toBeInTheDocument();
    });

    it('asks for the URL when the clone has no https origin', async () => {
        inspectRepoImport.mockResolvedValue({inspection: inspection({origin: null, url: null, local_commits: 0})});
        renderImportPage();
        fireEvent.click(screen.getByText('Pick directory'));
        expect(await screen.findByText(/no https:\/\/ origin/)).toBeInTheDocument();
        fireEvent.click(screen.getByLabelText(/I understand/));
        expect(screen.getByText('Import').closest('button')).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/^URL/), {target: {value: 'https://github.com/kiwix/kiwix-tools'}});
        expect(screen.getByText('Import').closest('button')).toBeEnabled();
    });

    it('explains a directory which cannot be imported', async () => {
        inspectRepoImport.mockResolvedValue({error: 'code/kiwix-tools is not a git clone'});
        renderImportPage();
        fireEvent.click(screen.getByText('Pick directory'));
        expect(await screen.findByText('code/kiwix-tools is not a git clone')).toBeInTheDocument();
        expect(screen.queryByText('Import')).not.toBeInTheDocument();
    });

    it('says when the files are not indexed', async () => {
        inspectRepoImport.mockResolvedValue({inspection: inspection({ignored: true})});
        renderImportPage();
        fireEvent.click(screen.getByText('Pick directory'));
        expect(await screen.findByText(/Its files are not indexed/)).toBeInTheDocument();
    });
});
