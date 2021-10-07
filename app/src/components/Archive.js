import React from "react";
import {Card, Confirm, Container, Form, Header, Icon, Image} from "semantic-ui-react";
import {Route} from "react-router-dom";
import {APIForm, uploadDate} from "./Common";
import {deleteArchive, postArchive, searchURLs} from "../api";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";


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
        this.state = {
            offset: 0,
            activePage: 1,
            limit: 20,
            urls: null,
            totalPages: null,
        };
        this.fetchURLs = this.fetchURLs.bind(this);
    }

    async componentDidMount() {
        await this.fetchURLs();
    }

    async fetchURLs() {
        let offset = this.state.limit * this.state.activePage - this.state.limit;
        let [urls, total] = await searchURLs(offset, this.state.limit);
        this.setState({urls, totalPages: total / this.state.limit});
    }

    render() {
        let {urls} = this.state;
        if (urls !== null) {
            return (
                <>
                    <Header as='h1'>Latest Archives</Header>
                    <URLCards urls={urls} fetchURLs={this.fetchURLs}/>
                </>
            )
        }
        return <></>;
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

class Archive extends React.Component {
    render() {
        return (
            <Container fluid style={{marginTop: '2em'}}>
                <ArchiveAddForm/>
                <Archives/>
            </Container>
        )
    }
}

export class ArchiveRoute extends React.Component {
    render() {
        return (
            <>
                <Container style={{marginTop: '2em', marginBottom: '2em'}}>
                    <Route path='/archive' exact component={Archive}/>
                </Container>
            </>
        )
    }
}
