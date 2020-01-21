import React, {useRef, useState} from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import {Link, Route} from "react-router-dom";
import {Button, ButtonGroup, Form, FormControl, InputGroup, ProgressBar} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";
import Card from "react-bootstrap/Card";
import '../static/external/fontawesome-free/css/all.min.css';
import Alert from "react-bootstrap/Alert";
import Breadcrumb from "react-bootstrap/Breadcrumb";
import Paginator, {VIDEOS_API} from "./Common"
import Container from "react-bootstrap/Container";
import Video from "./VideoPlayer";
import {Typeahead} from 'react-bootstrap-typeahead';
import 'react-bootstrap-typeahead/css/Typeahead.css';

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


async function getRecentVideos(offset) {
    let response = await fetch(`${VIDEOS_API}/recent?offset=${offset}`);
    if (response.status === 200) {
        let data = await response.json();
        return [data['videos'], data['total']];
    } else {
        throw Error('Unable to fetch recent videos');
    }
}

async function getSearchVideos(search_str, offset) {
    let form_data = {search_str: search_str, offset: offset};
    let response = await fetch(`${VIDEOS_API}/search`, {
        method: 'POST',
        body: JSON.stringify(form_data),
    });
    let data = await response.json();

    let videos = [];
    let total = null;
    if (data['videos']) {
        videos = data['videos'];
        total = data['totals']['videos'];
    }
    return [videos, total];
}

class EditChannel extends React.Component {

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
            this.setShow(false);
        } catch (e) {
            this.setError(e.message);
        }
    }

    componentDidUpdate(prevProps, prevState, snapshot) {
        this.setChannel();
    }

    setShow(show) {
        this.setState({show});
    }

    setChannel() {
        let channel = this.props.channel;
        if (this.state.show && channel) {
            this.name.current.value = channel.name || '';
            this.url.current.value = channel.url || '';
            this.directory.current.value = channel.directory || '';
            this.matchRegex.current.value = channel.match_regex || '';
        }
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

    render() {
        return (
            <>
                {/* TODO This span should be reworked later so its easier to find */}
                <span className="fa fa-ellipsis-v channel-edit fill"
                      onClick={() => this.setShow(true)}/>
                <ChannelModal
                    modalTitle="Edit Channel"
                    form_id="edit_channel"
                    handleSubmit={this.handleSubmit}
                    show={this.state.show}
                    setShow={this.setShow}
                    message={this.state.message}
                    error={this.state.error}
                    onDelete={this.handleDelete}

                    name={this.name}
                    url={this.url}
                    directory={this.directory}
                    matchRegex={this.matchRegex}
                />
            </>
        )
    }
}

function VideoCard({video, channel}) {
    // Videos come with their own channel, use it; fallback to the global channel
    channel = video['channel'] || channel;

    let upload_date = null;
    if (video.upload_date) {
        upload_date = new Date(video['upload_date'] * 1000);
        upload_date = `${upload_date.getFullYear()}-${upload_date.getMonth() + 1}-${upload_date.getDate()}`;
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

    setOffset(offset) {
        // used in parent Paginator
        this.props.setOffset(offset);
    }

    render() {
        return (
            <div className="d-flex flex-column">
                {this.props.title && <h4>{this.props.title}</h4>}
                <div className="d-flex flex-row">
                    <div className="card-deck justify-content-center">
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

function VideoWrapper(props) {

    return (
        (props.channel && props.video) ? <Video channel={props.channel} video={props.video} autoplay={false}/> : <></>
    )
}

class RecentVideos extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            offset: 0,
            videos: [],
            total: null,
        };
        this.fetchVideos = this.fetchVideos.bind(this);
    }

    async fetchVideos() {
        let [videos, total] = await getRecentVideos(this.state.offset);
        this.setState({videos, total});
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        if (prevState.offset !== this.state.offset) {
            await this.fetchVideos();
        }
    }

    async componentDidMount() {
        await this.fetchVideos();
    }

    render() {
        if (this.state.total > 0) {
            return (
                <>
                    <ChannelVideoPager
                        title="Recently Published Videos"
                        videos={this.state.videos}
                        total={this.state.total}
                        setOffset={(o) => this.setState({offset: o})}
                        offset={this.state.offset}
                    />
                </>
            )
        } else {
            return (
                <p>
                    No videos were retrieved. Have you refreshed your content?
                    Try adding a channel and downloading the videos
                </p>
            )
        }
    }
}

class ChannelVideos extends RecentVideos {

    constructor(props) {
        super(props);
        this.fetchVideos = this.fetchVideos.bind(this);
    }

    async fetchVideos() {
        let [videos, total] = await getChannelVideos(this.props.channel['link'], this.state.offset, 20);
        this.setState({videos, total});
    }

    render() {
        if (this.state.total > 0) {
            return (
                <ChannelVideoPager
                    channel={this.props.channel}
                    videos={this.state.videos}
                    total={this.state.total}
                    setOffset={(o) => this.setState({offset: o})}
                    offset={this.state.offset}
                />
            )
        } else {
            return <></>
        }
    }

}

class SearchVideos extends RecentVideos {

    constructor(props) {
        super(props);
        this.fetchVideos = this.fetchVideos.bind(this);
    }

    async fetchVideos() {
        let [videos, total] = await getSearchVideos(this.props.search_str, this.state.offset);
        this.setState({videos, total});
    }

    render() {
        if (this.state.total > 0) {
            return (
                <ChannelVideoPager
                    channel={this.props.channel}
                    videos={this.state.videos}
                    total={this.state.total}
                    setOffset={(o) => this.setState({offset: o})}
                    offset={this.state.offset}
                />
            )
        } else {
            return <></>
        }
    }

}

class Videos extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channel: null,
            video: null,
            channels: [],
            search_str: null,
            show: false,
        };

        this.channelSelect = this.channelSelect.bind(this);
        this.clearSearch = this.clearSearch.bind(this);
        this.handleSearchEvent = this.handleSearchEvent.bind(this);
        this.setShow = this.setShow.bind(this);

        this.channelTypeahead = React.createRef();
        this.searchInput = React.createRef();
    }

    async resetChannels() {
        let channels = await getChannels();
        this.setState({channels});
    }

    async componentDidMount() {
        await this.setChannel();
        await this.setVideo();
        await this.resetChannels();
    }

    async setChannel() {
        let channel_link = this.props.match.params.channel_link;
        let channel = null;
        if (channel_link) {
            channel = await getChannel(channel_link);
        }
        let currentSelected = this.channelTypeahead.current.state.selected[0] || null;
        if ((currentSelected && channel && currentSelected['id'] !== channel['id']) || (!channel)) {
            // Channel was changed, or is no longer selected
            this.channelTypeahead.current.clear();
        }
        this.setState({channel: channel, offset: 0, total: null, videos: [], video: null, search_str: null},
            this.fetchVideos);
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
        let params = this.props.match.params;

        let channelChange = params.channel_link !== prevProps.match.params.channel_link;
        if (channelChange) {
            await this.setChannel();
        }

        let videoChange = params.video_hash !== prevProps.match.params.video_hash;
        if (videoChange) {
            await this.setVideo();
        }
    }

    clearSearch() {
        this.searchInput.current.value = null;
        this.setState({search_str: null, offset: 0});
    }

    async handleSearchEvent(event) {
        event.preventDefault();
        let search_str = this.searchInput.current.value;
        this.setState({search_str, video: null, channel: null, offset: 0});
    }

    getBody() {
        if (this.state.search_str) {
            return (<SearchVideos search_str={this.state.search_str}/>)
        } else if (this.state.video) {
            return (
                <VideoWrapper
                    channel={this.state.channel}
                    video={this.state.video}
                />
            )
        } else if (this.state.channel !== null) {
            return (<ChannelVideos channel={this.state.channel}/>)
        } else {
            return (<RecentVideos/>)
        }
    }

    setShow(show) {
        this.setState({show});
    }

    channelSelect(selection) {
        let channel = selection[0];
        this.props.history.push(`/videos/${channel['link']}`);
    }

    render() {
        return (
            <>
                <div className="d-flex flex-row">
                    <div className="d-flex flex-column w-100">
                        <VideoBreadcrumb
                            channel={this.state.channel}
                            video={this.state.video}
                            search_str={this.state.search_str}
                        />
                    </div>
                </div>

                <div className="d-flex flex-row flex-wrap">
                    <div className="d-flex flex-row p-1">
                        <ButtonGroup>
                            <ManageContent/>
                            <AddChannel/>
                        </ButtonGroup>
                    </div>
                    <div className="d-flex flex-row flex-grow-1 p-1">
                        <Typeahead
                            id="channel_select"
                            className="flex-fill"
                            ref={this.channelTypeahead}
                            labelKey="name"
                            multiple={false}
                            options={this.state.channels}
                            placeholder="Select a Channel..."
                            onChange={this.channelSelect}
                        />
                        {
                            this.state.channel &&
                            <EditChannel channel={this.state.channel}/>
                        }
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
                    </div>
                    <div className="d-flex flex-column flex-grow-1 p-1">
                        <Form inline onSubmit={this.handleSearchEvent}>
                            <InputGroup className="flex-fill">
                                <FormControl
                                    ref={this.searchInput}
                                    type="text"
                                    placeholder="Search Videos"
                                />
                                <InputGroup.Append>
                                    <Button type="submit" variant="info">
                                        <span className="fas fa-search"/>
                                    </Button>
                                    <Button onClick={this.clearSearch} variant="secondary">
                                        <span className="fas fa-window-close"/>
                                    </Button>
                                </InputGroup.Append>
                            </InputGroup>
                        </Form>
                    </div>
                </div>
                <div className="d-flex flex-row">
                    <div className="d-flex flex-column w-100">
                        <Container fluid={true} style={{'padding': '0.5em'}}>
                            {this.getBody()}
                        </Container>
                    </div>
                </div>
            </>
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