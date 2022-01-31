import React, {useState} from "react";
import {Card, Confirm, Container, Icon, Image, Placeholder} from "semantic-ui-react";
import Paginator, {
    ClearButton,
    ExternalLink,
    SearchInput,
    TabLinks,
    textEllipsis,
    uploadDate,
    WROLModeMessage
} from "./Common";
import {deleteArchive, postDownload, refreshArchives} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link, Route} from "react-router-dom";
import {ArchivePlaceholder} from "./Placeholder";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useArchives, useDomains} from "../hooks/customHooks";


function FailedArchiveCard({archive, syncArchive, deleteArchive}) {

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
        <a href={archive.url} target='_blank' rel='noopener noreferrer'>
            <Icon name='sign-out' size='big'/>
        </a>
    );

    return (
        <Card>
            <Card.Content>
                <Card.Header>
                    {archive.url}
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

function ArchiveCard({archive, syncArchive, deleteArchive, setDomain}) {
    const [syncOpen, setSyncOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);

    const localSyncArchive = async () => {
        setSyncOpen(false);
        await syncArchive(archive.url);
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

    let syncIcon = null;
    if (syncArchive) {
        syncIcon = (<>
            <Button icon onClick={() => setSyncOpen(true)}>
                <Icon name='sync' size='large'/>
            </Button>
            <Confirm
                open={syncOpen}
                content='Download the latest version of this URL?'
                confirmButton='Confirm'
                onCancel={() => setSyncOpen(false)}
                onConfirm={localSyncArchive}
            />
        </>);
    }

    let deleteIcon = null;
    if (deleteArchive) {
        deleteIcon = (<>
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
        );
    }

    let externalIcon = (
        <Button icon href={archive.url} target='_blank' rel='noopener noreferrer'>
            <Icon name='sign-out' size='large'/>
        </Button>
    );

    const domain = archive.domain.domain;

    return (
        <Card>
            <ExternalLink to={singlefileUrl} className='no-link-underscore card-link'>
                <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}}/>
            </ExternalLink>
            <Card.Content>
                <Card.Header>
                    <Container textAlign='left'>
                        <ExternalLink to={singlefileUrl} className='no-link-underscore card-link'>
                            <p>{textEllipsis(archive.title || archive.url, 100)}</p>
                        </ExternalLink>
                    </Container>
                </Card.Header>
                <a onClick={() => setDomain(domain)} className="no-link-underscore card-link">
                    {textEllipsis(domain, 40)}
                </a>
                <Card.Meta>
                    <p>
                        {uploadDate(archive.archive_datetime)}
                    </p>
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

function ArchiveCards({archives, syncArchive, deleteArchive, setDomain}) {
    return (
        <Card.Group>
            {archives.map((i) => {
                return <ArchiveCard
                    key={i['id']}
                    archive={i}
                    syncArchive={syncArchive}
                    deleteArchive={deleteArchive}
                    setDomain={setDomain}
                />
            })}
        </Card.Group>
    )
}

export function ArchivesList({archives, searchStr, syncArchive, localDeleteArchive, setDomain}) {
    if (archives === null || archives === undefined) {
        // Fetching archives.
        return <ArchivePlaceholder/>;
    } else if (archives.length === 0 && searchStr) {
        // Search with no results.
        return <p>No archives found! Is your search too restrictive?</p>;
    } else if (archives.length === 0) {
        // No archives fetched.
        return <Message>
            <Message.Header>No archives</Message.Header>
            <Message.Content>Have you archived any webpages?</Message.Content>
        </Message>;
    } else {
        // Archives fetched successfully!
        return <ArchiveCards
            archives={archives}
            syncArchive={syncArchive}
            deleteArchive={localDeleteArchive}
            setDomain={setDomain}
        />;
    }
}

export function Archives() {
    const {archivesData, setPage, totalPages, searchStr, activePage, setSearchStr, domain, setDomain, search} =
        useArchives();
    const {archives} = archivesData;

    const syncArchive = async (url) => {
        await postDownload(url, 'archive');
        await search();
    }

    const localDeleteArchive = async (archive_id) => {
        await deleteArchive(archive_id);
        await search();
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
            <ArchivesList
                archives={archives}
                searchStr={searchStr}
                syncArchive={syncArchive}
                localDeleteArchive={localDeleteArchive}
                setDomain={setDomain}
            />
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
            <WROLModeMessage content='Cannot modify Archives'/>
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

    if (domains && domains.length > 0) {
        return (
            <>
                <Table celled>
                    <Table.Header>
                        <Table.Row>
                            <Table.HeaderCell>Domain</Table.HeaderCell>
                            <Table.HeaderCell>Archives</Table.HeaderCell>
                        </Table.Row>
                    </Table.Header>

                    <Table.Body>
                        {domains.map(row)}
                    </Table.Body>
                </Table>
            </>
        )
    }

    if (domains === null) {
        return (<>
            <Placeholder>
                <Placeholder.Header>
                    <Placeholder.Line/>
                    <Placeholder.Line/>
                </Placeholder.Header>
            </Placeholder>
        </>)
    }

    return (<>
        <Message>
            <Message.Header>No domains yet.</Message.Header>
            <Message.Content>Archive some webpages!</Message.Content>
        </Message>
    </>)
}


export function ArchiveRoute(props) {
    const links = [
        {text: 'Archives', to: '/archive', exact: true},
        {text: 'Domains', to: '/archive/domains'},
        {text: 'Manage', to: '/archive/manage'},
    ];
    return <>
        <TabLinks links={links}/>
        <Route path='/archive' exact component={Archives}/>
        <Route path='/archive/domains' component={Domains}/>
        <Route path='/archive/manage' component={ManageArchives}/>
    </>
}
