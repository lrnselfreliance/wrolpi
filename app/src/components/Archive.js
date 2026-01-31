import React, {useContext, useState} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Container,
    Form,
    GridColumn,
    GridRow,
    Image,
    Input,
    PlaceholderHeader,
    PlaceholderLine,
    StatisticLabel,
    StatisticValue,
    TableCell,
    TextArea,
} from "semantic-ui-react";
import Icon from "semantic-ui-react/dist/commonjs/elements/Icon";
import {
    APIButton,
    BackButton,
    CardLink,
    encodeMediaPath,
    ErrorMessage,
    ExternalCardLink,
    FileIcon,
    findPosterPath,
    humanFileSize,
    humanNumber,
    InfoHeader,
    isoDatetimeToAgoPopup,
    mimetypeColor,
    PageContainer,
    PreviewPath,
    resolveDataPath,
    SearchInput,
    SortButton,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common";
import {
    deleteArchives,
    deleteDomain,
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
import {InputForm, useForm} from "../hooks/useForm";
import {CollectionTagModal} from "./collections/CollectionTagModal";
import {CollectionReorganizeModal} from "./collections/CollectionReorganizeModal";
import {BatchReorganizeModal} from "./collections/BatchReorganizeModal";
import {useReorganizationStatus} from "../contexts/FileWorkerStatusContext";
import {Link, Route, Routes, useLocation, useNavigate, useParams} from "react-router";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {
    useArchive,
    useDockerized,
    useDomain,
    useDomains,
    useOneQuery,
    useSearchArchives,
    useSearchDomain,
    useSearchOrder
} from "../hooks/customHooks";
import {FileCards, FileRowTagIcon, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import _ from "lodash";
import {Media, ThemeContext} from "../contexts/contexts";
import {Button, Card, darkTheme, Header, Loader, Placeholder, Popup, Segment, Statistic, Tab} from "./Theme";
import {taggedImageLabel, TagsSelector} from "../Tags";
import {toast} from "react-semantic-toasts-2";
import {API_ARCHIVE_UPLOAD_URI, Downloaders} from "./Vars";
import {CollectionTable} from "./collections/CollectionTable";
import {CollectionEditForm} from "./collections/CollectionEditForm";
import {RecurringDownloadsTable} from "./admin/Downloads";
import {DestinationForm} from "./Download";

function archiveFileLink(path, directory = false) {
    if (path) {
        const href = directory ?
            `/media/${encodeMediaPath(path)}/`
            : `/media/${encodeMediaPath(path)}`;
        return <a href={href} target='_blank' rel='noopener noreferrer'>
            <pre>{path}</pre>
        </a>
    } else {
        return <p>Unknown</p>
    }
}

function ArchivePage() {
    const navigate = useNavigate();
    const {archiveId} = useParams();
    const {archiveFile, history, fetchArchive} = useArchive(archiveId);
    const {theme} = useContext(ThemeContext);

    let title = archiveFile ? archiveFile.title ? archiveFile.title : archiveFile.name : null;
    useTitle(title);

    if (archiveFile === null) {
        return <Segment><Loader active/></Segment>;
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
        <Button content='View' color='violet'/>
    </ExternalCardLink>;
    const readButton = <ExternalCardLink to={readabilityUrl}>
        <Button content='Read' color='blue' disabled={!!!readabilityUrl}/>
    </ExternalCardLink>

    const screenshot = screenshotUrl ?
        <Image src={screenshotUrl} size='large' style={{marginTop: '1em', marginBottom: '1em'}}/> :
        null;

    const localDeleteArchive = async () => {
        await deleteArchives([data.id]);
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
        const success = await generateArchiveScreenshot(data.id);
        if (success) {
            // Refresh the archive data after a short delay to show the new screenshot
            setTimeout(() => fetchArchive(), 2000);
        }
    }

    const updateButton = <APIButton
        text='Update'
        color='green'
        confirmContent='Download the latest version of this URL?'
        confirmButton='Update'
        onClick={localUpdateArchive}
        obeyWROLMode={true}
        style={{marginTop: '0.5em'}}
    >
        Update
    </APIButton>;
    const deleteButton = <APIButton
        text='Delete'
        color='red'
        confirmContent='Are you sure you want to delete this archive? All files will be deleted'
        confirmButton='Delete'
        onClick={localDeleteArchive}
        obeyWROLMode={true}
    >
        Delete
    </APIButton>;
    const generateScreenshotButton = !screenshotUrl ? <APIButton
        text='Generate Screenshot'
        color='yellow'
        confirmContent='Generate a screenshot for this archive?'
        confirmButton='Generate'
        onClick={localGenerateScreenshot}
        obeyWROLMode={true}
        style={{marginTop: '0.5em'}}
    >
        Generate Screenshot
    </APIButton> : null;

    let historyList = <Loader active/>;
    if (history && history.length === 0) {
        historyList = <p>No history available</p>;
    } else if (history) {
        historyList = <FileCards files={history}/>;
    }

    const domain = data.domain ? data.domain : null;
    let domainHeader = <p>Unknown</p>;
    if (domain) {
        const domainUrl = `/archive?domain=${domain}`;
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

    const aboutPane = {
        menuItem: 'About', render: () => <Tab.Pane>
            <Header as={'h3'}>Domain</Header>
            {domainHeader}

            <Header as='h3'>Size</Header>
            {humanFileSize(size)}

            <Header as={'h3'}>URL</Header>
            <p>{archiveFile.url ? <a href={archiveFile.url}>{archiveFile.url}</a> : 'N/A'}</p>

            <Header as={'h3'}>Modified Date</Header>
            <p>{modifiedDatetimeString}</p>
        </Tab.Pane>
    };

    // Helper to resolve and preview a data path
    const localPreviewPath = (dataPath, mimetype) => {
        const resolvedPath = resolveDataPath(dataPath, directory);
        if (resolvedPath) {
            return <PreviewPath path={resolvedPath} mimetype={mimetype} taggable={false}>{resolvedPath}</PreviewPath>
        } else {
            return 'Unknown'
        }
    }

    const filesPane = {
        menuItem: 'Files', render: () => <Tab.Pane>
            <Header as={'h3'}>Singlefile File</Header>
            {localPreviewPath(data.singlefile_path, 'text/html')}

            <Header as={'h3'}>Readability File</Header>
            {localPreviewPath(data.readability_path, 'text/html')}

            <Header as={'h3'}>Readability Text File</Header>
            {localPreviewPath(data.readability_txt_path, 'text/plain')}

            <Header as={'h3'}>Readability JSON File</Header>
            {localPreviewPath(data.readability_json_path, 'application/json')}

            <Header as={'h3'}>Screenshot File</Header>
            {screenshotPath ?
                archiveFileLink(screenshotPath)
                : 'Unknown'}

            <Header as={'h3'}>Directory</Header>
            {archiveFileLink(archiveFile.directory, true)}
        </Tab.Pane>
    };

    const tabPanes = [aboutPane, filesPane];
    const tabMenu = theme === darkTheme ? {inverted: true, attached: true} : {attached: true};

    return <>
        <BackButton/>

        <Segment>
            {screenshot}
            <ExternalCardLink to={singlefileUrl}>
                <Header as='h2'>{textEllipsis(archiveFile.title || data.url)}</Header>
            </ExternalCardLink>

            <Header as='h3'>Author: {archiveFile.author ? archiveFile.author : 'unknown'}</Header>

            <Grid columns={2} stackable>
                <GridRow>
                    <GridColumn>
                        <Header as='h4'>Published: {publishedDatetimeString}</Header>
                    </GridColumn>
                    <GridColumn>
                        <Header as='h4'>Downloaded: {downloadDatetimeString}</Header>
                    </GridColumn>
                </GridRow>
            </Grid>

            {singlefileButton}
            {readButton}
            {updateButton}
            {deleteButton}
            {generateScreenshotButton}
        </Segment>

        <Segment>
            <TagsSelector
                selectedTagNames={archiveFile['tags']}
                onAdd={localAddTag}
                onRemove={localRemoveTag}
            />
        </Segment>

        <Tab menu={tabMenu} panes={tabPanes}/>

        <Segment>
            <InfoHeader
                headerContent='History'
                popupContent='Other archives of this URL created at different times.'
            />
            {historyList}
        </Segment>
    </>
}

export function ArchiveCard({file}) {
    const {s} = useContext(ThemeContext);
    const {data, directory} = file;

    // Resolve data paths (filename-only) to full relative paths using directory
    const screenshotPath = resolveDataPath(data.screenshot_path, directory);
    const singlefilePath = resolveDataPath(data.singlefile_path, directory);

    const imageSrc = screenshotPath ? `/media/${encodeMediaPath(screenshotPath)}` : null;
    const singlefileUrl = singlefilePath ? `/media/${encodeMediaPath(singlefilePath)}` : null;

    let screenshot = <Card.Icon><FileIcon file={file}/></Card.Icon>;
    const imageLabel = file.tags && file.tags.length ? taggedImageLabel : null;
    if (imageSrc) {
        screenshot = <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}} label={imageLabel}/>;
    }

    const domain = data ? data.domain : null;
    const domainUrl = `/archive?domain=${domain}`;

    const title = file.title || data.url;
    const header = <ExternalCardLink to={singlefileUrl} className='card-title-ellipsis'>{title}</ExternalCardLink>;
    const dt = file.published_datetime || file.published_modified_datetime || file.modified;
    return <Card color={mimetypeColor(file.mimetype)}>
        <div>
            <ExternalCardLink to={singlefileUrl}>
                {screenshot}
            </ExternalCardLink>
        </div>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <Popup on='hover'
                           trigger={header}
                           content={title}/>
                </Container>
            </CardHeader>
            {domain &&
                <CardLink to={domainUrl}>
                    <span {...s}>{domain}</span>
                </CardLink>}
            <CardMeta {...s}>
                {isoDatetimeToAgoPopup(dt, false)}
            </CardMeta>
            <CardDescription>
                <Link to={`/archive/${data.id}`}>
                    <Button icon='file alternate' content='Details'
                            labelPosition='left'/>
                </Link>
                <Button icon='external' href={file.url} target='_blank' rel='noopener noreferrer'/>
            </CardDescription>
        </CardContent>
    </Card>
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
    list: '/archive/domains',
    edit: '/archive/domain/:id/edit',
    search: '/archive',
    searchParam: 'domain'
};

function DomainStatistics({statistics}) {
    if (!statistics) {
        return <></>
    }

    return <Segment>
        <Header as='h1'>Statistics</Header>
        <Statistic>
            <StatisticValue>{statistics.archive_count}</StatisticValue>
            <StatisticLabel>Archives</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanFileSize(statistics.size, true)}</StatisticValue>
            <StatisticLabel>Total Size</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanFileSize(statistics.largest_archive, true)}</StatisticValue>
            <StatisticLabel>Largest Archive</StatisticLabel>
        </Statistic>
        <Statistic>
            <StatisticValue>{humanNumber(statistics.archive_tags)}</StatisticValue>
            <StatisticLabel>Archive Tags</StatisticLabel>
        </Statistic>
    </Segment>
}

export function DomainsPage() {
    useTitle('Archive Domains');

    const [domains] = useDomains();
    const [searchStr, setSearchStr] = useOneQuery('domain');

    // Header section matching ChannelsPage pattern
    const header = <div style={{marginBottom: '1em'}}>
        <Grid stackable columns={2}>
            <Grid.Row>
                <Grid.Column>
                    <SearchInput
                        placeholder='Domain filter...'
                        size='large'
                        searchStr={searchStr}
                        disabled={!Array.isArray(domains) || domains.length === 0}
                        onClear={() => setSearchStr('')}
                        onChange={setSearchStr}
                        onSubmit={null}
                    />
                </Grid.Column>
                <Grid.Column textAlign='right'>
                    {/* No "New Domain" button - domains are auto-created */}
                </Grid.Column>
            </Grid.Row>
        </Grid>
    </div>;

    // Empty state
    if (domains && domains.length === 0) {
        return <>
            {header}
            <Message>
                <Message.Header>No domains yet. Archive some webpages!</Message.Header>
            </Message>
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
        return <Loader active>Loading domain...</Loader>;
    }

    // Handler for domain deletion
    const handleDelete = async () => {
        try {
            let response = await deleteDomain(parseInt(domainId));
            if (response.status === 204) {
                navigate('/archive/domains');
            }
        } catch (e) {
            console.error('Failed to delete domain', e);
        }
    };

    const deleteButton = <APIButton
        color='red'
        size='small'
        confirmContent='Are you sure you want to delete this domain? No archive files will be deleted, but archives will be orphaned.'
        confirmButton='Delete'
        confirmHeader='Delete Domain?'
        onClick={handleDelete}
        obeyWROLMode={true}
        style={{marginTop: '1em'}}
    >Delete</APIButton>;

    const refreshButton = domain?.directory ? (
        <APIButton
            color='blue'
            size='small'
            onClick={handleRefreshDomain}
            obeyWROLMode={true}
            style={{marginTop: '1em'}}
        >Refresh</APIButton>
    ) : null;

    const tagButton = <Button
        type="button"
        size='small'
        onClick={() => setTagEditModalOpen(true)}
        color='green'
        style={{marginTop: '1em'}}
    >Tag</Button>;

    const reorganizeButton = (
        <APIButton
            color='orange'
            size='small'
            onClick={() => setReorganizeModalOpen(true)}
            obeyWROLMode={true}
            style={{marginTop: '1em'}}
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
        <BackButton/>
        <Link to={`/archive?domain=${domain?.domain}`}>
            <Button>Archives</Button>
        </Link>

        {domain?.needs_reorganization && (
            <Message warning>
                <Message.Header>File Format Changed</Message.Header>
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
            <GridRow>
                <GridColumn>
                    <DestinationForm
                        form={form}
                        label='Directory'
                        name='directory'
                        path='directory'
                    />
                </GridColumn>
            </GridRow>
            <GridRow>
                <GridColumn>
                    <Form.Field>
                        <label>Description</label>
                        <TextArea
                            placeholder='Optional description'
                            {...descriptionProps}
                            onChange={(e, {value}) => descriptionProps.onChange(value)}
                            rows={3}
                        />
                    </Form.Field>
                </GridColumn>
            </GridRow>
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

        {/* Downloads Segment */}
        <Segment>
            <Header as='h1'>Downloads</Header>
            <RecurringDownloadsTable
                downloads={domain?.downloads}
                fetchDownloads={fetchDomain}
            />
        </Segment>

        {domain && domain.statistics && <DomainStatistics statistics={domain.statistics}/>}
    </>;
}

function ArchiveFileNameForm({form}) {
    const [message, setMessage] = React.useState(null);

    const onChange = async (value) => {
        const response = await postArchiveFileFormat(value);
        const {error, preview} = await response.json();
        if (error) {
            setMessage({content: error, header: 'Invalid File Name', negative: true});
        } else {
            setMessage({content: preview, header: 'File Name Preview', positive: true});
        }
    }

    const label = <InfoHeader
        headerSize='h5'
        headerContent='Archive File Format'
        popupProps={{wide: 'very', position: 'top left'}}
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
    />;

    return <InputForm
        form={form}
        name='file_name_format'
        path='file_name_format'
        label={label}
        onChange={onChange}
        message={message}
    />
}

function BrowserConfigForm({form, browsers, browsersAvailable}) {
    const {t} = React.useContext(ThemeContext);
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
        {key: 'auto', value: '', text: 'Auto-detect (recommended)'},
        ...browsers.map(b => ({key: b.key, value: b.path, text: `${b.name} (${b.path})`})),
        {key: 'custom', value: '__custom__', text: 'Custom path...'},
    ];

    const handleBrowserChange = (e, {value}) => {
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
        <p {...t}>
            Configure which browser SingleFile uses to create archives.
            These settings only apply to native deployments (Raspberry Pi/Debian).
        </p>

        <Form.Field>
            <label {...t}>Browser</label>
            <Form.Dropdown
                selection
                options={browserOptions}
                value={dropdownValue}
                onChange={handleBrowserChange}
                placeholder='Select browser...'
            />
        </Form.Field>

        {useCustomPath && (
            <Form.Field>
                <label {...t}>Custom Browser Path</label>
                <Input
                    fluid
                    placeholder='/usr/bin/chromium'
                    value={form.formData?.browser_executable || ''}
                    onChange={(e) => form.setValue('browser_executable', e.target.value)}
                />
                <small {...t}>Enter the absolute path to the browser executable.</small>
            </Form.Field>
        )}

        <Form.Field>
            <label {...t}>Browser Arguments</label>
            <Input
                fluid
                placeholder='["--no-sandbox"]'
                value={form.formData?.browser_args || '["--no-sandbox"]'}
                onChange={(e) => form.setValue('browser_args', e.target.value)}
            />
            <small {...t}>JSON array of arguments passed to the browser. Default: ["--no-sandbox"]</small>
        </Form.Field>

        <Form.Field>
            <label {...t}>User Agent</label>
            <Input
                fluid
                placeholder='Leave empty to use system default'
                value={form.formData?.user_agent || ''}
                onChange={(e) => form.setValue('user_agent', e.target.value || null)}
            />
            <small {...t}>Custom user agent string. Leave empty to use the system default.</small>
        </Form.Field>
    </>;
}

function ArchiveSettingsPage() {
    useTitle('Archive Settings');

    const {t} = React.useContext(ThemeContext);
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

    return <PageContainer>
        <Segment>
            <Header as='h3'>Archive Downloader Config</Header>

            <Form>
                <Grid>
                    <GridRow columns={1}>
                        <GridColumn mobile={16} computer={8}>
                            <ArchiveFileNameForm form={configForm}/>
                        </GridColumn>
                    </GridRow>

                    {/* Browser settings - only shown on native deployments */}
                    {!dockerized && browsersAvailable && (
                        <GridRow columns={1}>
                            <GridColumn mobile={16} computer={8}>
                                <BrowserConfigForm
                                    form={configForm}
                                    browsers={browsers}
                                    browsersAvailable={browsersAvailable}
                                />
                            </GridColumn>
                        </GridRow>
                    )}

                    <GridRow columns={1}>
                        <GridColumn textAlign='right'>
                            <APIButton
                                disabled={configForm.disabled || !configForm.ready}
                                type='submit'
                                style={{marginTop: '0.5em'}}
                                onClick={configForm.onSubmit}
                                id='archive_settings_save_button'
                            >Save</APIButton>
                        </GridColumn>
                    </GridRow>
                </Grid>
            </Form>
        </Segment>

        <Segment>
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
                onClick={() => setBatchModalOpen(true)}
                id='reorganize_all_domains_button'
                disabled={fetchingReorgCount || domainsNeedingReorg === 0}
                loading={fetchingReorgCount}
            >
                <Icon name='folder open outline'/> Reorganize All Domains
            </Button>
        </Segment>

        <BatchReorganizeModal
            open={batchModalOpen}
            onClose={() => setBatchModalOpen(false)}
            kind='domain'
            onComplete={() => {
                setBatchModalOpen(false);
                setDomainsNeedingReorg(0);
            }}
        />

        <Segment>
            <Header as='h3'>SingleFile Browser Extension</Header>

            <p {...t}>
                These are the settings necessary to configure the <a
                href="https://github.com/gildas-lormeau/SingleFile?tab=readme-ov-file#install">SingleFile Browser
                Extension</a> to automatically upload to your WROLPi.
            </p>

            <label {...t}>Upload URL</label>
            <Input fluid
                   value={API_ARCHIVE_UPLOAD_URI}
                   label={urlClipboardButton}
            />
            <label {...t}>Data Field Name</label>
            <Input fluid
                   value='singlefile_contents'
                   label={dataFieldNameClipboardButton}
            />
            <label {...t}>URL Field Name</label>
            <Input fluid
                   value='url'
                   label={urlFieldNameClipboardButton}
            />
        </Segment>
    </PageContainer>
}

function ArchivesPage() {
    const [selectedArchives, setSelectedArchives] = useState([]);

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

    const onDelete = async () => {
        const archiveIds = archives.filter(i => selectedArchives.indexOf(i['primary_path']) >= 0)
            .map(i => i['data']['id']);
        await deleteArchives(archiveIds);
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

    const selectElm = <div style={{marginTop: '0.5em'}}>
        <APIButton
            color='red'
            disabled={_.isEmpty(selectedArchives)}
            confirmButton='Delete'
            confirmContent='Are you sure you want to delete these archives files?  This cannot be undone.'
            onClick={onDelete}
        >Delete</APIButton>
        <Button
            color='grey'
            onClick={invertSelection}
            disabled={_.isEmpty(archives)}
        >
            Invert
        </Button>
        <Button
            color='yellow'
            onClick={clearSelection}
            disabled={_.isEmpty(archives) || _.isEmpty(selectedArchives)}
        >
            Clear
        </Button>
    </div>;

    const {body, paginator, selectButton, viewButton, limitDropdown, tagQuerySelector} = FilesView(
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


    const [localSearchStr, setLocalSearchStr] = React.useState(searchStr || '');
    const searchInput = <SearchInput
        onChange={setLocalSearchStr}
        onClear={() => setLocalSearchStr(null)}
        searchStr={localSearchStr}
        onSubmit={setSearchStr}
        placeholder='Search Archives...'
    />;

    // Domain header with edit link when filtering by domain
    let header;
    if (domainObj && domainObj.domain) {
        const editLink = `/archive/domain/${domainObj.id}/edit`;
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
        header = <Placeholder style={{marginBottom: '1em'}}>
            <PlaceholderHeader>
                <PlaceholderLine/>
            </PlaceholderHeader>
        </Placeholder>;
    }

    return <>
        {header}
        <Media at='mobile'>
            <Grid>
                <Grid.Row>
                    <Grid.Column width={2}>{selectButton}</Grid.Column>
                    <Grid.Column width={2}>{viewButton}</Grid.Column>
                    <Grid.Column width={4}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={2}>{tagQuerySelector}</Grid.Column>
                    <Grid.Column width={6}><SortButton sorts={archiveOrders}/></Grid.Column>
                </Grid.Row>
                <Grid.Row width={16}>
                    <Grid.Column>{searchInput}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        <Media greaterThanOrEqual='tablet'>
            <Grid>
                <Grid.Row>
                    <Grid.Column width={1}>{selectButton}</Grid.Column>
                    <Grid.Column width={1}>{viewButton}</Grid.Column>
                    <Grid.Column width={2}>{limitDropdown}</Grid.Column>
                    <Grid.Column width={1}>{tagQuerySelector}</Grid.Column>
                    <Grid.Column width={3}><SortButton sorts={archiveOrders}/></Grid.Column>
                    <Grid.Column width={8}>{searchInput}</Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {body}
        {paginator}
    </>
}

export function ArchiveRowCells({file}) {
    const {data} = file;
    let {sort} = useSearchOrder();
    sort = sort ? sort.replace(/^-+/, '') : null;

    const archiveUrl = `/archive/${data.id}`;
    const posterPath = findPosterPath(file);
    const posterUrl = posterPath ? `/media/${encodeMediaPath(posterPath)}` : null;

    let poster;
    if (posterUrl) {
        poster = <CardLink to={archiveUrl}>
            <Image wrapped src={posterUrl} width='50px'/>
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
        <TableCell>
            <center>{poster}</center>
        </TableCell>
        <TableCell>
            <CardLink to={archiveUrl}>
                <FileRowTagIcon file={file}/>
                {textEllipsis(file.title || file.stem)}
            </CardLink>
        </TableCell>
        <TableCell>{dataCell}</TableCell>
    </React.Fragment>
}

export function ArchiveRoute() {
    const location = useLocation();
    const path = location.pathname;

    const links = [
        {
            text: 'Archives',
            to: '/archive',
            end: true,
            isActive: () => path === '/archive' || /^\/archive\/\d+$/.test(path)
        },
        {
            text: 'Domains',
            to: '/archive/domains',
            isActive: () => path.startsWith('/archive/domain')
        },
        {text: 'Settings', to: '/archive/settings'},
    ];
    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' element={<ArchivesPage/>}/>
            <Route path='domains' element={<DomainsPage/>}/>
            <Route path='domain/:domainId/edit' element={<DomainEditPage/>}/>
            <Route path='settings' element={<ArchiveSettingsPage/>}/>
            <Route path=':archiveId' element={<ArchivePage/>}/>
        </Routes>
    </PageContainer>
}
