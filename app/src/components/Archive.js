import React, {useContext, useState} from "react";
import {
    CardContent,
    CardDescription,
    CardHeader,
    CardMeta,
    Confirm,
    Container,
    Dropdown,
    Image,
    Input,
    Modal,
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
    encodeMediaPath,
    ExternalCardLink,
    FileIcon,
    findPosterPath,
    HelpHeader,
    humanFileSize,
    isoDatetimeToString,
    mimetypeColor,
    PageContainer,
    PreviewLink,
    SearchInput,
    SortButton,
    TabLinks,
    textEllipsis,
    useTitle
} from "./Common";
import {addTag, deleteArchives, postDownload, removeTag} from "../api";
import {Link, Route, Routes, useNavigate, useParams} from "react-router-dom";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useArchive, useDomains, useQuery, useSearchArchives, useSearchDomain} from "../hooks/customHooks";
import {FileCards, FileRowTagIcon, FilesView} from "./Files";
import Grid from "semantic-ui-react/dist/commonjs/collections/Grid";
import _ from "lodash";
import {Media, ThemeContext} from "../contexts/contexts";
import {Button, Card, CardIcon, Header, Loader, Placeholder, Segment} from "./Theme";
import {SortableTable} from "./SortableTable";
import {taggedImageLabel, TagsSelector} from "../Tags";

function ArchivePage() {
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [updateOpen, setUpdateOpen] = useState(false);
    const navigate = useNavigate();
    const {archiveId} = useParams();
    const {archiveFile, history, fetchArchive} = useArchive(archiveId);

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

    const {data, size} = archiveFile;

    const singlefileUrl = data.singlefile_path ? `/media/${encodeMediaPath(data.singlefile_path)}` : null;
    const screenshotUrl = data.screenshot_path ? `/media/${encodeMediaPath(data.screenshot_path)}` : null;
    const readabilityUrl = data.readability_path;

    const singlefileButton = <ExternalCardLink to={singlefileUrl}>
        <Button content='View' color='violet'/>
    </ExternalCardLink>;

    const readabilityLink = readabilityUrl ?
        <PreviewLink file={{path: readabilityUrl, mimetype: 'text/html'}}><Button content='Article'/></PreviewLink> :
        <Button disabled content='Article'/>;

    const screenshot = screenshotUrl ?
        <Image src={screenshotUrl} size='large' style={{marginTop: '1em', marginBottom: '1em'}}/> :
        null;

    const localDeleteArchive = async () => {
        setDeleteOpen(false);
        await deleteArchives([data.id]);
        navigate(-1);
    }
    const localUpdateArchive = async () => {
        setUpdateOpen(false);
        await postDownload(data.url, 'archive');
    }

    const updateButton = (<>
        <Button color='green' onClick={() => setUpdateOpen(true)} content='Update'/>
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

    const domain = data.domain ? data.domain.domain : null;
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
    if (data.url) {
        urlHeader = <Header as='h5'>
            <ExternalCardLink to={data.url}>
                {textEllipsis(data.url)}
            </ExternalCardLink>
        </Header>;
    }

    const localAddTag = async (name) => {
        await addTag(archiveFile, name);
        await fetchArchive();
    }

    const localRemoveTag = async (name) => {
        await removeTag(archiveFile, name);
        await fetchArchive();
    }

    return <>
        <BackButton/>

        <Segment>
            {screenshot}
            <ExternalCardLink to={singlefileUrl}>
                <Header as='h2'>{textEllipsis(archiveFile.title || data.url)}</Header>
            </ExternalCardLink>
            <Header as='h3'>{isoDatetimeToString(data.archive_datetime)}</Header>
            {domainHeader}
            {urlHeader}
            <Header as='h5'>{humanFileSize(size)}</Header>

            {singlefileButton}
            {readabilityLink}
            {updateButton}
            {deleteButton}
        </Segment>

        <Segment>
            <TagsSelector selectedTagNames={archiveFile['tags']} onAdd={localAddTag} onRemove={localRemoveTag}/>
        </Segment>

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
                    <ExternalCardLink to={singlefileUrl}>
                        {cardTitleWrapper(file.title || data.url)}
                    </ExternalCardLink>
                </Container>
            </CardHeader>
            {domain &&
                <CardLink to={domainUrl}>
                    <p {...s}>{domain}</p>
                </CardLink>}
            <CardMeta {...s}>
                <p>
                    {isoDatetimeToString(data.archive_datetime)}
                </p>
            </CardMeta>
            <CardDescription>
                <Link to={`/archive/${data.id}`}>
                    <Button icon='file alternate' content='Details'
                            labelPosition='left'/>
                </Link>
                <Button icon='external' href={data.url} target='_blank' rel='noopener noreferrer'/>
            </CardDescription>
        </CardContent>
    </Card>
}

export function DomainsPage() {
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

export function SearchDomain() {
    // A Dropdown which allows the user to filter by Archive domains.
    const {domain, domains, setDomain} = useSearchDomain();
    const [open, setOpen] = useState(false);

    const handleOpen = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(true);
    }

    const handleClose = (e) => {
        if (e) {
            e.preventDefault();
        }
        setOpen(false);
    }

    const handleChange = (e, {value}) => {
        setDomain(value);
    }

    if (domains && domains.length > 0) {
        const domainOptions = domains.map(i => {
            return {key: i['domain'], value: i['domain'], text: i['domain']}
        });
        return <>
            <Modal closeIcon
                   open={open}
                   onOpen={() => handleOpen()}
                   onClose={() => handleClose()}
            >
                <Modal.Content>
                    domains
                </Modal.Content>
            </Modal>
            <Dropdown selection search clearable fluid
                      placeholder='Domains'
                      options={domainOptions}
                      onChange={handleChange}
                      value={domain}
            />
        </>
    }
    return <></>
}

function Archives() {
    const [selectedArchives, setSelectedArchives] = useState([]);
    const [deleteOpen, setDeleteOpen] = useState(false);

    useTitle('Archives');
    const {searchParams} = useQuery();

    let searchOrder = '-date';
    if (searchParams.get('order')) {
        // Use whatever order the user specified.
        searchOrder = searchParams.get('order');
    } else if (searchParams.get('q')) {
        // User used a search_str
        searchOrder = defaultSearchOrder;
    }

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
        {value: 'date', text: 'Date'},
        {value: 'size', text: 'Size'},
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

    const {body, paginator, selectButton, viewButton, limitDropdown, tagQuerySelector} = FilesView(
        archives,
        activePage,
        totalPages,
        selectElm,
        selectedArchives,
        onSelect,
        setPage,
    );

    const searchInput = <SearchInput clearable
                                     actionIcon='search'
                                     searchStr={searchStr}
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
                <Grid.Row>
                    <Grid.Column width={10}>{searchInput}</Grid.Column>
                    <Grid.Column width={6}><SearchDomain/></Grid.Column>
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
                    <Grid.Column width={5}><SortButton sorts={archiveOrders}/></Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column width={8}>{searchInput}</Grid.Column>
                    <Grid.Column width={6}><SearchDomain/></Grid.Column>
                </Grid.Row>
            </Grid>
        </Media>
        {body}
        {paginator}
    </>
}

export function ArchiveRowCells({file}) {
    const {data} = file;

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
            <Route path='/' element={<Archives/>}/>
            <Route path='domains' element={<DomainsPage/>}/>
            <Route path=':archiveId' element={<ArchivePage/>}/>
        </Routes>
    </PageContainer>
}
