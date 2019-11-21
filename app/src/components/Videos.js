import React from 'react';
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Nav from "react-bootstrap/Nav";
import {Switch} from "react-router-dom";


const channels = [
    {'link': 'foo', 'name': 'Foo'},
    {'link': 'bar', 'name': 'Bar'},
];

function ChannelsNav() {
    function channelRoute(channel) {
        return (
            <Nav.Item>
                <Nav.Link to={'/videos/' + channel.link}>
                    {channel.name}
                </Nav.Link>
            </Nav.Item>
        )
    }

    return (
        <div>
            <h4>Channels</h4>
            <Nav variant="pills" className="flex-column">
                {channels.map(channelRoute)}
            </Nav>
        </div>
    )
}

function ChannelVideoPager() {
    function buildChannelVideoPager(channel) {
        return <div>{channel.name}</div>
    }

    return (
        <Switch>
            {channels.map(buildChannelVideoPager)}
        </Switch>
    )
}

function Channels() {
    return (
        <Row>
            <Col>
                <ChannelsNav/>
            </Col>
            <Col>
                <ChannelVideoPager/>
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