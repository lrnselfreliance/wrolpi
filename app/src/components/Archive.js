import React, {useState} from "react";
import {useHotkeys} from "react-hotkeys-hook";
import {
    APIButton,
    BackButton,
    CardLink,
    DirectoryLink,
    encodeMediaPath,
    ErrorMessage,
    ExternalCardLink,
    FileIcon,
    findPosterPath,
    humanFileSize,
    humanNumber,
    InfoHeader,
    isoDatetimeToAgoPopup,
    PageContainer,
    PreviewPath,
    resolveDataPath,
    SearchInput,
    TabLinks,
    textEllipsis,
    mimetypeColor,
    useTitle,
} from "./Common";
import {
    deleteDomain,
    deleteFileGroups,
    fetchArchiveBrowsers,
    fetchArchiveDownloaderConfig,
    generateArchiveScreenshot,
    getCollectionTagInfo,
    postArchiveFileFormat,
    postDownload,
    previewBatchReorganization,
    refreshDomain,
    tagDomain,
    tagFileGroup,
    untagFileGroup,
    updateArchiveDownloaderConfig,
} from "../api";
import {useForm} from "../hooks/useForm";
import {TaggedDeleteConfirmModal} from "./TaggedDeleteConfirmModal";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {CollectionReorganizeModal} from "./collections/CollectionReorganizeModal";
import {BatchReorganizeModal} from "./collections/BatchReorganizeModal";
import {useReorganizationStatus} from "../contexts/FileWorkerStatusContext";
import {Link, Route, Routes, useLocation, useNavigate, useParams} from "react-router";
import {
    useArchive,
    useArchiveStatistics,
    useDockerized,
    useDomain,
    useDomains,
    useOneQuery,
    useSearchArchives,
    useSearchDomain,
    useSearchOrder
} from "../hooks/customHooks";
import {DeepSearchHint, FileCards, FileRowTagIcon, FilesView, SearchControlBar} from "./Files";
import _ from "lodash";
import {
    ActionInput,
    Button,
    Card,
    Header,
    Icon,
    IconButton,
    Loader,
    Loading,
    Message,
    Panel,
    Placeholder,
    Select,
    Statistic,
    StatisticGroup,
    Table,
    Tabs,
    Textarea,
    TextInput,
    Tooltip,
    toast,
} from "./ui";
import {BulkTagModal} from "./BulkTagModal";
import {TagsSelector} from "../Tags";
import {AddToPlaylistButton} from "./AddToPlaylist";
import {API_ARCHIVE_UPLOAD_URI, Downloaders} from "./Vars";
import {CollectionTable} from "./collections/CollectionTable";
import {CollectionEditForm} from "./collections/CollectionEditForm";
import {RecurringDownloadsTable} from "./admin/Downloads";
import {DestinationForm} from "./Download";

function ArchivePage() {
    const navigate = useNavigate();
    const {fileGroupId} = useParams();
    const {archiveFile, history, fetchArchive} = useArchive(fileGroupId);
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);

    let title = archiveFile ? archiveFile.title ? archiveFile.title : archiveFile.name : null;
    useTitle(title);

    if (archiveFile === null) {
        return <Panel><Loading>Loading archive...</Loading></Panel>;
    }
    if (archiveFile === undefined) {
        return <>
            <Header as='h2'>Unknown archive</Header>
            <Header as='h4'>This archive does not exist</Header>
        </>
    }

    const {data, size, directory} = archiveFile;

    // Resolve data paths (filename-only) to full relative paths using directory
    const singlefilePath = resolveDataPath(data.singlefile_path, directory);
    const readabilityPath = resolveDataPath(data.readability_path, directory);
    const screenshotPath = resolveDataPath(data.screenshot_path, directory);

    const singlefileUrl = singlefilePath ? `/media/${encodeMediaPath(singlefilePath)}` : null;
    const readabilityUrl = readabilityPath ? `/media/${encodeMediaPath(readabilityPath)}` : null;
    const screenshotUrl = screenshotPath ? `/media/${encodeMediaPath(screenshotPath)}` : null;

    const singlefileButton = <ExternalCardLink to={singlefileUrl}>
        <Button color='violet'>View</Button>
    </ExternalCardLink>;
    const readButton = <ExternalCardLink to={readabilityUrl}>
        <Button color='blue' disabled={!!!readabilityUrl}>Read</Button>
    </ExternalCardLink>

    const screenshot = screenshotUrl ?
        <img alt='Archive screenshot' src={screenshotUrl}
             style={{marginTop: '1em', marginBottom: '1em', maxWidth: '100%'}}/> :
        null;

    const localDeleteArchive = async (force = false) => {
        const result = await deleteFileGroups([archiveFile.id], force);
        if (result && result.tagged) {
            setTaggedFileGroups(result.file_groups);
            return;
        }
        toast({
            type: 'success',
            title: 'Archive Deleted',
            description: 'Archive was successfully deleted.',
            time: 2000,
        })
        navigate(-1);
    }

    const localUpdateArchive = async () => {
        const downloadData = {urls: [archiveFile.url], downloader: Downloaders.Archive};
        const response = await postDownload(downloadData);
        if (response.ok) {
            toast({
                type: 'success',
                title: 'Archive Downloading',
                description: 'Archive update has been scheduled.',
                time: 2000,
            });
        }
    }

    const localGenerateScreenshot = async () => {
        const success = await generateArchiveScreenshot(archiveFile.id);
        if (success) {
            // Refresh the archive data after a short delay to show the new screenshot
            setTimeout(() => fetchArchive(), 2000);
        }
    }

    const updateButton = <APIButton
        color='green'
        confirmContent='Download the latest version of this URL?'
        confirmButton='Update'
        onClick={localUpdateArchive}
        obeyWROLMode={true}
    >
        Update
    </APIButton>;
    const deleteButton = <APIButton
        role='danger'
        confirmContent='Are you sure you want to delete this archive? All files will be deleted'
        confirmButton='Delete Archive'
        onClick={() => localDeleteArchive(false)}
        obeyWROLMode={true}
    >
        Delete
    </APIButton>;
    const generateScreenshotButton = !screenshotUrl ? <APIButton
        color='yellow'
        confirmContent='Generate a screenshot for this archive?'
        confirmButton='Generate'
        onClick={localGenerateScreenshot}
        obeyWROLMode={true}
    >
        Generate Screenshot
    </APIButton> : null;

    let historyList = <Loader/>;
    if (history && history.length === 0) {
        historyList = <p>No history available</p>;
    } else if (history) {
        historyList = <FileCards files={history}/>;
    }

    const domain = data.domain ? data.domain : null;
    let domainHeader = <p>Unknown</p>;
    if (domain) {
        const domainUrl = `/archives?domain=${domain}`;
        domainHeader = <Header as='h4'>
            <a href={domainUrl}>{domain}</a>
        </Header>;
    }

    const localAddTag = async (name) => {
        await tagFileGroup(archiveFile, name);
        await fetchArchive();
    }

    const localRemoveTag = async (name) => {
        await untagFileGroup(archiveFile, name);
        await fetchArchive();
    }

    const downloadDatetimeString = archiveFile.download_datetime ?
        isoDatetimeToAgoPopup(archiveFile.download_datetime, true) : 'unknown';
    const publishedDatetimeString = archiveFile.published_datetime ?
        isoDatetimeToAgoPopup(archiveFile.published_datetime, true) : 'unknown';
    const modifiedDatetimeString = archiveFile.published_modified_datetime
        ? isoDatetimeToAgoPopup(archiveFile.published_modified_datetime, true)
        : 'unknown';

    // Helper to find file size from the files array by resolved path
    const findFileSize = (resolvedPath) => {
        if (!resolvedPath || !archiveFile.files) return null;
        const file = archiveFile.files.find(i => String(i.path) === String(resolvedPath));
        return file && file.size
            ? <span style={{marginLeft: '1em', color: 'var(--muted)'}}>({humanFileSize(file.size)})</span>
            : null;
    };

    // Helper to resolve and preview a data path
    const localPreviewPath = (dataPath, mimetype) => {
        const resolvedPath = resolveDataPath(dataPath, directory);
        if (resolvedPath) {
            return <><PreviewPath path={resolvedPath} mimetype={mimetype}
                                  taggable={false}>{resolvedPath}</PreviewPath>{findFileSize(resolvedPath)}</>
        } else {
            return 'Unknown'
        }
    }

    const tableStyle = {width: '100%', borderCollapse: 'separate', borderSpacing: '0 0.7em'};
    const labelStyle = {whiteSpace: 'nowrap', paddingRight: '1.5em', verticalAlign: 'top'};

    return <>
        <div className='wrolpi-button-row'><BackButton/></div>

        <Panel>
            {screenshot}
            <ExternalCardLink to={singlefileUrl}>
                <Header as='h2'>{textEllipsis(archiveFile.title || data.url)}</Header>
            </ExternalCardLink>

            <Header as='h3'>Author: {archiveFile.author ? archiveFile.author : 'unknown'}</Header>

            <div style={{display: 'flex', flexWrap: 'wrap', gap: '1em', marginBottom: '1em'}}>
                <div style={{flex: '1 1 240px'}}>
                    <Header as='h4'>Published: {publishedDatetimeString}</Header>
                </div>
                <div style={{flex: '1 1 240px'}}>
                    <Header as='h4'>Downloaded: {downloadDatetimeString}</Header>
                </div>
            </div>

            <div className='wrolpi-button-row'>
                {singlefileButton}
                {readButton}
                {updateButton}
                {deleteButton}
                {generateScreenshotButton}
                <AddToPlaylistButton fileGroupId={archiveFile.id}/>
            </div>
        </Panel>

        <Panel>
            <TagsSelector
                selectedTagNames={archiveFile['tags']}
                onAdd={localAddTag}
                onRemove={localRemoveTag}
            />
        </Panel>

        <Tabs defaultValue='about'>
            <Tabs.List>
                <Tabs.Tab value='about'>About</Tabs.Tab>
                <Tabs.Tab value='files'>Files</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value='about' pt='md'>
                <Header as={'h3'}>Domain</Header>
                {domainHeader}

                <Header as='h3'>Size</Header>
                {humanFileSize(size)}

                <Header as={'h3'}>URL</Header>
                <p>{archiveFile.url ? <a href={archiveFile.url}>{archiveFile.url}</a> : 'N/A'}</p>

                <Header as={'h3'}>Modified Date</Header>
                <p>{modifiedDatetimeString}</p>
            </Tabs.Panel>
            <Tabs.Panel value='files' pt='md'>
                <table style={tableStyle}>
                    <tbody>
                    <tr>
                        <td style={labelStyle}><strong>Singlefile File</strong></td>
                        <td>{localPreviewPath(data.singlefile_path, 'text/html')}</td>
                    </tr>
                    <tr>
                        <td style={labelStyle}><strong>Readability File</strong></td>
                        <td>{localPreviewPath(data.readability_path, 'text/html')}</td>
                    </tr>
                    <tr>
                        <td style={labelStyle}><strong>Readability Text File</strong></td>
                        <td>{localPreviewPath(data.readability_txt_path, 'text/plain')}</td>
                    </tr>
                    <tr>
                        <td style={labelStyle}><strong>Readability JSON File</strong></td>
                        <td>{localPreviewPath(data.readability_json_path, 'application/json')}</td>
                    </tr>
                    <tr>
                        <td style={labelStyle}><strong>Screenshot File</strong></td>
                        <td>
                            {screenshotPath
                                ? <><PreviewPath path={screenshotPath} mimetype='image/*'
                                                 taggable={false}>{screenshotPath}</PreviewPath>{findFileSize(screenshotPath)}</>
                                : 'Unknown'}
                        </td>
                    </tr>
                    <tr>
                        <td style={labelStyle}><strong>Directory</strong></td>
                        <td><DirectoryLink path={archiveFile.directory}/></td>
                    </tr>
                    </tbody>
                </table>
            </Tabs.Panel>
        </Tabs>

        <Panel>
            <InfoHeader
                headerContent='History'
                popupContent='Other archives of this URL created at different times.'
            />
            {historyList}
        </Panel>

        <TaggedDeleteConfirmModal
            open={taggedFileGroups !== null}
            taggedFileGroups={taggedFileGroups}
            onCancel={() => setTaggedFileGroups(null)}
            onConfirm={async () => {
                setTaggedFileGroups(null);
                await localDeleteArchive(true);
            }}
        />
    </>
}

export function ArchiveCard({file}) {
    const {sort} = useSearchOrder();
    const sortField = sort ? sort.replace(/^-/, '') : null;
    const {data, directory} = file;

    // Resolve data paths (filename-only) to full relative paths using directory
    const screenshotPath = resolveDataPath(data.screenshot_path, directory);
    const singlefilePath = resolveDataPath(data.singlefile_path, directory);

    const imageSrc = screenshotPath ? `/media/${encodeMediaPath(screenshotPath)}` : null;
    const singlefileUrl = singlefilePath ? `/media/${encodeMediaPath(singlefilePath)}` : null;

    // Marks a tagged file, pinned to the poster's corner (same convention as CardPoster).
    const cardTagIcon = <div className='wrolpi-card-tag'><Icon name='tag' size={14} label='Tagged'/></div>;
    const imageLabel = !_.isEmpty(file.tags) ? cardTagIcon : null;

    let media;
    if (imageSrc) {
        media = <ExternalCardLink to={singlefileUrl}>
            <div style={{position: 'relative'}}>
                {imageLabel}
                <img alt='' src={imageSrc} style={{width: '100%', display: 'block'}}/>
            </div>
        </ExternalCardLink>;
    } else {
        media = <ExternalCardLink to={singlefileUrl}>
            <div className='wrolpi-card-icon'>
                {imageLabel}
                <FileIcon file={file}/>
            </div>
        </ExternalCardLink>;
    }

    const domain = data ? data.domain : null;
    const domainUrl = `/archives?domain=${domain}`;

    const title = file.title || data.url;
    const titleElm = <Tooltip label={title}>
        <ExternalCardLink to={singlefileUrl} className='card-title-ellipsis'>{title}</ExternalCardLink>
    </Tooltip>;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;

    const meta = <>
        {domain && <div>
            <CardLink to={domainUrl}>{domain}</CardLink>
        </div>}
        <div>
            {sortField === 'published_modified_datetime'
                ? isoDatetimeToAgoPopup(file.published_modified_datetime, false)
                : sortField === 'download_datetime'
                ? isoDatetimeToAgoPopup(file.download_datetime, false)
                : sortField === 'size'
                ? humanFileSize(file.size)
                : sortField === 'viewed'
                ? isoDatetimeToAgoPopup(file.viewed, false)
                : isoDatetimeToAgoPopup(dt, false)
            }
        </div>
    </>;

    const actions = <div style={{display: 'flex', gap: '0.5em'}}>
        <Link to={`/archives/${file.id}`}>
            <Button icon='file alternate'>Details</Button>
        </Link>
        <IconButton
            icon='external'
            label='Open original URL'
            component='a'
            href={file.url}
            target='_blank'
            rel='noopener noreferrer'
        />
    </div>;

    return <Card media={media} title={titleElm} meta={meta} actions={actions}
                 color={mimetypeColor(file.mimetype, file.primary_path)}/>
}

// Domain table column configuration
const DOMAIN_COLUMNS = [
    {key: 'domain', label: 'Domain', sortable: true, width: 7},
    {key: 'tag_name', label: 'Tag', sortable: true, width: 2},
    {key: 'archive_count', label: 'Archives', sortable: true, align: 'right', width: 2},
    {
        key: 'min_download_frequency',
        label: 'Download Frequency',
        sortable: true,
        format: 'frequency',
        width: 2,
        hideOnMobile: true
    },
    {key: 'size', label: 'Size', sortable: true, align: 'right', format: 'bytes', width: 2, hideOnMobile: true},
    {key: 'actions', label: 'Manage', sortable: false, type: 'actions', width: 1}
];

const DOMAIN_ROUTES = {
    list: '/archives/domains',
    edit: '/archives/domain/:id/edit',
    search: '/archives',
    searchParam: 'domain'
};

function DomainStatistics({statistics}) {
    if (!statistics) {
        return <></>
    }

    return <Panel>
        <Header as='h1'>Statistics</Header>
        <StatisticGroup>
            <Statistic value={statistics.archive_count} label='Archives'/>
            <Statistic value={humanFileSize(statistics.size, true)} label='Total Size'/>
            <Statistic value={humanFileSize(statistics.largest_archive, true)} label='Largest Archive'/>
            <Statistic value={humanNumber(statistics.archive_tags)} label='Archive Tags'/>
        </StatisticGroup>
    </Panel>
}

export function DomainsPage() {
    useTitle('Archive Domains');

    const [domains] = useDomains();
    const [searchStr, setSearchStr] = useOneQuery('domain');
    const searchInputRef = React.useRef();

    useHotkeys('f', (e) => {
        e.preventDefault();
        if (searchInputRef.current) {
            searchInputRef.current.focus();
        }
    }, {enableOnFormTags: false});

    // Header section matching ChannelsPage pattern.  No `marginBottom`: this is a top-level block
    // of the page, and the page's stack spaces it -- its own margin was added to that gap.
    const header = <div style={{display: 'flex', flexWrap: 'wrap', gap: '1em', alignItems: 'center'}}>
        <div style={{flex: '1 1 240px'}}>
            <SearchInput
                placeholder='Domain filter...'
                size='large'
                searchStr={searchStr}
                disabled={!Array.isArray(domains) || domains.length === 0}
                onClear={() => setSearchStr('')}
                onChange={setSearchStr}
                onSubmit={null}
                inputRef={searchInputRef}
            />
        </div>
        <div style={{flex: '1 1 240px', textAlign: 'right'}}>
            {/* No "New Domain" button - domains are auto-created */}
        </div>
    </div>;

    // Empty state
    if (domains && domains.length === 0) {
        return <>
            {header}
            <Message kind='info' title='No domains yet. Archive some webpages!'/>
        </>;
    }

    // Error state
    if (domains === undefined) {
        return <>
            {header}
            <ErrorMessage>Could not fetch Domains</ErrorMessage>
        </>;
    }

    return <>
        {header}
        <CollectionTable
            collections={domains}
            columns={DOMAIN_COLUMNS}
            routes={DOMAIN_ROUTES}
            searchStr={searchStr}
        />
    </>;
}

export function DomainEditPage() {
    const {domainId} = useParams();
    const navigate = useNavigate();
    const {domain, form, fetchDomain} = useDomain(parseInt(domainId));

    // Modal state for tagging
    const [tagEditModalOpen, setTagEditModalOpen] = useState(false);
    // Modal state for reorganization
    const [reorganizeModalOpen, setReorganizeModalOpen] = useState(false);

    useTitle(`Edit Domain: ${domain?.domain || '...'}`);

    // Wrap form.onSubmit to add toast and refresh domain data
    React.useEffect(() => {
        if (form && form.onSubmit) {
            const originalOnSubmit = form.onSubmit;
            form.onSubmit = async () => {
                try {
                    await originalOnSubmit();
                    toast({
                        type: 'success',
                        title: 'Domain Updated',
                        description: 'Domain was successfully updated',
                        time: 3000,
                    });
                    // Refresh domain data to show updated values
                    await fetchDomain();
                } catch (e) {
                    console.error('Failed to update domain:', e);
                    throw e;
                }
            };
        }
    }, [form, fetchDomain]);

    // Handler for tag modal save
    const handleTagSave = async (tagName, directory) => {
        try {
            await tagDomain(parseInt(domainId), tagName, directory);
            toast({
                type: 'success',
                title: 'Domain Tagged',
                description: `Domain "${domain?.domain}" has been tagged with "${tagName}"`,
                time: 3000,
            });
        } catch (e) {
            console.error('Failed to tag domain', e);
        } finally {
            setTimeout(async () => {
                await fetchDomain();
            }, 500);
        }
    };

    // Handler for fetching tag info
    const handleGetTagInfo = async (tagName) => {
        if (domain?.id) {
            return await getCollectionTagInfo(domain.id, tagName);
        }
        return null;
    };

    const handleRefreshDomain = async (e) => {
        if (e) {
            e.preventDefault();
        }
        await refreshDomain(parseInt(domainId));
        // Refresh domain data after completion
        await fetchDomain();
    };

    if (!form.ready) {
        if (form.error) {
            return <>
                <div className='wrolpi-button-row'><BackButton/></div>
                <Message kind='error' title='Domain not found'>
                    <p>{form.error}</p>
                </Message>
            </>;
        }
        return <Loading>Loading domain...</Loading>;
    }

    // Handler for domain deletion
    const handleDelete = async () => {
        try {
            let response = await deleteDomain(parseInt(domainId));
            if (response.status === 204) {
                navigate('/archives/domains');
            }
        } catch (e) {
            console.error('Failed to delete domain', e);
        }
    };

    const deleteButton = <APIButton
        role='danger'
        size='small'
        confirmContent='Are you sure you want to delete this domain? No archive files will be deleted, but archives will be orphaned.'
        confirmButton='Delete Domain'
        confirmHeader='Delete Domain?'
        onClick={handleDelete}
        obeyWROLMode={true}
    >Delete</APIButton>;

    const refreshButton = domain?.directory ? (
        <APIButton
            color='blue'
            size='small'
            onClick={handleRefreshDomain}
            obeyWROLMode={true}
        >Refresh</APIButton>
    ) : null;

    const tagButton = <Button
        type="button"
        size='small'
        onClick={() => setTagEditModalOpen(true)}
        color='violet'
    >Tag</Button>;

    const reorganizeButton = (
        <APIButton
            color='orange'
            size='small'
            onClick={() => setReorganizeModalOpen(true)}
            obeyWROLMode={true}
        >Reorganize Files</APIButton>
    );

    const actionButtons = <>
        {deleteButton}
        {refreshButton}
        {tagButton}
        {reorganizeButton}
    </>;

    const [descriptionProps] = form.getCustomProps({name: 'description', path: 'description'});

    return <>
        <div className='wrolpi-button-row'>
            <BackButton/>
            <Link to={`/archives?domain=${domain?.domain}`}>
                <Button>Archives</Button>
            </Link>
        </div>

        {domain?.needs_reorganization && (
            <Message kind='warning' title='File Format Changed'>
                <p>
                    The file name format has changed. Click "Reorganize Files" to move existing files
                    to match the new format.
                </p>
            </Message>
        )}

        <CollectionEditForm
            form={form}
            title={`Edit Domain: ${domain?.domain || '...'}`}
            wrolModeContent='Domain editing is disabled while in WROL Mode.'
            actionButtons={actionButtons}
            appliedTagName={domain?.tag_name}
        >
            {/*
             * CollectionEditForm lays its children out as a grid, and "row"/"column" are that
             * grid's own class names -- plain divs, not components.
             */}
            <div className="row">
                <div className="column">
                    <DestinationForm
                        form={form}
                        label='Directory'
                        name='directory'
                        path='directory'
                    />
                </div>
            </div>
            <div className="row">
                <div className="column">
                    <label style={{display: 'block', marginBottom: 4}}>Description</label>
                    <Textarea
                        placeholder='Optional description'
                        value={descriptionProps.value || ''}
                        onChange={(e) => descriptionProps.onChange(e.target.value)}
                        rows={3}
                    />
                </div>
            </div>
        </CollectionEditForm>

        {/* Tag Modal */}
        <CollectionTagModal
            open={tagEditModalOpen}
            onClose={() => setTagEditModalOpen(false)}
            currentTagName={domain?.tag_name}
            originalDirectory={domain?.directory}
            getTagInfo={handleGetTagInfo}
            onSave={handleTagSave}
            collectionName="Domain"
            hasDirectory={!!domain?.directory}
        />

        {/* Reorganize Modal */}
        <CollectionReorganizeModal
            open={reorganizeModalOpen}
            onClose={() => setReorganizeModalOpen(false)}
            collectionId={domain?.id}
            collectionName={domain?.domain}
            onComplete={fetchDomain}
            needsReorganization={domain?.needs_reorganization}
        />

        {/* Downloads Panel */}
        <Panel>
            <Header as='h1'>Downloads</Header>
            <RecurringDownloadsTable
                downloads={domain?.downloads}
                fetchDownloads={fetchDomain}
            />
        </Panel>

        {domain && domain.statistics && <DomainStatistics statistics={domain.statistics}/>}
    </>;
}

function ArchiveFileNameForm({form}) {
    const [message, setMessage] = React.useState(null);

    const onChange = async (value) => {
        const response = await postArchiveFileFormat(value);
        const {error, preview} = await response.json();
        if (error) {
            setMessage({kind: 'error', title: 'Invalid File Name', content: error});
        } else {
            setMessage({kind: 'success', title: 'File Name Preview', content: preview});
        }
    }

    const [inputProps] = form.getInputProps({name: 'file_name_format', path: 'file_name_format', onChange});

    return <div>
        <InfoHeader
            headerSize='h5'
            headerContent='Archive File Format'
            popupContent={<>
                <p>Variables:</p>
                <ul>
                    <li><code>%(title)s</code> - Page title</li>
                    <li><code>%(download_datetime)s</code> - Full datetime (YYYY-MM-DD-HH-MM-SS)</li>
                    <li><code>%(download_date)s</code> - Date only (YYYY-MM-DD)</li>
                    <li><code>%(download_year)s</code> - Year</li>
                    <li><code>%(download_month)s</code> - Month (zero-padded)</li>
                    <li><code>%(download_day)s</code> - Day (zero-padded)</li>
                    <li><code>%(domain)s</code> - Domain name</li>
                    <li><code>%(ext)s</code> - File extension (required, must be at end)</li>
                </ul>
                <p>Subdirectories supported: <code>%(download_year)s/%(title)s.%(ext)s</code></p>
            </>}
        />
        <TextInput
            id='file_name_format_input'
            name='file_name_format'
            value={inputProps.value ?? ''}
            onChange={inputProps.onChange}
            data-path={inputProps['data-path']}
        />
        {message && <Message kind={message.kind} title={message.title}>{message.content}</Message>}
    </div>
}

function BrowserConfigForm({form, browsers, browsersAvailable}) {
    const [useCustomPath, setUseCustomPath] = useState(false);

    // Determine if custom path is being used based on current value
    React.useEffect(() => {
        const currentBrowser = form.formData?.browser_executable;
        if (currentBrowser) {
            // Check if current value matches any known browser
            const isKnownBrowser = browsers.some(b => b.path === currentBrowser || b.key === currentBrowser);
            setUseCustomPath(!isKnownBrowser);
        }
    }, [form.formData?.browser_executable, browsers]);

    if (!browsersAvailable) {
        return null;
    }

    // Build dropdown options: auto-detect + installed browsers + custom
    const browserOptions = [
        {value: '', label: 'Auto-detect (recommended)'},
        ...browsers.map(b => ({value: b.path, label: `${b.name} (${b.path})`})),
        {value: '__custom__', label: 'Custom path...'},
    ];

    const handleBrowserChange = (value) => {
        if (value === '__custom__') {
            setUseCustomPath(true);
            form.setValue('browser_executable', '');
        } else {
            setUseCustomPath(false);
            form.setValue('browser_executable', value || null);
        }
    };

    const currentValue = form.formData?.browser_executable || '';
    const dropdownValue = useCustomPath ? '__custom__' : currentValue;

    return <>
        <Header as='h4'>Browser Settings</Header>
        <p>
            Configure which browser SingleFile uses to create archives.
            These settings only apply to native deployments (Raspberry Pi/Debian).
        </p>

        <div style={{marginBottom: '1em'}}>
            <label style={{display: 'block', marginBottom: 4}}>Browser</label>
            <Select
                data={browserOptions}
                value={dropdownValue}
                onChange={handleBrowserChange}
                placeholder='Select browser...'
            />
        </div>

        {useCustomPath && (
            <div style={{marginBottom: '1em'}}>
                <label style={{display: 'block', marginBottom: 4}}>Custom Browser Path</label>
                <TextInput
                    placeholder='/usr/bin/chromium'
                    value={form.formData?.browser_executable || ''}
                    onChange={(e) => form.setValue('browser_executable', e.target.value)}
                />
                <small style={{color: 'var(--muted)'}}>Enter the absolute path to the browser executable.</small>
            </div>
        )}

        <div style={{marginBottom: '1em'}}>
            <label style={{display: 'block', marginBottom: 4}}>Browser Arguments</label>
            <TextInput
                placeholder='["--no-sandbox"]'
                value={form.formData?.browser_args || '["--no-sandbox"]'}
                onChange={(e) => form.setValue('browser_args', e.target.value)}
            />
            <small style={{color: 'var(--muted)'}}>JSON array of arguments passed to the browser. Default:
                ["--no-sandbox"]</small>
        </div>

        <div>
            <label style={{display: 'block', marginBottom: 4}}>User Agent</label>
            <TextInput
                placeholder='Leave empty to use system default'
                value={form.formData?.user_agent || ''}
                onChange={(e) => form.setValue('user_agent', e.target.value || null)}
            />
            <small style={{color: 'var(--muted)'}}>Custom user agent string. Leave empty to use the system
                default.</small>
        </div>
    </>;
}

function ArchiveSettingsPage() {
    useTitle('Archive Settings');

    const dockerized = useDockerized();
    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [domainsNeedingReorg, setDomainsNeedingReorg] = useState(0);
    const [fetchingReorgCount, setFetchingReorgCount] = useState(true);
    const [browsers, setBrowsers] = useState([]);
    const [browsersAvailable, setBrowsersAvailable] = useState(false);

    // Check if batch reorganization is currently active for domains
    const {isReorganizing, taskType, collectionKind} = useReorganizationStatus();
    const isBatchReorganizingDomains = isReorganizing && taskType === 'batch_reorganize' && collectionKind === 'domain';

    // Check how many domains need reorganization on mount (skip if batch is in progress)
    React.useEffect(() => {
        if (isBatchReorganizingDomains) {
            // Skip fetching preview while batch reorganization is in progress
            setFetchingReorgCount(false);
            return;
        }
        setFetchingReorgCount(true);
        previewBatchReorganization('domain')
            .then(data => {
                setDomainsNeedingReorg(data.total_collections || 0);
            })
            .catch(() => {
                setDomainsNeedingReorg(0);
            })
            .finally(() => {
                setFetchingReorgCount(false);
            });
    }, [isBatchReorganizingDomains]);

    // Fetch available browsers on mount (only if not dockerized)
    React.useEffect(() => {
        if (dockerized === false) {
            fetchArchiveBrowsers()
                .then(data => {
                    setBrowsers(data.browsers || []);
                    setBrowsersAvailable(data.available === true);
                })
                .catch(() => {
                    setBrowsers([]);
                    setBrowsersAvailable(false);
                });
        }
    }, [dockerized]);

    const emptyFormData = {
        file_name_format: '%(download_datetime)s_%(title)s.%(ext)s',
        browser_executable: null,
        browser_args: '["--no-sandbox"]',
        user_agent: null,
    };

    const configSubmitter = async () => {
        return await updateArchiveDownloaderConfig(configForm.formData);
    };

    const configForm = useForm({
        fetcher: fetchArchiveDownloaderConfig,
        submitter: configSubmitter,
        emptyFormData,
    });

    const urlClipboardButton = <APIButton
        icon='copy'
        onClick={() => navigator.clipboard.writeText(API_ARCHIVE_UPLOAD_URI)}
    />;
    const dataFieldNameClipboardButton = <APIButton
        icon='copy'
        onClick={() => navigator.clipboard.writeText('singlefile_contents')}
    />;
    const urlFieldNameClipboardButton = <APIButton
        icon='copy'
        onClick={() => navigator.clipboard.writeText('url')}
    />;

    /*
     * A fragment, not a `PageContainer`.  `ArchiveRoute` already wraps its `<Routes>` in one, and
     * a second applies its `margin-top: 1em` and `padding: 1em` again -- so this page sat 1em
     * lower and 1em further in on all four sides than /archives/domains beside it.  As a fragment
     * these panels become blocks of the route's own page stack, which spaces them.
     */
    return <>
        <Panel>
            <Header as='h3'>Archive Downloader Config</Header>

            <div style={{opacity: configForm.loading ? 0.6 : 1, pointerEvents: configForm.loading ? 'none' : 'auto'}}>
                <div style={{maxWidth: 500, marginBottom: '1em'}}>
                    <ArchiveFileNameForm form={configForm}/>
                </div>

                {/* Browser settings - only shown on native deployments */}
                {!dockerized && browsersAvailable && (
                    <div style={{maxWidth: 500, marginBottom: '1em'}}>
                        <BrowserConfigForm
                            form={configForm}
                            browsers={browsers}
                            browsersAvailable={browsersAvailable}
                        />
                    </div>
                )}

                <div style={{textAlign: 'right'}}>
                    <APIButton
                        disabled={configForm.disabled || !configForm.ready}
                        type='submit'
                        style={{marginTop: '0.5em'}}
                        onClick={configForm.onSubmit}
                        id='archive_settings_save_button'
                    >Save</APIButton>
                </div>
            </div>
        </Panel>

        <Panel>
            <Header as='h4'>File Organization</Header>
            <p>
                {fetchingReorgCount
                    ? 'Checking for domains that need reorganization...'
                    : <>
                        <strong>{domainsNeedingReorg}</strong> domain{domainsNeedingReorg !== 1 ? 's' : ''}
                        {domainsNeedingReorg > 0
                            ? ' have files that do not match the current file name format.'
                            : '. All domains are organized correctly.'}
                      </>
                }
            </p>
            <Button
                color='orange'
                icon='folder open outline'
                onClick={() => setBatchModalOpen(true)}
                id='reorganize_all_domains_button'
                disabled={fetchingReorgCount || domainsNeedingReorg === 0}
                loading={fetchingReorgCount}
            >
                Reorganize All Domains
            </Button>
        </Panel>

        <BatchReorganizeModal
            open={batchModalOpen}
            onClose={() => setBatchModalOpen(false)}
            kind='domain'
            onComplete={() => {
                setBatchModalOpen(false);
                setDomainsNeedingReorg(0);
            }}
        />

        <Panel>
            <Header as='h3'>SingleFile Browser Extension</Header>

            <p>
                These are the settings necessary to configure the <a
                href="https://github.com/gildas-lormeau/SingleFile?tab=readme-ov-file#install"
                rel='noopener noreferrer'
                target='_blank'>SingleFile Browser
                Extension</a> to automatically upload to your WROLPi.
            </p>

            <label style={{display: 'block', marginBottom: 4}}>Upload URL</label>
            <ActionInput readOnly
                   value={API_ARCHIVE_UPLOAD_URI}
                   action={urlClipboardButton}
            />
            <label style={{display: 'block', marginBottom: 4, marginTop: '1em'}}>Data Field Name</label>
            <ActionInput readOnly
                   value='singlefile_contents'
                   action={dataFieldNameClipboardButton}
            />
            <label style={{display: 'block', marginBottom: 4, marginTop: '1em'}}>URL Field Name</label>
            <ActionInput readOnly
                   value='url'
                   action={urlFieldNameClipboardButton}
            />
        </Panel>
    </>
}

function ArchivesPage() {
    const [selectedArchives, setSelectedArchives] = useState([]);
    const [bulkTagOpen, setBulkTagOpen] = useState(false);
    const [taggedFileGroups, setTaggedFileGroups] = useState(null);
    const searchInputRef = React.useRef();

    useHotkeys('f', (e) => {
        e.preventDefault();
        if (searchInputRef.current) {
            searchInputRef.current.focus();
        }
    }, {enableOnFormTags: false});

    const {domain, domains} = useSearchDomain();

    // Find the domain object from the domains list to get the ID for the edit link
    const domainObj = domain && domains ? domains.find(d => d.domain === domain) : null;

    let title = 'Archives';
    if (domainObj && domainObj.domain) {
        title = `${domainObj.domain} Archives`;
    }
    useTitle(title);

    const {
        archives,
        totalPages,
        activePage,
        setPage,
        searchStr,
        setSearchStr,
        fetchArchives,
    } = useSearchArchives();

    let archiveOrders = [
        {value: 'published_datetime', text: 'Published Date', short: 'P.Date'},
        {value: 'published_modified_datetime', text: 'Modified Date', short: 'M.Date'},
        {value: 'download_datetime', text: 'Download Date', short: 'D.Date'},
        {value: 'size', text: 'Size'},
        {value: 'viewed', text: 'Recently Viewed', short: 'R.Viewed'},
    ];

    if (searchStr) {
        archiveOrders = [{value: 'rank', text: 'Rank'}, ...archiveOrders];
    }

    const onSelect = (path, checked) => {
        if (checked && path) {
            setSelectedArchives([...selectedArchives, path]);
        } else if (path) {
            setSelectedArchives(selectedArchives.filter(i => i !== path));
        }
    }

    const fileGroupIdsForSelection = () => archives
        .filter(i => selectedArchives.indexOf(i['primary_path']) >= 0)
        .map(i => i['id']);

    const onDelete = async (force = false) => {
        const fileGroupIds = fileGroupIdsForSelection();
        const result = await deleteFileGroups(fileGroupIds, force);
        if (result && result.tagged) {
            setTaggedFileGroups(result.file_groups);
            return;
        }
        await fetchArchives();
        setSelectedArchives([]);
    }

    const invertSelection = async () => {
        const newSelectedArchives = archives.map(archive => archive['key']).filter(i => selectedArchives.indexOf(i) < 0);
        setSelectedArchives(newSelectedArchives);
    }

    const clearSelection = async (e) => {
        if (e) e.preventDefault();
        setSelectedArchives([]);
    }

    const onBulkTagComplete = async () => {
        await fetchArchives();
        setSelectedArchives([]);
    }

    const selectElm = <div className='wrolpi-button-row' style={{marginTop: '0.5em'}}>
        <Button
            role='primary'
            disabled={_.isEmpty(selectedArchives)}
            onClick={() => setBulkTagOpen(true)}
        >Tag</Button>
        <APIButton
            role='danger'
            disabled={_.isEmpty(selectedArchives)}
            confirmButton='Delete'
            confirmContent='Are you sure you want to delete these archives files?  This cannot be undone.'
            onClick={() => onDelete(false)}
        >Delete</APIButton>
        <Button
            role='cancel'
            onClick={invertSelection}
            disabled={_.isEmpty(archives)}
        >
            Invert
        </Button>
        <Button
            role='cancel'
            onClick={clearSelection}
            disabled={_.isEmpty(archives) || _.isEmpty(selectedArchives)}
        >
            Clear
        </Button>
        <BulkTagModal
            open={bulkTagOpen}
            onClose={() => setBulkTagOpen(false)}
            paths={selectedArchives}
            onComplete={onBulkTagComplete}
        />
    </div>;

    const {body, paginator, viewButton} = FilesView(
        {
            files: archives,
            activePage: activePage,
            totalPages: totalPages,
            selectElem: selectElm,
            selectedKeys: selectedArchives,
            onSelect: onSelect,
            setPage: setPage,
            headlines: !!searchStr
        },
    );


    // Domain header with edit link when filtering by domain
    let header;
    if (domainObj && domainObj.domain) {
        const editLink = `/archives/domain/${domainObj.id}/edit`;
        header = <>
            <Header as='h1'>
                {domainObj.domain}
                <Link to={editLink}>
                    <Icon name='edit' style={{marginLeft: '0.5em'}}/>
                </Link>
            </Header>
        </>;
    } else if (domain) {
        // Domain filter is set but domain object not loaded yet
        header = <div style={{marginBottom: '1em'}}>
            <Placeholder lines={1}/>
        </div>;
    }

    return <>
        {header}
        <SearchControlBar
            searchStr={searchStr}
            setSearchStr={setSearchStr}
            placeholder='Search Archives...'
            inputRef={searchInputRef}
            viewButton={viewButton}
            sorts={archiveOrders}
            showDeep={true}
        />
        {body}
        <DeepSearchHint searchStr={searchStr} files={archives}/>
        {paginator}
        <TaggedDeleteConfirmModal
            open={taggedFileGroups !== null}
            taggedFileGroups={taggedFileGroups}
            onCancel={() => setTaggedFileGroups(null)}
            onConfirm={async () => {
                setTaggedFileGroups(null);
                await onDelete(true);
            }}
        />
    </>
}

export function ArchiveRowCells({file}) {
    const {data} = file;
    let {sort} = useSearchOrder();
    sort = sort ? sort.replace(/^-+/, '') : null;

    const archiveUrl = `/archives/${file.id}`;
    const posterPath = findPosterPath(file);
    const posterUrl = posterPath ? `/media/${encodeMediaPath(posterPath)}` : null;

    let poster;
    if (posterUrl) {
        poster = <CardLink to={archiveUrl}>
            <img alt='' src={posterUrl} style={{width: '50px', height: 'auto'}}/>
        </CardLink>;
    } else {
        poster = <FileIcon file={file} size='large'/>;
    }

    let dataCell = file.published_datetime ? isoDatetimeToAgoPopup(file.published_datetime) : '';
    if (sort === 'published_modified_datetime') {
        dataCell = file.published_modified_datetime ? isoDatetimeToAgoPopup(file.published_modified_datetime) : '';
    } else if (sort === 'download_datetime') {
        dataCell = file.download_datetime ? isoDatetimeToAgoPopup(file.download_datetime) : '';
    } else if (sort === 'size') {
        dataCell = humanFileSize(file.size);
    } else if (sort === 'viewed') {
        dataCell = isoDatetimeToAgoPopup(file.viewed);
    }

    // Fragment for SelectableRow
    return <React.Fragment>
        <Table.Cell>
            <div style={{textAlign: 'center'}}>
                {poster}
            </div>
        </Table.Cell>
        <Table.Cell>
            <CardLink to={archiveUrl}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(file.title || file.stem)}
            </CardLink>
        </Table.Cell>
        <Table.Cell>{dataCell}</Table.Cell>
    </React.Fragment>
}

function ArchiveStatistics() {
    useTitle('Archive Statistics');

    const {statistics} = useArchiveStatistics();

    if (statistics === null) {
        // Request is pending.
        return <Loading/>
    } else if (statistics === undefined) {
        return <ErrorMessage>Unable to fetch Archive Statistics</ErrorMessage>
    }

    const {archives, historical, domains} = statistics;

    const archiveNames = [
        {key: 'archives', label: 'Archives'},
        {key: 'sum_size', label: 'Total Size'},
        {key: 'max_size', label: 'Largest Archive'},
        {key: 'week', label: 'Downloads Past Week'},
        {key: 'month', label: 'Downloads Past Month'},
        {key: 'year', label: 'Downloads Past Year'},
    ];
    const historicalNames = [
        {key: 'average_count', label: 'Average Monthly Downloads'},
        {key: 'average_size', label: 'Average Monthly Usage'},
    ];
    const domainNames = [
        {key: 'domains', label: 'Domains'},
        {key: 'tagged_domains', label: 'Tagged Domains'},
    ];

    const buildPanel = (title, names, stats) => {
        return <Panel>
            <Header as='h1' style={{textAlign: 'center'}}>{title}</Header>
            <StatisticGroup>
                {names.map(
                    ({key, label}) =>
                        <Statistic key={key} value={stats[key]} label={label}/>
                )}
            </StatisticGroup>
        </Panel>
    }

    return <>
        {buildPanel('Archives', archiveNames, archives)}
        {buildPanel('Historical Archives', historicalNames, historical)}
        {buildPanel('Domains', domainNames, domains)}
    </>
}

export function ArchiveRoute() {
    const location = useLocation();
    const path = location.pathname;

    const links = [
        {
            text: 'Archives',
            to: '/archives',
            end: true,
            isActive: () => path === '/archives' || /^\/archives\/\d+$/.test(path)
        },
        {
            text: 'Domains',
            to: '/archives/domains',
            isActive: () => path.startsWith('/archives/domain')
        },
        {text: 'Settings', to: '/archives/settings'},
        {text: 'Statistics', to: '/archives/statistics'},
    ];
    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' element={<ArchivesPage/>}/>
            <Route path='domains' element={<DomainsPage/>}/>
            <Route path='domain/:domainId/edit' element={<DomainEditPage/>}/>
            <Route path='settings' element={<ArchiveSettingsPage/>}/>
            <Route path='statistics' element={<ArchiveStatistics/>}/>
            <Route path=':fileGroupId' element={<ArchivePage/>}/>
        </Routes>
    </PageContainer>
}
