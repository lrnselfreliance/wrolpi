import React, {useRef, useState} from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Nav from "react-bootstrap/Nav";
import {Link, NavLink, Route, Switch} from "react-router-dom";
import {Button, ButtonGroup, Container, Form, FormControl, ProgressBar} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";
import Card from "react-bootstrap/Card";
import Video from "./VideoPlayer";
import '../static/external/fontawesome-free/css/all.min.css';
import Alert from "react-bootstrap/Alert";
import Breadcrumb from "react-bootstrap/Breadcrumb";
import Paginator from "./Common"

const VIDEOS_API = '/api/videos';

class ChannelsNav extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            'channels': [],
        };
    }

    async getChannels() {
        let url = `${VIDEOS_API}/channels`;
        let response = await fetch(url);
        let data = await response.json();
        this.setState({channels: data['channels']})
    }

    async componentDidMount() {
        await this.getChannels();
    }

    channelRoute(channel) {
        return (
            <Nav.Item key={channel.link}>
                <NavLink className="nav-link" to={'/videos/' + channel['link']}>
                    {channel.name}
                </NavLink>
            </Nav.Item>
        )
    }

    render() {
        return (
            <Nav variant="pills" className="flex-column">
                {this.state['channels'].map(this.channelRoute)}
            </Nav>
        )
    }
}

function VideoCard({video, channel_link}) {
    let video_url = "/videos/" + channel_link + "/" + video.video_path_hash;
    let poster_url = video.poster_path ? `${VIDEOS_API}/static/poster/${video.video_path_hash}` : null;
    return (
        <Link to={video_url}>
            <Card style={{'width': '18em', 'marginBottom': '1em'}}>
                <Card.Img
                    variant="top"
                    src={poster_url}
                />
                <Card.Body>
                    <h5>{video.title || video.video_path}</h5>
                    <Card.Text>
                        {video.upload_date}
                    </Card.Text>
                </Card.Body>
            </Card>
        </Link>
    )
}

async function getChannel(link) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}`);
    let data = await response.json();
    return data['channel'];
}

async function getVideos(link, offset, limit) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}/videos?offset=${offset}&limit=${limit}`);
    let data = await response.json();
    return [data['videos'], data['total']];
}

async function getVideo(video_hash) {
    let response = await fetch(`${VIDEOS_API}/video/${video_hash}`);
    let data = await response.json();
    return data['video'];
}

class ChannelVideoPager extends Paginator {
    constructor(props) {
        super(props);
        this.state = {
            'videos': [],
            'limit': 20,
            'offset': 0,
            'total': null,
        };
        this.setVideos = this.setVideos.bind(this);
    }

    async getVideos(link, offset, limit) {
        let [videos, total] = await getVideos(link, offset, limit);
        this.setVideos(videos, total);
    }

    setVideos(videos, total) {
        this.setState({'videos': videos, 'total': total});
    }

    async componentDidMount() {
        await this.getVideos(this.props.match.params.channel_link, this.state.offset, this.state.limit);
    }

    async componentDidUpdate(prevProps, prevState) {
        if (this.props.match.params.channel_link !== prevProps.match.params.channel_link ||
                this.state.offset !== prevState.offset) {
            await this.getVideos(this.props.match.params.channel_link, this.state.offset, this.state.limit);
        }
    }

    render() {
        return (
            <>
                <VideoSearch setVideos={this.setVideos}/>
                <div className="card-deck">
                    {this.state['videos'].map((v) => (
                        <VideoCard key={v['id']} video={v} channel_link={this.props.match.params.channel_link}/>))}
                </div>
                {this.getPagination()}
            </>
        )
    }
}

function AddChannel() {
    const name = useRef();
    const url = useRef();
    const directory = useRef();
    const matchRegex = useRef();

    const [show, setShow] = useState(false);
    const handleClose = () => setShow(false);
    const handleShow = () => setShow(true);
    const [error, setError] = useState(false);
    const [message, setMessage] = useState();

    async function handleSubmit(event) {
        event.preventDefault();
        let post_url = `${VIDEOS_API}/channels`;
        let form_data = {
            name: name.current.value,
            url: url.current.value,
            directory: directory.current.value,
            match_regex: matchRegex.current.value,
        };
        let response = await fetch(post_url, {
            method: 'POST',
            body: JSON.stringify(form_data),
        });

        let data = await response.json();
        if (data['success']) {
            setMessage(data['success']);
            setError(false);
        } else if (data['error']) {
            setMessage(data['error']);
            setError(true);
        }
    }

    return (
        <>
            <Button className="btn-success" onClick={handleShow}>
                <span className="fas fa-plus"/>
            </Button>

            <Modal show={show} onHide={handleClose}>
                <Modal.Header closeButton>
                    <Modal.Title>Add New Channel</Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    <Form id="add_channel" onSubmit={handleSubmit}>
                        <Form.Group controlId="name">
                            <Form.Label column="">Name</Form.Label>
                            <Form.Control name="name" type="text" placeholder="Short Name" required ref={name}/>
                        </Form.Group>

                        <Form.Group controlId="url">
                            <Form.Label column="">URL</Form.Label>
                            <Form.Control type="url" placeholder="https://example.com/some-channel" ref={url}/>
                        </Form.Group>

                        <Form.Group controlId="directory">
                            <Form.Label column="">Directory</Form.Label>
                            <Form.Control name="directory" type="directory" placeholder="prepping/something" required
                                          ref={directory}/>
                            <Form.Text className="text-muted">
                                This will be appended to the root video directory in the config.
                            </Form.Text>
                        </Form.Group>

                        <Form.Group controlId="match_regex">
                            <Form.Label column="">Title Match Regex</Form.Label>
                            <Form.Control name="match_regex" type="text" placeholder=".*(prepper|prepping).*"
                                          ref={matchRegex}/>
                            <Form.Text className="text-muted">
                                The title of the video will be compared to this Regular Expression. If you don't input
                                this,
                                all videos will be downloaded.
                            </Form.Text>
                        </Form.Group>
                    </Form>
                </Modal.Body>
                <Modal.Footer>
                    <Alert variant={(error ? 'danger' : 'success')} hidden={(!message)}>
                        {message}
                    </Alert>
                    <ButtonGroup>
                        <Button variant="secondary" onClick={handleClose}>
                            Close
                        </Button>
                        <Button type="submit" variant="primary" form="add_channel">
                            Add
                        </Button>
                    </ButtonGroup>
                </Modal.Footer>
            </Modal>
        </>
    )
}


function handleStream(stream_url, setAlertVariant, setAlertMessage, setProgress) {
    function setMessage(message) {
        setAlertVariant('success');
        setAlertMessage(message);
    }

    function setError(message) {
        setAlertVariant('danger');
        setAlertMessage(message);
    }

    function handleMessage(message) {
        let data = JSON.parse(message.data);
        if (data['error']) {
            setError(data['error']);
        } else if (data['message']) {
            setAlertVariant('success');
            setMessage(data['message']);
        }
        if (data['progresses']) {
            setProgress(data['progresses']);
        }
    }

    let ws = new WebSocket(stream_url);
    window.onbeforeunload = (e) => (ws.close);
    ws.onmessage = handleMessage;

    return ws;
}

function StripedProgressBar(props) {
    return (
        <ProgressBar striped={true} style={{'marginTop': '0.5em'}} {...props}/>
    )
}

function AlertProgress(props) {

    return (
        <Row style={{'marginBottom': '1em'}}>
            <Col className="col-5">
                <Button onClick={props.onClick} disabled={props.buttonDisabled}>
                    {props.buttonValue}
                </Button>
            </Col>
            <Col className="col-7">
                {props.description}
                <Alert variant={props.alertVariant} show={props.alertMessage !== ''}
                       style={{'marginTop': '1em'}}>
                    {props.alertMessage}
                </Alert>
                <StripedProgressBar hidden={props.progresses[0]['now'] == null} now={props.progresses[0]['now']}/>
                <StripedProgressBar hidden={props.progresses[1]['now'] == null} now={props.progresses[1]['now']}/>
                <StripedProgressBar hidden={props.progresses[2]['now'] == null} now={props.progresses[2]['now']}/>
            </Col>
        </Row>
    )
}

class ButtonProgressGroup extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            alertVariant: 'success',
            alertMessage: '',
            buttonDisabled: false,
            progresses: [{'now': null}, {'now': null}, {'now': null}],
            websocket: null,
        };

        this.setAlertVariant = this.setAlertVariant.bind(this);
        this.setAlertMessage = this.setAlertMessage.bind(this);
        this.setProgress = this.setProgress.bind(this);
    }

    componentWillUnmount() {
        if (this.state.websocket) {
            this.state.websocket.close();
        }
    }

    setAlertVariant(variant) {
        this.setState({'alertVariant': variant});
    }

    setError(message) {
        this.setState({alertMessage: message, alertVariant: 'danger'});
    }

    setAlertMessage(message) {
        this.setState({'alertMessage': message}, this.logState);
    }

    reset() {
        this.setState({alertMessage: '', alertVariant: 'success', buttonDisabled: false});
    }

    disableButton() {
        this.setState({buttonDisabled: true});
    }

    enableButton() {
        this.setState({buttonDisabled: false});
    }

    setProgress(progresses) {
        let new_progresses = [{'now': null}, {'now': null}, {'now': null}];
        for (let i = 0; i < progresses.length; i++) {
            new_progresses[i]['now'] = progresses[i]['now'];
        }
        this.setState({'progresses': new_progresses});
    }

    async fetchAndHandle(url) {
        this.reset();
        this.disableButton();
        try {
            let response = await fetch(url, {'method': 'POST'});
            let data = await response.json();
            if (data['stream_url']) {
                let stream_url = data['stream_url'];
                let ws = handleStream(stream_url, this.setAlertVariant, this.setAlertMessage, this.setProgress);
                this.setState({'websocket': ws});
            }
            if (data['error']) {
                this.setError('Server responded with an error');
            }

        } catch (e) {
            this.setError('Server did not respond as expected');
        }
        this.enableButton();
    }

    render() {
        return (
            <AlertProgress
                onClick={this.props.onClick}
                buttonDisabled={this.props.buttonDisabled}
                buttonValue={this.props.buttonValue}
                description={this.props.description}
                alertMessage={this.props.alertMessage}
                alertVariant={this.props.alertVariant}
                progresses={this.props.progresses}
            />
        )
    }
}

class RefreshContent extends ButtonProgressGroup {

    constructor(props) {
        super(props);
        this.onClick = this.onClick.bind(this);
    }

    async onClick() {
        let url = `${VIDEOS_API}/settings:refresh`;
        await this.fetchAndHandle(url);
    }

    render() {
        return (
            <ButtonProgressGroup
                onClick={this.onClick}
                buttonDisabled={this.state.buttonDisabled}
                buttonValue="Refresh Content"
                description="Find and process all videos stored on this WROLPi."
                alertMessage={this.state.alertMessage}
                alertVariant={this.state.alertVariant}
                progresses={this.state.progresses}
            />
        )
    }
}

class DownloadVideos extends ButtonProgressGroup {

    constructor(props) {
        super(props);
        this.onClick = this.onClick.bind(this);
    }

    async onClick() {
        let url = `${VIDEOS_API}/settings:download`;
        await this.fetchAndHandle(url);
    }

    render() {
        return (
            <ButtonProgressGroup
                onClick={this.onClick}
                buttonValue="Download Videos"
                description="Update channel catalogs, then download any missing videos."
                alertMessage={this.state.alertMessage}
                alertVariant={this.state.alertVariant}
                progresses={this.state.progresses}
            />
        )
    }
}

class ManageContent extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            show: false,
        };

        this.handleClose = this.handleClose.bind(this);
        this.handleShow = this.handleShow.bind(this);
    }

    handleClose() {
        this.setState({'show': false});
    }

    handleShow() {
        this.setState({'show': true});
    }

    render() {
        return (
            <>
                <Button
                    id="manage_content"
                    className="btn-secondary"
                    onClick={this.handleShow}
                    style={{'marginBottom': '0.5em'}}
                >
                    <span className="fas fa-cog"/>
                </Button>

                <Modal show={this.state.show} onHide={this.handleClose}>
                    <Modal.Header>
                        <Modal.Title>Manage Video Content</Modal.Title>
                    </Modal.Header>
                    <Modal.Body>
                        <RefreshContent/>
                        <DownloadVideos/>
                    </Modal.Body>
                    <Modal.Footer>
                        <Button variant="secondary" onClick={this.handleClose}>
                            Close
                        </Button>
                    </Modal.Footer>
                </Modal>
            </>
        )
    }
}

class VideoSearch extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            searchStr: '',
        };
        this.searchApi = `${VIDEOS_API}/search`;
    }

    async handleSubmitSearch(e) {
        e.preventDefault();
        // TODO hardcoded to first input, surely there is a better way?
        let value = e.target[0].value;
        await this.handleSearch(e, value)
    }

    async handleChangeSearch(e) {
        let value = e.target.value;
        await this.handleSearch(e, value)
    }

    async handleSearch(e, value) {
        let form_data = {
            'search_str': value,
            'offset': 0,
        };
        if (value.length > 2) {
            let response = await fetch(this.searchApi, {
                method: 'POST',
                body: JSON.stringify(form_data),
            });
            let data = await response.json();
            if (data['videos']) {
                await this.handleResults(data);
            }
        }
    }

    async handleResults(results) {
        let videos = results['videos'];
        let total = results['totals']['videos'];
        this.props.setVideos(videos, total);
    }

    render() {
        return (
            <Form inline style={{'marginBottom': '1em'}}
                  onSubmit={(e) => this.handleSubmitSearch(e)}>
                <FormControl
                    type="text"
                    className="mr-sm-2"
                    placeholder="Search"
                    onChange={(e) => this.handleChangeSearch(e)}
                />
                <Button type="submit" variant="outline-info">
                    <span className="fas fa-search"/>
                </Button>
            </Form>
        )
    }
}

class VideoBreadcrumb extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            'video': null,
            'channel': null,
        }
    }

    async getChannelAndVideo() {
        let channel_link = this.props.match.params.channel_link;
        this.setState({'channel': await getChannel(channel_link)});
        let video_hash = this.props.match.params.video_hash;
        this.setState({'video': await getVideo(video_hash)});
    }

    async componentDidMount() {
        await this.getChannelAndVideo();
    }

    async componentDidUpdate(prevProps, prevState) {
        if (this.props.match.params.video_hash !== prevProps.match.params.video_hash ||
            this.props.match.params.channel_link !== prevProps.match.params.channel_link) {
            await this.getChannelAndVideo();
        }
    }

    getChannelBreadcrumb() {
        if (this.state.channel) {
            return (
                <li className="breadcrumb-item">
                    <Link to={'/videos/' + this.props.match.params.channel_link}>
                        {this.state.channel['name']}
                    </Link>
                </li>
            )
        }
    }

    getBreadcrumb() {
        // If video: Channel Name / Video Title
        // else if channel: Channel Name
        if (this.state.video) {
            return (
                <>
                    {this.getChannelBreadcrumb()}
                    <li className="breadcrumb-item">
                        <Link
                            to={'/videos/' +
                            this.props.match.params.channel_link + '/' +
                            this.props.match.params.video_hash}>
                            {this.state.video['title'] || this.state.video['video_path']}
                        </Link>
                    </li>
                </>
            )
        } else if (this.state.channel) {
            return this.getChannelBreadcrumb()
        }
        return (<></>)
    }

    render() {
        return (
            this.getBreadcrumb()
        )
    }
}

class Videos extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            'channel': null,
            'video': null,
        }
    }

    breadcrumbs() {
        return (
            <Breadcrumb>
                {/* use li so we can link with a */}
                <li className="breadcrumb-item">
                    <Link to='/videos'>Videos</Link>
                </li>
                <Route path='/videos/:channel_link' exact={true} component={VideoBreadcrumb}/>
                <Route path='/videos/:channel_link/:video_hash' exact={true} component={VideoBreadcrumb}/>
            </Breadcrumb>
        )
    }

    render() {
        return (
            <Row style={{'marginTop': '1.5em'}}>
                <Col className="col-3">
                    <Row style={{'marginBottom': '1.5em'}}>
                        <Col className="col-9">
                            <h4>
                                Channels
                            </h4>
                        </Col>
                        <Col className="col-3">
                            <div className="ml-auto">
                                <ManageContent/>
                                <AddChannel/>
                            </div>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <ChannelsNav/>
                        </Col>
                    </Row>
                </Col>
                <Col className="col-9">
                    <Container>
                        {this.breadcrumbs()}
                        <Switch>
                            <Route path="/videos/:channel_link/:video_hash" component={Video}/>
                            <Route
                                path="/videos/:channel_link"
                                component={ChannelVideoPager}
                            />
                        </Switch>
                    </Container>
                </Col>
            </Row>
        )
    }
}

export default Videos;