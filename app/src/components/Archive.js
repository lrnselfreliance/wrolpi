import React, {useState} from "react";
import {Card, Confirm, Container, Divider, Header, Image, Loader, Placeholder, Segment} from "semantic-ui-react";
import {
    CardGroupCentered,
    ClearButton,
    PageContainer,
    Paginator,
    SearchInput,
    TabLinks,
    textEllipsis,
    uploadDate,
    WROLModeMessage
} from "./Common";
import {deleteArchive, postDownload, refreshArchives} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link, Route, useHistory} from "react-router-dom";
import {ArchivePlaceholder} from "./Placeholder";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import Message from "semantic-ui-react/dist/commonjs/collections/Message";
import {useArchive, useArchives, useDomains} from "../hooks/customHooks";

function ArchivePage(props) {
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [syncOpen, setSyncOpen] = useState(false);

    const history = useHistory();
    const archiveId = props.match.params.archive_id;
    const archive = useArchive(archiveId);
    if (archive === null) {
        return <Segment><Loader active/></Segment>;
    }
    if (archive === undefined) {
        return <>
            <Header as='h2'>Unknown archive</Header>
            This archive does not exist
        </>
    }

    const singlefileUrl = archive.singlefile_path ? `/media/${encodeURIComponent(archive.singlefile_path)}` : null;
    const readabilityUrl = archive.readability_path ? `/media/${encodeURIComponent(archive.readability_path)}` : null;

    const readabilityLink = readabilityUrl ?
        <a href={readabilityUrl}><Button icon='book' color='violet' content='Article' labelPosition='left'/></a> :
        <Button disabled color='violet' content='Article' labelPosition='left'/>;

    const localDeleteArchive = async () => {
        setDeleteOpen(false);
        await deleteArchive(archive.id);
    }
    const localSyncArchive = async () => {
        setSyncOpen(false);
        await postDownload(archive.url, 'archive');
    }

    return (
        <>
            <Button icon='arrow left' content='Back' onClick={() => history.goBack()}/>
            <Header as='h1'>{textEllipsis(archive.title || archive.url, 100)}</Header>
            <p>{uploadDate(archive.archive_datetime)}</p>
            <a href={singlefileUrl}><Button color='blue' icon='eye' content='View' labelPosition='left'/></a>
            {readabilityLink}
            <Button icon='sync' color='yellow' onClick={() => setSyncOpen(true)}
                    content='Sync' labelPosition='left'/>
            <Confirm
                open={syncOpen}
                content='Download the latest version of this URL?'
                confirmButton='Sync'
                onCancel={() => setSyncOpen(false)}
                onConfirm={localSyncArchive}
            />
            <Button icon='trash' color='red' onClick={() => setDeleteOpen(true)}
                    content='Delete' labelPosition='left'/>
            <Confirm
                open={deleteOpen}
                content='Are you sure you want to delete this archive? All files will be deleted'
                confirmButton='Delete'
                onCancel={() => setDeleteOpen(false)}
                onConfirm={localDeleteArchive}
            />

            <Divider/>

        </>
    )
}

function ArchiveCard({archive, setDomain}) {

    const imageSrc = archive.screenshot_path ? `/media/${encodeURIComponent(archive.screenshot_path)}` : null;
    const singlefileUrl = archive.singlefile_path ? `/media/${encodeURIComponent(archive.singlefile_path)}` : null;

    const domain = archive.domain.domain;

    return (
        <Card>
            <a href={singlefileUrl} target='_blank' className='no-link-underscore card-link'>
                <Image src={imageSrc} wrapped style={{position: 'relative', width: '100%'}}/>
            </a>
            <Card.Content>
                <Card.Header>
                    <Container textAlign='left'>
                        <a href={singlefileUrl} target='_blank' className='no-link-underscore card-link'>
                            <p>{textEllipsis(archive.title || archive.url, 100)}</p>
                        </a>
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
                    <Link to={`/archive/${archive.id}`}>
                        <Button icon='file alternate' color='blue' content='Details'
                                labelPosition='left'/>
                    </Link>
                    <Button icon='external' href={archive.url} target='_blank' rel='noopener noreferrer'/>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

function ArchiveCards({archives, syncArchive, deleteArchive, setDomain}) {
    return (
        <CardGroupCentered>
            {archives.map((i) => {
                return <ArchiveCard
                    key={i['id']}
                    archive={i}
                    syncArchive={syncArchive}
                    deleteArchive={deleteArchive}
                    setDomain={setDomain}
                />
            })}
        </CardGroupCentered>
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
    const {archives, setPage, totalPages, searchStr, activePage, setSearchStr, domain, setDomain, search} =
        useArchives(20);

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
                <Paginator activePage={activePage} totalPages={totalPages} onPageChange={setPage}/>
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
                    id='refresh_archives'
                    onClick={this.refresh}>
                Refresh Archive Files
            </Button>
            <label htmlFor='refresh_archives'>
                Find any new archive files. Remove Archives which no longer have files.
            </label>
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
        {text: 'Archives', to: '/archive', exact: true, key: 'archive'},
        {text: 'Domains', to: '/archive/domains', key: 'domains'},
        {text: 'Manage', to: '/archive/manage', key: 'manage'},
    ];
    return <PageContainer>
        <TabLinks links={links}/>
        <Route path='/archive/:archive_id' exact component={ArchivePage}/>
        <Route path='/archive' exact component={Archives}/>
        <Route path='/archive/domains' component={Domains}/>
        <Route path='/archive/manage' component={ManageArchives}/>
    </PageContainer>
}
