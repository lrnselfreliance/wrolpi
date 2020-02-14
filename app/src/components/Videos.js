import React, {useRef, useState} from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import {Link, Route} from "react-router-dom";
import {ButtonGroup, ProgressBar} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";
import '../static/external/fontawesome-free/css/all.min.css';
import Alert from "react-bootstrap/Alert";
import Paginator, {VIDEOS_API} from "./Common"
import Container from "react-bootstrap/Container";
import Video from "./VideoPlayer";
import 'react-bootstrap-typeahead/css/Typeahead.css';
import {
    getChannel,
    getChannels,
    getChannelVideos,
    getDirectories,
    getRecentVideos,
    getSearchVideos,
    getVideo
} from "../api";
import {Button, Card, Checkbox, Form, Grid, Header, Placeholder} from "semantic-ui-react";

function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "auto"
    });
}

function FieldPlaceholder() {
    return (
        <Form.Field>
            <Placeholder style={{'marginBottom': '0.5em'}}>
                <Placeholder.Line length="short"/>
            </Placeholder>
            <input disabled/>
        </Form.Field>
    )
}

class ChannelPage extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channel: null,
            name: null,
            directory: null,
            url: null,
            match_regex: null,
            generate_thumbnails: null,
            calculate_duration: null
        };

        this.handleInputChange = this.handleInputChange.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);

        this.generateThumbnails = React.createRef();
        this.calculateDuration = React.createRef();
    }

    async componentDidMount() {
        let channel_link = this.props.match.params.channel_link;
        let channel = await getChannel(channel_link);
        this.setState({
            channel: channel,
            name: channel.name,
            directory: channel.directory,
            url: channel.url,
            match_regex: channel.match_regex,
            generate_thumbnails: channel.generate_thumbnails,
            calculate_duration: channel.calculate_duration,
        });
    }

    async handleInputChange(event) {
        const target = event.target;
        const value = target.type === 'label' ? target.checked : target.value;
        const name = target.name;
        this.setState({[name]: value});
    }

    async handleCheckbox(checkbox) {
        let checked = checkbox.current.state.checked;
        let name = checkbox.current.props.name;
        this.setState({[name]: !checked});
    }

    async handleSubmit(e) {
        e.preventDefault();
        console.log({
            name: this.state.name,
            directory: this.state.directory,
            generate_thumbnails: this.state.generate_thumbnails,
            calculate_duration: this.state.calculate_duration,
        });
    }

    render() {
        if (this.state.channel) {
            return (
                <Container>
                    <Header as="h1">{this.props.header}</Header>
                    <Form id="editChannel" onSubmit={this.handleSubmit}>
                        <div className="two fields">
                            <Form.Field>
                                <label>Channel Name</label>
                                <input
                                    name="name"
                                    type="text"
                                    placeholder="Short Channel Name"
                                    value={this.state.name}
                                    onChange={this.handleInputChange}
                                />
                            </Form.Field>
                            <Form.Field>
                                <label>Directory</label>
                                <input
                                    name="directory"
                                    type="text"
                                    placeholder='videos/channel/directory'
                                    value={this.state.directory}
                                    onChange={this.handleInputChange}
                                />
                            </Form.Field>
                        </div>
                        <Form.Field>
                            <label>URL</label>
                            <input
                                name="url"
                                type="url"
                                placeholder='https://example.com/channel/videos'
                                value={this.state.url}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>

                        <Header as="h4" style={{'marginTop': '3em'}}>
                            The following settings are encouraged by default, modify them at your own risk.
                        </Header>
                        <Form.Field>
                            <label>Title Match Regex</label>
                            <input
                                name="match_regex"
                                type="text"
                                placeholder='.*([Nn]ame Matching).*'
                                value={this.state.title_regex}
                                onChange={this.handleInputChange}
                            />
                        </Form.Field>

                        <Checkbox
                            toggle
                            label="Generate thumbnails, if not found"
                            name="generate_thumbnails"
                            asdf="foo"
                            checked={this.state.generate_thumbnails}
                            ref={this.generateThumbnails}
                            onClick={() => this.handleCheckbox(this.generateThumbnails)}
                        />
                        <Checkbox
                            toggle
                            label="Calculate video duration"
                            name="calculate_duration"
                            checked={this.state.calculate_duration}
                            ref={this.calculateDuration}
                            onClick={() => this.handleCheckbox(this.calculateDuration)}
                        />

                        <br/>
                        <Button color="blue" type="submit">Save</Button>
                    </Form>
                </Container>
            )
        } else {
            // Channel not loaded yet
            return (
                <Container>
                    <Header as="h1">{this.props.header}</Header>
                    <Form>
                        <div className="two fields">
                            <FieldPlaceholder/>
                            <FieldPlaceholder/>
                        </div>
                        <FieldPlaceholder/>

                        <Header as="h4" style={{'marginTop': '3em'}}>
                            <Placeholder>
                                <Placeholder.Line length="very long"/>
                            </Placeholder>
                        </Header>
                        <FieldPlaceholder/>
                        <FieldPlaceholder/>
                    </Form>
                </Container>
            )
        }
    }
}

function EditChannel(props) {
    return (
        <ChannelPage header="Edit Channel" history={props.history} match={props.match}/>
    )
}


function VideoCard({video, channel}) {
    // Videos come with their own channel, use it; fallback to the global channel
    channel = video['channel'] || channel;

    let upload_date = null;
    if (video.upload_date) {
        upload_date = new Date(video['upload_date'] * 1000);
        upload_date = `${upload_date.getFullYear()}-${upload_date.getMonth() + 1}-${upload_date.getDate()}`;
    }
    let video_url = `/videos/channel/${channel.link}/video/${video.id}`;
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
                    <Header as="h4">{video.title || video.video_path}</Header>
                    <Card.Text>
                        <Header as="h5">{video.channel.name}</Header>
                        <p>{upload_date}</p>
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
                <Header as="h1">{this.props.title}</Header>
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

    let [directories, setDirectories] = React.useState([]);

    async function fetchDirectories(search_str) {
        let dirs = await getDirectories(search_str);
        setDirectories(dirs);
    }

    function getDirectoryInput() {
        if (props.disableDirectory !== true) {
            return (
                <>
                    <Form.Text className="text-muted">
                        This will be appended to the root video directory in the config.
                    </Form.Text>

                    <Form.Group controlId="mkdir">
                        <Form.Check label="Make directory, if it doesn't exist" ref={props.mkdir}/>
                    </Form.Group>
                </>
            )
        } else {
            return (
                <>
                    <Form.Control type="text" ref={props.directory} disabled={true}/>
                    <Form.Control type="hidden" ref={props.mkdir}/>
                </>
            )
        }
    }

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
                        {getDirectoryInput()}
                    </Form.Group>

                    <Form.Group controlId="match_regex">
                        <Form.Label column="">Title Match Regex</Form.Label>
                        <Form.Control name="match_regex" type="text" placeholder=".*(prepper|prepping).*"
                                      ref={props.matchRegex}/>
                        <Form.Text className="text-muted">
                            The title of the video will be compared to this Regular Expression.
                            <b> If you don't input this, all videos will be downloaded.</b>
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
    const mkdir = useRef();
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
            directory: directory.current.state.text,
            mkdir: mkdir.current.value,
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
                disableDirectory={false}

                name={name}
                url={url}
                directory={directory}
                mkdir={mkdir}
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

    function handleError(error) {
        console.log(`Websocket ${stream_url} error:`, error);
    }

    let ws = new WebSocket(stream_url);
    window.onbeforeunload = (e) => (ws.close);
    ws.onmessage = handleMessage;
    ws.onerror = handleError;

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

function VideoWrapper(props) {

    return (
        (props.channel && props.video) ? <Video channel={props.channel} video={props.video} autoplay={false}/> : <></>
    )
}

class NewestVideos extends React.Component {
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
            scrollToTop();
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
                        title="Newest Videos"
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
                    Try adding a channel and downloading the videos.
                </p>
            )
        }
    }
}

class ChannelVideos extends NewestVideos {

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
            return (
                <p>
                    No videos were retrieved. Have you downloaded videos for this channel?
                </p>
            )
        }
    }

}

class SearchVideos extends NewestVideos {

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

function ChannelCard(props) {
    let editTo = `/videos/channel/${props.channel.link}/edit`;
    let videosTo = `/videos/channel/${props.channel.link}/video`;

    return (
        <Card fluid={true}>
            <Card.Content>
                <Card.Header>
                    {props.channel.name}
                </Card.Header>
                <Card.Description>
                    Videos: {props.channel.video_count}
                </Card.Description>
            </Card.Content>
            <Card.Content extra>
                <div className="ui buttons two">
                    <Link className="ui button" to={videosTo}>View Videos</Link>
                    <Link className="ui button blue" to={editTo}>Edit</Link>
                </div>
            </Card.Content>
        </Card>
    )
}

function VideoPlaceholder() {
    return (
        <Placeholder>
            <Placeholder.Header image>
                <Placeholder.Line/>
                <Placeholder.Line/>
            </Placeholder.Header>
            <Placeholder.Paragraph>
                <Placeholder.Line length='medium'/>
                <Placeholder.Line length='short'/>
            </Placeholder.Paragraph>
        </Placeholder>
    )
}

function ChannelPlaceholder() {
    return (
        <Placeholder>
            <Placeholder.Header image>
                <Placeholder.Line/>
                <Placeholder.Line/>
            </Placeholder.Header>
            <Placeholder.Paragraph>
                <Placeholder.Line length='short'/>
            </Placeholder.Paragraph>
        </Placeholder>
    )
}

function ChannelsHeader() {
    return (<Header as="h1">Channels</Header>)
}

class Channels extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channels: null,
        };
    }

    async componentDidMount() {
        let channels = await getChannels();
        this.setState({channels});
    }

    render() {
        if (this.state.channels === null) {
            // Placeholders while fetching
            return (
                <>
                    <ChannelsHeader/>
                    <Grid columns={2} doubling>
                        {[1, 1, 1, 1, 1, 1].map(() => {
                            return (
                                <Grid.Column>
                                    <ChannelPlaceholder/>
                                </Grid.Column>
                            )
                        })}
                    </Grid>
                </>
            )
        } else if (this.state.channels === []) {
            return (
                <>
                    <ChannelsHeader/>
                    Not channels exist yet!
                    <Button primary>Create Channel</Button>
                </>
            )
        } else {
            return (
                <>
                    <ChannelsHeader/>
                    <Grid columns={2} doubling>
                        {this.state.channels.map((channel) => {
                            return (
                                <Grid.Column>
                                    <ChannelCard channel={channel}/>
                                </Grid.Column>
                            )
                        })}
                    </Grid>
                </>
            )
        }
    }
}

class Videos extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            channel: null,
            video: null,
            search_str: null,
            show: false,
        };

        this.channelSelect = this.channelSelect.bind(this);
        this.clearSearch = this.clearSearch.bind(this);
        this.handleSearchEvent = this.handleSearchEvent.bind(this);
        this.setShowModal = this.setShowModal.bind(this);

        this.searchInput = React.createRef();
    }

    async componentDidMount() {
        await this.fetchChannel();
        await this.fetchVideo();
    }

    async componentDidUpdate(prevProps, prevState, snapshot) {
        let params = this.props.match.params;

        let channelChange = params.channel_link !== prevProps.match.params.channel_link;
        if (channelChange) {
            await this.fetchChannel();
        }

        let videoChange = params.video_id !== prevProps.match.params.video_id;
        if (videoChange) {
            await this.fetchVideo();
        }
    }

    async fetchChannel() {
        // Get and display the channel specified in the Router match
        let channel_link = this.props.match.params.channel_link;
        let channel = null;
        if (channel_link) {
            channel = await getChannel(channel_link);
        }
        this.setState({channel: channel, offset: 0, total: null, videos: [], video: null, search_str: null},
            this.fetchVideos);
    }

    async fetchVideo() {
        // Get and display the Video specified in the Router match
        let video_id = this.props.match.params.video_id;
        let video = null;
        if (video_id) {
            video = await getVideo(video_id);
        }
        this.setState({video});
    }

    channelSelect(selection) {
        // Switch the channel link in the Router match
        let channel = selection[0];
        this.props.history.push(`/videos/${channel['link']}`);
    }

    async handleSearchEvent(event) {
        event.preventDefault();
        let search_str = this.searchInput.current.value;
        this.setState({search_str, video: null, channel: null, offset: 0});
    }

    clearSearch() {
        this.searchInput.current.value = null;
        this.setState({search_str: null, offset: 0});
    }

    setShowModal(show) {
        this.setState({show});
    }

    render() {
        return (
            <></>
        )
    }
}

class VideosRoute extends React.Component {

    render() {
        return (
            <Container fluid={true} style={{margin: '2em', padding: '0.5em'}}>
                <Route path='/videos' exact={true} component={Videos}/>
                <Route path='/videos/channels' exact component={Channels}/>
                <Route path='/videos/favorites' exact component={Videos}/>
                <Route path='/videos/channel/:channel_link/edit' exact component={EditChannel}/>
                <Route path='/videos/channel/:channel_link?/video/:video_id?' exact component={Videos}/>
            </Container>
        )
    }
}

export default VideosRoute;
