import React from 'react';
import {Button, Checkbox, Container, Divider, Form, Header, Loader, Tab} from "semantic-ui-react";
import {getConfig, saveConfig} from "../api";
import TimezoneSelect from 'react-timezone-select';

class Settings extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            disabled: false,
            ready: false,
            validTimezone: true,
            timezone: '',
        }
        this.mediaDirectory = React.createRef();

        this.handleSubmit = this.handleSubmit.bind(this);
    }

    async componentDidMount() {
        let config = await getConfig();
        this.setState({
            ready: true,
            disabled: config.wrol_mode,
            timezone: config.timezone || '',
        });
        this.mediaDirectory.current.value = config.media_directory;
    }

    async handleSubmit(e) {
        e.preventDefault();
        let config = {
            media_directory: this.mediaDirectory.current.value,
            timezone: this.state.timezone.value,
        };
        this.setState({validTimezone: true});
        let response = await saveConfig(config);
        if (response.status !== 200) {
            let json = await response.json();
            if (json.api_error === 'Invalid timezone') {
                this.setState({validTimezone: false});
            }
        }
    }

    handleTimezoneChange = async (timezone) => {
        this.setState({timezone});
    }

    render() {
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        return (
            <Container>
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

                    <Divider/>

                    <Form.Field>
                        <label>Timezone</label>
                        <TimezoneSelect
                            value={this.state.timezone}
                            onChange={this.handleTimezoneChange}
                        />
                    </Form.Field>

                    <Button color="blue" type="submit" disabled={this.state.disabled}>
                        Save
                    </Button>

                </Form>
            </Container>
        )
    }
}

class WROLMode extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            WROLMode: false,
        }
    }

    async componentDidMount() {
        let config = await getConfig();
        this.setState({ready: true, WROLMode: config.wrol_mode});
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
        if (this.state.ready === false) {
            return <Loader active inline='centered'/>
        }

        return (
            <Container>

                <Header as="h1">WROL Mode</Header>
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

            </Container>
        )
    }
}

class Admin extends React.Component {

    render() {

        const panes = [
            {menuItem: 'Settings', render: () => <Tab.Pane><Settings/></Tab.Pane>},
            {menuItem: 'WROL Mode', render: () => <Tab.Pane><WROLMode/></Tab.Pane>},
        ];

        return (
            <Container style={{marginTop: '2em'}}>
                <Tab panes={panes}/>
            </Container>
        )
    }

}

export default Admin;
