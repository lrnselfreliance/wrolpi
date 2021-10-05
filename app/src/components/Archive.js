import React from "react";
import {Card, Container, Form, Header, Icon, Image} from "semantic-ui-react";
import {Route} from "react-router-dom";
import {APIForm, uploadDate} from "./Common";
import {deleteArchive, postArchive, searchURLs} from "../api";


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

function URLCard({url, syncURL, deleteURL}) {
    let latest = url.latest;

    if (latest == null || latest.status === 'failed') {
        return <FailedUrlCard url={url} syncURL={syncURL} deleteURL={deleteURL}/>;
    }

    let imageSrc = latest.screenshot_path ? `/media/${latest.screenshot_path}` : null;
    let screenshotUrl = latest.screenshot_path ? `/media/${latest.screenshot_path}` : null;
    let screenshotIcon = <Icon name='camera' size='big' disabled/>;
    if (screenshotUrl) {
        screenshotIcon = (
            <a href={screenshotUrl} target='_blank' rel='noopener noreferrer'>
                <Icon name='camera' size='big'/>
            </a>);
    }

    let singlefileUrl = latest.singlefile_path ? `/media/${latest.singlefile_path}` : null;
    let singlefileIcon = <Icon name='file code' size='big' disabled/>;
    if (singlefileUrl) {
        singlefileIcon = (
            <a href={singlefileUrl} target='_blank' rel='noopener noreferrer'>
                <Icon name='file code' size='big'/>
            </a>);
    }

    let readabilityUrl = latest.readability_path ? `/media/${latest.readability_path}` : null;
    let readabilityIcon = <Icon name='book' size='big' disabled/>;
    if (readabilityUrl) {
        readabilityIcon = (
            <a href={readabilityUrl} target='_blank' rel='noopener noreferrer'>
                <Icon name='book' size='big'/>
            </a>);
    }

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
                        {singlefileIcon}
                        {readabilityIcon}
                        {screenshotIcon}
                        {syncIcon}
                        {trashIcon}
                        {externalIcon}
                    </Container>
                </Card.Description>
            </Card.Content>
        </Card>
    )
}

class URLCards extends React.Component {
    render() {
        return (
            <Card.Group>
                {this.props.urls.map((i) => {
                    return <URLCard key={i['id']} url={i}
                                    syncURL={this.props.syncURL} deleteURL={this.props.deleteURL}/>
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
        this.syncURL = this.syncURL.bind(this);
        this.fetchURLs = this.fetchURLs.bind(this);
        this.deleteURL = this.deleteURL.bind(this);
    }

    async componentDidMount() {
        await this.fetchURLs();
    }

    async fetchURLs() {
        let offset = this.state.limit * this.state.activePage - this.state.limit;
        let [urls, total] = await searchURLs(offset, this.state.limit);
        this.setState({urls, totalPages: total / this.state.limit});
    }

    async syncURL(url) {
        await postArchive(url);
        await this.fetchURLs();
    }

    async deleteURL(url_id) {
        await deleteArchive(url_id);
        await this.fetchURLs();
    }

    render() {
        let {urls} = this.state;
        if (urls !== null) {
            return (
                <>
                    <Header as='h1'>Latest Archives</Header>
                    <URLCards urls={urls} syncURL={this.syncURL} deleteURL={this.deleteURL}/>
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
