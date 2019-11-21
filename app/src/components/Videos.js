import React from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Nav from "react-bootstrap/Nav";
import {Link, NavLink, Route, Switch} from "react-router-dom";
import {Button, Form} from "react-bootstrap";
import Modal from "react-bootstrap/Modal";


const channels = [
    {'link': 'bigbuckbunny', 'name': 'Big Buck Bunny'},
];

function ChannelsNav() {
    function channelRoute(channel) {
        return (
            <Nav.Item key={channel.link}>
                <NavLink className="nav-link" to={'/videos/' + channel['link']}>
                    {channel.name}
                </NavLink>
            </Nav.Item>
        )
    }

    return (
        <Nav variant="pills" className="flex-column">
            {channels.map(channelRoute)}
        </Nav>
    )
}

function ChannelVideo(props) {
    return (
        <div>
            {console.log('video', props.match.params.channel_link, props.match.params.video_id)}
        </div>
    )
}


async function getChannel(link) {
    let response = await fetch('http://127.0.0.1:8080/api/videos/channel/' + link);
    let data = await response.json();
    return data;
}

async function getVideos(link) {
    let response = await fetch(`http://127.0.0.1:8080/api/videos/channel/${link}/videos`);
    let data = await response.json();
    return data;
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
        this.setState({'channel': await getVideos(link)})
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
            <div>
                {console.log('pager', this.state.link)}
                <Link to={this.state.link + '/bar'}>asdf</Link>
            </div>
        )
    }
}

function AddChannelForm(props) {
    return (
        <Form id="add_channel" ref={props.reference} onSubmit={props.onSubmit}>
            <Form.Group controlId="name">
                <Form.Label column="">Name</Form.Label>
                <Form.Control type="text" placeholder="Short Name" required/>
            </Form.Group>

            <Form.Group controlId="url">
                <Form.Label column="">URL</Form.Label>
                <Form.Control type="url" placeholder="https://example.com/some-channel"/>
            </Form.Group>

            <Form.Group controlId="directory">
                <Form.Label column="">Directory</Form.Label>
                <Form.Control type="directory" placeholder="prepping/something" required/>
                <Form.Text className="text-muted">
                    This will be appended to the root video directory in the config, unless its an absolute path.
                </Form.Text>
            </Form.Group>

            <Form.Group controlId="match_regex">
                <Form.Label column="">Title Match Regex</Form.Label>
                <Form.Control type="match_regex" placeholder=".*(prepper|prepping).*"/>
                <Form.Text className="text-muted">
                    The title of the video will be compared to this Regular Expression. If you don't input this,
                    all videos will be downloaded
                </Form.Text>
            </Form.Group>
        </Form>
    )
}

function AddChannel() {
    const [show, setShow] = React.useState(false);
    const form = React.useRef();

    const handleClose = () => setShow(false);
    const handleShow = () => setShow(true);

    function handleSubmit(event) {
        event.preventDefault();
        console.log(event);
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

function Channels() {
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
                <ChannelsNav/>
            </Col>
            <Col className="col-9">
                <Switch>
                    <Route path="/videos/:channel_link/:video_id" component={ChannelVideo}/>
                    <Route path="/videos/:channel_link" component={ChannelVideoPager}/>
                </Switch>
            </Col>
        </Row>
    )
}

function Videos() {
    return (
        <Channels/>
    )
}

export default Videos;