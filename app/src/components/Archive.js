import React, {useContext, useState} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Container,
    Dropdown,
    GridColumn,
    GridRow,
    Image,
    Input,
    PlaceholderHeader,
    PlaceholderLine,
    TableCell,
    TableRow
} from "semantic-ui-react";
import {
    APIButton,
    BackButton,
    CardLink,
    encodeMediaPath,
    ErrorMessage,
    ExternalCardLink,
    FileIcon,
    findPosterPath,
    HelpHeader,
    humanFileSize,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    PreviewPath,
    SearchInput,
    SortButton,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common";
import {deleteArchives, postDownload, tagFileGroup, untagFileGroup} from "../api";
import {Link, Route, Routes, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useArchive, useDomains, useSearchArchives, useSearchDomain, useSearchOrder} from "../hooks/customHooks";
import {FileCards, FileRowTagIcon, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import _ from "lodash";
import {Media, ThemeContext} from "../contexts/contexts";
import {Button, Card, CardIcon, darkTheme, Header, Loader, Placeholder, Segment, Tab, TabPane} from "./Theme";
import {SortableTable} from "./SortableTable";
import {taggedImageLabel, TagsSelector} from "../Tags";
import {toast} from "react-semantic-toasts-2";

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

    const {data, size} = archiveFile;

    const singlefileUrl = data.singlefile_path ? `/media/${encodeMediaPath(data.singlefile_path)}` : null;
    const readabilityUrl = data.readability_path ? `/media/${encodeMediaPath(data.readability_path)}` : null;
    const screenshotUrl = data.screenshot_path ? `/media/${encodeMediaPath(data.screenshot_path)}` : null;

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
        const response = await postDownload([archiveFile.url], 'archive');
        if (response.ok) {
            toast({
                type: 'success',
                title: 'Archive Downloading',
                description: 'Archive update has been scheduled.',
                time: 2000,
            });
        } else {
            toast({
                type: 'error',
                title: 'Archive Downloading',
                description: 'Archive update failed.',
                time: 2000,
            });
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

    const archivedDatetimeString = isoDatetimeToString(archiveFile.download_datetime, true);
    const publishedDatetimeString = archiveFile.published_datetime ? isoDatetimeToString(archiveFile.published_datetime, true)
        : 'unknown';
    const modifiedDatetimeString = archiveFile.published_modified_datetime
        ? isoDatetimeToString(archiveFile.published_modified_datetime, true)
        : 'unknown';

    const aboutPane = {
        menuItem: 'About', render: () => <TabPane>
            <Header as={'h3'}>Domain</Header>
            {domainHeader}

            <Header as='h3'>Size</Header>
            {humanFileSize(size)}

            <Header as={'h3'}>URL</Header>
            <p>{archiveFile.url ? <a href={archiveFile.url}>{archiveFile.url}</a> : 'N/A'}</p>

            <Header as={'h3'}>Modified Date</Header>
            <p>{modifiedDatetimeString}</p>
        </TabPane>
    };

    const localPreviewPath = (path, mimetype) => {
        if (path) {
            return <PreviewPath path={path} mimetype={mimetype} taggable={false}>{path}</PreviewPath>
        } else {
            return 'Unknown'
        }
    }

    const filesPane = {
        menuItem: 'Files', render: () => <TabPane>
            <Header as={'h3'}>Singlefile File</Header>
            {localPreviewPath(data.singlefile_path, 'text/html')}

            <Header as={'h3'}>Readability File</Header>
            {localPreviewPath(data.readability_path, 'text/html')}

            <Header as={'h3'}>Readability Text File</Header>
            {localPreviewPath(data.readability_txt_path, 'text/plain')}

            <Header as={'h3'}>Readability JSON File</Header>
            {localPreviewPath(data.readability_json_path, 'application/json')}

            <Header as={'h3'}>Screenshot File</Header>
            {data.screenshot_path ?
                archiveFileLink(data.screenshot_path)
                : 'Unknown'}

            <Header as={'h3'}>Directory</Header>
            {archiveFileLink(archiveFile.directory, true)}
        </TabPane>
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
                        <Header as='h4'>Archived: {archivedDatetimeString}</Header>
                    </GridColumn>
                </GridRow>
            </Grid>

            {singlefileButton}
            {readButton}
            {updateButton}
            {deleteButton}
        </Segment>

        <Segment>
            <TagsSelector selectedTagNames={archiveFile['tags']} onAdd={localAddTag} onRemove={localRemoveTag}/>
        </Segment>

        <Tab menu={tabMenu} panes={tabPanes}/>

        <Segment>
            <HelpHeader
                headerContent='History'
                popupContent='Other archives of this URL created at different times.'
            />
            {historyList}
        </Segment>
    </>
}

export function ArchiveCard({file}) {
    const {s} = useContext(ThemeContext);
    const {data} = file;

    const imageSrc = data.screenshot_path ? `/media/${encodeMediaPath(data.screenshot_path)}` : null;
    const singlefileUrl = data.singlefile_path ? `/media/${encodeMediaPath(data.singlefile_path)}` : null;

    let screenshot = <CardIcon><FileIcon file={file}/></CardIcon>;
    const imageLabel = file.tags && file.tags.length ? taggedImageLabel : null;
    if (imageSrc) {
        screenshot = <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}} label={imageLabel}/>;
    }

    const domain = data ? data.domain : null;
    const domainUrl = `/archive?domain=${domain}`;

    return <Card color={mimetypeColor(file.mimetype)}>
        <div>
            <ExternalCardLink to={singlefileUrl}>
                {screenshot}
            </ExternalCardLink>
        </div>
        <CardContent {...s}>
            <CardHeader>
                <Container textAlign='left'>
                    <ExternalCardLink to={singlefileUrl} className='card-title-ellipsis'>
                        {file.title || data.url}
                    </ExternalCardLink>
                </Container>
            </CardHeader>
            {domain &&
                <CardLink to={domainUrl}>
                    <span {...s}>{domain}</span>
                </CardLink>}
            <CardMeta {...s}>
                <p>
                    {isoDatetimeToString(file.published_datetime)}
                </p>
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

export function DomainsPage() {
    useTitle('Archive Domains');

    const [domains] = useDomains();
    const [searchStr, setSearchStr] = useState('');

    if (domains === null) {
        // Request is pending.
        return <>
            <Placeholder>
                <PlaceholderHeader>
                    <PlaceholderLine/>
                    <PlaceholderLine/>
                </PlaceholderHeader>
            </Placeholder>
        </>;
    } else if (domains === undefined) {
        return <ErrorMessage>Could not fetch domains</ErrorMessage>
    } else if (domains && domains.length === 0) {
        return <Message>
            <Message.Header>No domains yet.</Message.Header>
            <Message.Content>Archive some webpages!</Message.Content>
        </Message>;
    }

    let filteredDomains = domains;
    if (searchStr) {
        const re = new RegExp(_.escapeRegExp(searchStr), 'i');
        filteredDomains = domains.filter(i => re.test(i['domain']));
    }

    const domainRow = ({domain, url_count, size}) => {
        return <TableRow key={domain}>
            <TableCell>
                <Link to={`/archive?domain=${domain}`}>
                    {domain}
                </Link>
            </TableCell>
            <TableCell>{url_count}</TableCell>
            <TableCell>{humanFileSize(size)}</TableCell>
        </TableRow>
    }

    const headers = [
        {key: 'domain', text: 'Domain', sortBy: 'domain', width: 12},
        {key: 'archives', text: 'Archives', sortBy: 'url_count', width: 2},
        {key: 'Size', text: 'Size', sortBy: 'size', width: 2},
    ];

    return <>
        <Input
            icon='search'
            value={searchStr}
            placeholder='Search...'
            onChange={(e, {value}) => setSearchStr(value)}
        />
        <SortableTable
            tableProps={{unstackable: true}}
            data={filteredDomains}
            rowFunc={(i, sortData) => domainRow(i)}
            rowKey='domain'
            tableHeaders={headers}
        />
    </>;
}

export function SearchDomain() {
    // A Dropdown which allows the user to filter by Archive domains.
    const {domain, domains, setDomain} = useSearchDomain();

    const handleChange = (e, {value}) => {
        setDomain(value);
    }

    let domainOptions = [];

    if (domains && domains.length > 0) {
        domainOptions = domains.map(i => {
            return {key: i['domain'], value: i['domain'], text: i['domain']}
        });
    }
    return <>
        <Dropdown selection search clearable fluid
                  placeholder='Domains'
                  options={domainOptions}
                  onChange={handleChange}
                  value={domain}
        />
    </>
}

function ArchivesPage() {
    const [selectedArchives, setSelectedArchives] = useState([]);

    useTitle('Archives');

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
        archives,
        activePage,
        totalPages,
        selectElm,
        selectedArchives,
        onSelect,
        setPage,
        !!searchStr,
    );


    const [localSearchStr, setLocalSearchStr] = React.useState(searchStr || '');
    const searchInput = <SearchInput
        onChange={setLocalSearchStr}
        onClear={() => setLocalSearchStr(null)}
        searchStr={localSearchStr}
        onSubmit={setSearchStr}
        placeholder='Search Archives...'
    />;

    return <>
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

    let dataCell = file.published_datetime ? isoDatetimeToString(file.published_datetime) : '';
    if (sort === 'published_modified_datetime') {
        dataCell = file.published_modified_datetime ? isoDatetimeToString(file.published_modified_datetime) : '';
    } else if (sort === 'download_datetime') {
        dataCell = file.download_datetime ? isoDatetimeToString(file.download_datetime) : '';
    } else if (sort === 'size') {
        dataCell = humanFileSize(file.size);
    } else if (sort === 'viewed') {
        dataCell = isoDatetimeToString(file.viewed);
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
    const links = [
        {text: 'Archives', to: '/archive', end: true},
        {text: 'Domains', to: '/archive/domains'},
    ];
    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' element={<ArchivesPage/>}/>
            <Route path='domains' element={<DomainsPage/>}/>
            <Route path=':archiveId' element={<ArchivePage/>}/>
        </Routes>
    </PageContainer>
}
