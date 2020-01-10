import React from 'react';
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import {API_URI} from "./Common"

async function getConfig() {
    let url = `http://${API_URI}/api/settings`;
    console.log('url', url);
    let response = await fetch(url);
    let data = await response.json();
    return data['config'];
}

async function saveConfig(config) {
    let url = `http://${API_URI}/api/settings`;
    let response = await fetch(url, {method: 'PUT', body: JSON.stringify(config)});
}

class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.mediaDirectory = React.createRef();

        this.handleSubmit = this.handleSubmit.bind(this);
    }

    async componentDidMount() {
        let config = await getConfig();
        this.mediaDirectory.current.value = config.media_directory;
    }

    async handleSubmit(e) {
        e.preventDefault();
        let config = {
            media_directory: this.mediaDirectory.current.value,
        };
        await saveConfig(config);
    }

    render() {
        return (
            <>
                <h1>Settings</h1>
                <p className="lead">
                    The global settings for your server.
                </p>
                <p className="text-muted">
                    When saved, these will be written to your <i>local.yaml</i> file. Storing these settings in your
                    local
                    configuration file (rather than the database) allows your WROLPi to be rebuilt and save your
                    settings.
                </p>
                <Form id="settings" onSubmit={this.handleSubmit}>
                    <Form.Group controlId="media_directory">
                        <Form.Label>Media Directory</Form.Label>
                        <Form.Control type="text" placeholder="/some/absolute/path" ref={this.mediaDirectory}/>
                        <Form.Text className="text-muted">
                            <b>This directory must already exist</b>.
                            The directory in which your media will be stored. Typically, this will be some external
                            drive like <i>/media/8TB</i>.
                        </Form.Text>
                    </Form.Group>

                    <Button variant="primary" type="submit">
                        Save
                    </Button>
                </Form>
            </>
        )
    }
}

export default Settings;