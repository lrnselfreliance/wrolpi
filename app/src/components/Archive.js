import React from "react";
import {Card, Confirm, Container, Form, Header, Icon, Image, Input, Placeholder, Tab} from "semantic-ui-react";
import Paginator, {APIForm, uploadDate} from "./Common";
import {deleteArchive, postArchive, refreshArchives} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {Link, NavLink} from "react-router-dom";
import {ArchivePlaceholder} from "./Placeholder";
import Table from "semantic-ui-react/dist/commonjs/collections/Table";
import {useArchives} from "../hooks/useArchives";
import {useDomains} from "../hooks/useDomains";


function FailedArchiveCard({archive, syncURL, deleteURL}) {

    let url = archive.url;

    let syncIcon = (
        <Button onClick={() => syncURL(url.url)}>
            <Icon name='sync' size='big'/>
        </Button>
    );

    let trashIcon = (
        <Button onClick={() => deleteURL(archive.id)}>
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

class ArchiveCard extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            deleteOpen: false,
            syncOpen: false,
        }
    }

    syncURL = async () => {
        await postArchive(this.props.archive.url.url);
        await this.props.fetchURLs();
    }

    deleteURL = async () => {
        await deleteArchive(this.props.archive.id);
        await this.props.fetchURLs();
    }

    render() {
        let archive = this.props.archive;
        let url = archive.url;

        let imageSrc = archive.screenshot_path ? `/media/${archive.screenshot_path}` : null;
        let singlefileUrl = archive.singlefile_path ? `/media/${archive.singlefile_path}` : null;

        if (archive.status === 'failed') {
            return <FailedArchiveCard archive={archive} syncURL={this.syncURL} deleteURL={this.deleteURL}/>;
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
                <Button icon onClick={() => this.setState({syncOpen: true})}>
                    <Icon name='sync' size='large'/>
                </Button>
                <Confirm
                    open={this.state.syncOpen}
                    content='Download the latest version of this URL?'
                    confirmButton='Confirm'
                    onCancel={() => this.setState({syncOpen: false})}
                    onConfirm={this.syncURL}
                />
            </>
        );

        let deleteIcon = (
                <>
                    <Button icon onClick={() => this.setState({deleteOpen: true})}>
                        <Icon name='trash' size='large'/>
                    </Button>
                    <Confirm
                        open={this.state.deleteOpen}
                        content='Are you sure you want to delete this URL?  All files will be deleted.'
                        confirmButton='Delete'
                        onCancel={() => this.setState({deleteOpen: false})}
                        onConfirm={this.deleteURL}
                    />
                </>
            )
        ;

        let externalIcon = (
            <Button icon href={archive.url} target='_blank' rel='noopener noreferrer'>
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

}

function ArchiveCards({archives, fetchURLs}) {
    return (
        <Card.Group>
            {archives.map((i) => {
                return <ArchiveCard key={i['id']} archive={i}/>
            })}
        </Card.Group>
    )
}

function ArchiveSearchForm({searchStr, handleInputChange}) {
    return (
        <Form style={{marginBottom: '1em'}}>
            <Input
                icon='search'
                placeholder='Search...'
                name='searchStr'
                value={searchStr}
                onChange={handleInputChange}
            />
        </Form>
    )
}

function Archives(props) {
    const {archivesData, setPage, totalPages, searchStr, activePage, setSearchStr} = useArchives();
    const {archives} = archivesData;

    if (archives === null) {
        return (<>
            <Header as='h1'>Latest Archives</Header>
            <ArchivePlaceholder/>
        </>)
    }

    let pagination = null;
    if (totalPages) {
        pagination = (
            <div style={{marginTop: '3em', textAlign: 'center'}}>
                <Paginator
                    activePage={activePage}
                    changePage={setPage}
                    totalPages={totalPages}
                />
            </div>
        )
    }

    const handleInputChange = (e) => {
        e.preventDefault();
        setSearchStr(e.target.value);
    }

    return (
        <>
            <ArchiveSearchForm handleInputChange={handleInputChange} searchStr={searchStr}/>
            <ArchiveCards archives={archives}/>
            {pagination}
        </>
    )
}

class ArchiveAddForm extends APIForm {
    constructor(props) {
        super(props);
        this.archivesRef = props.archivesRef;

        this.state = {
            ...this.state,
            inputs: {
                url: '',
            },
            errors: {},
        };
        this.fetchURLs = this.fetchURLs.bind(this);
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        this.setLoading();
        try {
            let response = await postArchive(this.state.inputs.url);
            if (response.status === 204) {
                this.setState({inputs: {url: ''}, success: true}, this.fetchURLs);
            } else {
                this.setState({loading: false, success: undefined, error: true});
            }
        } finally {
            this.clearLoading();
        }
    }

    fetchURLs = async (e) => {
        await this.archivesRef.current.fetchURLs();
    }

    render() {
        return (
            <>
                <Form onSubmit={this.handleSubmit}>
                    <label htmlFor='url'>Archive URL</label>
                    <Form.Group>
                        <Form.Input
                            name='url'
                            placeholder='https://wrolpi.org'
                            value={this.state.inputs.url}
                            disabled={this.state.disabled}
                            error={this.state.error}
                            onChange={this.handleInputChange}
                            success={this.state.success}
                        />
                        <Form.Button primary disabled={this.state.disabled}>Archive</Form.Button>
                    </Form.Group>
                </Form>
            </>
        )
    }
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
                <ArchiveAddForm archivesRef={this.archivesRef}/>
                <Tab panes={this.archivePanes} activeIndex={this.state.activeIndex} renderActiveOnly={true}/>
            </Container>
        )
    }
}
