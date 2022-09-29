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
    uploadDate
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
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [syncOpen, setSyncOpen] = useState(false);
    const navigate = useNavigate();
    const {archiveId} = useParams();
    const {archiveFile, alternatives} = useArchive(archiveId);

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

    return (
        <>
            <Button icon='arrow left' content='Back' onClick={() => navigate(-1)}/>

            <Segment>
                {screenshot}
                <ExternalCardLink to={singlefileUrl}>
                    <Header as='h2'>{textEllipsis(archive.title || archive.url, 100)}</Header>
                </ExternalCardLink>
                <Header as='h3'>{uploadDate(archive.archive_datetime)}</Header>
                <p>
                    <ExternalCardLink to={archive.url}>
                        {textEllipsis(archive.url, 100)}
                    </ExternalCardLink>
                </p>

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
        fetchArchives
    } =
        useSearchArchives(24, domain, searchOrder);
    const setView = (value) => updateQuery({view: value});
    const view = searchParams.get('view');
    const setDomain = (value) => updateQuery({'domain': value});

    const archiveOrders = [
        {key: '-date', value: '-date', text: 'Newest'},
        {key: 'date', value: 'date', text: 'Oldest'},
    ];

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
        let archiveId;
        if (archives) {
            archives.forEach(i => {
                if (i && i['archive'] && i['path'] === path) {
                    archiveId = i['archive']['id'];
                }
            });
        }
        if (checked && archiveId) {
            setSelectedArchives([...selectedArchives, archiveId]);
        } else {
            setSelectedArchives(selectedArchives.filter(i => i !== archiveId));
        }
    }

    const onDelete = async (e) => {
        e.preventDefault();
        setDeleteOpen(false);
        await deleteArchives(selectedArchives);
        await fetchArchives();
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
