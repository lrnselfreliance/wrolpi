import React, {useState} from "react";
import {Card, Confirm, Container, Icon, Image, Placeholder, Tab} from "semantic-ui-react";
import Paginator, {ClearButton, SearchInput, uploadDate} from "./Common";
import {deleteArchive, postArchive, refreshArchives} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link, NavLink} from "react-router-dom";
import {ArchivePlaceholder} from "./Placeholder";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import {useArchives} from "../hooks/useArchives";
import {useDomains} from "../hooks/useDomains";


function FailedArchiveCard({archive, syncArchive, deleteArchive}) {

    let url = archive.url;

    let syncIcon = (
        <Button onClick={syncArchive}>
            <Icon name='sync' size='big'/>
        </Button>
    );

    let trashIcon = (
        <Button onClick={deleteArchive}>
            <Icon name='trash' size='big'/>
        </Button>
    );

    let externalIcon = (
        <a href={url.url} target='_blank' rel='noopener noreferrer'>
            <Icon name='sign-out' size='big'/>
        </a>
    );

    return (
        <Card>
            <Card.Content>
                <Card.Header>
                    {url.url}
                </Card.Header>
                <Card.Description>
                    <p>Failed!</p>
                    {syncIcon}
                    {trashIcon}
                    {externalIcon}
                </Card.Description>
            </Card.Content>
        </Card>
    );
}

function ArchiveCard({archive, syncArchive, deleteArchive}) {
    let url = archive.url;

    const [syncOpen, setSyncOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);

    const localSyncArchive = async () => {
        setSyncOpen(false);
        await syncArchive(url.url);
    }
    const localDeleteArchive = async () => {
        setDeleteOpen(false);
        await deleteArchive(archive.id);
    }

    let imageSrc = archive.screenshot_path ? `/media/${archive.screenshot_path}` : null;
    let singlefileUrl = archive.singlefile_path ? `/media/${archive.singlefile_path}` : null;

    if (archive.status === 'failed') {
        return <FailedArchiveCard archive={archive} syncArchive={localSyncArchive} deleteArchive={localDeleteArchive}/>;
    }

    let readabilityUrl = archive.readability_path ? `/media/${archive.readability_path}` : null;
    let readabilityIcon = <Button icon disabled><Icon name='book' size='large'/></Button>;
    if (readabilityUrl) {
        readabilityIcon = (
            <Button icon href={readabilityUrl} target='_blank' rel='noopener noreferrer'>
                <Icon name='book' size='large'/>
            </Button>);
    }

    let syncIcon = (
        <>
            <Button icon onClick={() => setSyncOpen(true)}>
                <Icon name='sync' size='large'/>
            </Button>
            <Confirm
                open={syncOpen}
                content='Download the latest version of this URL?'
                confirmButton='Confirm'
                onCancel={() => setSyncOpen(true)}
                onConfirm={localSyncArchive}
            />
        </>
    );

    let deleteIcon = (
            <>
                <Button icon onClick={() => setDeleteOpen(true)}>
                    <Icon name='trash' size='large'/>
                </Button>
                <Confirm
                    open={deleteOpen}
                    content='Are you sure you want to delete this Archive?  All files will be deleted.'
                    confirmButton='Delete'
                    onCancel={() => setDeleteOpen(false)}
                    onConfirm={localDeleteArchive}
                />
            </>
        )
    ;

    let externalIcon = (
        <Button icon href={url.url} target='_blank' rel='noopener noreferrer'>
            <Icon name='sign-out' size='large'/>
        </Button>
    );

    return (
        <Card>
            <Card.Content>
                <a href={singlefileUrl} target='_blank' rel='noopener noreferrer'>
                    <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}}/>
                    <Card.Header>
                        <Container textAlign='left'>
                            <p>{archive.title || url.url}</p>
                        </Container>
                    </Card.Header>
                </a>
                <Card.Meta>
                    {uploadDate(archive.archive_datetime)}
                </Card.Meta>
                <Card.Description>
                    <Container textAlign='left'>
                        {readabilityIcon}
                        {syncIcon}
                        {deleteIcon}
                        {externalIcon}
                    </Container>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

function ArchiveCards({archives, syncArchive, deleteArchive}) {
    return (
        <Card.Group>
            {archives.map((i) => {
                return <ArchiveCard key={i['id']} archive={i} syncArchive={syncArchive} deleteArchive={deleteArchive}/>
            })}
        </Card.Group>
    )
}

function Archives() {
    const {archivesData, setPage, totalPages, searchStr, activePage, setSearchStr, domain, setDomain, search} =
        useArchives();
    const {archives} = archivesData;

    const syncArchive = async (url) => {
        await postArchive(url);
        await search();
    }

    const localDeleteArchive = async (archive_id) => {
        await deleteArchive(archive_id);
        await search();
    }

    let body;
    if (archives === null) {
        // Fetching archives.
        body = <ArchivePlaceholder/>;
    } else if (archives.length === 0 && searchStr) {
        // Search with no results.
        body = <p>No archives found! Is your search too restrictive?</p>;
    } else if (archives.length === 0) {
        // No archives fetched.
        body = <p>No archives found! Have you archived any webpages?</p>;
    } else {
        // Archives fetched successfully!
        body = <ArchiveCards archives={archives} syncArchive={syncArchive} deleteArchive={localDeleteArchive}/>;
    }

    let domainClearButton = null;
    if (domain) {
        domainClearButton = <ClearButton
            onClick={() => setDomain(null)}
            style={{marginBottom: '1em'}}
            label={`Domain: ${domain}`}
        />;
    }

    return (
        <>
            <SearchInput initValue={searchStr} onSubmit={setSearchStr}/>
            {domainClearButton}
            {body}
            <div style={{marginTop: '3em', textAlign: 'center'}}>
                <Paginator
                    activePage={activePage}
                    changePage={setPage}
                    totalPages={totalPages}
                />
            </div>
        </>
    )
}

class ManageArchives extends React.Component {
    async refresh() {
        await refreshArchives();
    }

    render() {
        return (<>
            <Button secondary
                    onClick={this.refresh}>
                Refresh Archive Files
            </Button>
        </>)
    }
}

function Domains() {

    const [domains] = useDomains();

    const row = (domain) => {
        return <Table.Row key={domain['domain']}>
            <Table.Cell>
                <Link to={`/archive?domain=${domain['domain']}`}>
                    {domain['domain']}
                </Link>
            </Table.Cell>
            <Table.Cell>{domain['url_count']}</Table.Cell>
        </Table.Row>
    }

    if (domains) {
        return (
            <>
                <Table celled>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Domain</Table.HeaderCell>
                            <Table.HeaderCell>URLs</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>

                    <Table.Body>
                        {domains.map(row)}
                    </Table.Body>
                </Table>
            </>
        )
    }

    return (<>
        <Placeholder>
            <Placeholder.Header>
                <Placeholder.Line/>
                <Placeholder.Line/>
            </Placeholder.Header>
        </Placeholder>
    </>)
}


export class ArchiveRoute extends React.Component {

    constructor(props) {
        super(props);

        this.panesTos = ['/archive', '/archive/domains', '/archive/manage'];
        this.state = {
            activeIndex: this.matchPaneTo(),
        }
        this.archivesRef = React.createRef();

        this.archivePanes = [
            {
                menuItem: {
                    as: NavLink,
                    content: 'Archives',
                    id: 'archive',
                    to: '/archive',
                    exact: true,
                    key: 'home',
                },
                render: () => <Tab.Pane><Archives/></Tab.Pane>
            },
            {
                menuItem: {
                    as: NavLink,
                    content: 'Domains',
                    id: 'domains',
                    to: '/archive/domains',
                    exact: true,
                    key: 'domains',
                },
                render: () => <Tab.Pane><Domains/></Tab.Pane>
            },
            {
                menuItem: {
                    as: NavLink,
                    content: 'Manage',
                    id: 'manage',
                    to: '/archive/manage',
                    exact: true,
                    key: 'manage',
                },
                render: () => <Tab.Pane><ManageArchives/></Tab.Pane>
            },
        ];

    }

    componentDidUpdate(prevProps, prevState, snapshot) {
        if (prevProps.location.pathname !== this.props.location.pathname) {
            this.setState({activeIndex: this.matchPaneTo()});
        }
    }

    matchPaneTo = () => {
        return this.panesTos.indexOf(this.props.location.pathname);
    }

    render() {
        return (
            <Container style={{marginTop: '2em', marginBottom: '2em'}}>
                <Tab panes={this.archivePanes} activeIndex={this.state.activeIndex} renderActiveOnly={true}/>
            </Container>
        )
    }
}
