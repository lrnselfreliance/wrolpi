import React from 'react';
import {API_URI} from "./Common"
import {Button, Container, Form, Header} from "semantic-ui-react";

async function getConfig() {
    let url = `http://${API_URI}/api/settings`;
    let response = await fetch(url);
    let data = await response.json();
    return data['config'];
}

async function saveConfig(config) {
    let url = `http://${API_URI}/api/settings`;
    await fetch(url, {method: 'PUT', body: JSON.stringify(config)});
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
            <Container style={{'marginTop': '2em'}}>
                <Header as="h1" dividing>
                    Settings
                </Header>
                <p>
                    The global settings for your server.
                </p>
                <p className="text-muted">
                    When saved, these will be written to your <i>local.yaml</i> file. Storing these settings in your
                    local configuration file (rather than the database) allows your WROLPi to be rebuilt and save your
                    settings.
                </p>
                <Form id="settings" onSubmit={this.handleSubmit}>
                    <Form.Field>
                        <label>Media Directory</label>
                        <input
                            type="text"
                            placeholder="/some/absolute/path"
                            ref={this.mediaDirectory}
                        />
                    </Form.Field>

                    <p>
                        <b>This directory must already exist</b>.
                        The directory in which your media will be stored. Typically, this will be some external
                        drive like <i>/media/8TB</i>.
                    </p>

                    <Button color="blue" type="submit">
                        Save
                    </Button>
                </Form>
            </Container>
        )
    }
}

export default Settings;