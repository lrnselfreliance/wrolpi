import React, {createRef, useRef, useState} from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Nav from "react-bootstrap/Nav";
import {Link, NavLink, Route} from "react-router-dom";
import {Button, ButtonGroup, Form, FormControl, ProgressBar} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";
import Card from "react-bootstrap/Card";
import '../static/external/fontawesome-free/css/all.min.css';
import Alert from "react-bootstrap/Alert";
import Breadcrumb from "react-bootstrap/Breadcrumb";
import Paginator, {VIDEOS_API} from "./Common"
import Container from "react-bootstrap/Container";
import Video from "./VideoPlayer";

async function updateChannel(channel, name_ref, url_ref, directory_ref, matchRegex_ref) {
    let name = name_ref.current.value;
    let url = url_ref.current.value;
    let directory = directory_ref.current.value;
    let matchRegex = matchRegex_ref.current.value;
    let body = {name, url, directory, match_regex: matchRegex};

    let response = await fetch(`${VIDEOS_API}/channels/${channel['link']}`,
        {method: 'PUT', body: JSON.stringify(body)});

    if (response.status !== 204) {
        throw Error('Failed to update channel.  See browser logs.');
    }
}

async function deleteChannel(channel) {
    let response = await fetch(`${VIDEOS_API}/channels/${channel['link']}`, {method: 'DELETE'});

    if (response.status !== 204) {
        throw Error('Failed to delete channel.  See browser logs.');
    }
}

async function getChannels() {
    let url = `${VIDEOS_API}/channels`;
    let response = await fetch(url);
    let data = await response.json();
    return data['channels'];
}

async function getChannel(link) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}`);
    let data = await response.json();
    return data['channel'];
}

async function getChannelVideos(link, offset, limit) {
    let response = await fetch(`${VIDEOS_API}/channels/${link}/videos?offset=${offset}&limit=${limit}`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['total']];
    } else {
        throw Error('Unable to fetch videos for channel');
    }
}

async function getVideo(video_hash) {
    let response = await fetch(`${VIDEOS_API}/video/${video_hash}`);
    let data = await response.json();
    return data['video'];
}

class ChannelsNav extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            show: false,
            message: null,
            error: false,
        };

        this.name = React.createRef();
        this.url = React.createRef();
        this.directory = React.createRef();
        this.matchRegex = React.createRef();

        this.channelNavLink = this.channelNavLink.bind(this);
        this.setShow = this.setShow.bind(this);
        this.setError = this.setError.bind(this);
        this.setMessage = this.setMessage.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);
        this.handleDelete = this.handleDelete.bind(this);
    }

    async handleSubmit(e) {
        e.preventDefault();
        try {
            this.reset();
            await updateChannel(this.props.channel, this.name, this.url, this.directory, this.matchRegex);
            await this.getChannels();
            this.setShow(false);
        } catch (e) {
            this.setError(e.message);
        }
    }

    setShow(val) {
        this.setState({'show': val});
    }

    setChannel(channel) {
        this.name.current.value = channel.name || '';
        this.url.current.value = channel.url || '';
        this.directory.current.value = channel.directory || '';
        this.matchRegex.current.value = channel.match_regex || '';
    }

    showModalWithChannel(channel) {
        this.setState({show: true, channel: channel}, () => this.setChannel(channel));
    }

    async handleDelete() {
        await deleteChannel(this.state.channel);
        this.setShow(false);
    }

    reset() {
        this.setState({error: false, message: null})
    }

    setError(message) {
        this.setState({'error': true, 'message': message});
    }

    setMessage(message) {
        this.setState({'error': false, 'message': message});
    }

    channelNavLink(channel) {
        return (
            <div className="d-flex flex-row" key={channel['link']}>
                <div className="nav nav-item d-flex flex-row flex-fill align-items-center" key={channel.link}
                     style={{'padding': '0.5em'}}>
                    <NavLink className="nav-link flex-fill" to={'/videos/' + channel['link']}>
                        {channel.name}
                    </NavLink>
                    <span className="fa fa-ellipsis-v channel-edit fill"
                          onClick={() => this.showModalWithChannel(channel)}/>
                </div>
            </div>
        )
    }

    render() {
        return (
            <Nav variant="pills" className="flex-column">
                {this.props.channels.map(this.channelNavLink)}
                <ChannelModal
                    modalTitle="Edit Channel"
                    form_id="edit_channel"
                    handleSubmit={this.handleSubmit}
                    name={this.name}
                    url={this.url}
                    directory={this.directory}
                    matchRegex={this.matchRegex}
                    show={this.state.show}
                    setShow={this.setShow}
                    message={this.state.message}
                    error={this.state.error}
                    onDelete={this.handleDelete}
                />
            </Nav>
        )
    }
}

function VideoCard({video, channel}) {
    let upload_date = null;
    if (video.upload_date) {
        upload_date = new Date(video.upload_date * 1000);
        upload_date = `${upload_date.getFullYear()}-${upload_date.getMonth()}-${upload_date.getDay()}`;
    }
    let video_url = "/videos/" + channel.link + "/" + video.video_path_hash;
    let poster_url = video.poster_path ?
        `/media/${channel.directory}/${encodeURIComponent(video.poster_path)}` : null;
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
                        {upload_date}
                    </Card.Text>
                </Card.Body>
            </Card>
        </Link>
    )
}

class ChannelVideoPager extends Paginator {

    constructor(props) {
        super(props);
        this.searchInput = createRef();
        this.handleSearch = this.handleSearch.bind(this);
        this.clear = this.clear.bind(this);
    }

    handleSearch(e) {
        e.preventDefault();
        this.props.setSearch(this.searchInput.current.value);
    }

    clear() {
        this.searchInput.current.value = '';
        this.props.setSearch(null);
    }

    render() {
        return (
            <div className="d-flex flex-column">
                <div className="d-flex flex-row">
                    <Form inline style={{'marginBottom': '1em'}}
                          onSubmit={this.handleSearch}>
                        <FormControl
                            ref={this.searchInput}
                            type="text"
                            className="mr-sm-2"
                            placeholder="Search"
                        />
                        <ButtonGroup>
                            <Button type="submit" variant="info">
                                <span className="fas fa-search"/>
                            </Button>
                            <Button onClick={this.clear} variant="secondary">
                                <span className="fas fa-window-close"/>
                            </Button>
                        </ButtonGroup>
                    </Form>
                </div>
                <div className="d-flex flex-row">
                    <div className="card-deck">
                        {this.props.videos.map((v) => (
                            <VideoCard key={v['id']} video={v} channel={this.props.channel}/>))}
                    </div>
                </div>
                <div className="d-flex flex-row justify-content-center">
                    {this.getPagination()}
                </div>
            </div>
        )
    }
}

function ChannelModal(props) {
    const hide = () => props.setShow(false);

    return (
        <Modal show={props.show} onHide={hide}>
            <Modal.Header closeButton>
                <Modal.Title>{props.modalTitle}</Modal.Title>
            </Modal.Header>
            <Modal.Body>
                <Form id={props.form_id} onSubmit={props.handleSubmit}>
                    <Form.Group controlId="name">
                        <Form.Label column="">Name</Form.Label>
                        <Form.Control name="name" type="text" placeholder="Short Name" required ref={props.name}/>
                    </Form.Group>

                    <Form.Group controlId="url">
                        <Form.Label column="">URL</Form.Label>
                        <Form.Control type="url" placeholder="https://example.com/some-channel" ref={props.url}/>
                    </Form.Group>

                    <Form.Group controlId="directory">
                        <Form.Label column="">Directory</Form.Label>
                        <Form.Control name="directory" type="directory" placeholder="prepping/something" required
                                      ref={props.directory}/>
                        <Form.Text className="text-muted">
                            This will be appended to the root video directory in the config.
                        </Form.Text>
                    </Form.Group>

                    <Form.Group controlId="match_regex">
                        <Form.Label column="">Title Match Regex</Form.Label>
                        <Form.Control name="match_regex" type="text" placeholder=".*(prepper|prepping).*"
                                      ref={props.matchRegex}/>
                        <Form.Text className="text-muted">
                            The title of the video will be compared to this Regular Expression.
                            <b>If you don't input this, all videos will be downloaded.</b>
                        </Form.Text>
                    </Form.Group>
                </Form>
            </Modal.Body>
            <Modal.Footer>
                <div className="d-flex flex-row flex-fill">
                    <div className="d-flex flex-column align-content-start">
                        {props.onDelete &&
                        <Button variant="danger" onClick={props.onDelete}>
                            Delete
                        </Button>
                        }
                    </div>
                    <div className="d-flex flex-column flex-fill">
                        <Alert variant={(props.error ? 'danger' : 'success')} hidden={(!props.message)}>
                            {props.message}
                        </Alert>
                    </div>
                    <div className="d-flex flex-column align-content-end">
                        <ButtonGroup>
                            <Button variant="secondary" onClick={hide}>
                                Close
                            </Button>
                            <Button type="submit" variant={props.submitBtnVariant || 'primary'} form={props.form_id}>
                                Save
                            </Button>
                        </ButtonGroup>
                    </div>
                </div>
            </Modal.Footer>
        </Modal>
    )
}

function AddChannel() {
    const name = useRef();
    const url = useRef();
    const directory = useRef();
    const matchRegex = useRef();

    const [show, setShow] = useState(false);
    const [message, setMessage] = useState();
    const [error, setError] = useState(false);

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
            <Button className="btn-success" onClick={() => setShow(true)}>
                <span className="fas fa-plus"/>
            </Button>
            <ChannelModal
                modalTitle="Add New Channel"
                form_id="add_channel"
                handleSubmit={handleSubmit}
                name={name}
                url={url}
                directory={directory}
                matchRegex={matchRegex}
                show={show}
                setShow={setShow}
                message={message}
                error={error}
            />
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

class VideoBreadcrumb extends React.Component {

    render() {
        return (
            <Breadcrumb>
                {/* Always include the /videos breadcrumb */}
                <li className="breadcrumb-item">
                    <Link to='/videos'>Videos</Link>
                </li>
                {/* Show the channel only when its set */}
                {
                    this.props.channel &&
                    <li className="breadcrumb-item">
                        <Link to={'/videos/' + this.props.channel['link']}>
                            {this.props.channel['name']}
                        </Link>
                    </li>}
                {/* Show the video when the video is set */}
                {
                    this.props.video &&
                    <li className="breadcrumb-item">
                        <Link
                            to={'/videos/' +
                            this.props.channel['link'] + '/' +
                            this.props.video['video_path_hash']}>
                            {this.props.video['title'] || this.props.video['video_path']}
                        </Link>
                    </li>}
                {
                    !this.props.video && this.props.search_str &&
                    <li className="breadcrumb-item">
                        Search: {this.props.search_str}
                    </li>
                }
            </Breadcrumb>
        )
    }
}

class VideoWrapper extends React.Component {

    getVideo() {
        if (this.props.channel && this.props.video) {
            return <Video channel={this.props.channel} video={this.props.video}/>
        }
    }

    render() {
        return (
            this.getVideo() || <></>
        )
    }
}

class Videos extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channel: null,
            video: null,
            channels: [],
            videos: [],
            limit: 20,
            offset: 0,
            total: null,
            search_str: null,
        };
        this.setOffset = this.setOffset.bind(this);
        this.handleSearch = this.handleSearch.bind(this);
        this.setSearch = this.setSearch.bind(this);
    }

    async resetChannels() {
        let channels = await getChannels();
        this.setChannels(channels);
    }

    setChannels(channels,) {
        this.setState({channels});
    }

    setVideos(videos, videos_total) {
        this.setState({videos, videos_total});
    }

    async componentDidMount() {
        await this.resetChannels();
        await this.setChannel();
        await this.setVideo();
    }

    async setChannel() {
        let channel_link = this.props.match.params.channel_link;
        let channel = null;
        if (channel_link) {
            channel = await getChannel(channel_link);
        }
        this.setState({channel: channel, offset: 0, total: null, videos: [], video: null, search_str: null},
            this.setChannelVideos);
    }

    async setChannelVideos() {
        if (this.state.channel) {
            let channel_link = this.state.channel.link;
            let [videos, total] = await getChannelVideos(channel_link, this.state.offset, this.state.limit);
            this.setState({videos, total});
        }
    }

    async setVideo() {
        let video_hash = this.props.match.params.video_hash;
        let video = null;
        if (video_hash) {
            video = await getVideo(video_hash);
        }
        this.setState({video});
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        if (this.props.match.params.video_hash !== prevProps.match.params.video_hash) {
            await this.setVideo();
        }

        if (this.props.match.params.channel_link !== prevProps.match.params.channel_link) {
            await this.setChannel();
        }

        if (this.state.offset !== prevState.offset) {
            if (this.state.search_str) {
                await this.handleSearch(this.state.search_str);
            } else {
                await this.setChannelVideos();
            }
        }

        if (this.state.search_str !== prevState.search_str) {
            if (this.state.search_str) {
                await this.handleSearch(this.state.search_str);
            } else {
                this.setState({offset: 0}); // send the client back to the first page when clearing search
                await this.setChannelVideos();
                await this.resetChannels();
            }
        }
    }

    async handleSearch(search_str) {
        // Submit the search string to the API.  Overwrite the pager with the videos provided.
        // Overwrite the channels provided as well.
        let form_data = {search_str, offset: this.state.offset};
        let response = await fetch(`${VIDEOS_API}/search`, {
            method: 'POST',
            body: JSON.stringify(form_data),
        });
        let data = await response.json();

        let videos = [];
        let total = null;
        let channels = [];
        if (data['videos']) {
            videos = data['videos'];
            total = data['totals']['videos'];
        }
        if (data['channels']) {
            channels = data['channels'];
        }
        this.setState({videos, total, channels});
    }

    setSearch(search_str) {
        this.setState({search_str});
    }

    setOffset(offset) {
        this.setState({offset});
    }

    getBody() {
        if (this.state.video) {
            return (
                <VideoWrapper
                    channel={this.state.channel}
                    video={this.state.video}
                />
            )
        } else if (this.state.channel) {
            return (
                <ChannelVideoPager
                    setSearch={this.setSearch}
                    channel={this.state.channel}
                    videos={this.state.videos}
                    total={this.state.total}
                    limit={this.state.limit}
                    setOffset={this.setOffset}
                    offset={this.state.offset}
                />
            )
        }
    }

    render() {
        return (
            <div className="d-flex flex-row">
                <div className="d-flex flex-column w-25">
                    <div className="d-flex flex-row" style={{'margin': '1em'}}>
                        <h4 className="flex-fill">Channels</h4>
                        <ButtonGroup>
                            <ManageContent/>
                            <AddChannel/>
                        </ButtonGroup>
                    </div>
                    <div className="d-flex flex-column">
                        <ChannelsNav
                            setChannels={this.setChannels}
                            resetChannels={this.resetChannels}
                            channels={this.state.channels}
                            channel={this.state.channel}
                        />
                    </div>
                </div>
                <div className="d-flex flex-column w-75">
                    <Container fluid={true} style={{'padding': '1em'}}>
                        <VideoBreadcrumb
                            channel={this.state.channel}
                            video={this.state.video}
                            search_str={this.state.search_str}
                        />
                        {this.getBody()}
                    </Container>
                </div>
            </div>
        )
    }
}

class VideosRoute extends React.Component {

    render() {
        return (
            <Route path='/videos/:channel_link?/:video_hash?' exact component={Videos}/>
        )
    }
}

export default VideosRoute;