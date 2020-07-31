import React from 'react';
import {Button, Checkbox, Container, Divider, Form, Header} from "semantic-ui-react";
import {getConfig, saveConfig} from "../api";

class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            WROLMode: false,
            disabled: false,
        }
        this.mediaDirectory = React.createRef();

        this.handleSubmit = this.handleSubmit.bind(this);
    }

    async componentDidMount() {
        let config = await getConfig();
        this.mediaDirectory.current.value = config.media_directory;
        this.setState({WROLMode: config.wrol_mode, disabled: config.wrol_mode});
    }

    async handleSubmit(e) {
        e.preventDefault();
        let config = {
            media_directory: this.mediaDirectory.current.value,
        };
        await saveConfig(config);
    }

    toggleWROLMode = async () => {
        // Handle WROL Mode toggling by itself so that other settings are not modified.
        let config = {
            wrol_mode: !this.state.WROLMode,
        }
        await saveConfig(config);
        this.setState({disabled: !this.state.WROLMode, WROLMode: !this.state.WROLMode});
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
                <Divider/>
                <Form id="settings" onSubmit={this.handleSubmit}>

                    <Header as="h2">WROL Mode</Header>
                    <h4>
                        Enable read-only mode. No content can be deleted or modified. Enable this when the SHTF and you
                        want to prevent any potential loss of data.
                    </h4>
                    <p>
                        Note: User settings and favorites can still be modified.
                    </p>
                    <Checkbox toggle
                              checked={this.state.WROLMode}
                              onChange={this.toggleWROLMode}
                              label={this.state.WROLMode ? 'WROL Mode Enabled' : 'WROL Mode Disabled'}
                    />

                    <Divider/>
                    <Form.Field>
                        <label>Media Directory</label>
                        <input
                            disabled={this.state.disabled}
                            type="text"
                            placeholder="/some/absolute/path"
                            ref={this.mediaDirectory}
                        />
                    </Form.Field>

                    <p>
                        <b>This directory must already exist</b>.
                        The directory in which your media will be stored. Typically, this will be some external
                        drive like <i>/media/wrolpi</i>.
                    </p>

                    <Button color="blue" type="submit" disabled={this.state.disabled}>
                        Save
                    </Button>
                </Form>
            </Container>
        )
    }
}

export default Settings;