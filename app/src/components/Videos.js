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

const VIDEOS_API = 'http://127.0.0.1:8080/api/videos';

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

function VideoCard({video, channel}) {
    let video_url = "/videos/" + channel.link + "/" + video.video_path_hash;
    let poster_url = video.poster_path ? `${VIDEOS_API}/poster/${video.video_path_hash}` : null;
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
    let response = await fetch(`${VIDEOS_API}/channel/${link}`);
    let data = await response.json();
    return data['channel'];
}

async function getVideos(link) {
    let response = await fetch(`${VIDEOS_API}/channel/${link}/videos`);
    let data = await response.json();
    return data['videos'];
}

class ChannelVideoPager extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            'channel': [],
            'videos': [],
        };
    }

    async getChannel(link) {
        this.setState({'channel': await getChannel(link)})
    }

    async getVideos(link) {
        this.setState({'videos': await getVideos(link)})
    }

    async componentDidMount() {
        await this.getChannel(this.props.match.params.channel_link);
        await this.getVideos(this.props.match.params.channel_link);
    }

    async componentDidUpdate(prevProps, prevState) {
        if (this.props.match.params.channel_link !== prevProps.match.params.channel_link) {
            await this.getChannel(this.props.match.params.channel_link);
            await this.getVideos(this.props.match.params.channel_link);
        }
    }

    render() {
        return (
            <div className="card-deck">
                {this.state['videos'].map((v) => (<VideoCard key={v['id']} video={v} channel={this.state.channel}/>))}
            </div>
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
        let post_url = `${VIDEOS_API}/channel`;
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

class ManageContent extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            show: false,
            refreshMessage: '',
            refreshError: false,
            refreshProgress1: null,
            refreshProgress2: null,
            refreshDisabled: false,
            downloadMessage: '',
            downloadError: false,
            downloadProgress: null,
            downloadDisabled: false,
            websockets: [],
        };

        this.handleClose = this.handleClose.bind(this);
        this.handleShow = this.handleShow.bind(this);
        this.refreshContent = this.refreshContent.bind(this);
        this.downloadVideos = this.downloadVideos.bind(this);
    }

    componentWillUnmount() {
        let i = 0;
        while (this.state.websockets[i]) {
            let ws = this.state.websockets[i];
            ws.close();
            i++;
        }
    }

    handleClose() {
        this.setState({'show': false});
    }

    handleShow() {
        this.setState({'show': true});
    }

    handleStreamMessage(message, setMessage) {
        if (message !== 'stream-complete') {
            setMessage(message);
        }
    }

    handleStream(stream_url, setMessage, setProgress, setError, setProgress1, setProgress2) {
        let ws = new WebSocket(stream_url);
        window.onbeforeunload = (e) => (ws.close);
        ws.onmessage = (message) => {
            let data = JSON.parse(message.data);
            if (data['message']) {
                this.handleStreamMessage(data['message'], setMessage);
            }
            if (Number.isInteger(data['progress'])) {
                setProgress(data['progress']);
            }
            if (Number.isInteger(data['progress1'])) {
                setProgress1(data['progress1']);
            }
            if (Number.isInteger(data['progress2'])) {
                setProgress2(data['progress2']);
            }
            if (data['error']) {
                setError(true);
                setMessage(data['error']);
            }
        };
        this.setState({'websockets': [ws].concat(this.state.websockets)});
    }

    async refreshContent() {
        this.setState({'refreshDisabled': true});
        let url = `${VIDEOS_API}/settings:refresh`;
        let response = await fetch(url, {'method': 'POST'});
        try {
            let data = await response.json();
            if (data.hasOwnProperty('success')) {
                let stream_url = data['stream_url'];
                this.setState({'refreshError': false});
                await this.handleStream(
                    stream_url,
                    (v) => (this.setState({'refreshMessage': v})),
                    null,
                    (v) => (this.setState({'refreshError': v})),
                    (v) => (this.setState({'refreshProgress1': v})),
                    (v) => (this.setState({'refreshProgress2': v})),
                );
            } else {
                this.setState({
                    'refreshMessage': 'Failed to refresh content, see server logs.',
                    'refreshError': true
                })
            }
        } catch (e) {
            this.setState({
                'refreshMessage': 'Server did not respond as expected, see server logs.',
                'refreshError': true,
            });
            throw e;
        }
        this.setState({'refreshDisabled': false});
    }

    async downloadVideos() {
        this.setState({'downloadDisabled': true});
        let url = `${VIDEOS_API}/settings:download`;
        let response = await fetch(url, {'method': 'POST'});
        try {
            let data = await response.json();
            if (data.hasOwnProperty('success')) {
                let stream_url = data['stream_url'];
                this.setState({'downloadError': false});
                await this.handleStream(
                    stream_url,
                    (v) => (this.setState({'downloadMessage': v})),
                    (v) => (this.setState({'downloadProgress': v})),
                    (v) => (this.setState({'downloadError': v})),
                );
            } else {
                this.setState({
                    'downloadMessage': 'Failed to download videos, see server logs.',
                    'downloadError': true
                })
            }
        } catch (e) {
            this.setState({
                'downloadMessage': 'Server did not respond as expected, see server logs.',
                'downloadError': true,
            });
            throw e;
        }
        this.setState({'downloadDisabled': false});
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
                        <Row style={{'marginBottom': '1em'}}>
                            <Col className="col-5">
                                <Button onClick={this.refreshContent} disabled={this.state.refreshDisabled}>
                                    Refresh Content
                                </Button>
                            </Col>
                            <Col className="col-7">
                                <Row websocket={this.ws}>
                                    <Col>
                                        Find and process all videos stored on this WROLPi.
                                    </Col>
                                </Row>
                                <Alert
                                    variant={(this.state.refreshError ? 'danger' : 'success')}
                                    hidden={(!this.state.refreshMessage)}
                                >
                                    {this.state.refreshMessage}
                                </Alert>
                                <ProgressBar striped variant={(this.state.refreshError ? 'danger' : 'primary')}
                                             now={this.state.refreshProgress1}
                                             hidden={(this.state.refreshProgress1 == null)}
                                />
                                <ProgressBar striped variant={(this.state.refreshError ? 'danger' : 'info')}
                                             now={this.state.refreshProgress2}
                                             hidden={(this.state.refreshProgress2 == null)}
                                />
                            </Col>
                        </Row>
                        <Row style={{'marginBottom': '1em'}}>
                            <Col className="col-5">
                                <Button onClick={this.downloadVideos}>Download Videos</Button>
                            </Col>
                            <Col className="col-7">
                                <Row websocket={this.ws}>
                                    <Col>
                                        Update channel catalogs and download all videos not yet downloaded.
                                    </Col>
                                </Row>
                                <Alert
                                    variant={(this.state.downloadError ? 'danger' : 'success')}
                                    hidden={(!this.state.downloadMessage)}
                                >
                                    {this.state.downloadMessage}
                                </Alert>
                                <ProgressBar striped variant={(this.state.downloadError ? 'danger' : 'info')}
                                             now={this.state.downloadProgress}
                                             hidden={(this.state.downloadProgress == null)}
                                />
                            </Col>
                        </Row>
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

class VideoAPI {
    constructor() {
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

    async handleOnChange(e, searchApi) {
        let value = e.target.value;
        let form_data = {
            'search_str': e.target.value,
            'offset': 0,
        };
        if (value.length > 2) {
            let response = await fetch(searchApi, {
                method: 'POST',
                body: JSON.stringify(form_data),
            });
            let data = await response.json();
            console.log(data);
        }
    }

    render() {
        return (
            <Form inline style={{'margin-bottom': '1em'}}>
                <FormControl
                    type="text"
                    className="mr-sm-2"
                    placeholder="Search"
                    onChange={(e) => this.handleOnChange(e, this.searchApi)}
                />
                <Button type="submit" variant="outline-info">
                    <span className="fas fa-search"/>
                </Button>
            </Form>
        )
    }
}

function Videos() {
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
                    <VideoSearch/>
                    <Switch>
                        <Route path="/videos/:channel_link/:video_id" component={Video}/>
                        <Route path="/videos/:channel_link" component={ChannelVideoPager}/>
                    </Switch>
                </Container>
            </Col>
        </Row>
    )
}

export default Videos;