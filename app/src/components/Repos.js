import React, {useContext, useEffect, useState} from "react";
import {Link, Route, Routes, useNavigate, useParams} from "react-router";
import {IconBrandGit, IconFile, IconFolder, IconGitBranch, IconGitCommit} from "@tabler/icons-react";
import {
    Anchor,
    Button,
    ButtonGroup,
    Checkbox,
    Grid,
    Group,
    Header,
    Icon,
    Loading,
    Message,
    Modal,
    Panel,
    Select,
    Table,
    Textarea,
    TextInput,
    toast,
    Tooltip,
} from "./ui";
import {
    APIButton,
    BackButton,
    DirectorySearch,
    encodeMediaPath,
    ErrorMessage,
    formatFrequency,
    humanFileSize,
    InfoPopup,
    isoDatetimeToAgoPopup,
    PageContainer,
    SearchInput,
    useTitle,
} from "./Common";
import {useOneQuery, useWROLMode} from "../hooks/customHooks";
import {CollectionTable} from "./collections/CollectionTable";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {
    createRepo,
    deleteRepo,
    fetchRepos,
    getCollectionTagInfo,
    getFile,
    getRepo,
    getRepoLog,
    getRepoTree,
    importRepo,
    inspectRepoImport,
    repoArchiveURL,
    tagCollection,
    updateRepo,
    updateRepoNow,
} from "../api";
import {TagsContext, TagsSelector} from "../Tags";
import {FilePreviewContext} from "./FilePreview";
import {isMarkdownFile, MarkdownPreview} from "./MarkdownPreview";
import {longFrequencyOptions, weeklyOption} from "./Vars";

export const REPO_MODE_OPTIONS = [
    {value: 'full', label: 'Full history'},
    {value: 'snapshot', label: 'Snapshot (latest commit only)'},
];

// A Repo which is never updated (frequency 0) keeps its clone as it is (e.g. its upstream is gone).
const NEVER = 0;
const FREQUENCY_OPTIONS = [
    ...longFrequencyOptions.map(i => ({value: String(i.value), label: i.text})),
    {value: String(NEVER), label: 'Never'},
];

export function formatRepoFrequency(frequency) {
    return frequency === NEVER ? 'Never' : formatFrequency(frequency);
}

// The "Name" column links to the repo's page; the "Edit" button links to the edit page.
const REPO_ROUTES = {search: '/repos/:id', edit: '/repos/:id/edit', id_field: 'id'};

export const REPO_COLUMNS = [
    {key: 'name', label: 'Name', sortable: true, width: 4, render: (repo) => <RepoName repo={repo}/>},
    {key: 'tag_name', label: 'Tag', sortable: true, width: 2},
    {
        key: 'branch', label: 'Branch', sortable: false, width: 2, hideOnMobile: true,
        render: (repo) => repo.branch || repo.default_branch,
    },
    {
        key: 'head_date', label: 'Last Commit', sortable: true, width: 2,
        render: (repo) => repo.head_date ? isoDatetimeToAgoPopup(repo.head_date) : null,
    },
    {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes', width: 2, hideOnMobile: true},
    {
        key: 'frequency', label: 'Download Frequency', sortable: true, width: 2, hideOnMobile: true,
        render: (repo) => formatRepoFrequency(repo.frequency),
    },
    {key: 'actions', label: 'Manage', sortable: false, type: 'actions', width: 1},
];

/** A repo URL is only ever shown as a link when it is https (the API refuses anything else). */
export function safeRepoHref(url) {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' ? parsed.href : null;
    } catch (e) {
        return null;
    }
}

/** The media URL of a file in a repo; `path` is relative to the repo. */
export function repoFileURL(repo, path) {
    return `/media/${encodeMediaPath(`${repo.directory}/${path}`)}`;
}

export function RepoStatusIcon({repo}) {
    if (repo.download_error) {
        return <Tooltip label='The last update failed'>
            <span><Icon name='warning sign' style={{color: 'var(--warning)'}}/></span>
        </Tooltip>;
    }
    if (!repo.head_sha) {
        return <Tooltip label='Not downloaded yet'>
            <span><Icon name='download' style={{color: 'var(--muted)'}}/></span>
        </Tooltip>;
    }
    return null;
}

function RepoName({repo}) {
    return <span style={{display: 'inline-flex', alignItems: 'center', gap: '0.4em'}}>
        {repo.name}
        <RepoStatusIcon repo={repo}/>
    </span>;
}

function useRepos() {
    const [repos, setRepos] = useState(null);  // null=loading, []/[...]=ok, undefined=error

    const refetch = async () => {
        try {
            setRepos(await fetchRepos());
        } catch (e) {
            console.error(e);
            setRepos(undefined);
        }
    };

    useEffect(() => {
        refetch();
    }, []);

    return {repos, refetch};
}

function useRepo(repoId) {
    const [repo, setRepo] = useState(null);  // null=loading, undefined=error

    const refetch = async () => {
        try {
            setRepo(await getRepo(repoId));
        } catch (e) {
            console.error(e);
            setRepo(undefined);
        }
    };

    useEffect(() => {
        setRepo(null);
        refetch();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [repoId]);

    return {repo, refetch};
}

function useRepoTree(repoId, path, enabled) {
    const [tree, setTree] = useState(null);  // null=loading, undefined=error

    useEffect(() => {
        if (!enabled) {
            return;
        }
        let current = true;
        setTree(null);
        getRepoTree(repoId, path)
            .then(newTree => current && setTree(newTree))
            .catch(e => {
                console.error(e);
                if (current) setTree(undefined);
            });
        return () => {
            current = false;
        };
    }, [repoId, path, enabled]);

    return tree;
}

export function ReposPage() {
    useTitle('Repos');
    const {repos} = useRepos();
    const [searchStr, setSearchStr] = useOneQuery('name');
    const searchInputRef = React.useRef();

    const header = <Group justify='space-between' align='flex-end' wrap='wrap'>
        <SearchInput
            placeholder='Repo filter...'
            size='large'
            searchStr={searchStr}
            disabled={!Array.isArray(repos) || repos.length === 0}
            onClear={() => setSearchStr('')}
            onChange={setSearchStr}
            onSubmit={null}
            inputRef={searchInputRef}
        />
        <Group gap='xs'>
            <Button component={Link} to='/repos/import'>Import</Button>
            <Button role='primary' component={Link} to='/repos/new'>New Repo</Button>
        </Group>
    </Group>;

    return <>
        {header}
        <CollectionTable
            collections={repos}
            columns={REPO_COLUMNS}
            routes={REPO_ROUTES}
            searchStr={searchStr}
            emptyMessage='No repos yet.  Add a git repository to keep a copy of it.'
        />
    </>;
}

/** The name, upstream, branch and latest commit of a Repo. */
export function RepoSummary({repo}) {
    const {SingleTag} = useContext(TagsContext);
    const upstream = safeRepoHref(repo.url);
    const branch = repo.branch || repo.default_branch;
    const muted = {color: 'var(--muted)'};
    const meta = {display: 'inline-flex', alignItems: 'center', gap: '0.3em'};

    return <>
        <Header as='h1'>
            <span style={{display: 'inline-flex', alignItems: 'center', gap: '0.4em', flexWrap: 'wrap'}}>
                <IconBrandGit size={28}/>
                <span style={{overflowWrap: 'anywhere'}}>{repo.name}</span>
                {repo.tag_name && <SingleTag name={repo.tag_name}/>}
            </span>
        </Header>
        {repo.description && <p>{repo.description}</p>}
        <Group gap='lg' wrap='wrap' style={{marginBottom: '0.5em'}}>
            {upstream && <a href={upstream} target='_blank' rel='noopener noreferrer'
                            style={{...meta, overflowWrap: 'anywhere'}}>
                <Icon name='external' size='small'/>{repo.url}
            </a>}
            {branch && <span style={meta}>
                <IconGitBranch size={16}/>{branch}
                {!repo.branch && <span style={muted}>(default)</span>}
            </span>}
            <span style={muted}>
                {repo.mode === 'snapshot' ? 'Snapshot' : 'Full history'}
                {repo.size ? ` · ${humanFileSize(repo.size)}` : ''}
            </span>
        </Group>
        {repo.head_sha && <Panel style={{display: 'flex', alignItems: 'center', gap: '0.5em', flexWrap: 'wrap'}}>
            <IconGitCommit size={18}/>
            <code>{repo.head_sha.slice(0, 7)}</code>
            <span style={{flex: '1 1 200px', overflowWrap: 'anywhere'}}>{repo.head_message}</span>
            {repo.head_date && <span style={muted}>{isoDatetimeToAgoPopup(repo.head_date)}</span>}
        </Panel>}
        <RepoStatusMessage repo={repo}/>
    </>;
}

/** Explains a Repo that has not been downloaded, or whose last update failed. */
export function RepoStatusMessage({repo}) {
    if (repo.download_error) {
        return <Message kind='warning' title='The last update failed'>
            <p>The files below are from the last successful update.  {repo.frequency === NEVER
                ? 'This repo is never updated automatically; click Update Now to try again.'
                : 'The update will be tried again.'}</p>
            <pre style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '12em', overflow: 'auto'}}>
                {repo.download_error.trim().split('\n').slice(-8).join('\n')}
            </pre>
        </Message>;
    }
    if (!repo.head_sha) {
        return <Message kind='info' title='Not downloaded yet'>
            <p>This repo will be cloned soon.  Its progress is on the <Link to='/admin'>Downloads</Link> page.</p>
        </Message>;
    }
    return null;
}

/** The path within a repo, each directory a link back to it. */
export function RepoBreadcrumb({name, path, onNavigate}) {
    const parts = path ? path.split('/') : [];
    const crumb = (label, target, key) => <Anchor key={key} component='button' type='button'
                                                  onClick={() => onNavigate(target)}>{label}</Anchor>;
    return <div style={{display: 'flex', flexWrap: 'wrap', gap: '0.3em', overflowWrap: 'anywhere'}}>
        {parts.length ? crumb(name, '', 'root') : <strong>{name}</strong>}
        {parts.map((part, idx) => <React.Fragment key={idx}>
            <span style={{color: 'var(--muted)'}}>/</span>
            {idx === parts.length - 1
                ? <strong>{part}</strong>
                : crumb(part, parts.slice(0, idx + 1).join('/'), idx)}
        </React.Fragment>)}
    </div>;
}

/** One directory of a repo's files: directories first, then files.  */
export function RepoTreeTable({path, entries, onOpenDirectory, onOpenFile}) {
    const parent = path ? path.split('/').slice(0, -1).join('/') : null;
    const link = (onClick, children) => <Anchor component='button' type='button' onClick={onClick}
                                                style={{display: 'inline-flex', alignItems: 'center', gap: '0.4em',
                                                    overflowWrap: 'anywhere', textAlign: 'left'}}>
        {children}
    </Anchor>;

    return <Table striped>
        <Table.Body>
            {parent !== null && <Table.Row>
                <Table.Cell>{link(() => onOpenDirectory(parent), <><IconFolder size={18}/>..</>)}</Table.Cell>
                <Table.Cell/>
            </Table.Row>}
            {entries.map(entry => <Table.Row key={entry.path}>
                <Table.Cell>
                    {entry.is_dir
                        ? link(() => onOpenDirectory(entry.path), <><IconFolder size={18}/>{entry.name}</>)
                        : link(() => onOpenFile(entry), <><IconFile size={18}/>{entry.name}</>)}
                </Table.Cell>
                <Table.Cell style={{textAlign: 'right', color: 'var(--muted)', whiteSpace: 'nowrap'}}>
                    {entry.is_dir ? '' : humanFileSize(entry.size)}
                </Table.Cell>
            </Table.Row>)}
            {entries.length === 0 && <Table.Row>
                <Table.Cell colSpan={2}>This directory is empty</Table.Cell>
            </Table.Row>}
        </Table.Body>
    </Table>;
}

function PlainTextPreview({url}) {
    const [text, setText] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const controller = new AbortController();
        setText(null);
        setError(null);
        fetch(url, {signal: controller.signal})
            .then(response => {
                if (!response.ok) {
                    throw new Error(`${response.status} ${response.statusText}`);
                }
                return response.text();
            })
            .then(setText)
            .catch(e => e.name !== 'AbortError' && setError(e.message));
        return () => controller.abort();
    }, [url]);

    if (error) {
        return <ErrorMessage>Could not read the README: {error}</ErrorMessage>;
    }
    if (text === null) {
        return <Loading/>;
    }
    return <pre style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{text}</pre>;
}

/** A repo's README, formatted when it is markdown. */
export function RepoReadme({repo, readmePath}) {
    const url = repoFileURL(repo, readmePath);
    const name = readmePath.split('/').pop();
    return <Panel className='repo-readme'>
        <Header as='h4'>
            <span style={{display: 'inline-flex', alignItems: 'center', gap: '0.4em'}}>
                <Icon name='book' size='small'/>{name}
            </span>
        </Header>
        {isMarkdownFile('text/plain', readmePath.toLowerCase())
            ? <MarkdownPreview url={url}/>
            : <PlainTextPreview url={url}/>}
    </Panel>;
}

/** A page of a repo's commits, newest first. */
export function RepoHistoryTable({commits}) {
    return <Table striped>
        <Table.Body>
            {commits.map(commit => <Table.Row key={commit.sha}>
                <Table.Cell style={{whiteSpace: 'nowrap', width: '1%'}}><code>{commit.sha.slice(0, 7)}</code></Table.Cell>
                <Table.Cell style={{overflowWrap: 'anywhere'}}>
                    {commit.message}
                    <div style={{color: 'var(--muted)'}}><small>{commit.author}</small></div>
                </Table.Cell>
                <Table.Cell style={{textAlign: 'right', color: 'var(--muted)', whiteSpace: 'nowrap'}}>
                    {isoDatetimeToAgoPopup(commit.date)}
                </Table.Cell>
            </Table.Row>)}
        </Table.Body>
    </Table>;
}

const HISTORY_PAGE_SIZE = 50;

/** A repo's commits, a page at a time. */
export function RepoHistory({repo}) {
    const [commits, setCommits] = useState(null);  // null=loading, undefined=error
    const [total, setTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);

    const fetchPage = async (offset) => {
        const log = await getRepoLog(repo.id, offset, HISTORY_PAGE_SIZE);
        setTotal(log.total);
        return log.commits;
    };

    useEffect(() => {
        let current = true;
        setCommits(null);
        fetchPage(0)
            .then(page => current && setCommits(page))
            .catch(e => {
                console.error(e);
                if (current) setCommits(undefined);
            });
        return () => {
            current = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [repo.id, repo.head_sha]);

    if (commits === undefined) {
        return <ErrorMessage>Could not fetch the repo's history</ErrorMessage>;
    }
    if (commits === null) {
        return <Loading/>;
    }

    const loadMore = async () => {
        setLoadingMore(true);
        try {
            const page = await fetchPage(commits.length);
            setCommits([...commits, ...page]);
        } catch (e) {
            console.error(e);
        } finally {
            setLoadingMore(false);
        }
    };

    return <Panel>
        <Header as='h4'>{total === 1 ? '1 commit' : `${total} commits`}</Header>
        {repo.mode === 'snapshot' && <p style={{color: 'var(--muted)'}}>
            A snapshot only keeps the latest commit.  Change the repo's mode to Full history to keep all of them.
        </p>}
        <RepoHistoryTable commits={commits}/>
        {commits.length < total && <Button onClick={loadMore} disabled={loadingMore}>Load more</Button>}
    </Panel>;
}

export function RepoViewPage() {
    const {repoId} = useParams();
    const {repo, refetch} = useRepo(repoId);
    const [path, setPath] = useOneQuery('path');
    const [view, setView] = useOneQuery('view');
    const {setPreviewFile} = useContext(FilePreviewContext);
    // The files are only listed when they are shown.
    const tree = useRepoTree(repoId, path || '', !!repo?.head_sha && view !== 'history');

    useTitle(repo?.name ? `${repo.name} Repo` : 'Repo');

    if (repo === undefined) {
        return <ErrorMessage>Could not fetch the repo</ErrorMessage>;
    }
    if (repo === null) {
        return <Loading/>;
    }

    const handleUpdate = async () => {
        await updateRepoNow(repoId);
        toast({type: 'info', title: 'Updating repo', description: repo.name, time: 3000});
        await refetch();
    };

    const openFile = async (entry) => {
        const file = await getFile(`${repo.directory}/${entry.path}`, true);
        if (file) {
            setPreviewFile(file);
        }
    };

    const showHistory = view === 'history';
    let files = null;
    if (repo.head_sha && showHistory) {
        files = <RepoHistory repo={repo}/>;
    } else if (repo.head_sha) {
        if (tree === undefined) {
            files = <ErrorMessage>Could not list the repo's files</ErrorMessage>;
        } else if (tree === null) {
            files = <Loading/>;
        } else {
            files = <>
                <Panel>
                    <RepoBreadcrumb name={repo.name} path={tree.path} onNavigate={setPath}/>
                    <RepoTreeTable path={tree.path} entries={tree.entries} onOpenDirectory={setPath}
                                   onOpenFile={openFile}/>
                </Panel>
                {tree.readme_path && <RepoReadme repo={repo} readmePath={tree.readme_path}/>}
            </>;
        }
    }

    return <>
        <div className='wrolpi-button-row'>
            <BackButton/>
            <Button component={Link} to={`/repos/${repoId}/edit`} icon='edit'>Edit</Button>
            <APIButton color='blue' icon='refresh' onClick={handleUpdate} obeyWROLMode={true}>Update Now</APIButton>
            {repo.head_sha && <Button component='a' href={repoArchiveURL(repo.id)} download icon='download'>
                Download ZIP
            </Button>}
        </div>
        <RepoSummary repo={repo}/>
        {repo.head_sha && <ButtonGroup>
            <Button size='small' variant={showHistory ? 'default' : 'filled'} onClick={() => setView(null)}>
                Files
            </Button>
            <Button size='small' variant={showHistory ? 'filled' : 'default'} onClick={() => setView('history')}>
                History
            </Button>
        </ButtonGroup>}
        {files}
    </>;
}

/** The URL's last path segment, which the API uses as the default name. */
export function repoNameFromURL(url) {
    try {
        const parts = new URL(url).pathname.replace(/\/tree\/.*$/, '').split('/').filter(Boolean);
        return (parts.pop() || '').replace(/\.git$/, '');
    } catch (e) {
        return '';
    }
}

export function RepoNewPage() {
    useTitle('New Repo');
    const navigate = useNavigate();
    const wrolMode = useWROLMode();
    const [url, setUrl] = useState('');
    const [name, setName] = useState('');
    const [tagName, setTagName] = useState(null);
    const [frequency, setFrequency] = useState(String(weeklyOption.value));
    const [mode, setMode] = useState('full');
    const [branch, setBranch] = useState('');
    const [submodules, setSubmodules] = useState(false);
    const [description, setDescription] = useState('');
    const [directory, setDirectory] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const urlIsValid = !!safeRepoHref(url.trim());

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!urlIsValid) return;
        setSubmitting(true);
        try {
            const repo = await createRepo({
                url: url.trim(),
                name: name.trim() || null,
                tag_name: tagName,
                frequency: parseInt(frequency),
                mode,
                branch: branch.trim() || null,
                submodules,
                description: description.trim() || null,
                directory: directory.trim() || null,
            });
            toast({type: 'success', title: 'Repo added', description: repo.name, time: 3000});
            navigate(`/repos/${repo.id}`);
        } catch (e) {
            // Error toast already shown by the API client.
        } finally {
            setSubmitting(false);
        }
    };

    return <>
        <div className='wrolpi-button-row'><BackButton/></div>
        <Panel>
            <Header as='h1'>New Repo</Header>
            <p>
                WROLPi clones the repository, then keeps it up to date.  Only <code>https://</code> URLs are
                supported.
            </p>
            <form onSubmit={handleSubmit}>
                <Grid>
                    <Grid.Col span={12}>
                        <TextInput
                            autoFocus
                            required
                            label='URL'
                            placeholder='https://github.com/kiwix/kiwix-tools'
                            value={url}
                            error={url && !urlIsValid ? 'Must be an https:// URL' : null}
                            onChange={(e) => setUrl(e.currentTarget.value)}
                        />
                    </Grid.Col>
                    <Grid.Col span={{base: 12, sm: 6}}>
                        <TextInput
                            label='Name'
                            placeholder={repoNameFromURL(url) || 'From the URL'}
                            value={name}
                            onChange={(e) => setName(e.currentTarget.value)}
                        />
                    </Grid.Col>
                    <Grid.Col span={{base: 12, sm: 6}}>
                        <label style={{display: 'flex', alignItems: 'center', gap: '0.3em', marginBottom: '0.3em'}}>
                            Tag
                            <InfoPopup content='Optional.  A tagged repo lives under its tag in the Repos Directory.'/>
                        </label>
                        <TagsSelector
                            limit={1}
                            selectedTagNames={tagName ? [tagName] : []}
                            onAdd={setTagName}
                            onRemove={() => setTagName(null)}
                        />
                    </Grid.Col>
                    <RepoSettingsFields frequency={frequency} setFrequency={setFrequency} mode={mode}
                                        setMode={setMode} branch={branch} setBranch={setBranch}
                                        submodules={submodules} setSubmodules={setSubmodules}/>
                    <Grid.Col span={12}>
                        <label style={{display: 'block', marginBottom: 4}}>Directory</label>
                        <DirectorySearch value={directory} onSelect={(value) => setDirectory(value || '')}/>
                        <small style={{color: 'var(--muted)'}}>
                            Optional.  Empty saves it in the Repos Directory, whose files are never indexed.  The
                            files of a repo in another directory are indexed (searchable), unless you ignore that
                            directory in Files.  The directory must be empty.
                        </small>
                    </Grid.Col>
                    <Grid.Col span={12}>
                        <Textarea
                            label='Description'
                            placeholder='Optional description'
                            value={description}
                            onChange={(e) => setDescription(e.currentTarget.value)}
                            rows={2}
                        />
                    </Grid.Col>
                    <Grid.Col span={12}>
                        <Button role='save' type='submit' disabled={!urlIsValid || submitting || wrolMode}>
                            Add Repo
                        </Button>
                    </Grid.Col>
                </Grid>
            </form>
        </Panel>
    </>;
}

/** The update frequency, mode and branch of a Repo; shared by the new and edit pages. */
export function RepoSettingsFields({
                                       frequency, setFrequency, mode, setMode, branch, setBranch, submodules,
                                       setSubmodules, disabled,
                                   }) {
    return <>
        <Grid.Col span={{base: 12, sm: 4}}>
            <Select
                label='Download Frequency'
                description='How often to check for updates'
                data={FREQUENCY_OPTIONS}
                value={frequency}
                onChange={(value) => value && setFrequency(value)}
                allowDeselect={false}
                disabled={disabled}
            />
        </Grid.Col>
        <Grid.Col span={{base: 12, sm: 4}}>
            <Select
                label='Mode'
                description={mode === 'full' ? 'Every branch, tag and commit' : 'Uses the least space'}
                data={REPO_MODE_OPTIONS}
                value={mode}
                onChange={(value) => value && setMode(value)}
                allowDeselect={false}
                disabled={disabled}
            />
        </Grid.Col>
        <Grid.Col span={{base: 12, sm: 4}}>
            <TextInput
                label='Branch'
                description='Empty follows the default branch'
                placeholder='Default branch'
                value={branch}
                onChange={(e) => setBranch(e.currentTarget.value)}
                disabled={disabled}
            />
        </Grid.Col>
        <Grid.Col span={12}>
            <Checkbox
                label='Include submodules'
                description='Also download the other repos this repo includes.  Only https:// submodules can be
                    downloaded.'
                checked={submodules}
                onChange={(e) => setSubmodules(e.currentTarget.checked)}
                disabled={disabled}
            />
        </Grid.Col>
    </>;
}

/** What importing a clone would do: its origin, latest commit, and whether its files are indexed. */
export function RepoImportSummary({inspection}) {
    const muted = {color: 'var(--muted)'};
    return <Panel>
        <Grid>
            <Grid.Col span={{base: 12, sm: 6}}>
                <div style={muted}>Origin</div>
                <code style={{overflowWrap: 'anywhere'}}>{inspection.origin || 'None'}</code>
            </Grid.Col>
            <Grid.Col span={{base: 12, sm: 6}}>
                <div style={muted}>Branch</div>
                <span style={{display: 'inline-flex', alignItems: 'center', gap: '0.3em'}}>
                    <IconGitBranch size={16}/>{inspection.branch || 'Detached'}
                </span>
            </Grid.Col>
            {inspection.head_sha && <Grid.Col span={12}>
                <div style={muted}>Latest commit</div>
                <span style={{display: 'inline-flex', alignItems: 'center', gap: '0.5em', flexWrap: 'wrap'}}>
                    <IconGitCommit size={16}/>
                    <code>{inspection.head_sha.slice(0, 7)}</code>
                    <span style={{overflowWrap: 'anywhere'}}>{inspection.head_message}</span>
                    {inspection.head_date && <span style={muted}>{isoDatetimeToAgoPopup(inspection.head_date)}</span>}
                </span>
            </Grid.Col>}
        </Grid>
        {inspection.local_commits > 0 && <Message kind='warning' title={
            inspection.local_commits === 1 ? '1 commit is not on the remote' :
                `${inspection.local_commits} commits are not on the remote`}>
            <p>They will be discarded by the first update.  Push them first if you want to keep them.</p>
        </Message>}
        {inspection.shallow && <Message kind='info' title='This is a shallow clone'>
            <p>In Full history mode, the first update downloads the rest of its history.</p>
        </Message>}
        <p>
            It stays in <code>{inspection.directory}</code>.
            {inspection.ignored
                ? ' Its files are not indexed.'
                : ' Its files are indexed (searchable); to keep them out of search, ignore this directory in Files.'}
        </p>
    </Panel>;
}

export function RepoImportPage() {
    useTitle('Import Repo');
    const navigate = useNavigate();
    const wrolMode = useWROLMode();
    const [directory, setDirectory] = useState('');
    const [inspection, setInspection] = useState(null);
    const [inspectError, setInspectError] = useState(null);
    const [url, setUrl] = useState('');
    const [name, setName] = useState('');
    const [tagName, setTagName] = useState(null);
    const [frequency, setFrequency] = useState(String(weeklyOption.value));
    const [mode, setMode] = useState('full');
    const [branch, setBranch] = useState('');
    const [submodules, setSubmodules] = useState(false);
    const [confirm, setConfirm] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    // Inspect the directory again whenever it, the URL, or the name change.
    useEffect(() => {
        if (!directory) {
            setInspection(null);
            setInspectError(null);
            return;
        }
        let current = true;
        const timer = setTimeout(async () => {
            const {inspection: newInspection, error} = await inspectRepoImport(directory, name.trim(), tagName,
                url.trim());
            if (!current) return;
            setInspection(newInspection || null);
            setInspectError(error || null);
            if (newInspection && !url) {
                setUrl(newInspection.url || '');
            }
        }, 300);
        return () => {
            current = false;
            clearTimeout(timer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [directory, name, url]);

    const handleDirectory = (value) => {
        setDirectory(value || '');
        setUrl('');
        setConfirm(false);
    };

    const urlIsValid = !!safeRepoHref(url.trim());
    const canImport = inspection && urlIsValid && confirm && !submitting && !wrolMode;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!canImport) return;
        setSubmitting(true);
        try {
            const repo = await importRepo({
                directory,
                confirm,
                url: url.trim(),
                name: name.trim() || null,
                tag_name: tagName,
                frequency: parseInt(frequency),
                mode,
                branch: branch.trim() || null,
                submodules,
            });
            toast({type: 'success', title: 'Repo imported', description: repo.name, time: 3000});
            navigate(`/repos/${repo.id}`);
        } catch (e) {
            // Error toast already shown by the API client.
        } finally {
            setSubmitting(false);
        }
    };

    return <>
        <div className='wrolpi-button-row'><BackButton/></div>
        <Panel>
            <Header as='h1'>Import Repo</Header>
            <p>
                Import a git clone that is already in your media directory.  It stays where it is, and WROLPi
                keeps it up to date, as a mirror of its origin.
            </p>
            <form onSubmit={handleSubmit}>
                <Grid>
                    <Grid.Col span={12}>
                        <label style={{display: 'block', marginBottom: 4}}>Directory</label>
                        <DirectorySearch value={directory} onSelect={handleDirectory}/>
                    </Grid.Col>
                    {inspectError && <Grid.Col span={12}>
                        <Message kind='error' title='Cannot import this directory'><p>{inspectError}</p></Message>
                    </Grid.Col>}
                    {inspection && <>
                        <Grid.Col span={12}><RepoImportSummary inspection={inspection}/></Grid.Col>
                        <Grid.Col span={12}>
                            <TextInput
                                required
                                label='URL'
                                description={inspection.url
                                    ? 'From the clone\'s origin'
                                    : 'The clone has no https:// origin; enter the URL it was cloned from'}
                                placeholder='https://github.com/owner/repo'
                                value={url}
                                error={url && !urlIsValid ? 'Must be an https:// URL' : null}
                                onChange={(e) => setUrl(e.currentTarget.value)}
                            />
                        </Grid.Col>
                        <Grid.Col span={{base: 12, sm: 6}}>
                            <TextInput
                                label='Name'
                                placeholder={inspection.name}
                                value={name}
                                onChange={(e) => setName(e.currentTarget.value)}
                            />
                        </Grid.Col>
                        <Grid.Col span={{base: 12, sm: 6}}>
                            <label style={{display: 'block', marginBottom: '0.3em'}}>Tag</label>
                            <TagsSelector
                                limit={1}
                                selectedTagNames={tagName ? [tagName] : []}
                                onAdd={setTagName}
                                onRemove={() => setTagName(null)}
                            />
                        </Grid.Col>
                        <RepoSettingsFields frequency={frequency} setFrequency={setFrequency} mode={mode}
                                            setMode={setMode} branch={branch} setBranch={setBranch}
                                            submodules={submodules} setSubmodules={setSubmodules}/>
                        {inspection.branch && <Grid.Col span={12}>
                            <small style={{color: 'var(--muted)'}}>
                                The clone is on <code>{inspection.branch}</code>.  Enter it as the Branch to keep
                                following it; otherwise the repo follows the remote's default branch.
                            </small>
                        </Grid.Col>}
                        <Grid.Col span={12}>
                            <Checkbox
                                label='I understand that WROLPi will keep this clone identical to its origin: local
                                    changes, untracked files, and commits which are not on the remote will be
                                    discarded.'
                                checked={confirm}
                                onChange={(e) => setConfirm(e.currentTarget.checked)}
                            />
                        </Grid.Col>
                        <Grid.Col span={12}>
                            <Button role='save' type='submit' disabled={!canImport}>Import</Button>
                        </Grid.Col>
                    </>}
                </Grid>
            </form>
        </Panel>
    </>;
}

export function RepoEditPage() {
    const {repoId} = useParams();
    const {repo, refetch} = useRepo(repoId);
    const navigate = useNavigate();
    const wrolMode = useWROLMode();
    const [frequency, setFrequency] = useState(String(weeklyOption.value));
    const [mode, setMode] = useState('full');
    const [branch, setBranch] = useState('');
    const [submodules, setSubmodules] = useState(false);
    const [description, setDescription] = useState('');
    const [tagModalOpen, setTagModalOpen] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [deleteFiles, setDeleteFiles] = useState(false);

    useTitle(repo?.name ? `Edit ${repo.name} Repo` : 'Edit Repo');

    // Seed the form once the repo loads (keyed on id so a refetch doesn't clobber edits).
    const repoDbId = repo?.id;
    useEffect(() => {
        if (repoDbId) {
            setFrequency(String(repo.frequency ?? weeklyOption.value));
            setMode(repo.mode || 'full');
            setBranch(repo.branch || '');
            setSubmodules(!!repo.submodules);
            setDescription(repo.description || '');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [repoDbId]);

    if (repo === undefined) {
        return <ErrorMessage>Could not fetch the repo</ErrorMessage>;
    }
    if (repo === null) {
        return <Loading/>;
    }

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            await updateRepo(repoId, {
                description: description.trim(),
                frequency: parseInt(frequency),
                mode,
                branch: branch.trim(),
                submodules,
            });
            toast({type: 'success', title: 'Repo Updated', description: repo.name, time: 3000});
            await refetch();
        } catch (e) {
            // Error toast already shown by the API client.
        }
    };

    const handleTagSave = async (tagName, directory) => {
        try {
            await tagCollection(repo.collection_id, tagName, directory);
        } catch (e) {
            // Error toast already shown by the API client.
        } finally {
            setTimeout(refetch, 500);
        }
    };

    const handleDelete = async () => {
        try {
            await deleteRepo(repoId, deleteFiles);
            toast({type: 'success', title: 'Repo deleted', description: repo.name, time: 3000});
            navigate('/repos');
        } catch (e) {
            // Error toast already shown by the API client.
        }
    };

    const deleteModal = <Modal open={deleteModalOpen} onClose={() => setDeleteModalOpen(false)} size='tiny'>
        <Modal.Header>Delete Repo?</Modal.Header>
        <Modal.Content>
            <p>WROLPi will stop updating <strong>{repo.name}</strong>.</p>
            <Checkbox
                label={`Also delete its files (${repo.directory})`}
                checked={deleteFiles}
                onChange={(e) => setDeleteFiles(e.currentTarget.checked)}
            />
        </Modal.Content>
        <Modal.Actions>
            <Button role='cancel' onClick={() => setDeleteModalOpen(false)}>Cancel</Button>
            <Button role='danger' onClick={handleDelete}>Delete</Button>
        </Modal.Actions>
    </Modal>;

    return <>
        <div className='wrolpi-button-row'>
            <BackButton/>
            <Button component={Link} to={`/repos/${repoId}`}>View</Button>
        </div>
        <Panel>
            <Header as='h1'>Edit {repo.name}</Header>
            <p style={{overflowWrap: 'anywhere'}}>
                <code>{repo.url}</code><br/>
                Directory: <code>{repo.directory}</code>
            </p>
            {wrolMode && <Message kind='info' title='Repo editing is disabled while in WROL Mode.'/>}
            <form onSubmit={handleSave}>
                <Grid>
                    <RepoSettingsFields frequency={frequency} setFrequency={setFrequency} mode={mode}
                                        setMode={setMode} branch={branch} setBranch={setBranch}
                                        submodules={submodules} setSubmodules={setSubmodules}
                                        disabled={wrolMode}/>
                    <Grid.Col span={12}>
                        <Textarea
                            label='Description'
                            placeholder='Optional description'
                            value={description}
                            onChange={(e) => setDescription(e.currentTarget.value)}
                            rows={2}
                            disabled={wrolMode}
                        />
                    </Grid.Col>
                    <Grid.Col span={12}>
                        <div className='wrolpi-button-row'>
                            <Button role='save' type='submit' disabled={wrolMode}>Save</Button>
                            <Button type='button' color='violet' disabled={wrolMode}
                                    onClick={() => setTagModalOpen(true)}>Tag</Button>
                            <Button type='button' role='danger' disabled={wrolMode}
                                    onClick={() => setDeleteModalOpen(true)}>Delete</Button>
                        </div>
                    </Grid.Col>
                </Grid>
            </form>
        </Panel>
        {deleteModal}
        <CollectionTagModal
            open={tagModalOpen}
            onClose={() => setTagModalOpen(false)}
            currentTagName={repo.tag_name}
            originalDirectory={repo.directory}
            getTagInfo={(tagName) => getCollectionTagInfo(repo.collection_id, tagName)}
            onSave={handleTagSave}
            collectionName='Repo'
            hasDirectory={!!repo.directory}
        />
    </>;
}

export function ReposRoute() {
    return <PageContainer>
        <Routes>
            <Route path='/' element={<ReposPage/>}/>
            <Route path='new' element={<RepoNewPage/>}/>
            <Route path='import' element={<RepoImportPage/>}/>
            <Route path=':repoId' element={<RepoViewPage/>}/>
            <Route path=':repoId/edit' element={<RepoEditPage/>}/>
        </Routes>
    </PageContainer>;
}
