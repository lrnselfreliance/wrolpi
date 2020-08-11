import React from 'react';
import {Button, Checkbox, Container, Divider, Form, Header, Loader, Segment, Statistic, Tab} from "semantic-ui-react";
import {getConfig, getStatistics, saveConfig} from "../api";
import {humanFileSize, secondsToString} from "./Common";

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

class Statistics extends React.Component {

    constructor(props) {
        super(props);
        this.state = {};
        this.videoNames = [
            {key: 'videos', label: 'Downloaded Videos'},
            {key: 'favorites', label: 'Favorite Videos'},
            {key: 'sum_size', label: 'Total Size'},
            {key: 'max_size', label: 'Largest Video'},
            {key: 'week', label: 'Downloads Past Week'},
            {key: 'month', label: 'Downloads Past Month'},
            {key: 'year', label: 'Downloads Past Year'},
            {key: 'sum_duration', label: 'Total Duration'},
        ];
        this.channelNames = [
            {key: 'channels', label: 'Channels'},
        ];
        this.historicalNames = [
            {key: 'average_count', label: 'Average Downloads'},
            {key: 'average_size', label: 'Average Video Size'},
        ];
    }

    async componentDidMount() {
        await this.fetchStatistics();
    }

    async fetchStatistics() {
        let data = await getStatistics();
        data.statistics.videos.sum_duration = secondsToString(data.statistics.videos.sum_duration);
        data.statistics.videos.sum_size = humanFileSize(data.statistics.videos.sum_size, true);
        data.statistics.videos.max_size = humanFileSize(data.statistics.videos.max_size, true);
        data.statistics.historical.average_size = humanFileSize(data.statistics.historical.average_size, true);
        this.setState(data);
    }

    render() {
        if (this.state.statistics) {
            let videoStatistics = this.videoNames.map(
                ({key, label}) =>
                    <Statistic key={key} style={{margin: '2em'}}>
                        <Statistic.Value>{this.state.statistics.videos[key]}</Statistic.Value>
                        <Statistic.Label>{label}</Statistic.Label>
                    </Statistic>
            );
            let channelStatistics = this.channelNames.map(
                ({key, label}) =>
                    <Statistic key={key} style={{margin: '2em'}}>
                        <Statistic.Value>{this.state.statistics.channels[key]}</Statistic.Value>
                        <Statistic.Label>{label}</Statistic.Label>
                    </Statistic>
            );
            let historicalStatistics = this.historicalNames.map(
                ({key, label}) =>
                    <Statistic key={key} style={{margin: '2em'}}>
                        <Statistic.Value>{this.state.statistics.historical[key]}</Statistic.Value>
                        <Statistic.Label>{label}</Statistic.Label>
                    </Statistic>
            );
            return (
                <>
                    <Segment secondary>
                        <Header textAlign='center' as='h1'>Videos</Header>
                        <Statistic.Group>
                            {videoStatistics}
                        </Statistic.Group>
                    </Segment>
                    <Segment secondary>
                        <Header textAlign='center' as='h1'>Historical Video</Header>
                        <Statistic.Group>
                            {historicalStatistics}
                        </Statistic.Group>
                    </Segment>
                    <Segment secondary style={{marginTop: '2em'}}>
                        <Header textAlign='center' as='h1'>Channels</Header>
                        <Statistic.Group>
                            {channelStatistics}
                        </Statistic.Group>
                    </Segment>
                </>
            )
        } else {
            return <Loader active inline='centered'/>
        }
    }
}

class Admin extends React.Component {

    render() {

        const panes = [
            {menuItem: 'Settings', render: () => <Tab.Pane><Settings/></Tab.Pane>},
            {menuItem: 'Statistics', render: () => <Tab.Pane><Statistics/></Tab.Pane>},
        ];

        return (
            <Container style={{marginTop: '2em'}}>
                <Tab panes={panes}/>
            </Container>
        )
    }

}

export default Admin;