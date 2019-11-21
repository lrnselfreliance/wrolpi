import React, {useState} from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Nav from "react-bootstrap/Nav";
import {Link, NavLink, Route, Switch} from "react-router-dom";
import {Button, Container, Form} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";
import Card from "react-bootstrap/Card";

class ChannelsNav extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            'channels': [],
        };
    }

    async getChannels() {
        let url = 'http://127.0.0.1:8080/api/videos/channels';
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

function ChannelVideo(props) {
    return (
        <div>
            {console.log('video', props.match.params.channel_link, props.match.params.video_id)}
        </div>
    )
}

function VideoCard(props) {
    let video = props.video;
    return (
        <Link to={video}>
            <Card style={{'width': '18em', 'margin-bottom': '1em'}}>
                <Card.Img
                    variant="top"
                    src={"http://127.0.0.1:8080/api/videos/poster/" + video.video_path_hash}
                />
                <Card.Body>
                    <h5>{video.title}</h5>
                    <Card.Text>
                        {video.upload_date}
                    </Card.Text>
                </Card.Body>
            </Card>
        </Link>
    )
}

async function getChannel(link) {
    let response = await fetch('http://127.0.0.1:8080/api/videos/channel/' + link);
    let data = await response.json();
    return data['channel'];
}

async function getVideos(link) {
    let response = await fetch(`http://127.0.0.1:8080/api/videos/channel/${link}/videos`);
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
                {this.state['videos'].map((v) => (<VideoCard key={v['id']} video={v}/>))}
            </div>
        )
    }
}

function AddChannelForm(props) {
    return (
        <Form id="add_channel" ref={props.reference} onSubmit={props.onSubmit}>
            <Form.Group controlId="name">
                <Form.Label column="">Name</Form.Label>
                <Form.Control name="name" type="text" placeholder="Short Name" required/>
            </Form.Group>

            <Form.Group controlId="url">
                <Form.Label column="">URL</Form.Label>
                <Form.Control type="url" placeholder="https://example.com/some-channel"/>
            </Form.Group>

            <Form.Group controlId="directory">
                <Form.Label column="">Directory</Form.Label>
                <Form.Control name="directory" type="directory" placeholder="prepping/something" required/>
                <Form.Text className="text-muted">
                    This will be appended to the root video directory in the config, unless its an absolute path.
                </Form.Text>
            </Form.Group>

            <Form.Group controlId="match_regex">
                <Form.Label column="">Title Match Regex</Form.Label>
                <Form.Control name="match_regex" type="text" placeholder=".*(prepper|prepping).*"/>
                <Form.Text className="text-muted">
                    The title of the video will be compared to this Regular Expression. If you don't input this,
                    all videos will be downloaded.
                </Form.Text>
            </Form.Group>
        </Form>
    )
}

function AddChannel() {
    const form = React.useRef();

    const [show, setShow] = useState(false);
    const handleClose = () => setShow(false);
    const handleShow = () => setShow(true);

    function handleSubmit(event) {
        event.preventDefault();
    }

    return (
        <>
            <Button className="btn-success" onClick={handleShow}>+</Button>

            <Modal show={show} onHide={handleClose}>
                <Modal.Header closeButton>
                    <Modal.Title>Add New Channel</Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    <AddChannelForm reference={form} onSubmit={handleSubmit}/>
                </Modal.Body>
                <Modal.Footer>
                    <Button variant="secondary" onClick={handleClose}>
                        Close
                    </Button>
                    <Button type="submit" variant="primary" form="add_channel">
                        Add
                    </Button>
                </Modal.Footer>
            </Modal>
        </>
    )
}

function ManageContent() {
    const [show, setShow] = useState(false);
    const handleClose = () => setShow(false);
    const handleShow = () => setShow(true);

    async function refreshContent() {
        let url = 'http://127.0.0.1:8080/api/videos/settings/refresh';
        let response = await fetch(url, {'method': 'POST'});
    }

    return (
        <>
            <Button
                id="manage_content"
                className="btn-secondary"
                onClick={handleShow}
                style={{'margin-bottom': '0.5em'}}
            >
                Manage Content
            </Button>

            <Modal show={show} onHide={handleClose}>
                <Modal.Header>
                    <Modal.Title>Manage Channel Content</Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    <Row>
                        <Col>
                            <Button onClick={refreshContent}>Refresh Content</Button>
                        </Col>
                    </Row>
                </Modal.Body>
                <Modal.Footer>
                    <Button variant="secondary" onClick={handleClose}>
                        Close
                    </Button>
                </Modal.Footer>
            </Modal>
        </>
    )
}

function Videos() {
    return (
        <Row style={{'margin-top': '1.5em'}}>
            <Col className="col-3">
                <Row style={{'margin-bottom': '1.5em'}}>
                    <Col className="col-9">
                        <h4>
                            Channels
                        </h4>
                    </Col>
                    <Col className="col-3">
                        <div className="ml-auto">
                            <AddChannel/>
                        </div>
                    </Col>
                </Row>
                <Row>
                    <Col>
                        <ManageContent/>
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
                    <Switch>
                        <Route path="/videos/:channel_link/:video_id" component={ChannelVideo}/>
                        <Route path="/videos/:channel_link" component={ChannelVideoPager}/>
                    </Switch>
                </Container>
            </Col>
        </Row>
    )
}

export default Videos;