import React from "react";
import {Card, Confirm, Container, Form, Header, Icon, Image, Tab, Table} from "semantic-ui-react";
import Paginator, {APIForm, changePageHistory, uploadDate} from "./Common";
import {deleteArchive, fetchDomains, postArchive, refreshArchives, searchURLs} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";
import {NavLink, Route} from "react-router-dom";
import * as QueryString from "query-string";
import {ArchivePlaceholder} from "./Placeholder";


function FailedUrlCard({url, syncURL, deleteURL}) {

    let syncIcon = (
        <a onClick={() => syncURL(url.url)}>
            <Icon name='sync' size='big'/>
        </a>
    );

    let trashIcon = (
        <a onClick={() => deleteURL(url.id)}>
            <Icon name='trash' size='big'/>
        </a>
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

class URLCard extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            latest: props.url ? props.url.latest : null,
            deleteOpen: false,
            syncOpen: false,
        }
    }

    syncURL = async () => {
        await postArchive(this.props.url.url);
        await this.props.fetchURLs();
    }

    deleteURL = async () => {
        await deleteArchive(this.props.url.id);
        await this.props.fetchURLs();
    }

    render() {
        let url = this.props.url;
        let latest = url && url.latest ? url.latest : null;

        let imageSrc = latest.screenshot_path ? `/media/${latest.screenshot_path}` : null;
        let singlefileUrl = latest.singlefile_path ? `/media/${latest.singlefile_path}` : null;

        if (latest == null || latest.status === 'failed') {
            return <FailedUrlCard url={url} syncURL={this.syncURL} deleteURL={this.deleteURL}/>;
        }

        let readabilityUrl = latest.readability_path ? `/media/${latest.readability_path}` : null;
        let readabilityIcon = <Button icon><Icon name='book' size='large' disabled/></Button>;
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
                                <p>{url.latest.title || url.url}</p>
                            </Container>
                        </Card.Header>
                    </a>
                    <Card.Meta>
                        {uploadDate(latest.archive_datetime)}
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

class URLCards extends React.Component {
    render() {
        return (
            <Card.Group>
                {this.props.urls.map((i) => {
                    return <URLCard key={i['id']} url={i} fetchURLs={this.props.fetchURLs}/>
                })}
            </Card.Group>
        )
    }
}

class Archives extends React.Component {

    constructor(props) {
        super(props);
        const query = QueryString.parse(this.props.location.search);
        let activePage = query.page ? parseInt(query.page) : 1;

        this.state = {
            activePage: activePage,
            limit: 2,
            urls: null,
            totalPages: null,
        };
        this.fetchURLs = this.fetchURLs.bind(this);
        this.changePage = this.changePage.bind(this);
    }

    async componentDidMount() {
        await this.fetchURLs();
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        let pageChanged = (
            prevState.activePage !== this.state.activePage
        );

        if (pageChanged) {
            let {history, location} = this.props;
            let {activePage, queryStr, searchOrder} = this.state;
            changePageHistory(history, location, activePage, queryStr, searchOrder);
        }
    }

    async fetchURLs() {
        this.setState({urls: null});
        let offset = this.state.limit * this.state.activePage - this.state.limit;
        let [urls, total] = await searchURLs(offset, this.state.limit);
        this.setState({urls, totalPages: total / this.state.limit});
    }

    changePage(activePage) {
        this.setState({activePage});
    }

    render() {
        let {urls, activePage, totalPages} = this.state;

        let pagination = null;
        if (totalPages) {
            pagination = (
                <div style={{marginTop: '3em', textAlign: 'center'}}>
                    <Paginator
                        activePage={activePage}
                        changePage={this.changePage}
                        totalPages={totalPages}
                    />
                </div>
            )
        }

        if (urls !== null) {
            return (
                <>
                    <Header as='h1'>Latest Archives</Header>
                    <URLCards urls={urls} fetchURLs={this.fetchURLs}/>
                    {pagination}
                </>
            )
        }

        return (<>
            <Header as='h1'>Latest Archives</Header>
            <ArchivePlaceholder/>
        </>);
    }
}

class Domains extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            domains: null,
        };
        this.fetchDomains = this.fetchDomains.bind(this);
    }

    async componentDidMount() {
        await this.fetchDomains();
    }

    async fetchDomains() {
        this.setState({domains: null});
        let [domains, total] = await fetchDomains();
        this.setState({domains});
    }

    render() {
        if (this.state.domains) {
            return (
                <>
                    <Header as='h1'>Domains</Header>
                    <Table celled>
                        <Table.Header>
                            <Table.HeaderCell>Domain</Table.HeaderCell>
                            <Table.HeaderCell>URLs</Table.HeaderCell>
                        </Table.Header>

                        <Table.Body>
                            {this.state.domains.map((i) =>
                                <Table.Row>
                                    <Table.Cell>{i['domain']}</Table.Cell>
                                    <Table.Cell>{i['url_count']}</Table.Cell>
                                </Table.Row>
                            )}
                        </Table.Body>
                    </Table>
                </>
            )
        }
        return (<>
        </>)
    }
}

class ArchiveAddForm extends APIForm {
    constructor(props) {
        super(props);
        this.state = {
            ...this.state,
            inputs: {
                url: '',
            },
            errors: {},
        };
    }

    handleSubmit = async (e) => {
        e.preventDefault();
        await postArchive(this.state.inputs.url);
        this.setState({inputs: {url: ''}});
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
                            onChange={this.handleInputChange}
                            value={this.state.inputs.url}
                        />
                        <Form.Button primary>Archive</Form.Button>
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

export class ArchiveRoute extends React.Component {

    render() {
        const panes = [
            {
                menuItem: {
                    as: NavLink,
                    content: 'Archives',
                    id: 'archive',
                    to: '/archive',
                    exact: true,
                    key: 'home',
                },
                render: () => (
                    <Route path='/archive' exact
                           component={(i) => <Tab.Pane>
                               <Archives history={i.history} location={i.location}/>
                           </Tab.Pane>}
                    />)
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
                render: () => (
                    <Route path='/archive/domains' exact
                           component={(i) => <Tab.Pane>
                               <Domains history={i.history} location={i.location}/>
                           </Tab.Pane>}
                    />)
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
                render: () => (
                    <Route path='/archive/manage' exact
                           component={(i) => <Tab.Pane><ManageArchives history={i.history}/></Tab.Pane>}/>
                )
            },
        ];

        return (
            <>
                <Container style={{marginTop: '2em', marginBottom: '2em'}}>
                    <ArchiveAddForm/>
                    <Tab panes={panes}/>
                </Container>
            </>
        )
    }
}
