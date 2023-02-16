import React, {useContext, useState} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Confirm,
    Container,
    Image,
    Input,
    PlaceholderHeader,
    PlaceholderLine,
    TableCell,
    TableRow
} from "semantic-ui-react";
import {
    BackButton,
    CardLink,
    cardTitleWrapper,
    defaultSearchOrder,
    ExternalCardLink,
    FileIcon,
    HelpHeader,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    PreviewLink,
    SearchInput,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common";
import {deleteArchives, postDownload} from "../api";
import {Link, Route, Routes, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useArchive, useDomains, useQuery, useSearchArchives} from "../hooks/customHooks";
import {FileCards, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import Dropdown from "semantic-ui-react/dist/commonjs/modules/Dropdown";
import _ from "lodash";
import {ThemeContext} from "../contexts/contexts";
import {Button, Card, CardIcon, Header, Loader, Placeholder, Segment} from "./Theme";
import {SortableTable} from "./SortableTable";

function ArchivePage() {
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [updateOpen, setUpdateOpen] = useState(false);
    const navigate = useNavigate();
    const {archiveId} = useParams();
    const {archiveFile, history} = useArchive(archiveId);

    let title;
    if (archiveFile && archiveFile.archive) {
        title = archiveFile.archive.title;
    }
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

    const {archive} = archiveFile;

    const singlefileUrl = archive.singlefile_path ? `/media/${encodeURIComponent(archive.singlefile_path)}` : null;
    const screenshotUrl = archive.screenshot_path ? `/media/${encodeURIComponent(archive.screenshot_path)}` : null;
    const readabilityUrl = archive.readability_path;

    const singlefileButton = <ExternalCardLink to={singlefileUrl}>
        <Button content='View' color='blue'/>
    </ExternalCardLink>;

    const readabilityLink = readabilityUrl ?
        <PreviewLink file={{path: readabilityUrl, mimetype: 'text/html'}}><Button content='Article'/></PreviewLink> :
        <Button disabled content='Article'/>;

    const screenshot = screenshotUrl ?
        <Image src={screenshotUrl} size='large' style={{marginTop: '1em', marginBottom: '1em'}}/> :
        null;

    const localDeleteArchive = async () => {
        setDeleteOpen(false);
        await deleteArchives([archive.id]);
        navigate(-1);
    }
    const localUpdateArchive = async () => {
        setUpdateOpen(false);
        await postDownload(archive.url, 'archive');
    }

    const updateButton = (<>
        <Button color='yellow' onClick={() => setUpdateOpen(true)} content='Update'/>
        <Confirm
            open={updateOpen}
            content='Download the latest version of this URL?'
            confirmButton='Update'
            onCancel={() => setUpdateOpen(false)}
            onConfirm={localUpdateArchive}
        />
    </>);
    const deleteButton = (<>
        <Button color='red' onClick={() => setDeleteOpen(true)} content='Delete' aria-label='Delete'/>
        <Confirm
            open={deleteOpen}
            content='Are you sure you want to delete this archive? All files will be deleted'
            confirmButton='Delete'
            onCancel={() => setDeleteOpen(false)}
            onConfirm={localDeleteArchive}
        />
    </>);

    let historyList = <Loader active/>;
    if (history && history.length === 0) {
        historyList = <p>No history available</p>;
    } else if (history) {
        historyList = <FileCards files={history}/>;
    }

    const domain = archive.domain ? archive.domain.domain : null;
    let domainHeader;
    if (domain) {
        const domainUrl = `/archive?domain=${domain}`;
        domainHeader = <Header as='h5'>
            <CardLink to={domainUrl}>
                {domain}
            </CardLink>
        </Header>;
    }

    let urlHeader;
    if (archive.url) {
        urlHeader = <Header as='h5'>
            <ExternalCardLink to={archive.url}>
                {textEllipsis(archive.url)}
            </ExternalCardLink>
        </Header>;
    }

    return (
        <>
            <BackButton/>

            <Segment>
                {screenshot}
                <ExternalCardLink to={singlefileUrl}>
                    <Header as='h2'>{textEllipsis(archive.title || archive.url)}</Header>
                </ExternalCardLink>
                <Header as='h3'>{isoDatetimeToString(archive.archive_datetime)}</Header>
                {domainHeader}
                {urlHeader}

                {singlefileButton}
                {readabilityLink}
                {updateButton}
                {deleteButton}
            </Segment>

            <Segment>
                <HelpHeader
                    headerContent='History'
                    popupContent='Other archives of this URL created at different times.'
                />
                {historyList}
            </Segment>
        </>
    )
}

export function ArchiveCard({file}) {
    const {s} = useContext(ThemeContext);
    const {archive} = file;

    const imageSrc = archive.screenshot_path ? `/media/${encodeURIComponent(archive.screenshot_path)}` : null;
    const singlefileUrl = archive.singlefile_path ? `/media/${encodeURIComponent(archive.singlefile_path)}` : null;

    let screenshot = <CardIcon><FileIcon file={file}/></CardIcon>;
    if (imageSrc) {
        screenshot = <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}}/>;
    }

    const domain = archive.domain ? archive.domain.domain : null;
    const domainUrl = `/archive?domain=${domain}`;

    return (
        <Card color={mimetypeColor(file.mimetype)}>
            <div>
                <ExternalCardLink to={singlefileUrl}>
                    {screenshot}
                </ExternalCardLink>
            </div>
            <CardContent {...s}>
                <CardHeader>
                    <Container textAlign='left'>
                        <ExternalCardLink to={singlefileUrl}>
                            {cardTitleWrapper(archive.title || archive.url)}
                        </ExternalCardLink>
                    </Container>
                </CardHeader>
                {domain &&
                    <CardLink to={domainUrl}>
                        <p {...s}>{domain}</p>
                    </CardLink>}
                <CardMeta {...s}>
                    <p>
                        {isoDatetimeToString(archive.archive_datetime)}
                    </p>
                </CardMeta>
                <CardDescription>
                    <Link to={`/archive/${archive.id}`}>
                        <Button icon='file alternate' content='Details'
                                labelPosition='left'/>
                    </Link>
                    <Button icon='external' href={archive.url} target='_blank' rel='noopener noreferrer'/>
                </CardDescription>
            </CardContent>
        </Card>
    )
}

export function Domains() {
    useTitle('Archive Domains');

    const [domains] = useDomains();
    const [searchStr, setSearchStr] = useState('');

    if (!domains) {
        return <>
            <Placeholder>
                <PlaceholderHeader>
                    <PlaceholderLine/>
                    <PlaceholderLine/>
                </PlaceholderHeader>
            </Placeholder>
        </>;
    } else if (_.isEmpty(domains)) {
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

    const row = ({domain, url_count}) => {
        return <TableRow key={domain}>
            <TableCell>
                <Link to={`/archive?domain=${domain}`}>
                    {domain}
                </Link>
            </TableCell>
            <TableCell>{url_count}</TableCell>
        </TableRow>
    }

    const headers = [
        {key: 'domain', text: 'Domain', sortBy: 'domain', width: 12},
        {key: 'archives', text: 'Archives', sortBy: 'url_count', width: 2},
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
            rowFunc={(i, sortData) => row(i)}
            rowKey='domain'
            tableHeaders={headers}
        />
    </>;
}

function Archives() {
    const [domains] = useDomains();
    const [selectedArchives, setSelectedArchives] = useState([]);
    const [deleteOpen, setDeleteOpen] = useState(false);

    useTitle('Archives');

    let filterOptions = [];
    if (!_.isEmpty(domains)) {
        domains.forEach(i => {
            filterOptions = [...filterOptions, {text: i['domain'], key: i['domain'], value: i['domain']}]
        });
    }
    const {searchParams, updateQuery} = useQuery();

    let searchOrder = '-date';
    if (searchParams.get('order')) {
        // Use whatever order the user specified.
        searchOrder = searchParams.get('order');
    } else if (searchParams.get('q')) {
        // User used a search_str
        searchOrder = defaultSearchOrder;
    }

    const domain = searchParams.get('domain');
    const {
        archives,
        limit,
        setLimit,
        totalPages,
        activePage,
        setPage,
        searchStr,
        setSearchStr,
        setOrderBy,
        fetchArchives,
    } = useSearchArchives(24, domain, searchOrder);
    const setView = (value) => updateQuery({view: value});
    const view = searchParams.get('view');
    const setDomain = (value) => updateQuery({'domain': value, 'o': 0});

    let archiveOrders = [
        {key: '-date', value: '-date', text: 'Newest'},
        {key: 'date', value: 'date', text: 'Oldest'},
    ];

    if (searchStr) {
        archiveOrders = [{key: 'rank', value: 'rank', text: 'Search Rank'}, ...archiveOrders];
    }

    const menuColumns = (<>
        <Grid.Column width={5}>
            <SearchInput clearable
                         actionIcon='search'
                         searchStr={searchStr}
                         onSubmit={setSearchStr}
            />
        </Grid.Column>
        <Grid.Column width={5}>
            <Dropdown selection fluid
                      placeholder='Sort by...'
                      value={searchOrder}
                      options={archiveOrders}
                      onChange={(e, {value}) => setOrderBy(value)}
            />
        </Grid.Column>
    </>);

    const onSelect = (path, checked) => {
        if (checked && path) {
            setSelectedArchives([...selectedArchives, path]);
        } else if (path) {
            setSelectedArchives(selectedArchives.filter(i => i !== path));
        }
    }

    const onDelete = async (e) => {
        e.preventDefault();
        setDeleteOpen(false);
        const archiveIds = archives.filter(i => selectedArchives.indexOf(i['path']) >= 0).map(i => i['archive']['id']);
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
        <Button
            color='red'
            disabled={_.isEmpty(selectedArchives)}
            onClick={() => setDeleteOpen(true)}
        >Delete</Button>
        <Confirm
            open={deleteOpen}
            content='Are you sure you want to delete these archives files?  This cannot be undone.'
            confirmButton='Delete'
            onCancel={() => setDeleteOpen(false)}
            onConfirm={onDelete}
        />
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

    return <FilesView
        files={archives}
        limit={limit}
        setLimit={setLimit}
        activePage={activePage}
        totalPages={totalPages}
        showLimit={true}
        showSelect={true}
        onSelect={onSelect}
        selectElem={selectElm}
        selectedKeys={selectedArchives}
        view={view}
        setView={setView}
        setPage={setPage}
        filterOptions={filterOptions}
        activeFilters={domain}
        setFilters={setDomain}
        filterPlaceholder='Domain'
        menuColumns={menuColumns}
        menuColumnsCount={2}
    />
}

export function ArchiveRowCells({file}) {
    const {archive} = file;

    const archiveUrl = `/archive/${archive.id}`;
    const posterUrl = archive.screenshot_path ? `/media/${encodeURIComponent(archive.screenshot_path)}` : null;

    let poster;
    if (posterUrl) {
        poster = <CardLink to={archiveUrl}>
            <Image wrapped src={posterUrl} width='50px'/>
        </CardLink>;
    } else {
        poster = <FileIcon file={file} size='large'/>;
    }

    // Fragment for SelectableRow
    return (<React.Fragment>
        <TableCell>
            <center>{poster}</center>
        </TableCell>
        <TableCell>
            <CardLink to={archiveUrl}>
                {textEllipsis(archive.title || archive.stem)}
            </CardLink>
        </TableCell>
    </React.Fragment>)
}

export function ArchiveRoute() {
    const links = [
        {text: 'Archives', to: '/archive', end: true},
        {text: 'Domains', to: '/archive/domains'},
    ];
    return <PageContainer>
        <TabLinks links={links}/>
        <Routes>
            <Route path='/' element={<Archives/>}/>
            <Route path='domains' element={<Domains/>}/>
            <Route path=':archiveId' element={<ArchivePage/>}/>
        </Routes>
    </PageContainer>
}
