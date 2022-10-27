import React, {useContext, useState} from "react";
import {
    Card,
    Confirm,
    Container,
    Image,
    Input,
    PlaceholderHeader,
    PlaceholderLine,
    TableBody,
    TableCell,
    TableHeader,
    TableHeaderCell,
    TableRow
} from "semantic-ui-react";
import {
    CardLink,
    defaultSearchOrder,
    ExternalCardLink,
    FileIcon,
    HelpHeader,
    mimetypeColor,
    PageContainer,
    SearchInput,
    TabLinks,
    textEllipsis,
    uploadDate,
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
import {Button, CardIcon, Header, Loader, Placeholder, Segment, Table} from "./Theme";

function ArchivePage() {
    const {s} = useContext(ThemeContext);

    const [deleteOpen, setDeleteOpen] = useState(false);
    const [syncOpen, setSyncOpen] = useState(false);
    const navigate = useNavigate();
    const {archiveId} = useParams();
    const {archiveFile, alternatives} = useArchive(archiveId);

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
    const readabilityUrl = archive.readability_path ? `/media/${encodeURIComponent(archive.readability_path)}` : null;

    const singlefileButton = <ExternalCardLink to={singlefileUrl}>
        <Button content='View' color='blue'/>
    </ExternalCardLink>;

    const readabilityLink = readabilityUrl ?
        <ExternalCardLink to={readabilityUrl}><Button content='Article'/></ExternalCardLink> :
        <Button disabled content='Article'/>;

    const screenshot = screenshotUrl ?
        <Image src={screenshotUrl} size='large' style={{marginTop: '1em', marginBottom: '1em'}}/> :
        null;

    const localDeleteArchive = async () => {
        setDeleteOpen(false);
        await deleteArchives([archive.id]);
        navigate(-1);
    }
    const localSyncArchive = async () => {
        setSyncOpen(false);
        await postDownload(archive.url, 'archive');
    }

    const syncButton = (<>
        <Button color='yellow' onClick={() => setSyncOpen(true)} content='Sync'/>
        <Confirm
            open={syncOpen}
            content='Download the latest version of this URL?'
            confirmButton='Sync'
            onCancel={() => setSyncOpen(false)}
            onConfirm={localSyncArchive}
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

    let alternativesList = <Loader active/>;
    if (alternatives && alternatives.length > 0) {
        alternativesList = <FileCards files={alternatives}/>;
    } else if (alternatives && alternatives.length === 0) {
        alternativesList = <p>No alternatives available</p>;
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
                {textEllipsis(archive.url, 100)}
            </ExternalCardLink>
        </Header>;
    }

    return (
        <>
            <Button icon='arrow left' content='Back' onClick={() => navigate(-1)}/>

            <Segment>
                {screenshot}
                <ExternalCardLink to={singlefileUrl}>
                    <Header as='h2'>{textEllipsis(archive.title || archive.url, 100)}</Header>
                </ExternalCardLink>
                <Header as='h3'>{uploadDate(archive.archive_datetime)}</Header>
                {domainHeader}
                {urlHeader}

                {singlefileButton}
                {readabilityLink}
                {syncButton}
                {deleteButton}
            </Segment>

            <Segment>
                <HelpHeader
                    headerContent='Alternatives'
                    popupContent='Alternative archives are archives that have the same URL.'
                />
                {alternativesList}
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
        <Card color={mimetypeColor(file.mimetype)} {...s}>
            <div>
                <ExternalCardLink to={singlefileUrl}>
                    {screenshot}
                </ExternalCardLink>
            </div>
            <Card.Content>
                <Card.Header>
                    <Container textAlign='left'>
                        <ExternalCardLink to={singlefileUrl}>
                            {textEllipsis(archive.title || archive.url, 100)}
                        </ExternalCardLink>
                    </Container>
                </Card.Header>
                {domain &&
                    <CardLink to={domainUrl}>
                        <p {...s}>{domain}</p>
                    </CardLink>}
                <Card.Meta {...s}>
                    <p>
                        {uploadDate(archive.archive_datetime)}
                    </p>
                </Card.Meta>
                <Card.Description>
                    <Link to={`/archive/${archive.id}`}>
                        <Button icon='file alternate' content='Details'
                                labelPosition='left'/>
                    </Link>
                    <Button icon='external' href={archive.url} target='_blank' rel='noopener noreferrer'/>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

export function Domains() {
    useTitle('Archive Domains');

    const [domains] = useDomains();
    const [searchStr, setSearchStr] = useState('');

    if (domains === null) {
        return (<>
            <Placeholder>
                <PlaceholderHeader>
                    <PlaceholderLine/>
                    <PlaceholderLine/>
                </PlaceholderHeader>
            </Placeholder>
        </>)
    } else if (!domains || domains.length === 0) {
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

    return <>
        <Input
            icon='search'
            value={searchStr}
            placeholder='Search...'
            onChange={(e, {value}) => setSearchStr(value)}
        />
        <Table celled>
            <TableHeader>
                <TableRow>
                    <TableHeaderCell>Domain</TableHeaderCell>
                    <TableHeaderCell>Archives</TableHeaderCell>
                </TableRow>
            </TableHeader>

            <TableBody>
                {filteredDomains.map(row)}
            </TableBody>
        </Table>
    </>;
}

function Archives() {
    const [domains] = useDomains();
    const [selectedArchives, setSelectedArchives] = useState([]);
    const [deleteOpen, setDeleteOpen] = useState(false);

    useTitle('Archives');

    let filterOptions = [];
    if (domains && domains.length > 0) {
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
            disabled={!selectedArchives || selectedArchives.length === 0}
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
            onClick={() => invertSelection()}
            disabled={!archives || archives.length === 0}
        >
            Invert
        </Button>
        <Button
            color='yellow'
            onClick={() => clearSelection()}
            disabled={(archives && archives.length === 0) || selectedArchives.length === 0}
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
